# ====== Code Summary ======
# ProcessTreeHelpers — psutil reads/kills over a parse child AND its descendants. The RSS watchdog
# sums the RESIDENT set of the whole tree (docling/torch may spawn worker processes), and the pool's
# kill path SIGKILLs those descendants before the child itself, so a killed parse never leaves an
# orphaned grandchild holding memory. Every call tolerates a process vanishing mid-walk (it raced to
# exit), which is the normal case right after a kill.

# ====== Third-Party Library Imports ======
import psutil


class ProcessTreeHelpers:
    """Static psutil helpers over a process and its recursive children."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("ProcessTreeHelpers is a static-only class and cannot be instantiated.")

    @staticmethod
    def __descendants(pid: int) -> list[psutil.Process]:
        """The recursive children of ``pid`` (empty when the process is already gone)."""
        try:
            return psutil.Process(pid).children(recursive=True)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return []

    @classmethod
    def rss_bytes(cls, pid: int) -> int:
        """
        Total resident memory (bytes) of ``pid`` plus all of its descendants.

        Shared pages (the warm child's copy-on-write view of the forked worker) are counted per
        process, so the sum is an upper bound of the tree's real footprint — the conservative side
        for a kill threshold.

        Args:
            pid (int): The root process id (the parse child).

        Returns:
            int: The summed RSS in bytes; 0 when the root is already gone.
        """
        try:
            tree = [psutil.Process(pid), *cls.__descendants(pid)]
        except psutil.NoSuchProcess:
            return 0
        total = 0
        for proc in tree:
            try:
                total += proc.memory_info().rss
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return total

    @classmethod
    def kill_descendants(cls, pid: int) -> None:
        """
        SIGKILL every descendant of ``pid`` (the root itself is killed by its owner).

        Args:
            pid (int): The root process id (the parse child).
        """
        for proc in cls.__descendants(pid):
            try:
                proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue


__all__ = ["ProcessTreeHelpers"]
