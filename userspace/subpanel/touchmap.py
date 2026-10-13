#!/usr/bin/env python3
"""Print one line per touch stroke on both touch panels, in raw coordinates.

For mapping the printed buttons outside the displayed area. Does not grab the
devices, so X keeps moving the cursor while this runs. Each stroke shows the
press point, the settled point (median, first/last 2 samples dropped), the
bounding box and the pressure range. Also prints the ranges the kernel reports.

Usage: touchmap.py [SECONDS]   (needs read access to /dev/input/event*)
"""
import fcntl, os, select, struct, sys, time

DUR = float(sys.argv[1]) if len(sys.argv) > 1 else 300
TOUCH = {"/dev/input/event0": "sub", "/dev/input/event3": "main"}
EV_SYN, EV_KEY, EV_ABS = 0, 1, 3
ABS_X, ABS_Y, ABS_PRESSURE, BTN_TOUCH = 0, 1, 24, 0x14a


def absinfo(fd, code):
    buf = fcntl.ioctl(fd, 0x80184540 + code, bytes(24))  # EVIOCGABS(code)
    _, lo, hi, _, _, _ = struct.unpack("<6i", buf)
    return lo, hi


def median(v):
    s = sorted(v)
    return s[len(s) // 2]


def report(name, pts):
    core = pts[2:-2] if len(pts) > 6 else pts
    xs, ys = [p[0] for p in core], [p[1] for p in core]
    allx, ally = [p[0] for p in pts], [p[1] for p in pts]
    pr = [p[2] for p in pts if p[2] is not None]
    prs = f" p={min(pr)}-{max(pr)}" if pr else ""
    print(f"{name:4} n={len(pts):3} press=({pts[0][0]},{pts[0][1]}) "
          f"at=({median(xs)},{median(ys)}) "
          f"box=x{min(allx)}-{max(allx)} y{min(ally)}-{max(ally)}{prs}",
          flush=True)


fds = {}
for path, name in TOUCH.items():
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    fds[fd] = {"name": name, "x": None, "y": None, "p": None,
               "down": False, "pts": []}
    print(f"{name}: {path} x={absinfo(fd, ABS_X)} y={absinfo(fd, ABS_Y)}",
          flush=True)
print(f"ready for {DUR:.0f}s", flush=True)

end = time.monotonic() + DUR
while time.monotonic() < end:
    r, _, _ = select.select(list(fds), [], [], 0.5)
    for fd in r:
        s = fds[fd]
        data = os.read(fd, 16 * 64)
        for i in range(0, len(data) - 15, 16):
            _, _, typ, code, val = struct.unpack_from("<IIHHi", data, i)
            if typ == EV_ABS and code == ABS_X:
                s["x"] = val
            elif typ == EV_ABS and code == ABS_Y:
                s["y"] = val
            elif typ == EV_ABS and code == ABS_PRESSURE:
                s["p"] = val
            elif typ == EV_KEY and code == BTN_TOUCH:
                if val:
                    s["down"], s["pts"] = True, []
                elif s["down"]:
                    s["down"] = False
                    if s["pts"]:
                        report(s["name"], s["pts"])
            elif typ == EV_SYN and s["down"] and s["x"] is not None:
                s["pts"].append((s["x"], s["y"], s["p"]))
