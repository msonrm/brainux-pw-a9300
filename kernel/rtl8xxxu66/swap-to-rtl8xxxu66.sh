#!/bin/sh
# Brain 上で root として: setsid nohup sh swap-to-rtl8xxxu66.sh <rtl8xxxu66.ko> &
# r8188eu を外して rtl8xxxu66 に載せ替える。90 秒以内にゲートウェイへ ping が通らなければ r8188eu に戻す。
# Wi-Fi 越しに動かすので、途中で SSH が切れても最後まで進むようにしている。
log=/var/log/wifi-swap.log
say() { echo "$(date +%T) $*" >> $log; sync; }
ko="$1"
dst=/usr/lib/modules/$(uname -r)/extra
bl=/etc/modprobe.d/r8188eu-blacklist.conf

say "start"
mkdir -p $dst && cp "$ko" $dst/rtl8xxxu66.ko && depmod -a && say "installed"
echo "blacklist r8188eu" > $bl
sync
gw=$(ip route | awk '/^default/{print $3; exit}')
say "gw=$gw"
rmmod r8188eu; say "rmmod r8188eu: $?"
sleep 2
modprobe rtl8xxxu66; say "modprobe rtl8xxxu66: $?"
i=0
while [ $i -lt 18 ]; do
	sleep 5; i=$((i+1))
	if ping -c 1 -W 2 "$gw" >/dev/null 2>&1; then
		say "OK after $((i*5))s: $(ip -br a | grep wl)"
		exit 0
	fi
done
say "no link after 90s, reverting"
dmesg | grep -iE "rtl8xxxu|8188" | tail -20 >> $log
rmmod rtl8xxxu66
rm -f $bl
sync
modprobe r8188eu; say "reverted to r8188eu: $?"
