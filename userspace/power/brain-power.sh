#!/bin/sh
# 電源の様子を 1 行で出す（root 不要）。LRADC の値は mxs-lradc-adc（iio）から読む
#   batt: BATT 端子（LRADC ch7）  5v: VDD5V（ch15。USB や OTG のハブから 5V が来ていると約 5000）
#   vddd: コアの電圧（ch13）       vddio: I/O の電圧（ch10）
#   pins: 電池の見張りピン GPIO4_4/4_6/4_7/4_8（battpins、root のときだけ。新しい電池で 1111）
#   bvraw/bv: 電池の電圧（LRADC ch1。battvolt、root のときだけ。GPIO3_2 を一瞬 1 にして読む）。bv は分圧の比を 1 とした mV で、比はまだ決めていない
#   ※ batt は昇圧後の電圧で、電池の減りでは変わらない
iio=/sys/bus/iio/devices/iio:device0
mv() { awk -v r=$(cat $iio/in_voltage$1_raw) -v s=$(cat $iio/in_voltage$1_scale) 'BEGIN{printf "%d", r*s}'; }
b=$(mv 7); v5=$(mv 15)
src=batt; [ "$v5" -gt 4000 ] && src=5v
# 電池の見張りピン（root のときだけ。電池が減ると 0 になる）
pins=$(/usr/local/bin/battpins 2>/dev/null | tr -d ' ' | sed 's/4_[0-9]=//g')
bv=$(/usr/local/bin/battvolt 2>/dev/null)
echo "src=$src batt=${b}mV 5v=${v5}mV vddd=$(mv 13)mV vddio=$(mv 10)mV${pins:+ pins=$pins}${bv:+ $bv}"
