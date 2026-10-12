#!/bin/sh
# 電池だけで動かし、状態を切り替えながら BATT 端子の電圧を記録する（root で）。
# アルカリ電池は内部抵抗があるので、流れる電流が増えるほど電圧が下がる。
# 状態ごとの電圧の差から、何が電気を食っているかの大小がわかる（電流計の代わり）。
# 電池の自然な下がりを打ち消すため、基準の状態（base）を間に挟む。
#
# usage: loadtest.sh LOG [music]
#   5V（ハブや USB）が外れるまで最大 10 分待ってから始める。終わったら画面の明るさを戻す
#   music を付けると MUCOM88 の再生（内蔵スピーカー）も測る
log=$1; music=$2
iio=/sys/bus/iio/devices/iio:device0
bl=/sys/class/backlight/backlight@0; sbl=/sys/class/backlight/backlight@1
bl0=$(cat $bl/brightness); sbl0=$(cat $sbl/brightness)
PH=${PH:-45}  # 1 つの状態の秒数（試しに動かすときは PH=3 NOWAIT=1）

restore() { echo $bl0 > $bl/brightness; echo $sbl0 > $sbl/brightness; }
trap 'restore; [ -n "$busy" ] && kill $busy 2>/dev/null' EXIT INT TERM

v5() { read r < $iio/in_voltage15_raw; [ $r -gt 2200 ]; }  # 2200 × 1.8 mV ≈ 4 V
echo "# waiting for 5V to go away" >> $log
i=0; [ -n "$NOWAIT" ] || while v5; do sleep 2; i=$((i+2)); [ $i -ge 600 ] && { echo "# 5V still present, abort" >> $log; exit 1; }; done
echo "# start $(date +%T) bl=$bl0 sbl=$sbl0" >> $log
sleep 10

phase() {  # 名前を付けて PH 秒、1 秒ごとに BATT（ch7）の生の値を記録する
	n=0; while [ $n -lt $PH ]; do
		read r < $iio/in_voltage7_raw; read v < $iio/in_voltage15_raw
		echo "$1 $n $r $v" >> $log; n=$((n+1)); sleep 1
	done
}
base() { restore; phase base; }

base
echo 0 > $bl/brightness; phase bl_off
base
echo 0 > $sbl/brightness; phase sub_off
base
sh -c 'while :; do :; done' & busy=$!; phase cpu; kill $busy; busy=
base
if [ "$music" = music ]; then
	su user -c "sh /home/user/mucom88/mucplay.sh sampl1.muc $((PH + 5))" & phase music; wait
	base
fi
echo "# end $(date +%T)" >> $log
sync
