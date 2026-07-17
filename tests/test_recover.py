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

    def test_fsck_skipped_by_default(self):
        cfg, runner, log = FakeCfg(), FakeRunner(), Log()
        recover(cfg, runner, log, sleep=NOSLEEP, uuid_reader=lambda d: cfg.fs_uuid)
        self.assertFalse(any("e2fsck" in c for c in runner.calls))

    def test_fsck_runs_when_requested(self):
        cfg, runner, log = FakeCfg(), FakeRunner(), Log()
        ok = recover(cfg, runner, log, sleep=NOSLEEP, uuid_reader=lambda d: cfg.fs_uuid, fsck=True)
        self.assertTrue(ok)
        self.assertTrue(any("e2fsck" in c for c in runner.calls))

    def test_fsck_runs_after_unmount_and_before_mount(self):
        cfg, runner, log = FakeCfg(), FakeRunner(), Log()
        recover(cfg, runner, log, sleep=NOSLEEP, uuid_reader=lambda d: cfg.fs_uuid, fsck=True)
        unmount_idx = next(i for i, c in enumerate(runner.calls) if "unmountDisk" in c)
        fsck_idx = next(i for i, c in enumerate(runner.calls) if "e2fsck" in c)
        mount_idx = next(i for i, c in enumerate(runner.calls) if is_mount_cmd(c))
        self.assertLess(unmount_idx, fsck_idx)
        self.assertLess(fsck_idx, mount_idx)

    def test_fsck_does_not_bypass_uuid_safety_gate(self):
        """THE safety test, fsck variant: fsck must not weaken the wrong-disk refusal."""
        cfg, runner, log = FakeCfg(), FakeRunner(), Log()
        ok = recover(cfg, runner, log, sleep=NOSLEEP,
                     uuid_reader=lambda d: "ffffffff-0000-0000-0000-000000000000", fsck=True)
        self.assertFalse(ok)
        self.assertFalse(runner.mount_was_issued())
        self.assertIn("REFUSING", log.text())

    def test_uuid_read_retries_on_transient_failure_then_succeeds(self):
        """Real incident (2026-07-17): reading the device right after
        unmountDisk force can transiently fail (EPERM) even as root, then
        succeed moments later. The read must retry, not refuse on the first
        transient miss."""
        cfg = FakeCfg()
        cfg.uuid_read_retries = 3
        runner, log = FakeRunner(), Log()
        calls = []

        def flaky_reader(device):
            calls.append(device)
            if len(calls) < 3:
                return None  # unreadable, like the transient EPERM
            return cfg.fs_uuid

        ok = recover(cfg, runner, log, sleep=NOSLEEP, uuid_reader=flaky_reader)
        self.assertTrue(ok, "must succeed once the transient read failure clears within the retry budget")
        self.assertEqual(len(calls), 3)
        self.assertTrue(runner.mount_was_issued())

    def test_uuid_read_gives_up_after_exhausting_retries(self):
        cfg = FakeCfg()
        cfg.uuid_read_retries = 2
        runner, log = FakeRunner(), Log()
        calls = []

        def always_unreadable(device):
            calls.append(device)
            return None

        ok = recover(cfg, runner, log, sleep=NOSLEEP, uuid_reader=always_unreadable)
        self.assertFalse(ok)
        self.assertEqual(len(calls), 3, "1 initial attempt + 2 retries = 3 total reads")
        self.assertFalse(runner.mount_was_issued())

    def test_zero_uuid_read_retries_means_exactly_one_attempt(self):
        """Backward-compat default (FakeCfg.uuid_read_retries = 0): unchanged
        single-attempt behavior, matching every test above this one."""
        cfg = FakeCfg()  # uuid_read_retries = 0 by default
        runner, log = FakeRunner(), Log()
        calls = []

        def reader(device):
            calls.append(device)
            return None

        recover(cfg, runner, log, sleep=NOSLEEP, uuid_reader=reader)
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
