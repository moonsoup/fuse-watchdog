"""Command-line entry point: wire the real probe/recover and run the loop.

Usage:
    sudo python3 -m fuse_watchdog --config config.json
    sudo python3 -m fuse_watchdog --config config.json --check   # one-shot health probe
    sudo python3 -m fuse_watchdog --config config.json --recover-once

Runs privileged (mount/unmount/raw-device read need root). Logs to the config's
log_path, or stderr.
"""
import argparse
import sys
import time

from . import config as config_mod
from . import probe as probe_mod
from .recover import Runner, recover
from .watchdog import run_loop


def make_logger(log_path):
    def log(msg):
        line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
        if log_path:
            with open(log_path, "a") as f:
                f.write(line + "\n")
        else:
            print(line, file=sys.stderr, flush=True)
    return log


def main(argv=None):
    ap = argparse.ArgumentParser(description="fuse-ext2 device-drop recovery watchdog")
    ap.add_argument("--config", required=True, help="path to config JSON")
    ap.add_argument("--check", action="store_true", help="one-shot health probe, then exit")
    ap.add_argument("--recover-once", action="store_true", help="run a single recovery cycle, then exit")
    args = ap.parse_args(argv)

    cfg = config_mod.load(args.config)
    log = make_logger(cfg.log_path)
    runner = Runner()

    if args.check:
        health, err = probe_mod.probe_mount(cfg.mount_point)
        log(f"health={health.value} errno={err}")
        return 0 if health == probe_mod.Health.OK else 1

    if args.recover_once:
        ok = recover(cfg, runner, log)
        return 0 if ok else 1

    log(f"fuse-watchdog watching {cfg.mount_point} (device {cfg.device}, "
        f"uuid {cfg.fs_uuid}, every {cfg.poll_interval}s)")
    stats = run_loop(cfg, log, recover_fn=lambda: recover(cfg, runner, log))
    log(f"watchdog exited: {stats}")
    return 1 if stats.get("gave_up") else 0


if __name__ == "__main__":
    raise SystemExit(main())
