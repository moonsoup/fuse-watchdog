"""Shared test doubles."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class FakeCfg:
    device = "/dev/disk9s2"
    disk = "/dev/disk9"
    fs_uuid = "9d5cd7d1-2ed6-4123-ade8-c807e49b7e8c"
    mount_point = "/mnt/x"
    sentinel = "/mnt/x"
    settle = 0
    poll_interval = 0
    max_recover_attempts = 3

    def mount_command(self):
        return ["env", "FUSE_EXT2_WB_NORMAL_MIB=32", "/drv/fuse-ext2",
                self.device, self.mount_point, "-o", "rw+"]


def is_mount_cmd(cmd):
    return bool(cmd) and cmd[0] == "env"


class FakeRunner:
    """Records every command; returns configurable rc for the mount command."""

    def __init__(self, mount_rc=0):
        self.calls = []
        self.mount_rc = mount_rc

    def run(self, cmd):
        self.calls.append(cmd)
        if is_mount_cmd(cmd):
            return self.mount_rc, "", "" if self.mount_rc == 0 else "mount error"
        return 0, "", ""

    def mount_was_issued(self):
        return any(is_mount_cmd(c) for c in self.calls)


class Log:
    def __init__(self):
        self.lines = []

    def __call__(self, msg):
        self.lines.append(msg)

    def text(self):
        return "\n".join(self.lines)
