import os
import stat
from pathlib import Path


def _descriptor_flags(*, directory: bool = False) -> int:
    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    if directory:
        flags |= getattr(os, "O_DIRECTORY", 0)
    return flags


def _matching_stat(path_stat: os.stat_result, descriptor_stat: os.stat_result) -> bool:
    return (
        path_stat.st_dev == descriptor_stat.st_dev
        and path_stat.st_ino == descriptor_stat.st_ino
    )


def secure_instance_directory(instance_path: str) -> None:
    path = Path(instance_path)
    try:
        path_stat = os.lstat(path)
    except FileNotFoundError:
        try:
            path.mkdir(mode=0o700, parents=True)
        except FileExistsError:
            pass
        path_stat = os.lstat(path)

    if stat.S_ISLNK(path_stat.st_mode):
        raise RuntimeError("Flask instance path must not be a symbolic link")
    if not stat.S_ISDIR(path_stat.st_mode):
        raise RuntimeError("Flask instance path must be a directory")
    if os.name != "posix":
        return

    descriptor = None
    try:
        descriptor = os.open(path, _descriptor_flags(directory=True))
        descriptor_stat = os.fstat(descriptor)
        if not stat.S_ISDIR(descriptor_stat.st_mode) or not _matching_stat(
            path_stat, descriptor_stat
        ):
            raise RuntimeError("Flask instance directory changed during validation")
        os.fchmod(descriptor, 0o700)
    except OSError as error:
        raise RuntimeError("Unable to secure Flask instance directory") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


def secure_sqlite_database_file(database_path: str | None) -> None:
    if (
        os.name != "posix"
        or not database_path
        or database_path == ":memory:"
        or database_path.startswith("file::memory:")
        or (
            database_path.startswith("file:")
            and "mode=memory" in database_path.partition("?")[2].split("&")
        )
    ):
        return

    path = Path(database_path)
    try:
        path_stat = os.lstat(path)
    except OSError as error:
        raise RuntimeError("Unable to validate SQLite main database file") from error
    if stat.S_ISLNK(path_stat.st_mode):
        raise RuntimeError("SQLite main database path must not be a symbolic link")
    if not stat.S_ISREG(path_stat.st_mode):
        raise RuntimeError("SQLite main database must be a regular file")

    descriptor = None
    try:
        descriptor = os.open(path, _descriptor_flags())
        descriptor_stat = os.fstat(descriptor)
        if not stat.S_ISREG(descriptor_stat.st_mode) or not _matching_stat(
            path_stat, descriptor_stat
        ):
            raise RuntimeError("SQLite main database changed during validation")
        os.fchmod(descriptor, 0o600)
    except OSError as error:
        raise RuntimeError("Unable to secure SQLite main database file") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
