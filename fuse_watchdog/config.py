"""Watchdog configuration: load + validate JSON, build the remount command."""
import json


REQUIRED = ("mount_point", "disk", "device", "fs_uuid", "driver_path")

DEFAULTS = {
    "sentinel": None,               # defaults to mount_point
    "mount_options": "rw+,allow_other,local,no_default_permissions",
    "governor_mib": 32,             # opt-in writeback governor bound
    "poll_interval": 3.0,           # seconds between health probes
    "probe_timeout_secs": 10.0,     # bound on a single probe; wedged mount -> STALE, not a hang
    "settle": 2.0,                  # seconds to wait after unmount/remount
    "max_recover_attempts": 3,      # consecutive failed recoveries before giving up
    "log_path": None,               # None -> stderr
}


class Config:
    def __init__(self, data):
        missing = [k for k in REQUIRED if not data.get(k)]
        if missing:
            raise ValueError(f"config missing required keys: {', '.join(missing)}")
        merged = dict(DEFAULTS)
        merged.update(data)
        self._d = merged
        if not self._d.get("sentinel"):
            self._d["sentinel"] = self._d["mount_point"]

    def __getattr__(self, name):
        try:
            return self._d[name]
        except KeyError as e:
            raise AttributeError(name) from e

    def mount_command(self):
        """The argv to (re)mount: env FUSE_EXT2_WB_NORMAL_MIB=N driver dev mnt -o opts."""
        return [
            "env",
            f"FUSE_EXT2_WB_NORMAL_MIB={int(self.governor_mib)}",
            self.driver_path,
            self.device,
            self.mount_point,
            "-o",
            self.mount_options,
        ]


def load(path):
    with open(path) as f:
        return Config(json.load(f))
