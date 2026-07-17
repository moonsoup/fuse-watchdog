"""Command-line entry point: wire the real probe/recover and run the loop.

Usage:
    sudo python3 -m fuse_watchdog --config config.json
    sudo python3 -m fuse_watchdog --config config.json --check      # one-shot health probe
    sudo python3 -m fuse_watchdog --config config.json --recover-once
    sudo python3 -m fuse_watchdog --config config.json --show-uuid  # pure diagnostic, no mount changes

Runs privileged (mount/unmount/raw-device read need root). Logs to the config's
log_path, or stderr.
"""
import argparse
import sys
import time

from . import config as config_mod
from . import probe as probe_mod
from .recover import Runner, recover
from .uuid_check import read_device_uuid_diagnostic
from .watchdog import run_loop


def make_logger(log_path, also_print=False):
    """also_print: True for one-shot interactive commands (--show-uuid,
    --check) where a human is waiting right there in the terminal for the
    answer -- writing ONLY to log_path (real incident, 2026-07-17: a human
    ran --show-uuid, got "nothing" printed, and had to be told to go check
    the log file) is the wrong default for those. The continuous watch loop
    and --recover-once keep log-only behavior unchanged -- nobody's watching
    a terminal during an unattended watch cycle."""
    def log(msg):
        line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
        if log_path:
            with open(log_path, "a") as f:
                f.write(line + "\n")
            if also_print:
                print(line, flush=True)
        else:
            print(line, file=sys.stderr, flush=True)
    return log


def main(argv=None):
    ap = argparse.ArgumentParser(description="fuse-ext2 device-drop recovery watchdog")
    ap.add_argument("--config", required=True, help="path to config JSON")
    ap.add_argument("--check", action="store_true", help="one-shot health probe, then exit")
    ap.add_argument("--recover-once", action="store_true", help="run a single recovery cycle, then exit")
    ap.add_argument("--fsck", action="store_true", help="run e2fsck before remounting (--recover-once only)")
    ap.add_argument("--show-uuid", action="store_true", help="read and print the device's actual ext4 UUID -- pure diagnostic, no unmount/remount")
    args = ap.parse_args(argv)

    cfg = config_mod.load(args.config)
    # --show-uuid/--check are one-shot commands a human runs interactively
    # and waits on -- also print to the terminal, not just log_path.
    interactive = args.show_uuid or args.check
    log = make_logger(cfg.log_path, also_print=interactive)
    runner = Runner()

    if args.show_uuid:
        # Real incident (2026-07-17): a recovery refusal only proved SOMETHING
        # was wrong, not what -- this lets a human check the raw device state
        # directly, without unmounting/remounting anything, before deciding
        # whether to trust --recover-once (or update a stale config.json).
        uuid, reason = read_device_uuid_diagnostic(cfg.device)
        log(f"show-uuid: {cfg.device} actual={uuid or 'UNREADABLE'} reason={reason} expected={cfg.fs_uuid}")
        return 0 if uuid is not None else 1

    if args.check:
        health, err = probe_mod.probe_mount(cfg.mount_point)
        log(f"health={health.value} errno={err}")
        return 0 if health == probe_mod.Health.OK else 1

    if args.recover_once:
        ok = recover(cfg, runner, log, fsck=args.fsck)
        return 0 if ok else 1

    log(f"fuse-watchdog watching {cfg.mount_point} (device {cfg.device}, "
        f"uuid {cfg.fs_uuid}, every {cfg.poll_interval}s)")
    stats = run_loop(cfg, log, recover_fn=lambda: recover(cfg, runner, log))
    log(f"watchdog exited: {stats}")
    return 1 if stats.get("gave_up") else 0


if __name__ == "__main__":
    raise SystemExit(main())
