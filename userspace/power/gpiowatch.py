#!/usr/bin/env python3
"""Log changes of GPIO inputs (HW_PINCTRL_DIN0..4) via /dev/mem, read-only (root).

Only pins muxed as GPIO (MUXSEL = 3) with output disabled are watched; the rest
(LCD, SAIF, SD ...) toggle all the time.

Usage: gpiowatch.py LOG SECONDS
"""
import mmap, os, struct, sys, time

fd = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
m = mmap.mmap(fd, 0x1000, mmap.MAP_SHARED, mmap.PROT_READ, offset=0x80018000)
log = open(sys.argv[1], "a")
rd = lambda o: struct.unpack_from("<I", m, o)[0]
mask = []
for b in range(5):
    mk = 0
    for p in range(32):
        mux = rd(0x100 + 0x20 * b + 0x10 * (p // 16)) >> (2 * (p % 16)) & 3
        oe = rd(0xb00 + 0x10 * b) >> p & 1
        if mux == 3 and not oe:
            mk |= 1 << p
    mask.append(mk)
def din():
    return [rd(0x900 + 0x10 * b) & mask[b] for b in range(5)]
prev = din()
log.write("%s start in=%s mask=%s\n" % (time.strftime("%T"), " ".join("%08x" % v for v in prev), " ".join("%08x" % v for v in mask))); log.flush()
end = time.monotonic() + float(sys.argv[2])
while time.monotonic() < end:
    time.sleep(0.05)
    cur = din()
    for b in range(5):
        diff = cur[b] ^ prev[b]
        for p in range(32):
            if diff >> p & 1:
                log.write("%s GPIO%d_%d=%d\n" % (time.strftime("%T"), b, p, cur[b] >> p & 1))
    if cur != prev:
        log.flush()
    prev = cur
log.write("%s end\n" % time.strftime("%T"))
