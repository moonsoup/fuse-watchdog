import errno
import unittest

import _util  # noqa: F401  (sets sys.path)
from fuse_watchdog.probe import (
    Health,
    classify_errno,
    needs_recovery,
    probe_mount,
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


if __name__ == "__main__":
    unittest.main()
