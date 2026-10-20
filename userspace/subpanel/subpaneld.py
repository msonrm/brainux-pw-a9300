#!/usr/bin/env python3
"""Turn the sub panel touch (mxs-lradc-ts) into a touchpad and buttons, and
take the printed buttons beside the main display off its touch panel (run as root).

Grabs the sub panel touch so X no longer sees it, and feeds a uinput mouse instead.
- Displayed area: relative pointer. Tap = left click, long press = right click.
- Printed buttons on the right edge: volume up/down (ALSA "Speaker", or
  "Headphone" while something is plugged into the jack, one of 16 steps),
  backlight (cycles the main display brightness, the sub panel follows),
  clear (Esc).
- Main display (SX8654): also grabbed. A touch that starts on the display is
  passed on unchanged through a uinput touchscreen, so X calibrates it as
  before. A touch that starts on the printed buttons left and right of the
  display is taken as that button (MAIN_KEYS): the left column sends
  Home / Page Up / Page Down / End, the right column is not assigned yet.
- A narrow strip at the right edge of the sub panel shows the volume (with a
  speaker or headphone icon for the output in use, struck through at 0), the
  brightness and the battery, each next to its printed button. Plugging or
  unplugging the headphones redraws it at once.
- Power key (入/切): while it is held, a ring fills on the sub panel in the
  5 s logind waits before powering off (HandlePowerKeyLongPress). Let go
  early and the ring runs back, a moon shows, and this asks for the suspend
  (logind leaves the short press alone: HandlePowerKey=ignore, so the
  suspend never starts before the moon). For a few seconds after waking,
  logind refuses a suspend, or takes it and nothing happens (the last one is
  still finishing), so this asks again until brain-subpanel-sleep says the
  suspend has begun.
  The moon fills the panel and stays while asleep (the panel keeps its
  picture with the backlight off); volume and battery are hidden then, as
  they would be stale. Any suspend (lid too) draws the moon through
  brain-subpanel-sleep (SIGUSR1 before, SIGUSR2 after waking, which brings
  the normal picture back).
- Apps (APP_SOCK): an app that plays with the lid closed (a music player,
  through headphones) asks over a Unix socket, line by line: "keep-awake 1" / "0".
  While any connected app asks, this holds logind's handle-lid-switch block
  inhibitor (an ordinary user is refused one: Brainux has no polkit), and the
  lid closing turns both backlights off until it opens. When the app lets go
  (or goes away) with the lid closed, logind sleeps then. The battery
  running out (the empty mark) is sent to the apps as "battery-empty".
- The sub panel backlight goes off while X has the main display off (DPMS,
  after about 10 minutes untouched: kernel/0017 then powers the panel and its
  backlight down). Read from the connector every STATUS_POLL, and every
  SCREEN_FAST for a few seconds after a key or a touch, which is what wakes X.
Needs uinput.ko (kernel/uinput). Raw coordinates are in docs/subpanel.md.
The sub panel only shows anything once X stops holding card1 (docs/subpanel.md).

Usage: subpaneld.py [-v]
"""
import fcntl, math, mmap, os, re, select, signal, socket, struct, subprocess, sys, time

TOUCH = "mxs-lradc-ts"                  # input device names
MAIN_TOUCH = "SX8654 I2C Touchscreen"
JACK = "mxs_ymu818 Headphone"           # the headphone jack switch (ymu818)
FB = "/dev/fb1"
BACKLIGHT = "/sys/class/backlight/backlight@0"        # main display, 0-7
SUB_BACKLIGHT = "/sys/class/backlight/backlight@1"    # sub panel, 0-3
MAIN_DPMS = "/sys/class/drm/card0-DPI-1/dpms"         # main display: On / Off
BRIGHTNESS_STEPS = [7, 5, 3, 1]
SUB_BRIGHTNESS = {7: 3, 5: 2, 3: 1, 1: 1}            # sub panel follows the main one
# The volume buttons move between 16 steps (and 0), the same for both outputs,
# so each step is the same 3 px of the bar: round(max * step / 16).
VOLUME_STEPS = {"Speaker": [0, 2, 3, 5, 7, 8, 10, 12, 14, 15, 17, 19, 20, 22,
                            24, 25, 27],
                "Headphone": [0, 2, 4, 6, 8, 10, 12, 14, 16, 17, 19, 21, 23, 25,
                              27, 29, 31]}
STEP_PX = 3
STATUS_POLL = 30                     # seconds between battery/volume checks
SCREEN_FAST, SCREEN_AFTER = 0.2, 3   # main display check after an input (s)
VERBOSE = "-v" in sys.argv

# Raw coordinates of the sub panel: displayed area is x 356-3435, the button
# column is right of BUTTON_X; buttons split by y (top = large y). The
# volume/backlight/clear limits are the printed edges (display y 62 and 93),
# up/down splits the volume button halfway between the taps.
BUTTON_X = 3550
BUTTONS = [(2960, "volume_up"), (2130, "volume_down"), (1350, "backlight"),
           (-1, "clear")]
