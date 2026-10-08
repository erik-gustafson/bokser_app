"""Private JSON files for worker credentials and ingestion cursors."""
import json
import os
import stat
import tempfile
from pathlib import Path


def private_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    info = path.parent.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o022
            or info.st_uid not in (os.getuid(), 0)):
        raise PermissionError("JSON parent must be an owned, non-writable-by-others directory")


def checked_fd(path: Path, flags: int) -> int:
    fd = os.open(path, flags | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & 0o077 or info.st_nlink != 1):
            raise PermissionError("JSON file must be a private regular file owned by the worker")
    except BaseException:
        os.close(fd)
        raise
    return fd


def read_private_json(path: Path):
    private_parent(path)
    with os.fdopen(checked_fd(path, os.O_RDONLY), "r", encoding="utf-8") as handle:
        return json.load(handle)


def write_private_json(path: Path, value, *, atomic: bool = True) -> None:
    # Serialize before opening/truncating the existing credential file.
    text = json.dumps(value, indent=2, sort_keys=True)
    private_parent(path)
    if path.exists() or path.is_symlink():
        fd = checked_fd(path, os.O_RDONLY)
        os.close(fd)
    if not atomic:
        # File bind mounts cannot be replaced using rename. Retain the inode.
        with os.fdopen(checked_fd(path, os.O_WRONLY | os.O_CREAT), "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.truncate()
            handle.flush()
            os.fsync(handle.fileno())
        return
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                         dir=path.parent, delete=False) as handle:
            name = handle.name
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
        name = None
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        if name is not None:
            os.unlink(name)
