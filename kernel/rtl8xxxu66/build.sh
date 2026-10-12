#!/bin/sh
# usage: sh build.sh <linux-brain のソース> <ビルド出力 (O=)>
# 先に fetch-sources.sh を実行しておく。できるのは src/rtl8xxxu66.ko
set -eu
cd "$(dirname "$0")"
make -C "$1" O="$2" ARCH=arm CROSS_COMPILE=arm-linux-gnueabi- M="$PWD/src" modules
