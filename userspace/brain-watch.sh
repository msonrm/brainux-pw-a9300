#!/bin/sh
# 固まったときに直前の様子がわかるよう、10 秒ごとに 1 行ずつ書いて fsync する
log=/var/log/brain-watch.log
while :; do
	m=$(awk '/MemAvailable|SwapFree|^Dirty/{printf "%s%s ", $1, $2}' /proc/meminfo)
	l=$(cut -d" " -f1-3 /proc/loadavg)
	w=$(awk 'NR>2{print $1 $3 $4}' /proc/net/wireless 2>/dev/null | tr "\n" " ")
	t=$(ps -eo rss=,comm= --sort=-rss | head -3 | awk '{printf "%s:%s ", $2, $1}')
	u=$(cat /proc/uptime | cut -d" " -f1)
	p=$(/usr/local/bin/brain-power.sh 2>/dev/null)
	echo "$(date +%T) up=$u load=$l $m pwr=[$p] wifi=[$w] top=[$t]" >> $log
	sync -d $log 2>/dev/null || sync
	sleep 10
done
