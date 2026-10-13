#!/usr/bin/env python3
"""Turn the sub panel touch (mxs-lradc-ts) into a touchpad and buttons, and
take the printed buttons beside the main display off its touch panel (run as root).

Grabs the sub panel touch so X no longer sees it, and feeds a uinput mouse instead.
- Displayed area: relative pointer. Tap = left click, long press = right click.
- Printed buttons on the right edge: volume up/down (ALSA "Speaker"),
  backlight (cycles the main display brightness, the sub panel follows),
  clear (Esc).
- Main display (SX8654): also grabbed. A touch that starts on the display is
  passed on unchanged through a uinput touchscreen, so X calibrates it as
  before. A touch that starts on the printed buttons left and right of the
  display is taken as that button (MAIN_KEYS): the left column sends
  Home / Page Up / Page Down / End, the right column is not assigned yet.
- A narrow strip at the right edge of the sub panel shows the volume, the
  brightness and the battery, each next to its printed button.
Needs uinput.ko (kernel/uinput). Raw coordinates are in docs/subpanel.md.
The sub panel only shows anything once X stops holding card1 (docs/subpanel.md).

Usage: subpaneld.py [-v]
"""
import fcntl, mmap, os, re, select, signal, struct, subprocess, sys, time

TOUCH = "mxs-lradc-ts"                  # input device names
MAIN_TOUCH = "SX8654 I2C Touchscreen"
FB = "/dev/fb1"
BACKLIGHT = "/sys/class/backlight/backlight@0"        # main display, 0-7
SUB_BACKLIGHT = "/sys/class/backlight/backlight@1"    # sub panel, 0-3
BRIGHTNESS_STEPS = [7, 5, 3, 1]
SUB_BRIGHTNESS = {7: 3, 5: 2, 3: 1, 1: 1}            # sub panel follows the main one
VOLUME_STEP = 2
VOLUME_MAX = 27
STATUS_POLL = 30                     # seconds between battery/volume checks
VERBOSE = "-v" in sys.argv

# Raw coordinates of the sub panel: displayed area is x 356-3435, the button
# column is right of BUTTON_X; buttons split by y (top = large y). The
# volume/backlight/clear limits are the printed edges (display y 62 and 93),
# up/down splits the volume button halfway between the taps.
BUTTON_X = 3550
BUTTONS = [(2960, "volume_up"), (2130, "volume_down"), (1350, "backlight"),
           (-1, "clear")]
RAW_PER_PX = 3080 / 240            # raw units per sub panel pixel
SKIP = 2                            # samples dropped at press and release
START = 4                           # sub panel px from the press point before moving
# pointer gain (screen px per sub panel px) by finger speed (sub panel px/s)
SLOW, SLOW_GAIN = 30, 1.0
FAST, FAST_GAIN = 300, 3.0
# Main display, raw: the display is x 237-3627 (X calibration); printed
# buttons are left of MAIN_LEFT_X and right of MAIN_RIGHT_X (the display edges),
# split by y.
MAIN_LEFT_X, MAIN_RIGHT_X = 237, 3627
MAIN_LEFT = [(3000, "prev_heading"), (2000, "page_up"), (1050, "page_down"),
             (-1, "next_heading")]          # 前見出 ↑ ↓ 次見出
MAIN_RIGHT = [(3450, "handwriting"), (2960, "kana_keys"), (2460, "memo"),
              (1950, "back"), (1400, "enter"), (790, "text_larger"),
              (-1, "text_smaller")]         # 手書き大 50音キー 暗記メモ 戻る 検索/決定 文字大 小
TAP_TIME = 0.35
LONG_TIME = 0.6

EV_SYN, EV_KEY, EV_REL, EV_ABS = 0, 1, 2, 3
ABS_X, ABS_Y, BTN_TOUCH = 0, 1, 0x14a
REL_X, REL_Y = 0, 1
BTN_LEFT, BTN_RIGHT, KEY_ESC = 0x110, 0x111, 1
KEY_HOME, KEY_PAGEUP, KEY_END, KEY_PAGEDOWN = 102, 104, 107, 109
# main display buttons that send a key (the others are not assigned yet)
MAIN_KEYS = {"prev_heading": KEY_HOME, "page_up": KEY_PAGEUP,
             "page_down": KEY_PAGEDOWN, "next_heading": KEY_END}
