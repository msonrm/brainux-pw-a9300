#!/usr/bin/env python3
"""Record the raw sub panel touch (mxs-lradc-ts) for tuning the touchpad.

Records for the given seconds from the first touch and prints one line per
SYN frame: event time (s), x, y, touch (1/0). Stop subpaneld first (it grabs
the device):

    sudo systemctl stop subpaneld
    sudo python3 touchrec.py 60 > touch.log
    sudo systemctl start subpaneld
"""
import os
import re
import select
import struct
import sys
import time

EV_SYN, EV_KEY, EV_ABS = 0, 1, 3
ABS_X, ABS_Y, BTN_TOUCH = 0, 1, 0x14a
EVENT = struct.Struct("<IIHHi")  # 32-bit ARM struct input_event


def find_event(name):
    with open("/proc/bus/input/devices") as f:
        for block in f.read().split("\n\n"):
            if f'N: Name="{name}"' in block:
                return "/dev/input/" + re.search(r"\bevent\d+", block).group()
    raise SystemExit(f"no input device {name}")


def main():
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 30
    fd = os.open(find_event("mxs-lradc-ts"), os.O_RDONLY | os.O_NONBLOCK)
    x = y = touch = 0
    end = time.monotonic() + 300  # wait for the first touch at most this long
    started = False
    print(f"# {seconds:.0f} s from the first touch", file=sys.stderr, flush=True)
    while (left := end - time.monotonic()) > 0:
        if not select.select([fd], [], [], left)[0]:
            continue
        data = os.read(fd, EVENT.size * 64)
        for off in range(0, len(data), EVENT.size):
            sec, usec, typ, code, val = EVENT.unpack_from(data, off)
            if typ == EV_ABS and code == ABS_X:
                x = val
            elif typ == EV_ABS and code == ABS_Y:
                y = val
            elif typ == EV_KEY and code == BTN_TOUCH:
                touch = val
            elif typ == EV_SYN and code == 0:
                if not started:
                    if not touch:
                        continue
                    started = True
                    end = time.monotonic() + seconds
                print(f"{sec + usec / 1e6:.6f} {x} {y} {touch}")
    sys.stdout.flush()
    print("# done", file=sys.stderr)


if __name__ == "__main__":
    main()