# raw units per sub panel pixel: the 240 x 120 px panel is about 3080 x 2920 raw
RAW_PER_PX_X, RAW_PER_PX_Y = 3080 / 240, 2920 / 120
SKIP = 2                            # button: samples dropped at press and release
# Touchpad (measured 2026-10-19, userspace/subpanel/touchrec.py): a sample every
# 26 ms; the first one of a press jumps (up to 6 px, mostly in y) and so does
# the last before the release; a still finger jitters (sd 0.6 px in x, 1.2 px
# in y) and creeps a few px. The first sample is dropped, and the pointer runs
# one sample behind on the median of the newest three (drops a lone spike and
# the jump at the release), then through a One Euro filter (Casiez et al.
# 2012: smooths hard while slow, lightly while fast) and a hysteresis.
START = 3                           # sub panel px before a stroke moves (kept, not dropped)
HYST = 1.0                          # sub panel px of jitter left out while moving
MIN_CUTOFF, BETA, D_CUTOFF = 1.0, 0.1, 10.0     # One Euro: Hz, Hz per px/s, Hz
# pointer gain (screen px per sub panel px) by finger speed (sub panel px/s),
# smooth from MIN_GAIN to MAX_GAIN, half way at HALF_SPEED. Measured: slow
# strokes ~50 px/s, normal ~100-170, flicks ~1000.
MIN_GAIN, MAX_GAIN, HALF_SPEED = 1.0, 3.0, 250
Y_GAIN = 1.2                        # a little more up and down: the panel is only 120 px high
REPRESS = 0.12                      # a press this soon after the release goes on with
                                    # the stroke (the touch chatters: 27-99 ms gaps)
TAP_RANGE = 20                      # sub panel px a tap stays within (jumps included;
                                    # taps measured up to 7, flicks from 76)
# Main display, raw: the display is x 237-3627 (X calibration); printed
# buttons are left of MAIN_LEFT_X and right of MAIN_RIGHT_X (the display edges),
# split by y.
MAIN_LEFT_X, MAIN_RIGHT_X = 237, 3627
# SX8654 sends a sample every 3.6 ms, steady to 1 px, but the last one before
# the release jumps (up to 100 px, 8 of 11 touches, 2026-10-20): display
# touches go on this many samples late and the ones left at the release are
# dropped (7 ms)
MAIN_HOLD = 2
# A tap wanders before the release (pen up to 7 px, finger up to 17), and JWM
# keeps its root menu open only when the release is within 2 px of the press:
# the pointer stays at the press point until the touch has moved this far
# (screen px; the display is 480 x 320 over raw 3390 x 3874)
MAIN_SLOP = 10
MAIN_RAW_PER_PX_X, MAIN_RAW_PER_PX_Y = 3390 / 480, 3874 / 320
# While dragging, X gets the newest point at most this often: 280 points a
# second kept X redrawing a window being moved on a CPU already busy reading
# them (2026-10-20: SX8654's irq thread 22 %, X 21 %, this 14 %)
MAIN_INTERVAL = 1 / 60
MAIN_LEFT = [(3000, "prev_heading"), (2000, "page_up"), (1050, "page_down"),
             (-1, "next_heading")]          # 前見出 ↑ ↓ 次見出
MAIN_RIGHT = [(3450, "handwriting"), (2960, "kana_keys"), (2460, "memo"),
              (1950, "back"), (1400, "enter"), (790, "text_larger"),
              (-1, "text_smaller")]         # 手書き大 50音キー 暗記メモ 戻る 検索/決定 文字大 小
KBD = "brain-kbd-i2c"                   # power key and lid (not grabbed)
KEY_POWER = 116
POWER_LONG = 5.0                    # logind's long press (power off) in seconds
REWIND_SPEED = 4                    # the ring runs back this much faster
FRAME = 1 / 30                      # seconds between frames of the ring
ASLEEP_ACK = "/run/subpaneld-asleep"     # brain-subpanel-sleep waits for it
PID_FILE = "/run/subpaneld.pid"
APP_SOCK = "/run/subpaneld.sock"         # apps: keep-awake (docstring)
INHIBIT_CMD = ["systemd-inhibit", "--what=handle-lid-switch", "--mode=block",
               "--who=subpaneld", "--why=an app plays with the lid closed", "cat"]
SUSPEND_TRIES = 15.0                # seconds to keep asking for the suspend
SUSPEND_AGAIN = 6.0                 # ask again if it has not started by then (the
                                    # hook comes 3-4 s after logind takes it)
SUSPEND_CMD = ["busctl", "call", "org.freedesktop.login1", "/org/freedesktop/login1",
               "org.freedesktop.login1.Manager", "Suspend", "b", "false"]
TAP_TIME = 0.35
LONG_TIME = 0.6