EVIOCGRAB = 0x40044590
UI_SET_EVBIT, UI_SET_KEYBIT, UI_SET_RELBIT = 0x40045564, 0x40045565, 0x40045566
UI_SET_ABSBIT, UI_SET_PROPBIT = 0x40045567, 0x4004556e
INPUT_PROP_DIRECT = 1
UI_DEV_CREATE, UI_DEV_DESTROY = 0x5501, 0x5502


def log(msg):
    if VERBOSE:
        print(f"{time.monotonic():9.3f} {msg}", flush=True)


class Mouse:
    def __init__(self):
        self.fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
        for ev in (EV_SYN, EV_KEY, EV_REL):
            fcntl.ioctl(self.fd, UI_SET_EVBIT, ev)
        for key in (BTN_LEFT, BTN_RIGHT, KEY_ESC, *MAIN_KEYS.values()):
            fcntl.ioctl(self.fd, UI_SET_KEYBIT, key)
        for rel in (REL_X, REL_Y):
            fcntl.ioctl(self.fd, UI_SET_RELBIT, rel)
        # struct uinput_user_dev: name[80], input_id (bustype=BUS_VIRTUAL),
        # ff_effects_max, absmax/absmin/absfuzz/absflat[64]
        dev = struct.pack("<80s4HI", b"Brain sub panel touchpad", 6, 0, 0, 1, 0)
        os.write(self.fd, dev + bytes(4 * 64 * 4))
        fcntl.ioctl(self.fd, UI_DEV_CREATE)
        self.rx = self.ry = 0.0

    def emit(self, typ, code, val):
        os.write(self.fd, struct.pack("<IIHHi", 0, 0, typ, code, val))

    def move(self, dx, dy):
        self.rx += dx
        self.ry += dy
        ix, iy = int(self.rx), int(self.ry)
        if ix or iy:
            self.rx -= ix
            self.ry -= iy
            self.emit(EV_REL, REL_X, ix)
            self.emit(EV_REL, REL_Y, iy)
            self.emit(EV_SYN, 0, 0)

    def click(self, code):
        for val in (1, 0):
            self.emit(EV_KEY, code, val)
            self.emit(EV_SYN, 0, 0)

    def close(self):
        fcntl.ioctl(self.fd, UI_DEV_DESTROY)
        os.close(self.fd)


def find_event(name):
    """/dev/input/eventN of the input device with this name."""
    with open("/proc/bus/input/devices") as f:
        for block in f.read().split("\n\n"):
            if f'N: Name="{name}"' in block:
                return "/dev/input/" + re.search(r"\bevent\d+", block).group()
    raise SystemExit(f"no input device {name}")


class Touchscreen:
    """uinput copy of the main display touch panel (raw 0-4095, like SX8654)."""

    def __init__(self):
        self.fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
        for ev in (EV_SYN, EV_KEY, EV_ABS):
            fcntl.ioctl(self.fd, UI_SET_EVBIT, ev)
        fcntl.ioctl(self.fd, UI_SET_KEYBIT, BTN_TOUCH)
        for ax in (ABS_X, ABS_Y):
            fcntl.ioctl(self.fd, UI_SET_ABSBIT, ax)
        fcntl.ioctl(self.fd, UI_SET_PROPBIT, INPUT_PROP_DIRECT)
        absmax = [0] * 64
        absmax[ABS_X] = absmax[ABS_Y] = 4095
        dev = struct.pack("<80s4HI", b"Brain main panel touchscreen", 6, 0, 0, 1, 0)
        os.write(self.fd, dev + struct.pack("<64i", *absmax) + bytes(3 * 64 * 4))
        fcntl.ioctl(self.fd, UI_DEV_CREATE)

    def send(self, events):
        os.write(self.fd, b"".join(struct.pack("<IIHHi", 0, 0, t, c, v)
                                   for t, c, v in events + [(EV_SYN, 0, 0)]))

    def close(self):
        fcntl.ioctl(self.fd, UI_DEV_DESTROY)
        os.close(self.fd)


