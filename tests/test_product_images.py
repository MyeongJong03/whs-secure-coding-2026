import io
import os
import re
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image, PngImagePlugin
from werkzeug.datastructures import FileStorage

from app.products import images
from app.products.images import (
    ImageValidationError,
    read_product_image,
    remove_product_image,
    store_product_image,
    validate_and_reencode,
)


def upload(content: bytes, filename: str) -> FileStorage:
    return FileStorage(stream=io.BytesIO(content), filename=filename)


@pytest.mark.parametrize(
    ("image_format", "input_name", "extension", "mime", "expected_mode"),
    [
        ("JPEG", "photo.jpeg", ".jpg", "image/jpeg", "RGB"),
        ("PNG", "photo.PNG", ".png", "image/png", "RGB"),
        ("WEBP", "photo.webp", ".webp", "image/webp", "RGB"),
    ],
)
def test_valid_images_are_reencoded_and_normalized(
    app,
    image_bytes,
    image_format,
    input_name,
    extension,
    mime,
    expected_mode,
):
    with app.app_context():
        encoded, actual_extension, actual_mime = validate_and_reencode(
            upload(image_bytes(image_format), input_name)
        )

    assert actual_extension == extension
    assert actual_mime == mime
    with Image.open(io.BytesIO(encoded)) as result:
        assert result.format == image_format
        assert result.mode == expected_mode


def test_png_and_webp_alpha_is_preserved(app, image_bytes):
    for image_format, filename in (("PNG", "alpha.png"), ("WEBP", "alpha.webp")):
        content = image_bytes(image_format, mode="RGBA", color=(10, 20, 30, 128))
        with app.app_context():
            encoded, _extension, _mime = validate_and_reencode(
                upload(content, filename)
            )
        with Image.open(io.BytesIO(encoded)) as result:
            assert result.mode == "RGBA"


@pytest.mark.parametrize(
    ("content", "filename"),
    [
        (b"", "empty.png"),
        (b"not an image", "fake.png"),
        (b"<svg xmlns='http://www.w3.org/2000/svg'></svg>", "image.svg"),
        (b"BM" + b"\x00" * 64, "image.bmp"),
        (b"not an image", "no-extension"),
        (b"not an image", "archive.tar.png.exe"),
        (b"not an image", "../escape.png"),
        (b"not an image", r"..\escape.png"),
        (b"not an image", "bad\x00name.png"),
    ],
)
def test_invalid_or_unsafe_input_is_rejected(app, content, filename):
    with app.app_context(), pytest.raises(ImageValidationError):
        validate_and_reencode(upload(content, filename))


@pytest.mark.parametrize(
    ("actual_format", "filename"),
    [
        ("JPEG", "mismatch.png"),
        ("PNG", "mismatch.jpg"),
        ("WEBP", "mismatch.jpeg"),
    ],
)
def test_extension_must_match_decoded_format(app, image_bytes, actual_format, filename):
    with app.app_context(), pytest.raises(ImageValidationError):
        validate_and_reencode(upload(image_bytes(actual_format), filename))


def test_gif_is_rejected_even_when_static(app):
    output = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(output, format="GIF")
    with app.app_context(), pytest.raises(ImageValidationError):
        validate_and_reencode(upload(output.getvalue(), "image.gif"))


