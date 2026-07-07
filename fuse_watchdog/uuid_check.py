"""Read an ext4 filesystem UUID straight from the device superblock.

This is the safety keystone: before the watchdog remounts after a device drop,
it re-reads the UUID from the backing device and refuses to remount if it does
not match the expected one — so it can NEVER attach writes to the wrong disk
(e.g. if the device node got reassigned to a different drive on re-enumeration).

We read the superblock directly (16 bytes at a fixed offset) rather than shelling
out to dumpe2fs, because dumpe2fs does not work reliably against macOS raw/block
devices. Pure parsing (parse_uuid / superblock_is_ext4) is separated from the
device read so it is unit-testable with crafted bytes.
"""

# ext4 layout: the primary superblock starts 1024 bytes into the volume.
SUPERBLOCK_OFFSET = 1024
# Fields, as byte offsets *within* the superblock:
S_MAGIC_OFFSET = 0x38      # __le16, must equal 0xEF53 for ext2/3/4
S_UUID_OFFSET = 0x68       # 16-byte s_uuid
EXT_MAGIC = 0xEF53

# Absolute device offsets:
MAGIC_ABS_OFFSET = SUPERBLOCK_OFFSET + S_MAGIC_OFFSET   # 1080
UUID_ABS_OFFSET = SUPERBLOCK_OFFSET + S_UUID_OFFSET     # 1128
UUID_LEN = 16


def parse_uuid(raw16):
    """Format 16 raw bytes as a canonical lowercase UUID string. Pure."""
    if len(raw16) != UUID_LEN:
        raise ValueError(f"expected {UUID_LEN} bytes, got {len(raw16)}")
    h = raw16.hex()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def superblock_is_ext4(magic_bytes):
    """True if the 2 little-endian magic bytes are the ext magic (0xEF53). Pure."""
    if len(magic_bytes) != 2:
        return False
    return int.from_bytes(magic_bytes, "little") == EXT_MAGIC


def read_device_uuid(device, opener=open):
    """Read the ext4 UUID from `device`, or None if it can't be read / not ext.

    `opener` is injectable for tests. Any OSError (e.g. ENXIO on a dropped
    device) yields None — caller treats "can't confirm UUID" as "do not remount".
    """
    try:
        with opener(device, "rb") as f:
            f.seek(MAGIC_ABS_OFFSET)
            magic = f.read(2)
            if not superblock_is_ext4(magic):
                return None
            f.seek(UUID_ABS_OFFSET)
            raw = f.read(UUID_LEN)
            if len(raw) != UUID_LEN:
                return None
            return parse_uuid(raw)
    except OSError:
        return None


def uuid_matches(device, expected_uuid, reader=read_device_uuid):
    """True only if the device's ext4 UUID equals `expected_uuid`. Fail-closed:
    an unreadable device or any mismatch returns False (never remount)."""
    if not expected_uuid:
        return False
    actual = reader(device)
    if actual is None:
        return False
    return actual.lower() == expected_uuid.strip().lower()