class MainPanel:
    """Pass display touches on; turn touches on the printed buttons into actions."""

    def __init__(self, ts, mouse):
        self.ts = ts
        self.mouse = mouse
        self.frame = []
        self.x = self.y = None
        self.kind = None       # None (not touched), "screen", "left" or "right"
        self.pts = []

    def event(self, typ, code, val):
        if typ != EV_SYN:
            self.frame.append((typ, code, val))
            if typ == EV_ABS and code == ABS_X:
                self.x = val
            elif typ == EV_ABS and code == ABS_Y:
                self.y = val
            return
        frame, self.frame = self.frame, []
        touch = [v for t, c, v in frame if t == EV_KEY and c == BTN_TOUCH]
        if touch and touch[-1] and self.x is not None:
            self.kind = ("left" if self.x < MAIN_LEFT_X else
                         "right" if self.x > MAIN_RIGHT_X else "screen")
            self.pts = []
            if self.kind != "screen":
                log(f"main {self.kind} at ({self.x},{self.y})")
        if self.kind in (None, "screen"):
            if frame:
                self.ts.send(frame)
        elif self.y is not None:
            self.pts.append((self.x, self.y))
        if touch and not touch[-1]:
            if self.kind in ("left", "right"):
                self.button()
            self.kind = None

    def button(self):
        # SX8654 jumps a lot just before release: use the median of the middle
        core = self.pts[2:-2] if len(self.pts) > 6 else self.pts
        if not core:
            return
        y = sorted(p[1] for p in core)[len(core) // 2]
        side = MAIN_LEFT if self.kind == "left" else MAIN_RIGHT
        name = next(n for limit, n in side if y > limit)
        key = MAIN_KEYS.get(name)
        log(f"main button {name} (y={y}, n={len(self.pts)})"
            f"{f' -> key {key}' if key else ', not assigned'}")
        if key:
            self.mouse.click(key)


def volume(delta):
    sign = "+" if delta > 0 else "-"
    subprocess.run(["amixer", "-q", "sset", "Speaker", f"{abs(delta)}{sign}"])


def cycle_backlight():
    with open(f"{BACKLIGHT}/brightness") as f:
        cur = int(f.read())
    nxt = next((s for s in BRIGHTNESS_STEPS if s < cur), BRIGHTNESS_STEPS[0])
    with open(f"{BACKLIGHT}/brightness", "w") as f:
        f.write(str(nxt))
    with open(f"{SUB_BACKLIGHT}/brightness", "w") as f:
        f.write(str(SUB_BRIGHTNESS[nxt]))
    return nxt


# --- the status strip on the sub panel (240x120, 4 grays) -------------------
# Display y of the printed buttons, read off a photo: the volume button starts
# above the display, volume/backlight meet at y 62, backlight/clear at 93,
# clear ends at the bottom. Each band stays inside its button.
W, H = 240, 120
WHITE, LIGHT, DARK, BLACK = b"\xff\xff\xff\x00", b"\xaa\xaa\xaa\x00", \
    b"\x55\x55\x55\x00", b"\x00\x00\x00\x00"
STRIP_X = 231                        # strip is x 231-239
VOL_Y = (0, 56)                      # inclusive
BL_Y = (67, 87)
BATT_Y = (99, 111)                   # the icon, in the clear button
PLUG_Y = 114                         # plug below it (to the last row) on 5V
PLUG = [".#.#.", ".#.#.", "#####", "#####", ".###.", "..#.."]
FBIOGET_VSCREENINFO, FBIOPUT_VSCREENINFO = 0x4600, 0x4601
FB_ACTIVATE_FORCE = 128


class Panel:
    def __init__(self):
        self.fd = os.open(FB, os.O_RDWR)
        var = bytearray(160)
        fcntl.ioctl(self.fd, FBIOGET_VSCREENINFO, var)
        var[84:88] = FB_ACTIVATE_FORCE.to_bytes(4, "little")  # .activate
        try:
            fcntl.ioctl(self.fd, FBIOPUT_VSCREENINFO, var)
        except OSError as e:  # EBUSY while X holds card1; fine if already enabled
            log(f"modeset: {e}")
        self.buf = bytearray(WHITE * (W * H))

    def rect(self, x0, y0, x1, y1, color):
        """Fill x0..x1, y0..y1 (inclusive)."""
        row = color * (x1 - x0 + 1)
        for y in range(y0, y1 + 1):
            o = (y * W + x0) * 4
            self.buf[o:o + len(row)] = row

    def shade(self, x0, y0, x1, y1):
        """Fill with a checkerboard of the two grays (between LIGHT and DARK)."""
        for y in range(y0, y1 + 1):
            a, b = (LIGHT, DARK) if y % 2 else (DARK, LIGHT)
            row = (a + b) * ((x1 - x0 + 2) // 2)
            o = (y * W + x0) * 4
            self.buf[o:o + (x1 - x0 + 1) * 4] = row[:(x1 - x0 + 1) * 4]

    def pattern(self, x0, y0, rows, color):
        """Draw rows of '#' (color) and '.' (left alone)."""
        for dy, r in enumerate(rows):
            for dx, c in enumerate(r):
                if c == "#":
                    self.rect(x0 + dx, y0 + dy, x0 + dx, y0 + dy, color)

    def frame(self, x0, y0, x1, y1, color):
        self.rect(x0, y0, x1, y0, color)
        self.rect(x0, y1, x1, y1, color)
        self.rect(x0, y0, x0, y1, color)
        self.rect(x1, y0, x1, y1, color)

    def flush(self):
        t = time.monotonic()
        os.pwrite(self.fd, self.buf, 0)
        log(f"flush {1000 * (time.monotonic() - t):.0f}ms")


def draw_status(panel, vol, level, bars, usb):
    x0, x1 = STRIP_X + 1, W - 2
    panel.rect(STRIP_X, 0, W - 1, H - 1, WHITE)
    # volume: a bar from the bottom of the volume band, gray behind it
    top, bot = VOL_Y
    panel.shade(x0, top, x1, bot)
    h = round((bot - top + 1) * vol / VOLUME_MAX)
    if h:
        panel.rect(x0, bot - h + 1, x1, bot, BLACK)
    # brightness: 4 blocks stacked from the bottom of the backlight band
    top, bot = BL_Y
    panel.rect(x0, top, x1, bot, LIGHT)
    for i in range(4):
        y1 = bot - 1 - i * 5
        panel.rect(x0 + 1, y1 - 3, x1 - 1, y1, BLACK if i < level else WHITE)
    # battery: an upright cell with a nub, 3 bars inside, a cross when empty
    top, bot = BATT_Y
    panel.rect(x0 + 2, top, x1 - 2, top, BLACK)               # nub
    panel.frame(x0, top + 1, x1, bot, BLACK)
    if bars:
        for i in range(3):
            y1 = bot - 2 - i * 3
            panel.rect(x0 + 2, y1 - 1, x1 - 2, y1, BLACK if i < bars else WHITE)
    else:
        y0 = (top + 2 + bot - 1) // 2 - 2                     # 5x5 cross, centred
        for r in range(5):
            panel.rect(x0 + 1 + r, y0 + r, x0 + 1 + r, y0 + r, BLACK)
            panel.rect(x1 - 1 - r, y0 + r, x1 - 1 - r, y0 + r, BLACK)
    if usb:
        panel.pattern(x0 + 1, PLUG_Y, PLUG, BLACK)
    panel.flush()


def read_volume():
    out = subprocess.run(["amixer", "sget", "Speaker"], capture_output=True,
                         text=True).stdout
    m = re.search(r"Playback (\d+) \[", out)
    return int(m.group(1)) if m else 0


def read_level():
    with open(f"{BACKLIGHT}/brightness") as f:
        cur = int(f.read())
    return sum(1 for s in BRIGHTNESS_STEPS if cur >= s)


def read_reg(base, off, n=1):
    """Read a 32-bit register n times, 1 ms apart, through /dev/mem."""
    fd = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
    try:
        m = mmap.mmap(fd, 0x1000, mmap.MAP_SHARED, mmap.PROT_READ, offset=base)
        reads = []
        for i in range(n):
            if i:
                time.sleep(0.001)
            reads.append(struct.unpack_from("<I", m, off)[0])
        m.close()
    finally:
        os.close(fd)
    return reads


def battery_bars():
    """Bars from the battery watch pins (HW_PINCTRL_DIN4), 0 = empty.

    The pins read 0 as the cells run down: GPIO4_8 low = empty, GPIO4_7 low =
    1 bar, GPIO4_4 low = 2 bars, else 3 (alkaline cells; GPIO4_6 is not used).
    They flicker, so each pin takes the majority of 5 reads 1 ms apart.
    """
    reads = read_reg(0x80018000, 0x940, 5)
    low = lambda b: sum((d >> b) & 1 for d in reads) < 3
    if low(8):
        return 0
    if low(7):
        return 1
    if low(4):
        return 2
    return 3


def on_usb():
    """5V from USB or the OTG hub: HW_POWER_STS VBUSVALID.

    Not the LRADC (iio): reading it while the touch panel samples can leave
    the touch panel stuck (docs/subpanel.md).
    """
    return bool(read_reg(0x80044000, 0xc0)[0] & 0x2)


class Status:
    def __init__(self):
        try:
            self.panel = Panel()
        except OSError as e:
            log(f"sub panel not available: {e}")
            self.panel = None
        self.next_poll = 0 if self.panel else float("inf")
        self.shown = None
        self.bars = self.last_bars = None
        self.usb = False

    def poll_power(self):
        """Change the battery shown only when two polls in a row agree."""
        bars = battery_bars()
        if self.bars is None or bars == self.last_bars:
            self.bars = bars
        self.last_bars = bars
        self.usb = on_usb()

    def update(self, now, force=False):
        if not self.panel or not (force or now >= self.next_poll):
            return
        if now >= self.next_poll:
            self.next_poll = now + STATUS_POLL
            self.poll_power()
        cur = (read_volume(), read_level(), self.bars, self.usb)
        if cur != self.shown:
            log("status vol={} level={} bars={} usb={}".format(*cur))
            draw_status(self.panel, *cur)
            self.shown = cur


def button_at(y):
    return next(name for limit, name in BUTTONS if y > limit)


class Stroke:
    """One touch from press to release."""

    def __init__(self, now):
        self.start = now
        self.pts = []          # raw (x, y, time) samples
        self.kind = None       # "pad" or "button", decided after SKIP samples
        self.anchor = None     # smoothed point where the stroke settled
        self.last = None       # smoothed point last turned into motion
        self.moving = False
        self.long_done = False


def smoothed(pts, k):
    """Median of samples k-1..k+1 (raw x, y), and the time of sample k."""
    win = pts[k - 1:k + 2]
    xs = sorted(p[0] for p in win)
    ys = sorted(p[1] for p in win)
    return xs[1], ys[1], pts[k][2]


def gain(speed):
    if speed <= SLOW:
        return SLOW_GAIN
    if speed >= FAST:
        return FAST_GAIN
    return SLOW_GAIN + (FAST_GAIN - SLOW_GAIN) * (speed - SLOW) / (FAST - SLOW)


def on_sample(st, x, y, t, mouse):
    st.pts.append((x, y, t))  # t: event time, only for speed
    n = len(st.pts)
    if n <= SKIP:
        return
    if st.kind is None:
        st.kind = "button" if x >= BUTTON_X else "pad"
        log(f"stroke {st.kind} at ({x},{y})")
    # look SKIP samples behind, so the jump at release is never used
    k = n - 1 - SKIP
    if st.kind != "pad" or k < SKIP + 1:
        return
    p = smoothed(st.pts, k)
    if st.anchor is None:
        st.anchor = st.last = p
        return
    if not st.moving:
        dist = max(abs(p[0] - st.anchor[0]), abs(p[1] - st.anchor[1]))
        if dist < START * RAW_PER_PX:
            return
        st.moving = True
        st.last = p
        log("moving")
        return
    dx = (p[0] - st.last[0]) / RAW_PER_PX
    dy = (st.last[1] - p[1]) / RAW_PER_PX  # raw y grows upward
    dt = max(p[2] - st.last[2], 0.001)
    st.last = p
    g = gain((dx * dx + dy * dy) ** 0.5 / dt)
    mouse.move(dx * g, dy * g)


def on_release(st, now, mouse, status):
    if not st.pts:
        return
    if st.kind is None:  # too short to decide while touching
        st.kind = "button" if st.pts[0][0] >= BUTTON_X else "pad"
    log(f"release {st.kind} n={len(st.pts)} {now - st.start:.3f}s")
    if st.kind == "pad":
        if not st.long_done and not st.moving and now - st.start < TAP_TIME:
            mouse.click(BTN_LEFT)
            log("tap -> left click")
    elif st.kind == "button":
        core = st.pts[SKIP:-SKIP] or st.pts
        y = sorted(p[1] for p in core)[len(core) // 2]
        name = button_at(y)
        log(f"button {name} (y={y})")
        if name == "volume_up":
            volume(VOLUME_STEP)
        elif name == "volume_down":
            volume(-VOLUME_STEP)
        elif name == "backlight":
            log(f"brightness {cycle_backlight()}")
        elif name == "clear":
            mouse.click(KEY_ESC)
        status.update(now, force=True)


def check_long(st, now, mouse):
    if (st and st.kind == "pad" and not st.long_done
            and not st.moving and now - st.start >= LONG_TIME):
        st.long_done = True
        mouse.click(BTN_RIGHT)
        log("long press -> right click")


def main():
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    touch = os.open(find_event(TOUCH), os.O_RDONLY | os.O_NONBLOCK)
    fcntl.ioctl(touch, EVIOCGRAB, 1)
    mouse = Mouse()
    ts = Touchscreen()
    main_touch = os.open(find_event(MAIN_TOUCH), os.O_RDONLY | os.O_NONBLOCK)
    fcntl.ioctl(main_touch, EVIOCGRAB, 1)
    main_panel = MainPanel(ts, mouse)
    status = Status()
    log("ready")
    x = y = None
    st = None
    try:
        while True:
            # wake often only while touched (long press); else at the next poll
            wait = 0.05 if st else min(3600, max(0.05, status.next_poll - time.monotonic()))
            r, _, _ = select.select([touch, main_touch], [], [], wait)
            now = time.monotonic()
            if main_touch in r:
                data = os.read(main_touch, 16 * 64)
                for i in range(0, len(data) - 15, 16):
                    main_panel.event(*struct.unpack_from("<HHi", data, i + 8))
            if touch in r:
                data = os.read(touch, 16 * 64)
                for i in range(0, len(data) - 15, 16):
                    sec, usec, typ, code, val = struct.unpack_from("<IIHHi", data, i)
                    if typ == EV_ABS and code == ABS_X:
                        x = val
                    elif typ == EV_ABS and code == ABS_Y:
                        y = val
                    elif typ == EV_KEY and code == BTN_TOUCH:
                        if val:
                            st = Stroke(now)
                        elif st:
                            on_release(st, now, mouse, status)
                            st = None
                    elif typ == EV_SYN and st and x is not None:
                        on_sample(st, x, y, sec + usec / 1e6, mouse)
            check_long(st, now, mouse)
            status.update(now)
    finally:
        mouse.close()
        ts.close()


if __name__ == "__main__":
    main()
