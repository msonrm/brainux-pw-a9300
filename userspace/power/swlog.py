#!/usr/bin/env python3
"""Log switch events (SW_LID, SW_TABLET_MODE, SW_DOCK) from brain-kbd-i2c.

Usage: swlog.py LOG SECONDS   (run under `systemd-inhibit --what=handle-lid-switch`
so that logind does not suspend while testing)
"""
import os, select, struct, sys, time

SW = {0: "SW_LID", 1: "SW_TABLET_MODE", 5: "SW_DOCK"}
dev = None
for d in os.listdir("/sys/class/input"):
    if d.startswith("event"):
        try:
            if open(f"/sys/class/input/{d}/device/name").read().strip() == "brain-kbd-i2c":
                dev = f"/dev/input/{d}"
        except OSError:
            pass
log = open(sys.argv[1], "a")
fd = os.open(dev, os.O_RDONLY | os.O_NONBLOCK)
log.write(f"{time.strftime('%T')} start {dev}\n"); log.flush()
end = time.monotonic() + float(sys.argv[2])
while time.monotonic() < end:
    if not select.select([fd], [], [], 1)[0]:
        continue
    data = os.read(fd, 16 * 64)
    for i in range(0, len(data) - 15, 16):
        _, _, typ, code, val = struct.unpack_from("<IIHHi", data, i)
        if typ == 5:  # EV_SW
            log.write(f"{time.strftime('%T')} {SW.get(code, code)}={val}\n"); log.flush()
log.write(f"{time.strftime('%T')} end\n")
