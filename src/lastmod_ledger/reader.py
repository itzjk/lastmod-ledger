import errno
import hashlib
import os
import stat
from dataclasses import dataclass


@dataclass(frozen=True)
class Limits:
    entries: int = 50000
    manifest_bytes: int = 4 * 1024 * 1024
    sitemap_bytes: int = 16 * 1024 * 1024
    file_bytes: int = 32 * 1024 * 1024
    total_bytes: int = 512 * 1024 * 1024


class ReadIssue(Exception):
    def __init__(self, code, path):
        self.code = code
        self.path = str(path)
        super().__init__(f'{code}: {path}')


def identity(info):
    return {key: getattr(info, 'st_' + key) for key in ('dev', 'ino', 'size', 'mtime_ns', 'ctime_ns')}


def open_regular(path):
    if not hasattr(os, 'O_NOFOLLOW') or not hasattr(os, 'O_DIRECTORY'):
        raise ReadIssue('unsupported-platform', path)
    parts = os.fspath(path).split('/')
    directory = os.open('/' if os.path.isabs(path) else '.', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in parts[:-1]:
            if not part or part == '.':
                continue
            try:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            except OSError:
                if stat.S_ISLNK(os.stat(part, dir_fd=directory, follow_symlinks=False).st_mode):
                    raise ReadIssue('symlink', path)
                raise
            os.close(directory)
            directory = child
        descriptor = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    except OSError as error:
        code = 'missing-file' if error.errno == errno.ENOENT else 'unreadable-file'
        if error.errno == errno.ELOOP:
            code = 'symlink'
        raise ReadIssue(code, path) from error
    finally:
        os.close(directory)
    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise ReadIssue('not-regular-file', path)
    return descriptor


class Reader:
    def __init__(self, limits):
        self.limits = limits
        self.bytes_read = 0
        self.observations = []

    def read(self, path, maximum, keep=False):
        path = str(path)
        fd = open_regular(path)
        try:
            initial = identity(os.fstat(fd))
            if initial['size'] > maximum:
                raise ReadIssue('file-byte-limit', path)
            if self.bytes_read + initial['size'] > self.limits.total_bytes:
                raise ReadIssue('total-byte-limit', path)
            digest = hashlib.sha256()
            chunks = []
            size = 0
            while True:
                amount = min(65536, maximum - size + 1, self.limits.total_bytes - self.bytes_read + 1)
                chunk = os.read(fd, amount)
                if not chunk:
                    break
                size += len(chunk)
                self.bytes_read += len(chunk)
                if size > maximum or self.bytes_read > self.limits.total_bytes:
                    raise ReadIssue('byte-limit-during-read', path)
                digest.update(chunk)
                if keep:
                    chunks.append(chunk)
            final = identity(os.fstat(fd))
            if initial != final or size != initial['size']:
                raise ReadIssue('concurrent-change', path)
        finally:
            os.close(fd)
        observation = {'path': path, 'sha256': digest.hexdigest(), 'size': size, 'stat': initial, 'stable': True}
        self.observations.append(observation)
        self.check(observation)
        if not observation['stable']:
            raise ReadIssue('concurrent-change', path)
        return observation, b''.join(chunks) if keep else None

    def check(self, observation):
        try:
            fd = open_regular(observation['path'])
            try:
                current = identity(os.fstat(fd))
            finally:
                os.close(fd)
            if current != observation['stat']:
                observation['stable'] = False
        except ReadIssue:
            observation['stable'] = False
        return observation['stable']

    def recheck(self):
        for observation in self.observations:
            self.check(observation)
