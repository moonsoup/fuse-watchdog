"""Recovery orchestration: kill stale daemon → release device → VERIFY UUID →
remount. All side effects go through an injected `runner`, so the whole sequence
(including the safety refusal) is unit-testable without touching real hardware.

Safety invariant: the remount command is issued ONLY after the backing device is
confirmed to still carry the expected ext4 UUID. Never attach to the wrong disk.
"""
import subprocess
import time

from .uuid_check import read_device_uuid_diagnostic


class Runner:
    """Thin subprocess wrapper (the real side-effect boundary)."""

    def run(self, cmd):
        p = subprocess.run(cmd, capture_output=True, text=True)
        return p.returncode, p.stdout, p.stderr


def recover(cfg, runner, log, sleep=time.sleep, uuid_reader=None, fsck=False):
    """Attempt one recovery cycle. Returns True on a confirmed-safe remount.

    Order matters: we tear down first, then (optionally) fsck, then re-read
    the device UUID from the freshly-released device, and only remount if it
    matches. `fsck` is opt-in per-call (not persisted config) since it's a
    more invasive step than a plain remount — the caller decides per attempt.
    """
    log(f"recovery: killing stale daemon for {cfg.device}")
    runner.run(["pkill", "-9", "-f", f"fuse-ext2 {cfg.device}"])

    log(f"recovery: releasing {cfg.disk}")
    runner.run(["diskutil", "unmountDisk", "force", cfg.disk])
    sleep(cfg.settle)

    if fsck:
        log(f"recovery: running e2fsck on {cfg.device}")
        rc, _out, err = runner.run(["e2fsck", "-y", cfg.device])
        # A non-zero fsck exit does not by itself block remount -- e2fsck's
        # own exit codes include "errors corrected" (rc=1) as non-fatal; the
        # UUID gate below is what actually decides whether it's safe to
        # remount, independent of fsck's outcome.
        log(f"recovery: e2fsck exited rc={rc}" + (f" {err.strip()[:200]}" if err else ""))

    # SAFETY GATE — never remount a device that isn't provably our filesystem.
    # Real incident (2026-07-17): the refusal log used to only print the
    # EXPECTED uuid, never what was actually found or WHY the read failed --
    # making it impossible to tell from the log alone whether the drive's
    # real UUID genuinely changed (config.json is stale), the raw open threw
    # an OSError (device gone/busy), or the bytes at the expected superblock
    # offset simply weren't ext4 (wrong partition offset). `uuid_reader` (test
    # injection) keeps its original single-value shape for backward
    # compatibility with existing tests; the real path uses the diagnostic
    # reader so a live refusal is actually debuggable.
    #
    # Also real (same incident): reading the device immediately after
    # `diskutil unmountDisk force` can transiently fail with EPERM even as
    # root -- confirmed live: --show-uuid succeeded reading the SAME device
    # cleanly a few minutes after a recovery attempt's own read failed with
    # "Operation not permitted" right after teardown. Retry the READ
    # specifically (not the whole recovery cycle -- teardown already
    # happened, no need to repeat it) a few times with a short delay before
    # concluding it's genuinely unreadable, not just still settling.
    attempts = 1 + max(0, int(cfg.uuid_read_retries))
    actual_uuid, reason = None, "not-attempted"
    for attempt in range(1, attempts + 1):
        if uuid_reader is not None:
            actual_uuid, reason = uuid_reader(cfg.device), "test-injected"
        else:
            actual_uuid, reason = read_device_uuid_diagnostic(cfg.device)
        if actual_uuid is not None:
            break
        if attempt < attempts:
            log(f"recovery: UUID read attempt {attempt}/{attempts} unreadable ({reason}) -- retrying in {cfg.uuid_read_retry_delay}s")
            sleep(cfg.uuid_read_retry_delay)
    if actual_uuid is None or actual_uuid.lower() != cfg.fs_uuid.strip().lower():
        log(f"recovery: REFUSING remount — {cfg.device} actual UUID is "
            f"{actual_uuid if actual_uuid else f'UNREADABLE ({reason})'}, expected {cfg.fs_uuid} "
            f"(device missing, wrong disk, or config.json's fs_uuid is stale); "
            f"manual/hardware check needed")
        return False

    log(f"recovery: UUID verified, remounting {cfg.device} -> {cfg.mount_point}")
    rc, _out, err = runner.run(cfg.mount_command())
    sleep(cfg.settle)
    if rc != 0:
        log(f"recovery: remount command failed rc={rc} {err.strip()[:200]}")
        return False
    log("recovery: remount issued OK")
    return True
