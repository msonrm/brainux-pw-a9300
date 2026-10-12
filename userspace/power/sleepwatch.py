#!/usr/bin/env python3
"""眠っていた時間と蓋の状態を記録する（root 不要）。

1 秒ごとに起きるループを回し、間が大きく空いたら、その分は止められていた（眠っていた）とみなす。
この機種の s2idle は cpuidle ドライバがないので時計を止めない（CLOCK_MONOTONIC も BOOTTIME も進む）。
そのため時計どうしの差では測れない。蓋は logind の LidClosed を見る。
使い方: sleepwatch.py [秒数]（既定 300 秒）。nohup で動かしておき、あとでログを読む。
"""
import subprocess
import sys
import time


def lid():
    try:
        out = subprocess.run(
            ["busctl", "get-property", "org.freedesktop.login1", "/org/freedesktop/login1",
             "org.freedesktop.login1.Manager", "LidClosed"],
            capture_output=True, text=True, timeout=5).stdout.split()
        return "閉" if out[-1] == "true" else "開"
    except Exception:
        return "?"


def log(msg):
    print(time.strftime("%T"), msg, flush=True)


def main():
    limit = float(sys.argv[1]) if len(sys.argv) > 1 else 300
    last_lid = lid()
    log(f"開始 蓋={last_lid}")
    prev = time.monotonic()
    end = prev + limit
    while prev < end:
        time.sleep(1)
        now = time.monotonic()
        if now - prev > 3:
            log(f"止まっていた: 約 {now - prev - 1:.0f} 秒")
        prev = now
        cur = lid()
        if cur != last_lid:
            log(f"蓋: {last_lid} → {cur}")
            last_lid = cur
    log("終了")


if __name__ == "__main__":
    main()
