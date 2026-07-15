"""The watch loop: probe health, recover on a drop, back off / give up cleanly.

Everything external (probing, recovery, sleeping, logging) is injected, so the
loop's control flow is fully unit-testable with scripted probes.
"""
import time

from .probe import Health, needs_recovery, probe_mount_bounded


def run_loop(cfg, log, probe_fn=None, recover_fn=None, sleep=time.sleep,
             max_iterations=None):
    """Run the watchdog. Returns a summary dict (also handy for tests).

    Stops (returns) if `max_iterations` is reached, or after
    `cfg.max_recover_attempts` *consecutive* failed recoveries — at which point
    the problem is beyond software (hardware / wrong disk) and a human is needed.
    """
    if probe_fn is None:
        # Bounded (see probe_mount_bounded) -- a probe that hangs on a wedged
        # mount must not hang this whole loop forever along with it.
        probe_fn = lambda: probe_mount_bounded(cfg.mount_point, cfg.probe_timeout_secs)  # noqa: E731
    if recover_fn is None:
        raise ValueError("recover_fn is required")

    stats = {"iterations": 0, "recoveries": 0, "recovery_failures": 0,
             "gave_up": False}
    consecutive_fail = 0
    i = 0
    while max_iterations is None or i < max_iterations:
        health, err = probe_fn()
        if health == Health.OK:
            if consecutive_fail:
                log("mount healthy again")
            consecutive_fail = 0
        elif needs_recovery(health):
            log(f"mount unhealthy: {health.value} (errno={err}); recovering")
            ok = recover_fn()
            stats["recoveries"] += 1
            if ok:
                consecutive_fail = 0
            else:
                consecutive_fail += 1
                stats["recovery_failures"] += 1
                if consecutive_fail >= cfg.max_recover_attempts:
                    log(f"giving up after {consecutive_fail} failed recoveries — "
                        f"needs manual/hardware intervention")
                    stats["gave_up"] = True
                    stats["iterations"] = i + 1
                    return stats
        stats["iterations"] = i + 1
        i += 1
        if max_iterations is None or i < max_iterations:
            sleep(cfg.poll_interval)
    return stats
