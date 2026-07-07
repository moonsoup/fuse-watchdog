# fuse-watchdog

> ⚠️ **Not for normal use.** This tool was built specifically to work around a
> **flaky USB drive dock** (a JMicron Bulk-Only-Transport bridge) that kept
> dropping off the bus on macOS and wedging fuse-ext2 mounts mid-operation. It is
> a **workaround for bad hardware, not a general-purpose component.** If your dock
> or enclosure is reliable (e.g. an ASMedia/UASP or Thunderbolt unit), you do not
> need this and should not run it. The correct fix for a dropping dock is to
> **replace the hardware.** Install this only if you're stuck on a flaky enclosure
> and want unattended remount-on-drop in the meantime.

An **optional, external recovery companion** for [fuse-ext2](https://github.com/moonsoup/fuse-ext2) on macOS.

It watches a fuse-ext2 mount and, when the backing device drops off the bus
(`ENXIO` — *"Device not configured"*), automatically recovers the mount:

```
kill stale daemon  →  release device (diskutil unmountDisk force)
                   →  VERIFY the ext4 UUID still matches  →  remount
```

It is **not part of the driver.** It's a tier‑3 "installable extension": a
userspace supervisor that touches no in‑flight writes and holds no filesystem
state, so it carries none of the write‑consistency risk an in‑driver reconnect
would. The core driver stays boring; you install this only if you're on flaky
removable hardware (USB docks/dongles) and want unattended recovery.

## Why it exists

fuse-ext2 mounts of USB-docked drives can wedge when the enclosure's USB‑SATA
bridge drops the link under sustained load (common with JMicron Bulk‑Only‑Transport
docks on macOS). The daemon survives but its device handle is dead, so every op
returns `ENXIO` until you manually kill it, release the device, and remount. This
tool does that loop for you — safely.

## The safety invariant

**It will never remount the wrong disk.** After tearing down the stale mount it
re-reads the ext4 filesystem UUID *directly from the device superblock* (16 bytes
at offset 1128) and **refuses to remount unless it matches the configured
`fs_uuid`.** If the device is gone, or a *different* disk now occupies that device
node, the UUID won't match and it declines — logging loudly for a human. This is
covered by `tests/test_recover.py::test_refuses_wrong_disk`.

It also only ever acts *between* filesystem operations (it polls, it doesn't
intercept I/O), so it cannot corrupt an in‑flight write.

## Install

Requires Python 3 (stdlib only) and must run as root (mount/unmount and raw
device reads need it).

```sh
cp config.example.json config.json      # then edit for your mount
sudo python3 -m fuse_watchdog --config config.json --check        # one-shot health probe
sudo python3 -m fuse_watchdog --config config.json --recover-once # single recovery cycle
sudo python3 -m fuse_watchdog --config config.json                # run the watch loop
```

To run it continuously, install the LaunchDaemon:

```sh
sudo cp launchd/com.moonsoup.fuse-watchdog.plist /Library/LaunchDaemons/
# edit the plist paths to match your checkout + config
sudo launchctl load /Library/LaunchDaemons/com.moonsoup.fuse-watchdog.plist
```

## Configuration (`config.json`)

| key | meaning |
|---|---|
| `mount_point` | the fuse-ext2 mount to watch (e.g. `~/DockProjects`) |
| `disk` | whole-disk node to release, e.g. `/dev/disk4` |
| `device` | partition node the fs lives on, e.g. `/dev/disk4s2` |
| `fs_uuid` | **the ext4 UUID to require before remounting** (safety) |
| `driver_path` | path to the `fuse-ext2` binary |
| `mount_options` | `-o` options for the remount |
| `governor_mib` | opt-in writeback governor bound (`FUSE_EXT2_WB_NORMAL_MIB`) |
| `poll_interval` | seconds between health probes |
| `settle` | seconds to wait after unmount/remount |
| `max_recover_attempts` | consecutive failed recoveries before giving up |
| `log_path` | log file, or `null` for stderr |

Find your `fs_uuid` after formatting (`mke2fs` prints `Filesystem UUID:`), or read
it back with `--check` once mounted.

## Limitations (honest)

- It recovers the **mount**, not the one in‑flight operation that hit the drop —
  that op still fails; the *next* one (or a resumable `rsync`) continues.
- If the hardware is truly failing (repeated drops), it gives up after
  `max_recover_attempts` and asks for a human. **It is a mitigation, not a fix for
  bad hardware** — replace the flaky enclosure.
- macOS-only (uses `diskutil`; raw superblock read is ext4-specific).

## Tests

```sh
python3 -m unittest discover -s tests
```

All side effects are injected, so the full recovery flow — including the
wrong-disk refusal and simulated `ENXIO` drops — is tested with **no real
hardware**.
