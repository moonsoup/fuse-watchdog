"""fuse-watchdog — external recovery companion for fuse-ext2 on macOS.

Watches a fuse-ext2 mount for a backing-device drop (ENXIO / "Device not
configured"), and recovers it *between* filesystem operations by killing the
stale daemon, releasing the device, and remounting — but ONLY after verifying
the backing device still carries the expected ext4 filesystem UUID, so it can
never attach the wrong disk.

It is deliberately external to the driver (tier-3 "installable extension"): it
touches no in-flight writes and holds no filesystem state, so it carries none of
the write-consistency risk an in-driver reconnect would. The core driver stays
boring; this is opt-in.
"""

__version__ = "0.1.0"
