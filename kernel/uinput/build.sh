#!/bin/sh
# usage: sh build.sh <linux-brain のソース> <ビルド出力 (O=)>
# linux-brain の brain_defconfig は CONFIG_INPUT_UINPUT が無効なので、
# ツリーの drivers/input/misc/uinput.c を外付けモジュールとして作る。できるのは src/uinput.ko
set -eu
cd "$(dirname "$0")"
mkdir -p src
cp "$1/drivers/input/misc/uinput.c" src/
printf 'obj-m := uinput.o\n# uinput.c は "../input-compat.h" を読む\nccflags-y := -I$(srctree)/drivers/input/misc\n' > src/Kbuild
make -C "$1" O="$2" ARCH=arm CROSS_COMPILE=arm-linux-gnueabi- M="$PWD/src" modules
