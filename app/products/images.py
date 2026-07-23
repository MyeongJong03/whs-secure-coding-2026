import io
import os
import re
import secrets
import stat
import warnings
from dataclasses import dataclass
from pathlib import Path

from flask import current_app
from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.datastructures import FileStorage

from app.products.policy import (
    ALLOWED_IMAGE_FORMATS,
    FORMAT_EXTENSIONS,
    FORMAT_MIMETYPES,
    IMAGE_EXTENSIONS,
)


SAFE_STORED_FILENAME = re.compile(r"^[0-9a-f]{32}\.(?:jpg|png|webp)$")
GENERIC_IMAGE_ERROR = "안전한 JPEG, PNG 또는 WebP 이미지를 선택하세요."


class ImageValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class StoredImage:
    filename: str
    content_type: str


@dataclass(frozen=True, slots=True)
class StoredImageData:
    content: bytes
    content_type: str
    extension: str


def _limits() -> tuple[int, int, int]:
    return (
        int(current_app.config["PRODUCT_MAX_FILE_BYTES"]),
        int(current_app.config["PRODUCT_MAX_DIMENSION"]),
        int(current_app.config["PRODUCT_MAX_PIXELS"]),
    )


def _upload_root() -> Path:
    return Path(current_app.config["PRODUCT_UPLOAD_DIR"])


def _root_open_flags() -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    return flags


def _file_open_flags(base_flags: int) -> int:
    flags = base_flags
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    return flags


def _close_descriptor(descriptor: int) -> None:
    try:
        os.close(descriptor)
    except OSError:
        pass


def _open_upload_root() -> int | None:
    root = _upload_root()
    try:
        before_open = os.lstat(root)
        if stat.S_ISLNK(before_open.st_mode) or not stat.S_ISDIR(before_open.st_mode):
            return None
        descriptor = os.open(root, _root_open_flags())
    except (OSError, RuntimeError, TypeError, ValueError):
        return None
    try:
        after_open = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(after_open.st_mode)
            or before_open.st_dev != after_open.st_dev
            or before_open.st_ino != after_open.st_ino
        ):
            _close_descriptor(descriptor)
            return None
        return descriptor
    except OSError:
        _close_descriptor(descriptor)
        return None


def _open_stored_file(root_descriptor: int, filename: str) -> int | None:
    try:
        before_open = os.stat(
            filename,
            dir_fd=root_descriptor,
            follow_symlinks=False,
        )
        if stat.S_ISLNK(before_open.st_mode) or not stat.S_ISREG(before_open.st_mode):
            return None
        descriptor = os.open(
            filename,
            _file_open_flags(os.O_RDONLY),
            dir_fd=root_descriptor,
        )
    except OSError:
        return None
    try:
        after_open = os.fstat(descriptor)
        if (
            not stat.S_ISREG(after_open.st_mode)
            or before_open.st_dev != after_open.st_dev
            or before_open.st_ino != after_open.st_ino
        ):
            _close_descriptor(descriptor)
            return None
        return descriptor
    except OSError:
        _close_descriptor(descriptor)
        return None


def ensure_upload_root() -> int:
    root = _upload_root()
    try:
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
    except (OSError, RuntimeError):
        raise ImageValidationError(GENERIC_IMAGE_ERROR) from None

    descriptor = _open_upload_root()
    if descriptor is None:
        raise ImageValidationError(GENERIC_IMAGE_ERROR)
    try:
        os.fchmod(descriptor, 0o700)
    except OSError:
        _close_descriptor(descriptor)
        raise ImageValidationError(GENERIC_IMAGE_ERROR) from None
    return descriptor


def _input_extension(filename: str | None) -> str:
    if not isinstance(filename, str) or not filename:
        raise ImageValidationError(GENERIC_IMAGE_ERROR)
    if "/" in filename or "\\" in filename or "\x00" in filename:
        raise ImageValidationError(GENERIC_IMAGE_ERROR)
    extension = Path(filename).suffix.lower()
    if extension not in IMAGE_EXTENSIONS:
        raise ImageValidationError(GENERIC_IMAGE_ERROR)
    return extension


def _safe_converted_mode(image: Image.Image, image_format: str) -> Image.Image:
    if image_format == "JPEG":
        return image.convert("RGB")
    has_alpha = image.mode in {"RGBA", "LA"} or (
        image.mode == "P" and "transparency" in image.info
    )
    return image.convert("RGBA" if has_alpha else "RGB")


