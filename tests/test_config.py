import json
import os
import tempfile
import unittest

import _util  # noqa: F401
from fuse_watchdog.config import Config, load

GOOD = {
    "mount_point": "/Users/isme/DockProjects",
    "disk": "/dev/disk4",
    "device": "/dev/disk4s2",
    "fs_uuid": "9d5cd7d1-2ed6-4123-ade8-c807e49b7e8c",
    "driver_path": "/drv/fuse-ext2",
}


class TestConfig(unittest.TestCase):
    def test_missing_required(self):
        for key in ("mount_point", "disk", "device", "fs_uuid", "driver_path"):
            d = dict(GOOD)
            del d[key]
            with self.assertRaises(ValueError):
                Config(d)

    def test_defaults_and_sentinel(self):
        c = Config(dict(GOOD))
        self.assertEqual(c.sentinel, GOOD["mount_point"])  # defaults to mount_point
        self.assertEqual(c.governor_mib, 32)
        self.assertEqual(c.max_recover_attempts, 3)

    def test_mount_command(self):
        c = Config(dict(GOOD, governor_mib=16, mount_options="rw+,local"))
        cmd = c.mount_command()
        self.assertEqual(cmd[0], "env")
        self.assertIn("FUSE_EXT2_WB_NORMAL_MIB=16", cmd)
        self.assertIn("/dev/disk4s2", cmd)
        self.assertIn("/Users/isme/DockProjects", cmd)
        self.assertEqual(cmd[-2], "-o")
        self.assertEqual(cmd[-1], "rw+,local")

    def test_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "c.json")
            with open(p, "w") as f:
                json.dump(GOOD, f)
            c = load(p)
            self.assertEqual(c.device, "/dev/disk4s2")


if __name__ == "__main__":
    unittest.main()
