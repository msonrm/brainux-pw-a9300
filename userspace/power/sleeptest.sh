#!/bin/sh
# バックライトとサスペンドの試験。sudo sh ~/sleeptest.sh で動かす
bl=/sys/class/backlight/backlight@0/brightness
say() { echo; echo "$(date +%T)  $*"; }
say "1: 3 秒後に、明るさを 0 にします（5 秒）"; sleep 3
echo 0 > $bl; sleep 5; echo 7 > $bl
say "1: 明るさを戻しました"
sleep 3
say "2: 5 秒後にサスペンドします。画面が消えたら 10 秒ほど待って、キーを 1 つ押してください"
sleep 5; sync
# systemctl suspend は眠るのを待たずに戻る。PM: suspend exit が出るまで待つ
since=$(date "+%F %T")
systemctl suspend
until journalctl -k --since "$since" --no-pager -q | grep -q "PM: suspend exit"; do sleep 1; done
say "2: 起きました"
journalctl -k --since "$since" --no-pager | grep -E "PM: suspend (entry|exit)"
echo "（眠っていた時間は userspace/power/sleepwatch.py で測る。この機種の s2idle は時計を止めない）"