def validate_and_reencode(file_storage: FileStorage) -> tuple[bytes, str, str]:
    max_bytes, max_dimension, max_pixels = _limits()
    extension = _input_extension(file_storage.filename)
    raw = file_storage.stream.read(max_bytes + 1)
    if not raw or len(raw) > max_bytes:
        raise ImageValidationError(GENERIC_IMAGE_ERROR)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as initial:
                image_format = (initial.format or "").upper()
                if image_format not in ALLOWED_IMAGE_FORMATS:
                    raise ImageValidationError(GENERIC_IMAGE_ERROR)
                if (
                    getattr(initial, "is_animated", False)
                    or getattr(initial, "n_frames", 1) > 1
                ):
                    raise ImageValidationError(GENERIC_IMAGE_ERROR)
                initial.verify()

            with Image.open(io.BytesIO(raw)) as decoded:
                image_format = (decoded.format or "").upper()
                width, height = decoded.size
                if (
                    width < 1
                    or height < 1
                    or width > max_dimension
                    or height > max_dimension
                    or width * height > max_pixels
                ):
                    raise ImageValidationError(GENERIC_IMAGE_ERROR)
                if (
                    getattr(decoded, "is_animated", False)
                    or getattr(decoded, "n_frames", 1) > 1
                ):
                    raise ImageValidationError(GENERIC_IMAGE_ERROR)
                expected_extensions = {
                    "JPEG": {".jpg", ".jpeg"},
                    "PNG": {".png"},
                    "WEBP": {".webp"},
                }[image_format]
                if extension not in expected_extensions:
                    raise ImageValidationError(GENERIC_IMAGE_ERROR)

                decoded.load()
                transposed = ImageOps.exif_transpose(decoded)
                normalized = _safe_converted_mode(transposed, image_format)
                normalized.info.clear()
                output = io.BytesIO()
                save_options: dict[str, object] = {}
                if image_format == "JPEG":
                    save_options = {
                        "quality": 85,
                        "optimize": True,
                        "progressive": True,
                    }
                elif image_format == "WEBP":
                    save_options = {"quality": 85, "method": 4}
                normalized.save(output, format=image_format, **save_options)
    except ImageValidationError:
        raise
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        ValueError,
    ) as error:
        raise ImageValidationError(GENERIC_IMAGE_ERROR) from error

    encoded = output.getvalue()
    if not encoded or len(encoded) > max_bytes:
        raise ImageValidationError(GENERIC_IMAGE_ERROR)
    return (
        encoded,
        FORMAT_EXTENSIONS[image_format],
        FORMAT_MIMETYPES[image_format],
    )


def store_product_image(file_storage: FileStorage) -> StoredImage:
    content, extension, content_type = validate_and_reencode(file_storage)
    root_descriptor = ensure_upload_root()
    flags = _file_open_flags(os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    try:
        for _attempt in range(16):
            filename = f"{secrets.token_hex(16)}{extension}"
            try:
                descriptor = os.open(
                    filename,
                    flags,
                    0o600,
                    dir_fd=root_descriptor,
                )
            except FileExistsError:
                continue
            except OSError:
                raise ImageValidationError(GENERIC_IMAGE_ERROR) from None
            try:
                os.fchmod(descriptor, 0o600)
                with os.fdopen(descriptor, "wb") as destination:
                    destination.write(content)
                    destination.flush()
                    os.fsync(destination.fileno())
                descriptor = -1
            except Exception:
                if descriptor >= 0:
                    _close_descriptor(descriptor)
                try:
                    os.unlink(filename, dir_fd=root_descriptor)
                except OSError:
                    pass
                raise ImageValidationError(GENERIC_IMAGE_ERROR) from None
            return StoredImage(filename=filename, content_type=content_type)
        raise ImageValidationError(GENERIC_IMAGE_ERROR)
    finally:
        _close_descriptor(root_descriptor)


def remove_product_image(filename: str | None) -> bool:
    if not isinstance(filename, str) or not SAFE_STORED_FILENAME.fullmatch(filename):
        return False
    root_descriptor = _open_upload_root()
    if root_descriptor is None:
        return False
    descriptor = _open_stored_file(root_descriptor, filename)
    if descriptor is None:
        _close_descriptor(root_descriptor)
        return False
    try:
        _close_descriptor(descriptor)
        os.unlink(filename, dir_fd=root_descriptor)
        return True
    except OSError:
        return False
    finally:
        _close_descriptor(root_descriptor)


def read_product_image(filename: str | None) -> StoredImageData | None:
    if not isinstance(filename, str) or not SAFE_STORED_FILENAME.fullmatch(filename):
        return None
    max_bytes, max_dimension, max_pixels = _limits()
    root_descriptor = _open_upload_root()
    if root_descriptor is None:
        return None

    descriptor = _open_stored_file(root_descriptor, filename)
    if descriptor is None:
        _close_descriptor(root_descriptor)
        return None
    try:
        try:
            details = os.fstat(descriptor)
            if (
                not stat.S_ISREG(details.st_mode)
                or details.st_size < 1
                or details.st_size > max_bytes
            ):
                return None
            chunks: list[bytes] = []
            remaining = max_bytes + 1
            while remaining:
                chunk = os.read(descriptor, min(64 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            content = b"".join(chunks)
            if not content or len(content) > max_bytes:
                return None
        finally:
            _close_descriptor(descriptor)
    except OSError:
        return None
    finally:
        _close_descriptor(root_descriptor)

    extension = f".{filename.rsplit('.', 1)[1]}"
    expected_format = {".jpg": "JPEG", ".png": "PNG", ".webp": "WEBP"}[extension]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as image:
                actual_format = (image.format or "").upper()
                width, height = image.size
                if (
                    actual_format not in ALLOWED_IMAGE_FORMATS
                    or actual_format != expected_format
                    or width < 1
                    or height < 1
                    or width > max_dimension
                    or height > max_dimension
                    or width * height > max_pixels
                    or getattr(image, "is_animated", False)
                    or getattr(image, "n_frames", 1) > 1
                ):
                    return None
                image.verify()
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        ValueError,
    ):
        return None
    return StoredImageData(
        content=content,
        content_type=FORMAT_MIMETYPES[expected_format],
        extension=extension,
    )
