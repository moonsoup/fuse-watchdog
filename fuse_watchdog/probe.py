"""Mount health probing — classify what a stat() of the mount tells us.

Pure logic (classify_errno) separated from the syscall (probe_path) so the
decision table is unit-testable without a real device.
"""
import enum
import errno
import os
import queue
import threading


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


def probe_mount_bounded(mount_point, timeout_secs, probe_fn=None):
    """Same result shape as probe_mount, but bounded: if the underlying probe
    doesn't return within timeout_secs, treat it as Health.STALE instead of
    blocking forever.

    Without this, a mount wedged in an uninterruptible KERNEL I/O wait (the
    documented "frozen-session hazard" — distinct from a cleanly-dropped
    device, which surfaces ENXIO/ENODEV promptly) hangs os.stat()/os.listdir()
    indefinitely. That would hang THIS watchdog's own poll loop forever too —
    exactly the scenario a supervisor process must never get stuck in, since
    nothing else would then notice or recover the mount.

    Runs probe_fn in a daemon thread and waits at most timeout_secs via a
    Queue. A signal-based timeout can't work here: a thread genuinely blocked
    in an uninterruptible kernel wait does not process signals until the
    syscall returns. Using daemon=True (not concurrent.futures.
    ThreadPoolExecutor, whose worker threads register an atexit handler that
    WAITS for them) means a truly stuck probe thread is simply abandoned —
    it can't block process exit or later polls, it's just leaked until (if
    ever) the underlying syscall returns, at which point its result is
    silently discarded into a queue nothing is reading anymore.
    """
    if probe_fn is None:
        probe_fn = lambda: probe_mount(mount_point)  # noqa: E731
    result_q = queue.Queue(maxsize=1)

    def _worker():
        try:
            result_q.put(probe_fn())
        except Exception:
            result_q.put((Health.STALE, None))

    threading.Thread(target=_worker, daemon=True).start()
    try:
        return result_q.get(timeout=timeout_secs)
    except queue.Empty:
        return Health.STALE, None
