# fuse-watchdog

- **Category**: personal
- **Path**: `/Users/isme/Software/Drivers/fuse-watchdog` (sibling of `fuse-ext2/` inside Drivers/)
- **GitHub**: not yet — gets its own repo on moonsoup when published (per repo policy)

## What it is

External recovery companion for fuse-ext2 on macOS: watches a mount, and on a
backing-device drop (`ENXIO`) recovers it by kill-daemon → release → **verify
ext4 UUID** → remount. Tier-3 "installable extension" — NOT part of the driver;
no in-flight-write risk. Productized from `../scratchpad`-style recovery scripts.

## Safety invariant (do not weaken)

Never remount a device whose ext4 UUID (read from the superblock at offset 1128)
doesn't match the configured `fs_uuid`. `recover()` gates the mount command on
`uuid_check.uuid_matches`, fail-closed. Test: `test_recover.py::test_refuses_wrong_disk`.

## Layout

- `fuse_watchdog/probe.py` — mount health classification (pure `classify_errno`
  + `probe_mount` using st_dev mount-detection + a forced listdir to surface drops).
- `fuse_watchdog/uuid_check.py` — read/parse ext4 UUID from the raw device (pure
  parse + injectable reader).
- `fuse_watchdog/recover.py` — recovery sequence via an injected `Runner`; takes an opt-in
  `fsck` flag (runs `e2fsck -y` after unmount, before the UUID gate — never bypasses it).
- `fuse_watchdog/watchdog.py` — the poll loop (DI: probe_fn/recover_fn/sleep).
- `fuse_watchdog/config.py`, `cli.py` (`--recover-once --fsck`), `__main__.py`.
- `tests/` — 41 tests, all side effects injected (no hardware needed).

## How to run / test

```sh
python3 -m unittest discover -s tests    # tests (must pass before live use)
ruff check fuse_watchdog tests           # lint (keep clean)
sudo python3 -m fuse_watchdog --config config.json --check
```

## Status / next

MVP complete and green (2026-07-06). The original flaky-dock trigger this tool
was built for (a JMicron Bulk-Only-Transport bridge dropping the link under
load) is resolved: the Inateck ASM1153E (UASP) enclosure has been in use for
~2 weeks as of 2026-07-17 and that specific drop pattern has not recurred.

**Open, separate incident (2026-07-17)**: the DockProjects mount still dropped
(`ENXIO`) overnight on the *new* enclosure, staying dead for several hours and
causing real projectMan instability. Since the known JMicron-bridge cause is
already fixed, this is presumed a **different** root cause, not yet
identified — do not assume it's the old flaky-dock pattern. Follow-up
diagnostic work (separate from this repo's own code) should check what's
actually behind `/dev/disk4` now, whether the drop correlates with system
load/power events, and whether it's a repeat occurrence, before concluding
anything about the new hardware.

Being integrated into projectMan as an observe-only plugin (poll + surface
status + human-triggered remount with an optional `--fsck` step) — see
projectMan's own plan doc for that work. This tool itself remains the one
place that actually performs privileged recovery; projectMan's engine only
triggers it, never reimplements it.
