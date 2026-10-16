#!/usr/bin/env python3
"""Log the switches of brain-kbd-i2c (lid, and 5V as SW_DOCK) with the kernel's timestamps.

Reads the input device without grabbing it, so logind and X still get the
events. The timestamps are switched to CLOCK_REALTIME (EVIOCSCLOCKID), so
events that sat in the buffer while user space was frozen in a suspend keep
the time the kernel saw them, and can be compared with the journal.

Keys are not logged unless --keys is given (the service runs without it,
so what is typed never reaches the journal).

Usage (root): lidlog.py [--keys] [SECONDS]   (0 or none = until stopped)
"""
import fcntl, os, select, struct, sys, time

EV_KEY, EV_SW, SW_LID, SW_DOCK = 0x01, 0x05, 0x00, 0x05
EVIOCSCLOCKID = 0x400445a0          # _IOW('E', 0xa0, int)
EVIOCGSW_8 = 0x8008451b              # _IOC(READ, 'E', 0x1b, 8)
FMT = "LLHHi"                        # struct input_event on 32-bit ARM
SIZE = struct.calcsize(FMT)


def find(name):
    for d in sorted(os.listdir("/sys/class/input")):
        if not d.startswith("event"):
            continue
        try:
            with open(f"/sys/class/input/{d}/device/name") as f:
                if f.read().strip() == name:
                    return f"/dev/input/{d}"
        except OSError:
            pass
    sys.exit(f"no input device named {name}")


def stamp(sec, usec):
    return time.strftime("%H:%M:%S", time.localtime(sec)) + f".{usec:06d}"


def main():
    args = sys.argv[1:]
    keys = "--keys" in args
    args = [a for a in args if a != "--keys"]
    secs = float(args[0]) if args else 0
    path = find("brain-kbd-i2c")
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    fcntl.ioctl(fd, EVIOCSCLOCKID, struct.pack("i", time.CLOCK_REALTIME))
    sw = fcntl.ioctl(fd, EVIOCGSW_8, bytes(8))
    now = time.time()
    print(f"{stamp(int(now), int(now % 1 * 1e6))} start {path}, lid "
          f"{'closed' if sw[0] & 1 else 'open'}", flush=True)
    end = time.monotonic() + secs if secs > 0 else float("inf")
    while time.monotonic() < end:
        if not select.select([fd], [], [], 1)[0]:
            continue
        data = os.read(fd, SIZE * 64)
        for off in range(0, len(data) - SIZE + 1, SIZE):
            sec, usec, typ, code, val = struct.unpack_from(FMT, data, off)
            now = time.time()
            got = stamp(int(now), int(now % 1 * 1e6))
            if typ == EV_SW and code == SW_LID:
                print(f"{stamp(sec, usec)} lid {'closed' if val else 'opened'}"
                      f"  (read {got})", flush=True)
            elif typ == EV_SW:
                name = {SW_DOCK: "5V (dock)"}.get(code, f"switch {code}")
                print(f"{stamp(sec, usec)} {name} {'on' if val else 'off'}"
                      f"  (read {got})", flush=True)
            elif typ == EV_KEY and val != 2 and keys:
                print(f"{stamp(sec, usec)} key {code} {'down' if val else 'up'}"
                      f"  (read {got})", flush=True)
    print("end", flush=True)


main()
