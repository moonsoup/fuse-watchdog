"""Recovery orchestration: kill stale daemon → release device → VERIFY UUID →
remount. All side effects go through an injected `runner`, so the whole sequence
(including the safety refusal) is unit-testable without touching real hardware.

Safety invariant: the remount command is issued ONLY after the backing device is
confirmed to still carry the expected ext4 UUID. Never attach to the wrong disk.
"""
import subprocess
import time

from .uuid_check import uuid_matches


class Runner:
    """Thin subprocess wrapper (the real side-effect boundary)."""

    def run(self, cmd):
        p = subprocess.run(cmd, capture_output=True, text=True)
        return p.returncode, p.stdout, p.stderr


def recover(cfg, runner, log, sleep=time.sleep, uuid_reader=None):
    """Attempt one recovery cycle. Returns True on a confirmed-safe remount.

    Order matters: we tear down first, then re-read the device UUID from the
    freshly-released device, and only remount if it matches.
    """
    log(f"recovery: killing stale daemon for {cfg.device}")
    runner.run(["pkill", "-9", "-f", f"fuse-ext2 {cfg.device}"])

    log(f"recovery: releasing {cfg.disk}")
    runner.run(["diskutil", "unmountDisk", "force", cfg.disk])
    sleep(cfg.settle)

    # SAFETY GATE — never remount a device that isn't provably our filesystem.
    kwargs = {} if uuid_reader is None else {"reader": uuid_reader}
    if not uuid_matches(cfg.device, cfg.fs_uuid, **kwargs):
        log(f"recovery: REFUSING remount — {cfg.device} UUID != {cfg.fs_uuid} "
            f"(device missing or wrong disk); manual/hardware check needed")
        return False

    log(f"recovery: UUID verified, remounting {cfg.device} -> {cfg.mount_point}")
    rc, _out, err = runner.run(cfg.mount_command())
    sleep(cfg.settle)
    if rc != 0:
        log(f"recovery: remount command failed rc={rc} {err.strip()[:200]}")
        return False
    log("recovery: remount issued OK")
    return True
