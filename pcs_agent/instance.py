"""OS-held lock: crashes release it; a stale filename cannot block a restart."""
import os
from pathlib import Path


def _acquire_lock(stream):
    stream.seek(0)
    if os.name == "nt":
        import msvcrt
        # Windows permits locking a region beyond EOF, including a new file.
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _release_lock(stream):
    if os.name == "nt":
        import msvcrt
        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
    # Closing the descriptor also releases the POSIX lock.


class InstanceLock:
    def __init__(self, folder):
        root = Path(folder)
        root.mkdir(parents=True, exist_ok=True)
        self.stream = (root / "strident-instance.lock").open("a+b", buffering=0)
        try:
            _acquire_lock(self.stream)
        except OSError:
            self.stream.close()
            raise RuntimeError("Strident is already running. Restore its window from the taskbar or tray.") from None
        except BaseException:
            self.stream.close()
            raise
        try:
            # A second Windows process must never read the already-locked byte.
            self.stream.seek(0)
            if not self.stream.read(1):
                self.stream.write(b"0")
                self.stream.flush()
        except BaseException:
            self.stream.close()
            raise

    def close(self):
        if self.stream.closed:
            return
        try:
            _release_lock(self.stream)
        finally:
            self.stream.close()
