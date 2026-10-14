#!/usr/bin/env python3
"""Log the 5V input every 0.5 s while switching Wi-Fi off and on (root).

Asks whether the OTG hub stops feeding 5V back when the Wi-Fi stick goes
quiet, and whether HW_POWER_5VCTRL (the 4P2 current limit) changes when 5V
comes back. Each line: seconds, VDD5V (LRADC ch15), VBUSVALID, the 4P2 limit,
DCDC4P2, whether the hub (1-1) and the Wi-Fi stick (1-1.3) are on the bus, the
battery watch pins (GPIO4_4/6/7/8). Lines are fsync'ed, so a log survives a
crash up to the last line. Reads registers only; changes nothing but Wi-Fi
and NetworkManager.

Usage: vbuswatch.py LOG [--plan 10:wifi-off,30:wifi-on,60:end]
  each step: wait N seconds, then do the action (wifi-off, wifi-on,
  nm-sleep, nm-wake = NetworkManager's Sleep(true/false) as before a
  suspend, suspend = systemctl suspend, end; any other word only marks the
  log). Nothing is logged while asleep; the first line after waking shows
  whether 5V was there (the s2idle here keeps CLOCK_MONOTONIC running).
Run it detached (systemd-run), since switching Wi-Fi off drops SSH.
For the lid alone, without sleeping (2026-10-14):
  systemd-run systemd-inhibit --what=handle-lid-switch vbuswatch.py LOG --plan 90:end
"""
import argparse, mmap, os, struct, subprocess, time

POWER, PINCTRL = 0x80044000, 0x80018000
IIO = "/sys/bus/iio/devices/iio:device0"


def ilimit_ma(v):
    return sum(ma for bit, ma in enumerate((10, 20, 50, 100, 200, 400))
               if v >> bit & 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--plan", default="10:wifi-off,30:wifi-on,60:end")
    a = ap.parse_args()
    plan = [(float(s), act) for s, act in
            (step.split(":") for step in a.plan.split(","))]

    fd = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
    pw = mmap.mmap(fd, 0x1000, mmap.MAP_SHARED, mmap.PROT_READ, offset=POWER)
    pc = mmap.mmap(fd, 0x1000, mmap.MAP_SHARED, mmap.PROT_READ, offset=PINCTRL)
    reg = lambda m, o: struct.unpack("<I", m[o:o + 4])[0]
    scale = float(open(f"{IIO}/in_voltage15_scale").read())
    out = open(a.log, "a")

    def line(s):
        out.write(s + "\n")
        out.flush()
        os.fsync(out.fileno())

    t0 = time.monotonic()
    due = t0 + plan[0][0]
    step = 0
    line(f"# start {time.strftime('%F %T')} plan={a.plan}")
    while True:
        now = time.monotonic()
        v5 = int(int(open(f"{IIO}/in_voltage15_raw").read()) * scale)
        sts, vc, d42 = reg(pw, 0xc0), reg(pw, 0x10), reg(pw, 0x80)
        din = reg(pc, 0x940)
        pins = "".join(str(din >> b & 1) for b in (4, 6, 7, 8))
        hub = int(os.path.exists("/sys/bus/usb/devices/1-1"))
        wl = int(os.path.exists("/sys/bus/usb/devices/1-1.3"))
        line(f"{now - t0:6.1f} 5v={v5} vbusvalid={sts >> 1 & 1} "
             f"ilimit={ilimit_ma(vc >> 12 & 0x3f)}mA 5vctrl={vc:#010x} "
             f"dcdc4p2={d42:#010x} hub={hub} wifi={wl} pins={pins}")
        if now >= due:
            act = plan[step][1]
            line(f"# {now - t0:.1f} {act}")
            if act == "end":
                break
            if act in ("wifi-off", "wifi-on"):
                subprocess.run(["nmcli", "radio", "wifi", act[5:]])
            elif act == "suspend":
                subprocess.run(["systemctl", "suspend"])
            elif act in ("nm-sleep", "nm-wake"):
                subprocess.run(["busctl", "call", "org.freedesktop.NetworkManager",
                                "/org/freedesktop/NetworkManager",
                                "org.freedesktop.NetworkManager", "Sleep", "b",
                                "true" if act == "nm-sleep" else "false"])
            step += 1
            due = now + plan[step][0]
        time.sleep(0.5)


if __name__ == "__main__":
    main()
