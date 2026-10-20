#!/bin/sh
# Brainux（PW-A9300、RAM 112MB）を安定させる設定をまとめて入れる。何度実行しても同じ結果になる。
# usage: sudo sh setup-stability.sh [--dry-run]
#   1. /proc/cpu/alignment を fixup に（unaligned access の値が狂うのを防ぐ）
#   2. apt-daily / apt-daily-upgrade / man-db の timer を止める（apt-get が約 50MB 使い OOM になる）
#   3. 128MB のスワップファイル /swapfile と zswap
#   4. 画面に出すカーネルのメッセージを重大なものだけに（ログイン画面が乱れるのを防ぐ）
#   5. 使わないものを止める（起動を短く、常駐を減らす）。USB ケーブル用の 2 つは peripheral のときだけ動かす。journal は 50MB まで
set -eu
cd "$(dirname "$0")"
run() { if [ "$DRY" = 1 ]; then echo "+ $*"; else sh -c "$*"; fi; }
DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1

run "install -m644 etc/tmpfiles.d/alignment.conf etc/tmpfiles.d/zswap.conf /etc/tmpfiles.d/"
run "echo 2 > /proc/cpu/alignment"
run "echo Y > /sys/module/zswap/parameters/enabled"
run "systemctl disable --now apt-daily.timer apt-daily-upgrade.timer man-db.timer"
if [ ! -e /swapfile ]; then
	run "dd if=/dev/zero of=/swapfile bs=1M count=128 status=none && chmod 600 /swapfile && mkswap /swapfile >/dev/null"
fi
run "grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab"
run "swapon --show=NAME --noheadings 2>/dev/null | grep -q /swapfile || /usr/sbin/swapon /swapfile"
run "install -D -m644 etc/sysctl.d/90-brain-console-loglevel.conf /etc/sysctl.d/90-brain-console-loglevel.conf"
run "sysctl -q -p /etc/sysctl.d/90-brain-console-loglevel.conf"
# 5. 使わないもの: brain-config（cpufreq のないカーネルでガバナーを変えるだけ）、triggerhappy（割り当てが空）、
#    e2scrub（LVM がない）、cron（中身はどれも systemd のタイマーに任せて何もしない）、avahi（IP でつなぐ）、
#    シリアルの getty（console=ttyAMA0 から generator が作るので disable では止まらず mask）
run "systemctl disable --now brain-config.service triggerhappy.socket triggerhappy.service e2scrub_reap.service e2scrub_all.timer cron.service avahi-daemon.socket avahi-daemon.service"
run "systemctl mask --now serial-getty@ttyAMA0.service"
#    triggerhappy の udev ルールは、本体を止めても入力デバイスごとに th-cmd を起こして失敗するので消す
run "ln -sf /dev/null /etc/udev/rules.d/60-triggerhappy.rules"
for u in ethernet_gadget networking; do
	run "install -D -m644 etc/systemd/system/$u.service.d/brain-only-peripheral.conf /etc/systemd/system/$u.service.d/brain-only-peripheral.conf"
done
run "install -D -m644 etc/systemd/journald.conf.d/brain-size.conf /etc/systemd/journald.conf.d/brain-size.conf"
run "systemctl daemon-reload"
run "systemctl restart systemd-journald"
run sync
echo "done (alignment: $(sed -n 's/User faults:[[:space:]]*//p' /proc/cpu/alignment))"
