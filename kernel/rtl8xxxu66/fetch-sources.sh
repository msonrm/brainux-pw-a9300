#!/bin/sh
# Linux v6.6 の drivers/net/wireless/realtek/rtl8xxxu を kernel.org から取ってきて、
# チェックサムを確かめ、6.1 用のパッチを当てる。src/ にできる。
set -eu
cd "$(dirname "$0")"
BASE='https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git/plain/drivers/net/wireless/realtek/rtl8xxxu'
TAG=v6.6
rm -rf src && mkdir src
for f in $(awk '{print $2}' SHA256SUMS.v6.6); do
	curl -fsSL "$BASE/$f?h=$TAG" -o "src/$f"
done
(cd src && sha256sum -c --quiet ../SHA256SUMS.v6.6)
patch -d src -p1 < 6.1-compat.patch
cp Kbuild src/Makefile
echo "ready: src/"
