#!/usr/bin/env python3
"""Log raw Brain keyboard codes and touch events for a while (run as root).

Unbinds brain-kbd-i2c (0-0028) so that keys missing from the DT keymap
(Bookmark, Home, Dictionary Menu, ...) are seen too, polls the keyboard MCU
over /dev/i2c-0, and reads the touch input devices. Rebinds the driver on exit.
While unbound, KEY_POWER does not reach logind, so the power key is safe to press.

Usage: sudo inputlog.py LOGFILE [SECONDS]
"""
import ctypes, fcntl, os, select, signal, struct, sys, time

LOG = open(sys.argv[1], "a")
DUR = float(sys.argv[2]) if len(sys.argv) > 2 else 600
DRV = "/sys/bus/i2c/drivers/brain-kbd-i2c"
DEV = "0-0028"
TOUCH = {"/dev/input/event0": "lradc-ts", "/dev/input/event3": "sx8654"}

I2C_SLAVE, I2C_SMBUS = 0x0703, 0x0720
I2C_SMBUS_READ, I2C_SMBUS_WORD_DATA = 1, 3


class SmbusData(ctypes.Union):
    _fields_ = [("byte", ctypes.c_uint8), ("word", ctypes.c_uint16),
                ("block", ctypes.c_uint8 * 34)]


class SmbusIoctl(ctypes.Structure):
    _fields_ = [("read_write", ctypes.c_uint8), ("command", ctypes.c_uint8),
                ("size", ctypes.c_uint32), ("data", ctypes.POINTER(SmbusData))]


def log(msg):
    LOG.write(f"{time.monotonic():10.3f} {msg}\n")
    LOG.flush()
    os.fsync(LOG.fileno())


def read_word(fd, cmd):
    d = SmbusData()
    a = SmbusIoctl(I2C_SMBUS_READ, cmd, I2C_SMBUS_WORD_DATA, ctypes.pointer(d))
    fcntl.ioctl(fd, I2C_SMBUS, a)
    return d.word & 0xff, d.word >> 8  # first byte on the wire, second byte


def desc(v):
    if v & 0x80:
        return f"switch code={(v >> 1) & 0x1f} on={int((v & 1) == 0)} raw={v:02x}"
    return f"key 0x{v & 0x3f:02x} {'down' if not v & 0x40 else 'up'} raw={v:02x}"


def rebind():
    if unbound and not os.path.exists(f"{DRV}/{DEV}"):
        with open(f"{DRV}/bind", "w") as f:
            f.write(DEV)
        log("keyboard driver rebound")


def stop(*_):
    raise SystemExit


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGHUP, stop)
touch_fds = {}
unbound = False
if not os.path.exists(f"{DRV}/{DEV}"):
    sys.exit("keyboard driver is not bound (another inputlog running?)")
try:
    with open(f"{DRV}/unbind", "w") as f:
        f.write(DEV)
    unbound = True
    log("keyboard driver unbound")
    i2c = os.open("/dev/i2c-0", os.O_RDWR)
    fcntl.ioctl(i2c, I2C_SLAVE, 0x28)
    for p, name in TOUCH.items():
        touch_fds[os.open(p, os.O_RDONLY | os.O_NONBLOCK)] = name
    log(f"ready, logging for {DUR:.0f}s")
    end = time.monotonic() + DUR
    while time.monotonic() < end:
        r, _, _ = select.select(list(touch_fds), [], [], 0.02)
        for fd in r:
            data = os.read(fd, 16 * 64)
            for i in range(0, len(data) - 15, 16):
                _, _, typ, code, val = struct.unpack_from("<IIHHi", data, i)
                if typ != 0:  # skip EV_SYN
                    log(f"touch {touch_fds[fd]} type={typ} code={code} value={val}")
        try:
            n, k1 = read_word(i2c, 0x04)
        except OSError as e:
            log(f"i2c error {e}")
            time.sleep(0.2)
            continue
        if k1 == 0 or n < 1:
            continue
        keys = [k1]
        if n >= 2:
            k2, k3 = read_word(i2c, 0x04)
            keys += [k2] + ([k3] if n >= 3 else [])
        for v in keys:
            log(desc(v))
finally:
    rebind()
    log("done")
