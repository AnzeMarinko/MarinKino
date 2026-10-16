"""Confined paths and crash-safe JSON storage for local application data."""

from __future__ import annotations

import fcntl
import json
import os
import stat
import tempfile
import threading
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Iterator, ParamSpec, TypeVar
from weakref import WeakValueDictionary

_P = ParamSpec("_P")
_R = TypeVar("_R")
_Path = str | os.PathLike[str]
_registry_guard = threading.Lock()
_thread_locks: WeakValueDictionary = WeakValueDictionary()
_held_locks = threading.local()


def safe_resolved_path(base: _Path, name: _Path) -> str:
    """Resolve a relative file name, refusing escapes and the base itself."""
    value = os.fspath(name)
    if not value or "\x00" in value or Path(value).is_absolute():
        raise ValueError("Expected a relative file path")
    root = Path(base).resolve()
    target = (root / value).resolve()
    if target == root or not target.is_relative_to(root):
        raise ValueError("File path escapes its directory")
    return str(target)


def _file_path(path: _Path) -> Path:
    """Resolve directory aliases without following the destination symlink."""
    target = Path(path)
    if not target.name or target.name in {".", ".."}:
        raise ValueError("Expected a file path")
    return target.parent.resolve() / target.name


def _private_directories(directory: Path) -> None:
    """Give every newly created directory private permissions."""
    missing = []
    current = directory
    while not current.exists():
        missing.append(current)
        current = current.parent
    for item in reversed(missing):
        try:
            item.mkdir(mode=0o700)
        except FileExistsError:
            if not item.is_dir():
                raise


@contextmanager
def locked_path(path: _Path) -> Iterator[str]:
    """Serialize cooperating threads/processes, including nested operations.

    Locks live beside the data rather than on the replaced data inode. Do not
    delete lock files: replacing them would let processes acquire two locks.
    """
    target = _file_path(path)
    key = str(target)
    with _registry_guard:
        thread_lock = _thread_locks.get(key)
        if thread_lock is None:
            thread_lock = threading.RLock()
            _thread_locks[key] = thread_lock
    with thread_lock:
        held = getattr(_held_locks, "files", None)
        if held is None:
            held = _held_locks.files = {}
        if key in held:
            yield key
            return

        _private_directories(target.parent)
        flags = os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW
        descriptor = os.open(
            target.with_name(f".{target.name}.lock"), flags, 0o600
        )
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ValueError("Lock must be a regular file")
            os.fchmod(descriptor, 0o600)
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            held[key] = descriptor
            try:
                yield key
            finally:
                del held[key]
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def atomic_write_json(path: _Path, data: Any, mode: int = 0o600) -> None:
    """Replace flushed JSON atomically; encode errors preserve old data."""
    target = _file_path(path)
    with locked_path(target):
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                os.fchmod(stream.fileno(), mode)
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
            directory_fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def read_json(path: _Path, default: Any) -> Any:
    """Default only for missing files; propagate other errors."""
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    except FileNotFoundError:
        return default
    with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
        return json.load(stream)


def serialized_json(path_getter: Callable[[], _Path]):
    """Lock the view's complete transaction for its chosen file."""

    def decorate(function: Callable[_P, _R]) -> Callable[_P, _R]:
        @wraps(function)
        def wrapped(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            with locked_path(path_getter()):
                return function(*args, **kwargs)

        return wrapped

    return decorate
