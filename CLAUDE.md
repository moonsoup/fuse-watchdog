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
- `fuse_watchdog/recover.py` — recovery sequence via an injected `Runner`.
- `fuse_watchdog/watchdog.py` — the poll loop (DI: probe_fn/recover_fn/sleep).
- `fuse_watchdog/config.py`, `cli.py`, `__main__.py`.
- `tests/` — 31 tests, all side effects injected (no hardware needed).

## How to run / test

```sh
python3 -m unittest discover -s tests    # tests (must pass before live use)
ruff check fuse_watchdog tests           # lint (keep clean)
sudo python3 -m fuse_watchdog --config config.json --check
```

## Status / next

MVP complete and green (2026-07-06). Not yet exercised against a live drop on
real hardware — validate once the reliable enclosure (Inateck ASM1153E) arrives,
or by deliberately yanking a test USB. See `../` migration memory for context.
