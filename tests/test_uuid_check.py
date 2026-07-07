import errno
import io
import unittest

import _util  # noqa: F401
from fuse_watchdog import uuid_check as U


def make_superblock_device(uuid_hex, magic=U.EXT_MAGIC):
    """Build a fake device image: zeros up to the superblock, with magic + uuid."""
    buf = bytearray(U.UUID_ABS_OFFSET + U.UUID_LEN)
    buf[U.MAGIC_ABS_OFFSET:U.MAGIC_ABS_OFFSET + 2] = int(magic).to_bytes(2, "little")
    buf[U.UUID_ABS_OFFSET:U.UUID_ABS_OFFSET + U.UUID_LEN] = bytes.fromhex(uuid_hex)
    return bytes(buf)


def opener_for(image):
    def _open(_path, _mode):
        return io.BytesIO(image)
    return _open


class TestUuid(unittest.TestCase):
    UHEX = "9d5cd7d12ed64123ade8c807e49b7e8c"
    USTR = "9d5cd7d1-2ed6-4123-ade8-c807e49b7e8c"

    def test_parse_uuid(self):
        self.assertEqual(U.parse_uuid(bytes.fromhex(self.UHEX)), self.USTR)

    def test_parse_uuid_bad_len(self):
        with self.assertRaises(ValueError):
            U.parse_uuid(b"\x00\x01")

    def test_magic(self):
        self.assertTrue(U.superblock_is_ext4(b"\x53\xef"))
        self.assertFalse(U.superblock_is_ext4(b"\x00\x00"))

    def test_read_uuid_ok(self):
        img = make_superblock_device(self.UHEX)
        self.assertEqual(U.read_device_uuid("/dev/x", opener=opener_for(img)), self.USTR)

    def test_read_uuid_not_ext(self):
        img = make_superblock_device(self.UHEX, magic=0x1234)
        self.assertIsNone(U.read_device_uuid("/dev/x", opener=opener_for(img)))

    def test_read_uuid_device_gone(self):
        def boom(_p, _m):
            raise OSError(errno.ENXIO, "Device not configured")
        self.assertIsNone(U.read_device_uuid("/dev/x", opener=boom))

    def test_matches_true(self):
        self.assertTrue(U.uuid_matches("/dev/x", self.USTR.upper(),
                                       reader=lambda d: self.USTR))

    def test_matches_wrong_disk(self):
        self.assertFalse(U.uuid_matches("/dev/x", self.USTR,
                                        reader=lambda d: "ffffffff-0000-0000-0000-000000000000"))

    def test_matches_unreadable(self):
        self.assertFalse(U.uuid_matches("/dev/x", self.USTR, reader=lambda d: None))

    def test_matches_empty_expected(self):
        self.assertFalse(U.uuid_matches("/dev/x", "", reader=lambda d: self.USTR))


if __name__ == "__main__":
    unittest.main()
