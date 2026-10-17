#!/usr/bin/env python3
"""Tell from brain-watch.log whether the batteries drain while 5V is there.

With 5V present and the SoC powered from it, the battery voltage (bvraw,
LRADC ch1 through battvolt) stays flat or creeps up as alkaline cells rest.
When the DC-DC runs from the batteries anyway (5V plugged back in while
running and 4P2 not restarted, 2026-10-17), it falls by tens per minute.

usage: battcheck.py [MINUTES] [LOG]   (default: last 10 minutes of /var/log/brain-watch.log)
Looks at the latest stretch of src=5v lines within that window.
"""
import re
import sys

LINE = re.compile(r"^(\d\d):(\d\d):(\d\d) .*pwr=\[src=(\w+) .*?bvraw=(\d+)")
FALLING = -5  # bvraw per minute; the bad case was about -30, resting cells are >= 0


def main():
    minutes = float(sys.argv[1]) if len(sys.argv) > 1 else 10
    path = sys.argv[2] if len(sys.argv) > 2 else "/var/log/brain-watch.log"
    rows = []
    with open(path, errors="replace") as f:
        for line in f.readlines()[-int(minutes * 6) - 6:]:
            m = LINE.match(line)
            if m:
                h, mi, s, src, raw = m.groups()
                rows.append((int(h) * 3600 + int(mi) * 60 + int(s), src, int(raw)))
    if not rows:
        print("no lines with bvraw (battvolt not installed, or not root?)")
        return 2
    # the latest run of src=5v lines; a gap over a minute (sleep) ends it
    run = []
    for t, src, raw in reversed(rows):
        if src != "5v" or (run and run[-1][0] - t > 60) or (run and t > run[-1][0]):
            break
        run.append((t, raw))
    run.reverse()
    if len(run) < 6:
        print(f"5V for less than a minute in the last {minutes:g} min (now src={rows[-1][1]}, bvraw={rows[-1][2]})")
        return 2
    span = (run[-1][0] - run[0][0]) / 60
    # compare the averages of the first and last six samples (one minute each)
    a = sum(r for _, r in run[:6]) / 6
    b = sum(r for _, r in run[-6:]) / 6
    slope = (b - a) / max(span - 1, 0.5)
    verdict = ("draining: running from the batteries although 5V is there"
               if slope < FALLING else "ok: not running from the batteries")
    print(f"5V for {span:.1f} min, bvraw {a:.0f} -> {b:.0f} ({slope:+.1f}/min): {verdict}")
    return 1 if slope < FALLING else 0


if __name__ == "__main__":
    sys.exit(main())
