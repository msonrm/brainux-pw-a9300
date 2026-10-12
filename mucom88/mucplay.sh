#!/bin/sh
# Brain 上で: sh mucplay.sh <曲.muc> [秒数]
# MUCOM88 が作った音を、ファイルを通さずにそのまま aplay へ流して鳴らす
cd "$(dirname "$0")"
f="$1"; len=${2:+-l $2}
./mucom88 -x $len -w - -c "$f" 2>>mucplay.log | aplay -q -t raw -f cd --buffer-time=500000 2>>mucplay.log