EV_SYN, EV_KEY, EV_REL, EV_ABS, EV_SW = 0, 1, 2, 3, 5
SW_LID = 0
SW_DOCK = 5                          # 5V from the hub, from the keyboard controller
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


def find_event(name, required=True):
    """/dev/input/eventN of the input device with this name."""
    with open("/proc/bus/input/devices") as f:
        for block in f.read().split("\n\n"):
            if f'N: Name="{name}"' in block:
                return "/dev/input/" + re.search(r"\bevent\d+", block).group()
    if required:
        raise SystemExit(f"no input device {name}")
    return None


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
        self.held = []         # display frames not sent yet (MAIN_HOLD), with x, y
        self.down_sent = False
        self.press = None      # raw point of the press, until the touch leaves MAIN_SLOP
        self.pending = None    # newest point of a drag not sent yet (MAIN_INTERVAL)
        self.sent_at = 0.0
        self.start = None      # where and when the touch began, and its samples (log)
        self.n = 0
        self.reads = []        # (delay, events) of each read (log)

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
            self.held = []
            self.down_sent = False
            self.press = (self.x, self.y)
            self.start = (self.x, self.y, time.monotonic())
            self.n = 0
            self.reads = []
            if self.kind != "screen":
                log(f"main {self.kind} at ({self.x},{self.y})")
        if self.kind == "screen":
            if touch and not touch[-1]:
                if self.held and not self.down_sent:
                    self.ts.send(self.held[0][0])  # a short tap: the press, where it began
                self.held = []
                if self.pending:
                    self.ts.send([(EV_ABS, ABS_X, self.pending[0]),
                                  (EV_ABS, ABS_Y, self.pending[1])])
                    self.pending = None
                self.ts.send(frame)
                x0, y0, t0 = self.start
                late = sorted(d for d, _ in self.reads) or [0]
                log(f"main screen ({x0},{y0}) -> ({self.x},{self.y}) n={self.n} "
                    f"{time.monotonic() - t0:.2f}s{' dragged' if self.press is None else ''} "
                    f"reads={len(self.reads)} late median {late[len(late) // 2] * 1000:.0f} "
                    f"max {late[-1] * 1000:.0f} ms, "
                    f"{sum(e for _, e in self.reads) / max(1, len(self.reads)):.1f} events/read")
            elif frame:
                self.n += 1
                self.held.append((frame, self.x, self.y))
                if len(self.held) > MAIN_HOLD:
                    self.send_screen(*self.held.pop(0))
                    self.down_sent = True
        elif self.kind is None:
            if frame:
                self.ts.send(frame)
        elif self.y is not None:
            self.pts.append((self.x, self.y))
        if touch and not touch[-1]:
            if self.kind in ("left", "right"):
                self.button()
            self.kind = None

    def send_screen(self, frame, x, y):
        if not self.down_sent:
            self.ts.send(frame)
            return
        rest = [e for e in frame if e[0] != EV_ABS]
        if self.press:
            if (abs(x - self.press[0]) / MAIN_RAW_PER_PX_X <= MAIN_SLOP
                    and abs(y - self.press[1]) / MAIN_RAW_PER_PX_Y <= MAIN_SLOP):
                if rest:
                    self.ts.send(rest)  # stay at the press
                return
            self.press = None  # dragging from here on
        now = time.monotonic()
        if not rest and now - self.sent_at < MAIN_INTERVAL:
            self.pending = (x, y)
            return
        self.ts.send(rest + [(EV_ABS, ABS_X, x), (EV_ABS, ABS_Y, y)])
        self.sent_at = now
        self.pending = None

    def flush(self, now):
        """Send the newest point of a drag once MAIN_INTERVAL has passed."""
        if self.pending and now - self.sent_at >= MAIN_INTERVAL:
            self.ts.send([(EV_ABS, ABS_X, self.pending[0]),
                          (EV_ABS, ABS_Y, self.pending[1])])
            self.sent_at = now
            self.pending = None

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


def volume_control():
    """The ALSA control of the output in use: the driver follows the jack."""
    out = subprocess.run(["amixer", "cget", "iface=CARD,name=Headphone Jack"],
                         capture_output=True, text=True).stdout
    return "Headphone" if re.search(r": values=on", out) else "Speaker"


def get_volume(name):
    out = subprocess.run(["amixer", "sget", name], capture_output=True,
                         text=True).stdout
    m = re.search(r"Playback (\d+) \[", out)
    return int(m.group(1)) if m else 0


def volume(up):
    """One step up or down. A value between steps goes to the next one."""
    name = volume_control()
    cur, steps = get_volume(name), VOLUME_STEPS[name]
    if up:
        new = next((v for v in steps if v > cur), steps[-1])
    else:
        new = next((v for v in reversed(steps) if v < cur), 0)
    subprocess.run(["amixer", "-q", "sset", name, str(new)])


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
VOL_Y = (0, 47)                      # inclusive
OUT_Y = 50                           # output icon below the bar, to y 56 like
                                     # the bar alone, in the volume down button
