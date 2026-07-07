"""Mount health probing — classify what a stat() of the mount tells us.

Pure logic (classify_errno) separated from the syscall (probe_path) so the
decision table is unit-testable without a real device.
"""
import enum
import errno
import os


class Health(enum.Enum):
    OK = "ok"                  # mount responds normally
    DROPPED = "dropped"        # ENXIO / ENODEV — device fell off the bus
    UNMOUNTED = "unmounted"    # ENOENT — nothing mounted at the path
    STALE = "stale"            # other I/O error — mount wedged


# errno values that mean "the backing device is gone", the case this tool exists for.
_DROP_ERRNOS = frozenset({errno.ENXIO, errno.ENODEV})


def classify_errno(err):
    """Map an errno (or None for success) to a Health. Pure."""
    if err is None:
        return Health.OK
    if err in _DROP_ERRNOS:
        return Health.DROPPED
    if err == errno.ENOENT:
        return Health.UNMOUNTED
    return Health.STALE


def probe_path(sentinel, statfn=os.stat):
    """stat `sentinel` and classify. Returns (Health, errno_or_None). Low-level
    primitive; `probe_mount` is what the watchdog actually uses."""
    try:
        statfn(sentinel)
        return Health.OK, None
    except OSError as e:
        return classify_errno(e.errno), e.errno


def probe_mount(mount_point, statfn=os.stat, listfn=os.listdir):
    """Classify a mount point's health. Returns (Health, errno_or_None).

    Two checks, because statting the mount-point directory alone is not enough —
    the directory exists whether or not a filesystem is mounted on it:
      1. Is anything actually mounted? Compare st_dev of the mount point to its
         parent; equal means nothing is mounted (UNMOUNTED).
      2. Is the mounted device alive? Force a real filesystem op (listdir) so a
         dropped/stale backing device surfaces its ENXIO (DROPPED) instead of
         being masked by a cached stat.
    statfn/listfn are injectable for tests.
    """
    try:
        st = statfn(mount_point)
        parent = statfn(os.path.dirname(os.path.abspath(mount_point)) or "/")
    except OSError as e:
        return classify_errno(e.errno), e.errno
    if st.st_dev == parent.st_dev:
        return Health.UNMOUNTED, None
    try:
        listfn(mount_point)
    except OSError as e:
        return classify_errno(e.errno), e.errno
    return Health.OK, None


def needs_recovery(health):
    """True for any non-OK state the watchdog should act on. Pure."""
    return health in (Health.DROPPED, Health.STALE, Health.UNMOUNTED)
