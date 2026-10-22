#!/bin/sh
# X のキーの配置で、枠の右のボタンの文字大・文字小（subpaneld が送る KEY_F21・F22）を F21・F22 にする。
# 何度実行しても同じ結果になる。xkb-data を更新したら、もう一度実行する（rules を作り直す）。
# usage: sudo sh setup-xkb.sh [--dry-run]
#   標準の配置（inet(evdev)）では XF86TouchpadToggle・XF86TouchpadOn になり、SDL 2 のアプリに届かない。
#   inet(evdev) はレイアウトより後に重なるので、上書きは rules のオプションでしかできない。X の evdev の
#   ドライバは rules を必ず「evdev」にする（別の名前の rules は使えない）ので、パッケージの rules/evdev を
#   dpkg-divert で evdev.distrib に退け、そこに brain:fkeys の 1 行を足したものを rules/evdev に置く
#   （xkb-data を更新しても、パッケージは evdev.distrib のほうを書き換える）。効くのは X を起動し直してから
#   戻すとき: rm /etc/X11/xorg.conf.d/30-brain-fkeys.conf /usr/share/X11/xkb/rules/evdev &&
#             dpkg-divert --remove --rename /usr/share/X11/xkb/rules/evdev
set -eu
cd "$(dirname "$0")"
run() { if [ "$DRY" = 1 ]; then echo "+ $*"; else sh -c "$*"; fi; }
DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1
RULES=/usr/share/X11/xkb/rules

run "dpkg-divert --quiet --add --rename --divert $RULES/evdev.distrib $RULES/evdev"
[ "$DRY" = 1 ] || grep -q '^! option[[:space:]]*=[[:space:]]*symbols' $RULES/evdev.distrib || { echo "no '! option = symbols' in $RULES/evdev.distrib" >&2; exit 1; }
run "install -D -m644 usr/share/X11/xkb/symbols/brain /usr/share/X11/xkb/symbols/brain"
run "sed '/^! option[[:space:]]*=[[:space:]]*symbols/a\\  brain:fkeys\t\t\t=\t+brain(fkeys)' $RULES/evdev.distrib > $RULES/evdev.tmp && mv $RULES/evdev.tmp $RULES/evdev"
run "install -D -m644 etc/X11/xorg.conf.d/30-brain-fkeys.conf /etc/X11/xorg.conf.d/30-brain-fkeys.conf"
