#!/usr/bin/env python3
"""Show where the i.MX28 DC-DC takes its power from, and how often the 4P2 rail sags.

Reads the HW_POWER registers through /dev/mem (root). With 5V present, the
DC-DC runs from the DCDC_4P2 rail, which takes at most CHARGE_4P2_ILIMIT from
5V. When the load is larger, VDD4P2 sags (DCDC_4P2_BO in HW_POWER_STS) and the
rest comes from the battery. Sampling STS shows how often that happens, but
only while the brownout comparators are powered (MINPWR.PWD_BO clear).

Changes nothing (brain-5v-ilimit raises the limit).

Usage: pwrpath.py [-s SECONDS] [--load]
  -s SECONDS   sample HW_POWER_STS for this long (default 10)
  --load       run a busy loop in a child process while sampling
"""
import argparse, mmap, os, struct, subprocess, sys, time

BASE = 0x80044000
REGS = [("CTRL", 0x00), ("5VCTRL", 0x10), ("MINPWR", 0x20), ("CHARGE", 0x30),
        ("VDDDCTRL", 0x40), ("VDDACTRL", 0x50), ("VDDIOCTRL", 0x60),
        ("VDDMEMCTRL", 0x70), ("DCDC4P2", 0x80), ("MISC", 0x90),
        ("STS", 0xc0), ("BATTMONITOR", 0xe0)]
STS_BITS = {10: "DCDC_4P2_BO", 13: "BATT_BO", 4: "VDD5V_DROOP",
            6: "VDDD_BO", 7: "VDDA_BO", 8: "VDDIO_BO", 1: "VBUSVALID",
            5: "VDD5V_GT_VDDIO", 9: "DC_OK"}
SRC = {0: "4P2 regardless of BATT", 1: "4P2, BATT only when 4P2 < BATT",
       2: "higher of 4P2/BATT", 3: "higher of 4P2/BATT"}


def ilimit_ma(v):
    return sum(ma for bit, ma in enumerate((10, 20, 50, 100, 200, 400))
               if v >> bit & 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-s", type=float, default=10)
    ap.add_argument("--load", action="store_true")
    a = ap.parse_args()

    fd = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
    m = mmap.mmap(fd, 0x1000, mmap.MAP_SHARED, mmap.PROT_READ, offset=BASE)
    rd = lambda off: struct.unpack_from("<I", m, off)[0]

    for name, off in REGS:
        print(f"{name:12} {rd(off):#010x}")
    v5, d4 = rd(0x10), rd(0x80)
    il = (v5 >> 12) & 0x3f
    print(f"4P2: {'on' if d4 >> 23 & 1 else 'off'}, DC-DC may use 4P2: "
          f"{'yes' if d4 >> 22 & 1 else 'no'}, source: {SRC[d4 >> 28 & 3]}, "
          f"dropout margin {(25, 50, 100, 200)[d4 >> 30 & 3]} mV, "
          f"CMPTRIP {d4 & 0x1f}")
    print(f"5V current limit (charger + 4P2): {il:#x} = {ilimit_ma(il)} mA, "
          f"4P2/charger block {'off' if v5 >> 20 & 1 else 'on'}, battery "
          f"charger {'off' if rd(0x30) >> 16 & 1 else 'on'}")
    if rd(0x20) >> 12 & 1:
        print("MINPWR.PWD_BO is set: the brownout comparators are off, so the"
              " *_BO bits below mean nothing")
    sts = rd(0xc0)
    print("STS now:", " ".join(n for b, n in sorted(STS_BITS.items())
                               if sts >> b & 1))

    child = None
    if a.load:
        child = subprocess.Popen([sys.executable, "-c", "while 1: pass"])
    counts, n = {b: 0 for b in STS_BITS}, 0
    end = time.monotonic() + a.s
    try:
        while time.monotonic() < end:
            s = rd(0xc0)
            for b in counts:
                counts[b] += s >> b & 1
            n += 1
    finally:
        if child:
            child.kill()
    print(f"sampled STS {n} times in {a.s:.0f}s"
          f"{' with a busy loop' if a.load else ''}:")
    for b, name in sorted(STS_BITS.items()):
        print(f"  {name:15} {100 * counts[b] / n:6.2f}%")


if __name__ == "__main__":
    main()
