import unittest

from _util import FakeCfg, Log
from fuse_watchdog.probe import Health
from fuse_watchdog.watchdog import run_loop

NOSLEEP = lambda _s: None  # noqa: E731


def scripted_probe(sequence):
    """Return a probe_fn that yields each (Health, errno) in order, then repeats last."""
    it = iter(sequence)
    last = [None]

    def _probe():
        try:
            last[0] = next(it)
        except StopIteration:
            pass
        return last[0]
    return _probe


class TestWatchdog(unittest.TestCase):
    def test_healthy_never_recovers(self):
        cfg, log = FakeCfg(), Log()
        probe = scripted_probe([(Health.OK, None)] * 5)
        calls = []
        stats = run_loop(cfg, log, probe_fn=probe,
                         recover_fn=lambda: calls.append(1) or True,
                         sleep=NOSLEEP, max_iterations=5)
        self.assertEqual(stats["recoveries"], 0)
        self.assertEqual(calls, [])

    def test_drop_triggers_recovery_then_stable(self):
        cfg, log = FakeCfg(), Log()
        probe = scripted_probe([(Health.OK, None), (Health.DROPPED, 6),
                                (Health.OK, None), (Health.OK, None)])
        stats = run_loop(cfg, log, probe_fn=probe,
                         recover_fn=lambda: True, sleep=NOSLEEP, max_iterations=4)
        self.assertEqual(stats["recoveries"], 1)
        self.assertFalse(stats["gave_up"])

    def test_gives_up_after_max_attempts(self):
        cfg, log = FakeCfg(), Log()  # max_recover_attempts = 3
        probe = scripted_probe([(Health.DROPPED, 6)] * 10)
        stats = run_loop(cfg, log, probe_fn=probe,
                         recover_fn=lambda: False, sleep=NOSLEEP, max_iterations=10)
        self.assertTrue(stats["gave_up"])
        self.assertEqual(stats["recovery_failures"], 3)
        self.assertIn("giving up", log.text())

    def test_recovers_resets_failure_streak(self):
        cfg, log = FakeCfg(), Log()
        # fail, fail, succeed, fail, fail  -> never 3 consecutive -> no give-up
        results = iter([False, False, True, False, False])
        probe = scripted_probe([(Health.DROPPED, 6)] * 5)
        stats = run_loop(cfg, log, probe_fn=probe,
                         recover_fn=lambda: next(results), sleep=NOSLEEP,
                         max_iterations=5)
        self.assertFalse(stats["gave_up"])


if __name__ == "__main__":
    unittest.main()
