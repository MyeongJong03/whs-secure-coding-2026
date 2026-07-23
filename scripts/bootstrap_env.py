import argparse
import os
import secrets
import sys
from pathlib import Path
from typing import Sequence


ENV_VALUE_MARKER = "replace-with-a-long-random-local-value"


class BootstrapEnvironmentError(RuntimeError):
    pass


def _write_all(descriptor: int, content: bytes) -> None:
    remaining = memoryview(content)
    while remaining:
        written = os.write(descriptor, remaining)
        if written <= 0:
            raise OSError("environment file write made no progress")
        remaining = remaining[written:]


def create_environment_file(
    example_path: str | os.PathLike[str] = ".env.example",
    target_path: str | os.PathLike[str] = ".env",
) -> Path:
    example = Path(example_path)
    target = Path(target_path)
    try:
        template = example.read_text(encoding="utf-8")
    except OSError:
        raise BootstrapEnvironmentError(
            f"환경 template을 읽을 수 없습니다: {example}"
        ) from None

    if template.count(ENV_VALUE_MARKER) != 1:
        raise BootstrapEnvironmentError(
            "환경 template에는 Secret Key placeholder가 정확히 한 번 있어야 합니다."
        )

    secret_key = secrets.token_urlsafe(64)
    content = template.replace(ENV_VALUE_MARKER, secret_key, 1).encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC

    descriptor: int | None = None
    created = False
    try:
        descriptor = os.open(target, flags, 0o600)
        created = True
        os.fchmod(descriptor, 0o600)
        _write_all(descriptor, content)
        os.fsync(descriptor)
    except OSError:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
            descriptor = None
        if created:
            try:
                os.unlink(target)
            except OSError:
                pass
        raise BootstrapEnvironmentError(
            f"환경 파일을 안전하게 생성할 수 없습니다: {target}"
        ) from None
    finally:
        if descriptor is not None:
            os.close(descriptor)

    return target


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a private local .env from .env.example."
    )
    parser.add_argument("--example", default=".env.example")
    parser.add_argument("--target", default=".env")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        target = create_environment_file(args.example, args.target)
    except BootstrapEnvironmentError as error:
        print(f"오류: {error}", file=sys.stderr)
        return 1

    print(f"환경 파일을 생성했습니다: {target}")
    print("다음 단계: .venv/bin/flask --app run.py db upgrade")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
