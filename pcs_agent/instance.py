"""OS-held lock: crashes release it; a stale filename cannot block a restart."""
import os
from pathlib import Path


class InstanceLock:
    def __init__(self, folder):
        root = Path(folder)
        root.mkdir(parents=True, exist_ok=True)
        self.stream = (root / "strident-instance.lock").open("a+b")
        try:
            # Do not read a byte locked by another Windows instance.
            if os.fstat(self.stream.fileno()).st_size == 0:
                self.stream.write(b"0")
                self.stream.flush()
            self.stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.stream.close()
            raise RuntimeError("Strident is already running. Restore its window from the taskbar or tray.") from None

    def close(self):
        if self.stream.closed:
            return
        try:
            if os.name == "nt":
                import msvcrt
                self.stream.seek(0)
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            self.stream.close()
