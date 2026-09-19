import os
import hashlib
import stat
import sys
from contextlib import contextmanager


class UnsafePath(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class DeletionError(UnsafePath):
    def __init__(self, code, removed, changed, error):
        super().__init__(code)
        self.bytes_removed = removed
        self.changed = changed
        self.errno = getattr(error, "errno", None)


def identity(value):
    return value.st_dev, value.st_ino


def fingerprint(value):
    return (*identity(value), value.st_mode, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def tree_summary(tree):
    digest = hashlib.sha256()
    for name, value in tree["records"].items():
        digest.update(os.fsencode(name) + b"\0" + repr(value).encode() + b"\0")
    return {"chain": tree["chain"], "digest": digest.hexdigest(), "bytes": tree["bytes"]}


def mount_points():
    if sys.platform != "linux":
        return set()
    try:
        with open("/proc/self/mountinfo", encoding="utf-8") as source:
            lines = source.readlines()
        return {line.split()[4].replace("\\040", " ").replace("\\011", "\t").replace("\\134", "\\") for line in lines}
    except (OSError, IndexError, UnicodeError) as error:
        raise UnsafePath("unsafe_path") from error


@contextmanager
def open_directory(path, expected=None):
    if not os.path.isabs(path) or os.path.normpath(path) != path:
        raise UnsafePath("unsafe_path")
    descriptors = []
    chain = []
    try:
        descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
        descriptors.append(descriptor)
        chain.append(identity(os.fstat(descriptor)))
        for part in path.split("/")[1:]:
            if not part or part in (".", ".."):
                raise UnsafePath("unsafe_path")
            descriptor = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            descriptors.append(descriptor)
            chain.append(identity(os.fstat(descriptor)))
        if expected is not None and chain != expected:
            raise UnsafePath("path_changed")
        yield descriptor, chain
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def inspect_tree(path, mounts, cancelled):
    records = {}
    total = 0
    path = str(path)
    if path in mounts or os.path.ismount(path):
        raise UnsafePath("mount_point")
    with open_directory(path) as (root_fd, chain):
        root = os.fstat(root_fd)
        device = root.st_dev
        records[""] = fingerprint(root)

        def visit(descriptor, relative="", depth=0):
            nonlocal total
            if depth > 128:
                raise UnsafePath("size_unknown")
            for name in sorted(os.listdir(descriptor)):
                if cancelled.is_set():
                    raise UnsafePath("cancelled")
                if len(records) >= 250_000:
                    raise UnsafePath("size_unknown")
                child = f"{relative}/{name}" if relative else name
                value = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                records[child] = fingerprint(value)
                if value.st_dev != device or os.path.join(path, child) in mounts:
                    raise UnsafePath("mount_point")
                if stat.S_ISDIR(value.st_mode):
                    child_fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
                    try:
                        if identity(os.fstat(child_fd)) != identity(value):
                            raise UnsafePath("path_changed")
                        visit(child_fd, child, depth + 1)
                    finally:
                        os.close(child_fd)
                elif stat.S_ISREG(value.st_mode):
                    total += value.st_size
                elif not stat.S_ISLNK(value.st_mode):
                    raise UnsafePath("unsafe_path")

        visit(root_fd)
    return {"chain": chain, "records": records, "bytes": total}


def remove_tree(path, reviewed, mounts):
    removed = 0
    changed = False

    def track(size):
        nonlocal removed, changed
        removed += size
        changed = True

    try:
        return _remove_tree(path, reviewed, mounts, track)
    except (UnsafePath, OSError) as error:
        raise DeletionError(getattr(error, "code", "io_error"), removed, changed, error) from None


def _remove_tree(path, reviewed, mounts, record_removal):
    path = str(path)
    parent, name = os.path.split(path)
    with open_directory(parent, reviewed["chain"][:-1]) as (parent_fd, _):
        value = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if fingerprint(value) != reviewed["records"][""]:
            raise UnsafePath("path_changed")
        root_fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
        try:
            if identity(os.fstat(root_fd)) != identity(value):
                raise UnsafePath("path_changed")
            device = value.st_dev

            def remove(descriptor, relative=""):
                for child_name in sorted(os.listdir(descriptor)):
                    child = f"{relative}/{child_name}" if relative else child_name
                    value = os.stat(child_name, dir_fd=descriptor, follow_symlinks=False)
                    if fingerprint(value) != reviewed["records"].get(child):
                        raise UnsafePath("path_changed")
                    if value.st_dev != device or os.path.join(path, child) in mounts:
                        raise UnsafePath("mount_point")
                    if stat.S_ISDIR(value.st_mode):
                        child_fd = os.open(child_name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
                        try:
                            if identity(os.fstat(child_fd)) != identity(value):
                                raise UnsafePath("path_changed")
                            remove(child_fd, child)
                            if identity(os.stat(child_name, dir_fd=descriptor, follow_symlinks=False)) != identity(value):
                                raise UnsafePath("path_changed")
                            os.rmdir(child_name, dir_fd=descriptor)
                            record_removal(0)
                        finally:
                            os.close(child_fd)
                    else:
                        os.unlink(child_name, dir_fd=descriptor)
                        record_removal(value.st_size if stat.S_ISREG(value.st_mode) else 0)

            remove(root_fd)
            if identity(os.stat(name, dir_fd=parent_fd, follow_symlinks=False)) != identity(os.fstat(root_fd)):
                raise UnsafePath("path_changed")
            os.rmdir(name, dir_fd=parent_fd)
            record_removal(0)
            try:
                os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                return
            raise UnsafePath("path_changed")
        finally:
            os.close(root_fd)
