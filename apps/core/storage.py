import os
import errno
from django.core.files import locks
from django.core.files.storage import FileSystemStorage

# Global patch for django.core.files.locks to prevent [Errno 35] Resource deadlock avoided on Docker / macOS mounts
try:
    import fcntl

    def _safe_lock(f, flags):
        try:
            return fcntl.flock(f, flags) == 0
        except OSError as e:
            if getattr(e, 'errno', None) in (getattr(errno, 'EDEADLK', 35), getattr(errno, 'EAGAIN', 11), getattr(errno, 'ENOTSUP', 45), 35, 11, 45):
                return True
            raise

    def _safe_unlock(f):
        try:
            return fcntl.flock(f, fcntl.LOCK_UN) == 0
        except OSError:
            return True

    locks.lock = _safe_lock
    locks.unlock = _safe_unlock
except (ImportError, AttributeError):
    pass


class SafeFileSystemStorage(FileSystemStorage):
    """
    subclass of FileSystemStorage tailored for development on macOS / Docker volume mounts
    (VirtioFS, osxfs, NFS).
    
    bypasses OS file locking (fcntl.flock / fcntl.lockf) during file saves to prevent:
    `[Errno 35] Resource deadlock avoided` (POSIX EDEADLK / EAGAIN).
    """

    def _save(self, name, content):
        full_path = self.path(name)

        directory = os.path.dirname(full_path)
        if not os.path.exists(directory):
            try:
                if self.directory_permissions_mode is not None:
                    os.makedirs(directory, self.directory_permissions_mode, exist_ok=True)
                else:
                    os.makedirs(directory, exist_ok=True)
            except FileExistsError:
                pass

        while True:
            if os.path.exists(full_path):
                name = self.get_available_name(name)
                full_path = self.path(name)

            try:
                with open(full_path, "wb") as destination:
                    if hasattr(content, "chunks"):
                        for chunk in content.chunks():
                            destination.write(chunk)
                    elif hasattr(content, "read"):
                        destination.write(content.read())
                    elif isinstance(content, (bytes, bytearray)):
                        destination.write(content)
                    else:
                        destination.write(str(content).encode('utf-8'))
                break
            except FileExistsError:
                name = self.get_available_name(name)
                full_path = self.path(name)

        if self.file_permissions_mode is not None:
            try:
                os.chmod(full_path, self.file_permissions_mode)
            except OSError:
                pass

        return name.replace("\\", "/")