BL_Y = (67, 87)
BATT_Y = (99, 111)                   # the icon, in the clear button
PLUG_Y = 114                         # plug below it on 5V
# icons face right, like the printed buttons they sit beside
SPEAKER = ["...#...", "..##.#.", "####..#", "####..#", "####..#", "..##.#.",
           "...#..."]
HEADPHONE = ["..###..", ".#...#.", "#.....#", "#.....#", "##...##", "##...##",
             "##...##"]
MUTED = ["#......", ".#.....", "..#....", "...#...", "....#..", ".....#.",
         "......#"]                  # drawn over the icon, grayed out, at 0
PLUG = ["...##...", "..######", "#####...", "..######", "...##..."]
FBIOGET_VSCREENINFO, FBIOPUT_VSCREENINFO = 0x4600, 0x4601
FB_ACTIVATE_FORCE = 128


class Canvas:
    """A picture of the whole sub panel in memory."""

    def __init__(self):
        self.buf = bytearray(WHITE * (W * H))

    def left(self):
        """Copy of the area left of the strip."""
        return bytes(self.buf)

    def put_all(self, pic):
        self.buf[:] = pic

    def put_left(self, pic):
        """Put back the area left of the strip from a copy (rows of x 0..STRIP_X-1)."""
        n = STRIP_X * 4
        for y in range(H):
            o = y * W * 4
            self.buf[o:o + n] = pic[o:o + n]

    def point(self, x, y, color):
        o = (y * W + x) * 4
        self.buf[o:o + 4] = color

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



class Panel(Canvas):
    def __init__(self):
        self.fd = os.open(FB, os.O_RDWR)
        var = bytearray(160)
        fcntl.ioctl(self.fd, FBIOGET_VSCREENINFO, var)
        var[84:88] = FB_ACTIVATE_FORCE.to_bytes(4, "little")  # .activate
        try:
            fcntl.ioctl(self.fd, FBIOPUT_VSCREENINFO, var)
        except OSError as e:  # EBUSY while X holds card1; fine if already enabled
            log(f"modeset: {e}")
        super().__init__()

    def flush(self):
        t = time.monotonic()
        os.pwrite(self.fd, self.buf, 0)
        log(f"flush {1000 * (time.monotonic() - t):.0f}ms")


def draw_status(panel, vol, hp, level, bars, usb):
    x0, x1 = STRIP_X + 1, W - 2
    panel.rect(STRIP_X, 0, W - 1, H - 1, WHITE)
    # volume: a bar from the bottom of the volume band, gray behind it
    top, bot = VOL_Y
    panel.shade(x0, top, x1, bot)
    h = STEP_PX * vol
    if h:
        panel.rect(x0, bot - h + 1, x1, bot, BLACK)
    # the output in use below it
    panel.pattern(x0, OUT_Y, HEADPHONE if hp else SPEAKER, BLACK if vol else LIGHT)
    if not vol:
        panel.pattern(x0, OUT_Y, MUTED, BLACK)
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
        panel.pattern(x0, PLUG_Y, PLUG, BLACK)      # 8 wide, to the right edge
    panel.flush()


def read_volume():
    """Volume step of the output in use (0-16; a value between steps shows as
    the step above, so only 0 shows as muted), and whether it is the headphones."""
    name = volume_control()
    cur = get_volume(name)
    step = next(i for i, v in enumerate(VOLUME_STEPS[name] + [cur]) if v >= cur)
    return min(step, 16), name == "Headphone"


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
        cur = (*read_volume(), read_level(), self.bars, self.usb)
        if cur != self.shown:
            log("status vol={} hp={} level={} bars={} usb={}".format(*cur))
            draw_status(self.panel, *cur)
            self.shown = cur


# --- power key and sleep, on the sub panel left of the strip ----------------
CX, CY = STRIP_X // 2, H // 2       # ring centre
RING_R, RING_W = 46, 10             # outer radius, width


def _ring_pixels():
    """Pixels of the ring sorted clockwise from 12 o'clock: (angle 0-1, x, y,
    edge). Edge pixels are half covered: dark when filled, left white when not."""
    import math
    out = []
    r_in = RING_R - RING_W
    for y in range(CY - RING_R - 1, CY + RING_R + 2):
        for x in range(CX - RING_R - 1, CX + RING_R + 2):
            d = math.hypot(x - CX, y - CY)
            if r_in <= d <= RING_R:
                edge = False
            elif r_in - 0.7 <= d < r_in or RING_R < d <= RING_R + 0.7:
                edge = True
            else:
                continue
            a = math.atan2(x - CX, CY - y) / (2 * math.pi) % 1.0
            out.append((a, x, y, edge))
    out.sort()
    return out


