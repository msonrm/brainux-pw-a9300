#!/bin/sh
# YMU818 の試し鳴らし。Brain 上で: sudo sh run-test.sh [VOL] [HZ]
#   VOL: YMU818 の音量レジスタ 0x025 の値（0x20..0x2a、既定 0x22 = WinCE の音量 1/8 程度）
#   HZ : 正弦波の周波数（既定 1000）
# 途中で失敗したら mute / stop / saif off をしてから終わる。
set -u
cd "$(dirname "$0")"
VOL=${1:-0x22}
HZ=${2:-1000}

cleanup() {
	echo "== cleanup"
	python3 ymu818.py mute stop || true
	./saif off || true
}
step() {
	echo "== $*"
	"$@" || { echo "!! failed: $*"; cleanup; exit 1; }
}

step ./saif setup                                  # MCLK を出す（YMU818 の PLL に必要）
step python3 ymu818.py probe
step python3 ymu818.py reset init                  # WinCE の WAV_Init 相当
step python3 ymu818.py start                       # BSPAudioStartDAC 相当（PLL ロックを待つ）
step python3 ymu818.py --vol "$VOL" amp            # スピーカーアンプを入れて音量を設定
# FIFO が 4 フレームしかないので、送り出しの 3 秒だけ実時間優先度の休み (1 秒ごとに 50ms) を外す
RT=$(cat /proc/sys/kernel/sched_rt_runtime_us)
echo -1 > /proc/sys/kernel/sched_rt_runtime_us
./saif tone "$HZ" 3 0.1                            # 3 秒、振幅 0.1
echo "$RT" > /proc/sys/kernel/sched_rt_runtime_us
cleanup
echo "done"
