import unittest

from _util import FakeCfg, FakeRunner, Log, is_mount_cmd
from fuse_watchdog.recover import recover

NOSLEEP = lambda _s: None  # noqa: E731


class TestRecover(unittest.TestCase):
    def test_happy_path_remounts(self):
        cfg, runner, log = FakeCfg(), FakeRunner(), Log()
        ok = recover(cfg, runner, log, sleep=NOSLEEP, uuid_reader=lambda d: cfg.fs_uuid)
        self.assertTrue(ok)
        self.assertTrue(runner.mount_was_issued())
        # tear-down happened before the mount
        self.assertTrue(any("pkill" in c for c in runner.calls))
        self.assertTrue(any("unmountDisk" in c for c in runner.calls))

    def test_refuses_wrong_disk(self):
        """THE safety test: a mismatched UUID must NOT remount."""
        cfg, runner, log = FakeCfg(), FakeRunner(), Log()
        ok = recover(cfg, runner, log, sleep=NOSLEEP,
                     uuid_reader=lambda d: "ffffffff-0000-0000-0000-000000000000")
        self.assertFalse(ok)
        self.assertFalse(runner.mount_was_issued())
        self.assertIn("REFUSING", log.text())

    def test_refuses_unreadable_device(self):
        cfg, runner, log = FakeCfg(), FakeRunner(), Log()
        ok = recover(cfg, runner, log, sleep=NOSLEEP, uuid_reader=lambda d: None)
        self.assertFalse(ok)
        self.assertFalse(runner.mount_was_issued())

    def test_mount_command_failure(self):
        cfg, runner, log = FakeCfg(), FakeRunner(mount_rc=1), Log()
        ok = recover(cfg, runner, log, sleep=NOSLEEP, uuid_reader=lambda d: cfg.fs_uuid)
        self.assertFalse(ok)
        self.assertTrue(runner.mount_was_issued())  # it tried, but rc!=0

    def test_teardown_precedes_mount(self):
        cfg, runner, log = FakeCfg(), FakeRunner(), Log()
        recover(cfg, runner, log, sleep=NOSLEEP, uuid_reader=lambda d: cfg.fs_uuid)
        mount_idx = next(i for i, c in enumerate(runner.calls) if is_mount_cmd(c))
        unmount_idx = next(i for i, c in enumerate(runner.calls) if "unmountDisk" in c)
        self.assertLess(unmount_idx, mount_idx)


if __name__ == "__main__":
    unittest.main()
