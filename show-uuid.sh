#!/bin/bash
# Pure read-only diagnostic: reads the actual ext4 UUID directly off the
# configured device's superblock and compares it to config.json's expected
# fs_uuid. No unmount/remount, no mount-state changes at all -- safe to run
# any time you want to know why a recovery attempt is refusing to remount
# (mismatched UUID vs. unreadable device, and if unreadable, why).
#
# Usage: sudo ./show-uuid.sh [path/to/config.json]
# Defaults to config.json in this same directory.
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG="${1:-$DIR/config.json}"

cd "$DIR"
exec python3 -m fuse_watchdog --config "$CONFIG" --show-uuid
