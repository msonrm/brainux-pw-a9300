#!/bin/sh
# Wi-Fi の負荷試験（Chromebook など母艦側で実行）: ping を打ちながら、1 分ごとに SSH でつなぎ、3 回に 1 回 5MB を送る
# usage: sh wifi-stress.sh <Brain の IP> [秒数=1200]
H=$1; S=$(dirname "$0"); out=$S/wifi-stress.txt
ping -i 2 -W 2 -D -w ${2:-1200} $H > $S/wifi-ping2.txt 2>&1 &
pp=$!
head -c 5000000 /dev/urandom > $S/rand5m.bin
n=0
while kill -0 $pp 2>/dev/null; do
	n=$((n+1)); t0=$(date +%s)
	if [ $((n % 3)) -eq 0 ]; then
		r=$(python3 $S/throttle.py 300000 < $S/rand5m.bin 2>/dev/null | timeout 120 sshpass -p brain ssh -o ConnectTimeout=40 user@$H 'cat > /tmp/r.bin; md5sum < /tmp/r.bin; rm /tmp/r.bin; tail -1 /var/log/brain-watch.log | cut -c1-80' 2>&1 | tr '\n' ' ')
	else
		r=$(timeout 60 sshpass -p brain ssh -o ConnectTimeout=40 user@$H 'uptime; tail -1 /var/log/brain-watch.log | cut -c1-80' 2>&1 | tr '\n' ' ')
	fi
	echo "$(date +%T) #$n $(( $(date +%s) - t0 ))s $r" >> $out
	sleep 60
done
