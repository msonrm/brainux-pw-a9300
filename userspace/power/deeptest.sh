#!/bin/sh
# deep（suspend-to-mem）で 1 回眠らせ、起きたあとの様子を記録する。root で、SSH が切れても
# 続くように別のユニットで動かす:
#   sudo systemd-run --unit=deeptest --collect -p StandardOutput=file:/tmp/deeptest.log \
#        sh /path/to/deeptest.sh [level]
# level は kernel/0009 の mxs_pm.level（0 = WFI だけ、1 = DRAM のセルフリフレッシュ、
# 2 = さらに PLL0 を止める）。0009 の入っていないカーネルでは無視する。
# 起こすのはキー・蓋・入/切。眠った長さは RTC の秒のカウンタと時計の両方で出し、
# 0009 が時計に眠っていた時間を足せているかを比べる（足せていなければ時計の側が 0 秒近くになる）。
lvl=${1:-}
say() { echo "$(date +%T) $*"; }
rtcsec() {
	python3 -c 'import mmap,os,struct
fd=os.open("/dev/mem",os.O_RDONLY|os.O_SYNC)
m=mmap.mmap(fd,0x1000,mmap.MAP_SHARED,mmap.PROT_READ,offset=0x80056000)
print(struct.unpack_from("<I",m,0x30)[0])'
}
p=/sys/module/mxs_pm/parameters/level
if [ -n "$lvl" ] && [ -w $p ]; then
	echo "$lvl" > $p
fi
say "kernel $(uname -v | cut -c1-20) level=$(cat $p 2>/dev/null || echo none)"
cat /proc/interrupts > /tmp/deeptest.irq.before
r0=$(rtcsec); t0=$(date +%s)
echo deep > /sys/power/mem_sleep
say "suspend"
sync
echo mem > /sys/power/state; rc=$?
r1=$(rtcsec); t1=$(date +%s)
echo s2idle > /sys/power/mem_sleep
say "back rc=$rc: slept $((r1 - r0)) s by the RTC, $((t1 - t0)) s by the clock"
cat /proc/interrupts > /tmp/deeptest.irq.after
paste /tmp/deeptest.irq.before /tmp/deeptest.irq.after |
	awk '$1 ~ /:$/ { n = NF / 2; if ($2 != $(n + 2)) print "irq", $1, $2, "->", $(n + 2), $NF }'
journalctl -k -b --no-pager -o short-precise | grep -E "PM: suspend|mxs" | tail -4
/usr/local/bin/brain-wifi-reprobe
for i in $(seq 60); do
	[ "$(nmcli -t -f STATE g)" = connected ] && { say "network connected"; break; }
	sleep 1
done
say "done"
