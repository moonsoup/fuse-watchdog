import errno
import threading
import unittest

import _util  # noqa: F401  (sets sys.path)
from fuse_watchdog.probe import (
    Health,
    classify_errno,
    needs_recovery,
    probe_mount,
    probe_mount_bounded,
    probe_path,
)


class FakeStat:
    def __init__(self, dev):
        self.st_dev = dev


class TestProbe(unittest.TestCase):
    def test_classify(self):
        self.assertEqual(classify_errno(None), Health.OK)
        self.assertEqual(classify_errno(errno.ENXIO), Health.DROPPED)
        self.assertEqual(classify_errno(errno.ENODEV), Health.DROPPED)
        self.assertEqual(classify_errno(errno.ENOENT), Health.UNMOUNTED)
        self.assertEqual(classify_errno(errno.EIO), Health.STALE)

    def test_probe_ok(self):
        health, err = probe_path("/whatever", statfn=lambda p: None)
        self.assertEqual(health, Health.OK)
        self.assertIsNone(err)

    def test_probe_drop(self):
        def boom(_p):
            raise OSError(errno.ENXIO, "Device not configured")
        health, err = probe_path("/mnt/x", statfn=boom)
        self.assertEqual(health, Health.DROPPED)
        self.assertEqual(err, errno.ENXIO)

    def test_needs_recovery(self):
        self.assertFalse(needs_recovery(Health.OK))
        self.assertTrue(needs_recovery(Health.DROPPED))
        self.assertTrue(needs_recovery(Health.STALE))
        self.assertTrue(needs_recovery(Health.UNMOUNTED))

    def test_mount_healthy(self):
        # mount point on a different device than its parent, listdir works
        devs = {"/mnt/x": 42, "/mnt": 1}
        health, err = probe_mount("/mnt/x", statfn=lambda p: FakeStat(devs[p]),
                                  listfn=lambda p: [])
        self.assertEqual(health, Health.OK)

    def test_mount_nothing_mounted(self):
        # empty mount-point dir: same st_dev as parent -> UNMOUNTED (the false-OK bug)
        health, err = probe_mount("/mnt/x", statfn=lambda p: FakeStat(1),
                                  listfn=lambda p: [])
        self.assertEqual(health, Health.UNMOUNTED)

    def test_mount_dropped(self):
        # mounted (diff dev) but the device dropped: listdir raises ENXIO
        devs = {"/mnt/x": 42, "/mnt": 1}

        def boom(_p):
            raise OSError(errno.ENXIO, "Device not configured")
        health, err = probe_mount("/mnt/x", statfn=lambda p: FakeStat(devs[p]),
                                  listfn=boom)
        self.assertEqual(health, Health.DROPPED)
        self.assertEqual(err, errno.ENXIO)

    def test_mount_stat_enxio(self):
        def boom(_p):
            raise OSError(errno.ENXIO, "Device not configured")
        health, err = probe_mount("/mnt/x", statfn=boom, listfn=lambda p: [])
        self.assertEqual(health, Health.DROPPED)


class TestProbeBounded(unittest.TestCase):
    """probe_mount_bounded: a probe that hangs (wedged mount, uninterruptible
    kernel I/O wait) must not hang the caller forever along with it."""

    def test_fast_probe_returns_its_real_result(self):
        health, err = probe_mount_bounded(
            "/mnt/x", timeout_secs=1.0, probe_fn=lambda: (Health.OK, None)
        )
        self.assertEqual(health, Health.OK)
        self.assertIsNone(err)

    def test_fast_probe_propagates_a_real_error_result(self):
        health, err = probe_mount_bounded(
            "/mnt/x", timeout_secs=1.0,
            probe_fn=lambda: (Health.DROPPED, errno.ENXIO),
        )
        self.assertEqual(health, Health.DROPPED)
        self.assertEqual(err, errno.ENXIO)

    def test_hung_probe_times_out_as_stale_instead_of_blocking_forever(self):
        # Simulates a probe stuck in an uninterruptible kernel I/O wait: the
        # probe_fn never returns (blocks on an Event that's never set). The
        # bound must still return within ~timeout_secs.
        never = threading.Event()

        def hangs_forever():
            never.wait()  # never set -> blocks until the process exits
            return (Health.OK, None)  # unreachable in this test

        health, err = probe_mount_bounded(
            "/mnt/x", timeout_secs=0.1, probe_fn=hangs_forever
        )
        self.assertEqual(health, Health.STALE)
        self.assertIsNone(err)

    def test_hung_probe_does_not_block_a_second_call_afterward(self):
        # The leaked thread from a timed-out probe must not somehow wedge
        # subsequent calls (e.g. via a shared/blocking resource) -- the
        # watchdog loop calls this every poll_interval, forever.
        never = threading.Event()

        def hangs_forever():
            never.wait()
            return (Health.OK, None)

        probe_mount_bounded("/mnt/x", timeout_secs=0.1, probe_fn=hangs_forever)
        # A second, independent bounded probe (fast this time) must complete
        # promptly -- not be starved by the first call's still-leaked thread.
        health, err = probe_mount_bounded(
            "/mnt/x", timeout_secs=1.0, probe_fn=lambda: (Health.OK, None)
        )
        self.assertEqual(health, Health.OK)

    def test_probe_fn_raising_is_treated_as_stale_not_an_uncaught_exception(self):
        def boom():
            raise RuntimeError("unexpected failure inside the worker thread")

        health, err = probe_mount_bounded("/mnt/x", timeout_secs=1.0, probe_fn=boom)
        self.assertEqual(health, Health.STALE)

    def test_default_probe_fn_is_probe_mount_bound_to_mount_point(self):
        # No probe_fn given -> uses the real probe_mount against mount_point.
        # Exercise the OK path so the test doesn't touch a real device.
        health, err = probe_mount_bounded(
            "/mnt/x", timeout_secs=1.0,
        )
        # No probe_fn injected means this calls the REAL probe_mount against
        # a path that doesn't exist -- must resolve (as UNMOUNTED or STALE
        # via a raised OSError), not hang, proving the wiring itself is sound.
        self.assertIn(health, (Health.UNMOUNTED, Health.STALE, Health.DROPPED))


if __name__ == "__main__":
    unittest.main()
