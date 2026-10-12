#!/bin/sh
# OPEN MUCOM88 を Brain (armel, ARM926) 向けにクロスビルドする。
# 要: arm-linux-gnueabi-gcc / arm-linux-gnueabi-g++ (Debian: g++-arm-linux-gnueabi), git
# できるもの: out/mucom88 (Brain 用), out/ に配布用データ一式
set -eu
cd "$(dirname "$0")"
HERE=$PWD
REV=2c8adbed5b21a8876bc530925c8308048e254dfc
[ -d upstream ] || git clone -q https://github.com/onitama/mucom88 upstream
cd upstream
git checkout -q "$REV"
git apply --check "$HERE"/0001-*.patch 2>/dev/null && git apply "$HERE"/0001-*.patch
cd src
make OS_SDL=0 OBJS_DIR=objs-armel TARGET_NAME=mucom88-armel \
	CXX=arm-linux-gnueabi-g++ CC=arm-linux-gnueabi-gcc \
	COMMON_FLAGS="-Wall -O2 -march=armv5te -mtune=arm926ej-s" \
	LDFLAGS="-static-libstdc++ -static-libgcc" -j"$(nproc)"
mkdir -p "$HERE/out"
cp mucom88-armel "$HERE/out/mucom88"
cp ../package/sampl1.muc ../package/sampl2.muc ../package/sampl3.muc \
   ../package/voice.dat ../package/mucompcm.bin ../package/license.txt "$HERE/out/"
cp "$HERE"/rhythm/2608_*.WAV "$HERE"/rhythm/PROVENANCE_2608modoki2*.txt "$HERE/out/"
cp "$HERE/mucplay.sh" "$HERE/out/"
echo "built: $HERE/out"
