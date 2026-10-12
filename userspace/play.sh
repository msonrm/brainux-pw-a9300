#!/bin/sh
# Brain 上で: sh ~/play.sh <ファイル>
# SSH が切れても止まらないよう nohup で鳴らし、xrun などを ~/play.log に残す
f="$1"; log=~/play.log
: > "$log"
case "$f" in
  *.mp3) nohup mpg123 -q -o alsa "$f" >>"$log" 2>&1 & ;;
  *)     nohup aplay -q "$f" >>"$log" 2>&1 & ;;
esac
echo "started pid $!"