def test_truncated_image_is_rejected(app, image_bytes):
    content = image_bytes("PNG")
    with app.app_context(), pytest.raises(ImageValidationError):
        validate_and_reencode(upload(content[: len(content) // 2], "broken.png"))


def test_input_byte_limit_is_bounded(app):
    app.config["PRODUCT_MAX_FILE_BYTES"] = 32
    stream = io.BytesIO(b"x" * 100)
    storage = FileStorage(stream=stream, filename="large.png")
    with app.app_context(), pytest.raises(ImageValidationError):
        validate_and_reencode(storage)
    assert stream.tell() == 33


@pytest.mark.parametrize(
    ("size", "dimension", "pixels"),
    [
        ((11, 1), 10, 100),
        ((5, 5), 10, 24),
        ((0, 0), 10, 100),
    ],
)
def test_dimension_and_pixel_limits(app, image_bytes, size, dimension, pixels):
    app.config["PRODUCT_MAX_DIMENSION"] = dimension
    app.config["PRODUCT_MAX_PIXELS"] = pixels
    if size == (0, 0):
        content = b"\x89PNG\r\n\x1a\n"
    else:
        content = image_bytes("PNG", size=size)
    with app.app_context(), pytest.raises(ImageValidationError):
        validate_and_reencode(upload(content, "large.png"))


def test_animated_png_and_webp_are_rejected(app):
    for image_format, filename in (("PNG", "animated.png"), ("WEBP", "animated.webp")):
        output = io.BytesIO()
        frames = [Image.new("RGB", (4, 4), color) for color in ("red", "blue")]
        frames[0].save(
            output,
            format=image_format,
            save_all=True,
            append_images=frames[1:],
            duration=100,
            loop=0,
        )
        with app.app_context(), pytest.raises(ImageValidationError):
            validate_and_reencode(upload(output.getvalue(), filename))


def test_exif_orientation_is_applied_and_metadata_removed(app):
    source = Image.new("RGB", (4, 8), "red")
    exif = Image.Exif()
    exif[274] = 6
    output = io.BytesIO()
    source.save(
        output,
        format="JPEG",
        exif=exif,
        comment=b"private-comment",
        icc_profile=b"private-profile",
    )

    with app.app_context():
        encoded, _extension, _mime = validate_and_reencode(
            upload(output.getvalue(), "photo.jpg")
        )

    assert b"private-comment" not in encoded
    assert b"private-profile" not in encoded
    with Image.open(io.BytesIO(encoded)) as result:
        assert result.size == (8, 4)
        assert not result.getexif()
        assert "comment" not in result.info
        assert "icc_profile" not in result.info


def test_png_text_metadata_and_trailing_payload_are_removed(app):
    source = Image.new("RGB", (8, 8), "green")
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("secret", "private-value")
    output = io.BytesIO()
    source.save(output, format="PNG", pnginfo=metadata)
    marker = b"<script>alert(1)</script>PK\x03\x04"

    with app.app_context():
        encoded, _extension, _mime = validate_and_reencode(
            upload(output.getvalue() + marker, "photo.png")
        )

    assert b"private-value" not in encoded
    assert marker not in encoded
    with Image.open(io.BytesIO(encoded)) as result:
        assert "secret" not in result.info


def test_stored_name_permissions_and_upload_root_mode(app, image_bytes):
    with app.app_context():
        stored = store_product_image(
            upload(image_bytes("JPEG"), "user-controlled.jpeg")
        )
        root = Path(app.config["PRODUCT_UPLOAD_DIR"])
        target = root / stored.filename

    assert re.fullmatch(r"[0-9a-f]{32}\.jpg", stored.filename)
    assert "user-controlled" not in stored.filename
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_random_name_collision_never_overwrites_existing_file(
    app, image_bytes, monkeypatch
):
    values = iter(("1" * 32, "1" * 32, "2" * 32))
    monkeypatch.setattr(images.secrets, "token_hex", lambda _length: next(values))
    with app.app_context():
        first = store_product_image(upload(image_bytes("PNG"), "first.png"))
        first_path = Path(app.config["PRODUCT_UPLOAD_DIR"]) / first.filename
        first_content = first_path.read_bytes()
        second = store_product_image(upload(image_bytes("PNG"), "second.png"))

    assert first.filename == f"{'1' * 32}.png"
    assert second.filename == f"{'2' * 32}.png"
    assert first_path.read_bytes() == first_content


def test_store_uses_filename_relative_to_upload_root_descriptor(
    app, image_bytes, monkeypatch
):
    original_open = images.os.open
    open_calls = []

    def record_open(path, flags, mode=0o777, *, dir_fd=None):
        open_calls.append((path, flags, mode, dir_fd))
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(images.os, "open", record_open)
    with app.app_context():
        stored = store_product_image(upload(image_bytes("PNG"), "photo.png"))

    stored_calls = [call for call in open_calls if call[0] == stored.filename]
    assert len(stored_calls) == 1
    assert stored_calls[0][3] is not None
    assert not os.path.isabs(os.fspath(stored_calls[0][0]))


def test_upload_root_symlink_rejects_store_without_changing_target(
    app, image_bytes, tmp_path
):
    root = Path(app.config["PRODUCT_UPLOAD_DIR"])
    target_root = tmp_path / "external-upload-root"
    target_root.mkdir(mode=0o751)
    target_root.chmod(0o751)
    existing_name = f"{'a' * 32}.png"
    existing = target_root / existing_name
    existing_content = image_bytes("PNG")
    existing.write_bytes(existing_content)
    entries_before = {path.name for path in target_root.iterdir()}
    mode_before = stat.S_IMODE(target_root.stat().st_mode)
    root.parent.mkdir(parents=True)
    root.symlink_to(target_root, target_is_directory=True)

    with app.app_context(), pytest.raises(ImageValidationError):
        store_product_image(upload(image_bytes("JPEG"), "new.jpg"))

    assert root.is_symlink()
    assert {path.name for path in target_root.iterdir()} == entries_before
    assert stat.S_IMODE(target_root.stat().st_mode) == mode_before
    assert existing.read_bytes() == existing_content


def test_upload_root_symlink_rejects_read_and_remove_without_touching_target(
    app, image_bytes, tmp_path
):
    root = Path(app.config["PRODUCT_UPLOAD_DIR"])
    target_root = tmp_path / "external-read-root"
    target_root.mkdir(mode=0o751)
    target_root.chmod(0o751)
    filename = f"{'b' * 32}.png"
    existing = target_root / filename
    existing_content = image_bytes("PNG")
    existing.write_bytes(existing_content)
    mode_before = stat.S_IMODE(target_root.stat().st_mode)
    root.parent.mkdir(parents=True)
    root.symlink_to(target_root, target_is_directory=True)

    with app.app_context():
        assert read_product_image(filename) is None
        assert remove_product_image(filename) is False

    assert root.is_symlink()
    assert existing.read_bytes() == existing_content
    assert stat.S_IMODE(target_root.stat().st_mode) == mode_before


def test_upload_root_inode_mismatch_is_rejected_and_descriptor_is_closed(
    app, monkeypatch
):
    root = Path(app.config["PRODUCT_UPLOAD_DIR"])
    root.mkdir(mode=0o700, parents=True)
    original_open = images.os.open
    original_fstat = images.os.fstat
    opened_descriptors = []

    def record_open(*args, **kwargs):
        descriptor = original_open(*args, **kwargs)
        opened_descriptors.append(descriptor)
        return descriptor

    def mismatched_fstat(descriptor):
        details = original_fstat(descriptor)
        return SimpleNamespace(
            st_mode=details.st_mode,
            st_dev=details.st_dev,
            st_ino=details.st_ino + 1,
        )

    monkeypatch.setattr(images.os, "open", record_open)
    monkeypatch.setattr(images.os, "fstat", mismatched_fstat)
    with app.app_context():
        assert images._open_upload_root() is None

    assert len(opened_descriptors) == 1
    with pytest.raises(OSError):
        original_fstat(opened_descriptors[0])


@pytest.mark.parametrize(
    "filename",
    [
        "../outside.png",
        r"..\outside.png",
        "A" * 32 + ".png",
        "a" * 31 + ".png",
        "a" * 32 + ".gif",
        "a" * 32 + ".png/extra",
        None,
    ],
)
def test_unsafe_database_filename_is_never_read_or_removed(app, filename):
    with app.app_context():
        assert read_product_image(filename) is None
        assert remove_product_image(filename) is False


def test_symlink_missing_and_oversized_stored_files_are_rejected(
    app, image_bytes, tmp_path
):
    root = Path(app.config["PRODUCT_UPLOAD_DIR"])
    root.mkdir(mode=0o700, parents=True)
    outside = tmp_path / "outside.png"
    outside.write_bytes(image_bytes("PNG"))
    symlink_name = f"{'b' * 32}.png"
    (root / symlink_name).symlink_to(outside)

    with app.app_context():
        assert read_product_image(symlink_name) is None
        assert remove_product_image(symlink_name) is False
        assert outside.read_bytes() == image_bytes("PNG")
        assert read_product_image(f"{'c' * 32}.png") is None
        app.config["PRODUCT_MAX_FILE_BYTES"] = 4
        oversized = root / f"{'d' * 32}.png"
        oversized.write_bytes(b"12345")
        assert read_product_image(oversized.name) is None


def test_stored_content_must_match_normalized_extension(app, image_bytes):
    root = Path(app.config["PRODUCT_UPLOAD_DIR"])
    root.mkdir(mode=0o700, parents=True)
    mismatched = root / f"{'e' * 32}.jpg"
    mismatched.write_bytes(image_bytes("PNG"))
    non_image = root / f"{'f' * 32}.png"
    non_image.write_bytes(b"not an image")

    with app.app_context():
        assert read_product_image(mismatched.name) is None
        assert read_product_image(non_image.name) is None


@pytest.mark.parametrize(
    ("image_format", "extension", "marker"),
    [
        ("JPEG", ".jpg", "7"),
        ("PNG", ".png", "8"),
        ("WEBP", ".webp", "9"),
    ],
)
def test_read_rejects_on_disk_image_over_current_dimension_limit(
    app, image_bytes, image_format, extension, marker
):
    root = Path(app.config["PRODUCT_UPLOAD_DIR"])
    root.mkdir(mode=0o700, parents=True)
    target = root / f"{marker * 32}{extension}"
    target.write_bytes(image_bytes(image_format, size=(9, 2)))
    app.config["PRODUCT_MAX_DIMENSION"] = 8
    app.config["PRODUCT_MAX_PIXELS"] = 100

    with app.app_context():
        assert read_product_image(target.name) is None


def test_read_rejects_on_disk_image_over_current_pixel_limit(app, image_bytes):
    root = Path(app.config["PRODUCT_UPLOAD_DIR"])
    root.mkdir(mode=0o700, parents=True)
    target = root / f"{'a' * 32}.png"
    target.write_bytes(image_bytes("PNG", size=(4, 4)))
    app.config["PRODUCT_MAX_DIMENSION"] = 10
    app.config["PRODUCT_MAX_PIXELS"] = 15

    with app.app_context():
        assert read_product_image(target.name) is None


def test_read_rejects_on_disk_animated_image(app):
    root = Path(app.config["PRODUCT_UPLOAD_DIR"])
    root.mkdir(mode=0o700, parents=True)
    target = root / f"{'b' * 32}.png"
    output = io.BytesIO()
    frames = [Image.new("RGB", (4, 4), color) for color in ("red", "blue")]
    frames[0].save(
        output,
        format="PNG",
        save_all=True,
        append_images=frames[1:],
        duration=100,
        loop=0,
    )
    target.write_bytes(output.getvalue())

    with app.app_context():
        assert read_product_image(target.name) is None


def test_normal_stored_image_is_still_readable(app, image_bytes):
    with app.app_context():
        stored = store_product_image(upload(image_bytes("JPEG"), "photo.jpeg"))
        result = read_product_image(stored.filename)

    assert result is not None
    assert result.content_type == "image/jpeg"
    assert result.extension == ".jpg"
    with Image.open(io.BytesIO(result.content)) as decoded:
        assert decoded.format == "JPEG"


def test_read_rejects_decompression_bomb_warning(app, image_bytes, monkeypatch):
    root = Path(app.config["PRODUCT_UPLOAD_DIR"])
    root.mkdir(mode=0o700, parents=True)
    target = root / f"{'c' * 32}.png"
    target.write_bytes(image_bytes("PNG"))
    original_open = images.Image.open

    def warn_then_open(*args, **kwargs):
        import warnings

        warnings.warn("bomb", Image.DecompressionBombWarning)
        return original_open(*args, **kwargs)

    monkeypatch.setattr(images.Image, "open", warn_then_open)
    with app.app_context():
        assert read_product_image(target.name) is None


def test_remove_product_image_deletes_only_regular_safe_file(app, image_bytes):
    with app.app_context():
        stored = store_product_image(upload(image_bytes("WEBP"), "photo.webp"))
        target = Path(app.config["PRODUCT_UPLOAD_DIR"]) / stored.filename
        assert remove_product_image(stored.filename) is True
        assert remove_product_image(stored.filename) is False
    assert not target.exists()


def test_decompression_bomb_warning_is_rejected(app, image_bytes, monkeypatch):
    original_open = images.Image.open

    def warn_then_open(*args, **kwargs):
        import warnings

        warnings.warn("bomb", Image.DecompressionBombWarning)
        return original_open(*args, **kwargs)

    monkeypatch.setattr(images.Image, "open", warn_then_open)
    with app.app_context(), pytest.raises(ImageValidationError):
        validate_and_reencode(upload(image_bytes("PNG"), "photo.png"))
