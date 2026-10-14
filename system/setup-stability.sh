#!/bin/sh
# Brainux（PW-A9300、RAM 112MB）を安定させる設定をまとめて入れる。何度実行しても同じ結果になる。
# usage: sudo sh setup-stability.sh [--dry-run]
#   1. /proc/cpu/alignment を fixup に（unaligned access の値が狂うのを防ぐ）
#   2. apt-daily / apt-daily-upgrade / man-db の timer を止める（apt-get が約 50MB 使い OOM になる）
#   3. 128MB のスワップファイル /swapfile と zswap
#   4. 画面に出すカーネルのメッセージを重大なものだけに（ログイン画面が乱れるのを防ぐ）
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
run sync
echo "done (alignment: $(sed -n 's/User faults:[[:space:]]*//p' /proc/cpu/alignment))"
