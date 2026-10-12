#!/bin/sh
# メイン画面のバックライトの試験。sudo sh ~/bltest.sh で動かす
# 2026-10-12、kernel/0002 を当てる前に使った記録。結果: A でほぼ消えた。B・C はかえって明るくなった
# （GPIO3_5 は点灯のピンではない）。GPIO3_5 は DT で使われていないピンに /dev/mem で直接書くので、
# 理由がなければ動かさないこと。
bl=/sys/class/backlight/backlight@0/brightness
gp() { python3 -c "
import mmap,os,sys
fd=os.open(\"/dev/mem\",os.O_RDWR|os.O_SYNC); m=mmap.mmap(fd,0x1000,offset=0x80018000)
off=0x734 if sys.argv[1]==\"1\" else 0x738
m[off:off+4]=(1<<5).to_bytes(4,\"little\")
" $1; }
say() { echo; echo "$(date +%T)  $*"; }
say "3 秒後に A を始めます"; sleep 3
say "A: 明るさを一番暗い段 (1) に（6 秒）"; echo 1 > $bl; sleep 6; echo 7 > $bl
say "（休み 4 秒）"; sleep 4
say "B: GPIO3_5 を 1 に（6 秒）"; gp 1; sleep 6; gp 0
say "（休み 4 秒）"; sleep 4
say "C: 明るさ 0 + GPIO3_5 を 1 に（6 秒）"; echo 0 > $bl; gp 1; sleep 6; gp 0; echo 7 > $bl
say "おわり"