def _power_icon():
    """Pixels of the power symbol (an open circle and a bar) inside the ring."""
    import math
    out = []
    for y in range(CY - 20, CY + 18):
        for x in range(CX - 18, CX + 19):
            d = math.hypot(x - CX, y - CY)
            a = abs(math.degrees(math.atan2(x - CX, CY - y)))
            if (13 <= d <= 16.5 and a > 35) or (abs(x - CX) <= 1 and CY - 20 <= y <= CY - 3):
                out.append((x, y))
    return out


def _moon(c):
    """A crescent in the middle of the whole panel (the strip is hidden)."""
    import math
    cx = W // 2
    for y in range(CY - 30, CY + 31):
        for x in range(cx - 30, cx + 31):
            if math.hypot(x - cx, y - CY) <= 28 and \
                    math.hypot(x - cx - 13, y - CY + 9) > 24:
                c.point(x, y, BLACK)


class PowerUI:
    """Ring while the power key is held, moon while asleep.

    The pictures are drawn once at start-up (Python draws a few thousand
    pixels slowly on the Brain); a frame then only touches the ring pixels
    that change."""

    def __init__(self, status):
        self.status = status
        self.panel = status.panel
        self.state = "idle"         # idle, fill, rewind, moon, off
        self.filled = 0             # ring pixels drawn filled
        self.frac = 0.0
        self.t0 = 0.0
        self.moon_until = None      # key path: back to idle if no suspend came
        self.ack = False            # brain-subpanel-sleep waits for the moon
        self.normal = None          # the picture to put back after waking
        self.suspend = None         # (systemctl process, give up at) while asking
        self.offset = None          # CLOCK_BOOTTIME - CLOCK_MONOTONIC
        if not self.panel:
            return
        self.ring = _ring_pixels()
        self.angles = [p[0] for p in self.ring]
        self.icon = _power_icon()
        c = Canvas()
        for _, x, y, edge in self.ring:
            if not edge:
                c.point(x, y, LIGHT)
        for x, y in self.icon:
            c.point(x, y, DARK)
        self.ring_pic = c.left()
        c = Canvas()
        _moon(c)
        self.moon_pic = c.left()

    @property
    def animating(self):
        return self.state in ("fill", "rewind")

    @property
    def polling(self):
        """Asleep, or about to be: watch for the wake-up."""
        return self.state == "moon"

    def _set(self, frac):
        import bisect
        frac = min(max(frac, 0.0), 1.0)
        n = bisect.bisect_right(self.angles, frac) if frac < 1 else len(self.ring)
        lo, hi = sorted((self.filled, n))
        p = self.panel
        for _, x, y, edge in self.ring[lo:hi]:
            if n > self.filled:
                p.point(x, y, DARK if edge else BLACK)
            else:
                p.point(x, y, WHITE if edge else LIGHT)
        self.filled, self.frac = n, frac

    def key(self, down, now):
        if not self.panel:
            return
        if down:
            if self.state == "idle":
                self.normal = self.panel.left()
            if self.state != "rewind":
                self.panel.put_left(self.ring_pic)
                self.filled, self.frac = 0, 0.0
            self.t0 = now - self.frac * POWER_LONG
            self.state = "fill"
            log("power key down")
        elif self.state == "fill":
            self.t0, self.state = now, "rewind"
            self.rewind_from = self.frac
            log(f"power key up at {self.frac * POWER_LONG:.1f} s")
        self.tick(now)

    def tick(self, now):
        if not self.panel:
            return
        if self.state == "fill":
            self._set((now - self.t0) / POWER_LONG)
            if self.frac >= 1:
                for x, y in self.icon:
                    self.panel.point(x, y, BLACK)
                self.state = "off"
                log("power key held: power off")
            self.panel.flush()
        elif self.state == "rewind":
            self._set(self.rewind_from - (now - self.t0) * REWIND_SPEED / POWER_LONG)
            if self.frac <= 0:
                self.moon(now + SUSPEND_TRIES + 2)
                self.ask_suspend(now)
            else:
                self.panel.flush()
        elif self.state == "moon":
            self.check_suspend(now)
            if self.moon_until and now >= self.moon_until:
                log("no suspend came")
                self.wake()
            elif self.slept():
                log("woke up")
                self.wake()

    def ask_suspend(self, now, until=None):
        """Short press: ask logind for the suspend (it ignores the key)."""
        proc = subprocess.Popen(SUSPEND_CMD, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        self.suspend = (proc, now, until or now + SUSPEND_TRIES)

    def check_suspend(self, now):
        """Ask again until the suspend begins (asleep() clears the request)."""
        if not self.suspend:
            return
        proc, asked, until = self.suspend
        rc = proc.poll()
        if rc is None:
            return
        if now >= until:
            log("the suspend never began")
            self.suspend = None
        elif rc != 0 or now - asked >= SUSPEND_AGAIN:
            log(f"suspend: {rc}, asking again")
            self.ask_suspend(now, until)

    def slept(self):
        """True once after a suspend-to-mem (the kernel adds the time slept to
        CLOCK_BOOTTIME, not to CLOCK_MONOTONIC)."""
        off = time.clock_gettime(time.CLOCK_BOOTTIME) - time.monotonic()
        jumped = self.offset is not None and off - self.offset > 0.5
        self.offset = off
        return jumped

    def moon(self, until=None):
        """Show the moon. until: give up waiting for the suspend then."""
        if not self.panel or self.state == "off":
            return
        if self.state != "moon":
            if self.state == "idle":
                self.normal = self.panel.left()
            self.panel.put_all(self.moon_pic)
            self.panel.flush()
            self.offset = None
            self.slept()
        self.state, self.moon_until = "moon", until
        if self.ack:
            self.ack, self.moon_until = False, None
            with open(ASLEEP_ACK, "w"):
                pass

    def asleep(self):
        """SIGUSR1 from brain-subpanel-sleep, just before suspending. A ring
        that is running back finishes first (it is short)."""
        self.ack = True
        self.suspend = None
        if self.state == "rewind":
            return
        self.moon()
        self.moon_until = None

    def wake(self):
        """SIGUSR2 after waking, the clock jump, or no suspend: back to normal."""
        try:
            os.unlink(ASLEEP_ACK)
        except FileNotFoundError:
            pass
        if not self.panel or self.state == "idle":
            return
        self.state, self.moon_until, self.suspend = "idle", None, None
        if self.normal:
            self.panel.put_all(self.normal)
        self.panel.flush()
        self.status.shown = None
        self.status.update(time.monotonic(), force=True)


class Apps:
    """Apps that want the lid not to suspend (docstring at the top), and the
    backlights: both off for the lid, the sub panel's also while the main
    display is off.

    The inhibitor is held by systemd-inhibit running cat: closing its stdin
    lets go, and so does this process going away."""

    def __init__(self):
        try:
            os.unlink(APP_SOCK)
        except FileNotFoundError:
            pass
        self.srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.srv.bind(APP_SOCK)
        os.chmod(APP_SOCK, 0o666)
        self.srv.listen(4)
        self.srv.setblocking(False)
        self.clients = {}           # fd -> [socket, wants keep-awake, partial line]
        self.hold = None            # systemd-inhibit while held
        self.lid = False            # closed
        self.dark = False           # backlights turned off by us
        self.screen_off = False     # main display off (X's DPMS)
        self.sub_dark = False       # sub panel backlight turned off by us
        self.screen_next = 0        # when to read MAIN_DPMS next
        self.screen_fast_until = 0
        self.empty = False          # battery-empty already sent

    def fds(self):
        return [self.srv.fileno(), *self.clients]

    def ready(self, fds):
        if self.srv.fileno() in fds:
            try:
                c, _ = self.srv.accept()
                c.setblocking(False)
                self.clients[c.fileno()] = [c, False, b""]
                log("app connected")
            except OSError:
                pass
        for fd in [fd for fd in fds if fd in self.clients]:
            cl = self.clients[fd]
            try:
                data = cl[0].recv(256)
            except BlockingIOError:
                continue
            except OSError:
                data = b""
            if not data:
                cl[0].close()
                del self.clients[fd]
                log("app gone")
                continue
            *lines, cl[2] = (cl[2] + data).split(b"\n")
            for line in lines:
                if line.startswith(b"keep-awake "):
                    cl[1] = line.endswith(b"1")
                    log(f"app keep-awake {int(cl[1])}")
        self.sync()

    def sync(self):
        want = any(cl[1] for cl in self.clients.values())
        if want and not self.hold:
            self.hold = subprocess.Popen(INHIBIT_CMD, stdin=subprocess.PIPE,
                                         stdout=subprocess.DEVNULL)
            log("lid inhibitor taken")
        elif not want and self.hold:
            self.hold.stdin.close()
            try:
                self.hold.wait(2)
            except subprocess.TimeoutExpired:
                self.hold.kill()
            self.hold = None
            log("lid inhibitor released")
        self.backlight()

    def lid_switch(self, closed):
        self.lid = closed
        self.backlight()

    def input(self, now):
        """A key or a touch: X may be turning the main display on."""
        if self.screen_off:
            self.screen_fast_until = now + SCREEN_AFTER
            self.screen_next = min(self.screen_next, now)

    def screen_tick(self, now):
        if now < self.screen_next:
            return
        fast = now < self.screen_fast_until
        self.screen_next = now + (SCREEN_FAST if fast else STATUS_POLL)
        try:
            with open(MAIN_DPMS) as f:
                off = f.read().strip() != "On"
        except OSError:
            return
        if off != self.screen_off:
            self.screen_off = off
            log(f"main display {'off' if off else 'on'}")
            self.backlight()

    @staticmethod
    def bl_power(bl, off):
        try:
            with open(f"{bl}/bl_power", "w") as f:
                f.write("4" if off else "0")    # FB_BLANK_POWERDOWN / UNBLANK
        except OSError as e:
            log(f"{bl}: {e}")

    def backlight(self):
        dark = self.lid and self.hold is not None
        if dark != self.dark:
            self.dark = dark
            self.bl_power(BACKLIGHT, dark)
            log(f"main backlight {'off' if dark else 'on'}")
        sub_dark = dark or self.screen_off
        if sub_dark != self.sub_dark:
            self.sub_dark = sub_dark
            self.bl_power(SUB_BACKLIGHT, sub_dark)
            log(f"sub backlight {'off' if sub_dark else 'on'}")

    def battery(self, bars):
        """Tell the apps once when the empty mark shows."""
        if bars is None:
            return
        if bars > 0:
            self.empty = False
        elif not self.empty:
            self.empty = True
            log("battery empty")
            for cl in self.clients.values():
                try:
                    cl[0].send(b"battery-empty\n")
                except OSError:
                    pass


def button_at(y):
    return next(name for limit, name in BUTTONS if y > limit)


class Stroke:
    """One touch from press to release."""

    def __init__(self, now):
        self.start = now
        self.pts = []          # raw (x, y, time) samples
        self.kind = None       # "pad" or "button", decided after SKIP samples
        self.pad = []          # pad: (x, y, time) in sub panel px, y down
        self.fresh = True      # the next sample is the first of a press (dropped)
        self.filt = None       # One Euro: x, y, vx, vy, time
        self.ref = None        # point the pointer stands for
        self.up = None         # time of the release, until REPRESS has passed
        self.moving = False
        self.long_done = False


def alpha(cutoff, dt):
    return 1 / (1 + 1 / (2 * math.pi * cutoff * dt))


def gain(speed):
    s2 = speed * speed
    return MIN_GAIN + (MAX_GAIN - MIN_GAIN) * s2 / (s2 + HALF_SPEED * HALF_SPEED)


def on_sample(st, x, y, t, mouse):
    st.pts.append((x, y, t))  # t: event time, only for speed
    if st.kind is None and len(st.pts) > SKIP:
        st.kind = "button" if x >= BUTTON_X else "pad"
        log(f"stroke {st.kind} at ({x},{y})")
    if st.fresh:
        st.fresh = False
        return
    st.pad.append((x / RAW_PER_PX_X, -y / RAW_PER_PX_Y, t))  # raw y grows upward
    if st.kind == "button" or len(st.pad) < 2:
        return
    # one sample behind: the median of the newest three stands for the one before
    win = st.pad[-3:]
    mx = sorted(p[0] for p in win)[len(win) // 2]
    my = sorted(p[1] for p in win)[len(win) // 2]
    t = st.pad[-2][2]
    f = st.filt
    if f is None:
        st.filt = [mx, my, 0.0, 0.0, t]
        st.ref = (mx, my)
        return
    dt = max(t - f[4], 0.001)
    a = alpha(D_CUTOFF, dt)
    f[2] += a * ((mx - f[0]) / dt - f[2])
    f[3] += a * ((my - f[1]) / dt - f[3])
    speed = math.hypot(f[2], f[3])
    a = alpha(MIN_CUTOFF + BETA * speed, dt)
    f[0] += a * (mx - f[0])
    f[1] += a * (my - f[1])
    f[4] = t
    dx, dy = f[0] - st.ref[0], f[1] - st.ref[1]
    if not st.moving:
        if max(abs(dx), abs(dy)) < START:
            return
        st.moving = True
        log("moving")
    else:
        d = math.hypot(dx, dy)
        if d <= HYST:
            return
        dx, dy = dx * (1 - HYST / d), dy * (1 - HYST / d)
    st.ref = (st.ref[0] + dx, st.ref[1] + dy)
    g = gain(speed)
    mouse.move(dx * g, dy * g * Y_GAIN)


def on_release(st, now, mouse, status):
    if not st.pts:
        return
    if st.kind is None:  # too short to decide while touching
        st.kind = "button" if st.pts[0][0] >= BUTTON_X else "pad"
    log(f"release {st.kind} n={len(st.pts)} {st.up - st.start:.3f}s")
    if st.kind == "pad":
        xs = [p[0] for p in st.pts]
        ys = [p[1] for p in st.pts]
        spread = max((max(xs) - min(xs)) / RAW_PER_PX_X,
                     (max(ys) - min(ys)) / RAW_PER_PX_Y)
        if (not st.long_done and not st.moving and st.up - st.start < TAP_TIME
                and len(st.pts) >= 2 and spread < TAP_RANGE):
            mouse.click(BTN_LEFT)
            log("tap -> left click")
    elif st.kind == "button":
        core = st.pts[SKIP:-SKIP] or st.pts
        y = sorted(p[1] for p in core)[len(core) // 2]
        name = button_at(y)
        log(f"button {name} (y={y})")
        if name == "volume_up":
            volume(True)
        elif name == "volume_down":
            volume(False)
        elif name == "backlight":
            log(f"brightness {cycle_backlight()}")
        elif name == "clear":
            mouse.click(KEY_ESC)
        status.update(now, force=True)


def check_long(st, now, mouse):
    if (st and st.kind == "pad" and not st.long_done and st.up is None
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
    # not grabbed: only to redraw the strip when the headphones go in or out
    jack_dev = find_event(JACK, required=False)
    jack = os.open(jack_dev, os.O_RDONLY | os.O_NONBLOCK) if jack_dev else None
    status = Status()
    power = PowerUI(status)
    kbd_dev = find_event(KBD, required=False)
    kbd = os.open(kbd_dev, os.O_RDONLY | os.O_NONBLOCK) if kbd_dev else None
    apps = Apps()
    if kbd is not None:             # EVIOCGSW(8): the lid as it is now
        apps.lid = bool(fcntl.ioctl(kbd, 0x8008451b, bytes(8))[0] & 1)
    # signals from brain-subpanel-sleep arrive through a pipe, so the drawing
    # happens in the loop and never in the middle of another frame
    sig_r, sig_w = os.pipe()
    os.set_blocking(sig_w, False)
    signal.set_wakeup_fd(sig_w)
    for sig in (signal.SIGUSR1, signal.SIGUSR2):
        signal.signal(sig, lambda *_: None)
    with open(PID_FILE, "w") as f:
        f.write(f"{os.getpid()}\n")
    log("ready")
    x = y = None
    st = None
    try:
        while True:
            # wake often only while touched (long press); else at the next poll
            wait = 0.05 if st else min(3600, max(0.05, status.next_poll - time.monotonic()))
            if main_panel.pending:
                wait = min(wait, MAIN_INTERVAL)
            if power.animating:
                wait = FRAME
            elif power.polling:
                wait = min(wait, 0.2)
            wait = min(wait, max(0.05, apps.screen_next - time.monotonic()))
            fds = [touch, main_touch, sig_r] + [d for d in (jack, kbd) if d is not None]
            r, _, _ = select.select(fds + apps.fds(), [], [], wait)
            now = time.monotonic()
            if sig_r in r:
                for signum in os.read(sig_r, 64):
                    if signum == signal.SIGUSR1:
                        power.asleep()
                    elif signum == signal.SIGUSR2:
                        power.wake()
            if kbd is not None and kbd in r:
                data = os.read(kbd, 16 * 64)
                for i in range(0, len(data) - 15, 16):
                    typ, code, val = struct.unpack_from("<HHi", data, i + 8)
                    if typ == EV_KEY and code == KEY_POWER and val in (0, 1):
                        power.key(val == 1, now)
                    elif typ == EV_SW and code == SW_LID:
                        apps.lid_switch(val == 1)
                    elif typ == EV_SW and code == SW_DOCK:
                        # show the plug at once; the next poll reads VBUSVALID again
                        status.usb = val == 1
                        status.update(now, force=True)
            power.tick(now)
            if jack in r:
                os.read(jack, 16 * 64)
                status.update(now, force=True)
            if main_touch in r:
                data = os.read(main_touch, 16 * 64)
                if VERBOSE and data:     # how late the oldest event is read
                    sec, usec = struct.unpack_from("<II", data)
                    main_panel.reads.append((time.time() - sec - usec / 1e6, len(data) // 16))
                for i in range(0, len(data) - 15, 16):
                    main_panel.event(*struct.unpack_from("<HHi", data, i + 8))
            main_panel.flush(now)
            if touch in r:
                data = os.read(touch, 16 * 64)
                for i in range(0, len(data) - 15, 16):
                    sec, usec, typ, code, val = struct.unpack_from("<IIHHi", data, i)
                    if typ == EV_ABS and code == ABS_X:
                        x = val
                    elif typ == EV_ABS and code == ABS_Y:
                        y = val
                    elif typ == EV_KEY and code == BTN_TOUCH:
                        if (val and st and st.up is not None and st.kind != "button"
                                and now - st.up < REPRESS):
                            st.up = None        # chatter: the same stroke goes on
                            st.fresh = True
                        elif val:
                            if st:
                                on_release(st, now, mouse, status)
                            st = Stroke(now)
                        elif st:
                            st.up = now
                    elif typ == EV_SYN and st and st.up is None and x is not None:
                        on_sample(st, x, y, sec + usec / 1e6, mouse)
            if st and st.up is not None and now - st.up >= REPRESS:
                on_release(st, now, mouse, status)
                st = None
            if any(d in r for d in (kbd, touch, main_touch) if d is not None):
                apps.input(now)
            apps.screen_tick(now)
            apps.ready(r)
            check_long(st, now, mouse)
            if not power.animating:     # reading the volume runs amixer, slow on the Brain
                status.update(now)
                apps.battery(status.bars)
    finally:
        mouse.close()
        ts.close()


if __name__ == "__main__":
    main()
