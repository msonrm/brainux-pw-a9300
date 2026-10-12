# 入れ方（PW-A9300 + Brainux 2026-03-25）

元のファイルは必ず別名で残してください。Brain は再起動すると状況によって WinCE から立ち上がり直すことがあり、失敗すると戻すのに手間がかかります。

## 0. 用意するもの

- Debian 系の PC（クロスビルド用）: `gcc-arm-linux-gnueabi g++-arm-linux-gnueabi make bc bison flex libssl-dev git curl python3`
- Brainux の SD カード
- 音: 自分の Brain から取り出した `ymu818-brain.bin`（[audio-ymu818.md](audio-ymu818.md)）
- Wi-Fi: OTG ケーブル、電源付き USB ハブ、TL-WN725N、`wpasupplicant`、`rtlwifi/rtl8188eufw.bin`

## 1. 安定化（先にやる）

Brain で:

```sh
sudo sh system/setup-stability.sh
```

unaligned access の fixup、apt の自動更新の停止、スワップ 128MB、zswap が入ります。

## 2. カーネル（音声ドライバ）

PC で:

```sh
git clone https://github.com/brain-hackers/linux-brain
cd linux-brain
git checkout a9f534c7
git apply ../brainux-sound-wifi-mucom88/kernel/0001-ASoC-YMU818-audio-for-Brain-PW-A9300.patch
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabi- O=../build brain_defconfig
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabi- O=../build -j8 zImage dtbs modules
```

`git apply` で当てると、カーネルの版は `6.1.70-ga9f534c7f53e-dirty` になります。コミットすると版の名前が変わるので、手順 4 のモジュールも同じビルドから作ってください。

SD カードの boot パーティションで:

1. `zImage` を `zImage.orig` に改名し、`../build/arch/arm/boot/zImage` を置く
2. `imx28-pwa7200.dtb` を `imx28-pwa7200.dtb.orig` に改名し、`../build/arch/arm/boot/dts/imx28-pwa7200.dtb` を置く

rootfs パーティションで:

3. `make ... modules_install INSTALL_MOD_PATH=<rootfs>` で `/usr/lib/modules/6.1.70-ga9f534c7f53e-dirty/` を作る（Chromebook のように rootfs に直接書けないときは、tar で固めてホームに置き、Brain で展開する）
4. `ymu818-brain.bin` を `/usr/lib/firmware/` に置く

USB で PC とつないで使う人は、DTB を置いたあとで `sudo brain-config nonint do_usb peripheral` を実行してから再起動してください（新しい DTB は `dr_mode = "host"` です）。

起動したら:

```sh
uname -r                      # 6.1.70-ga9f534c7f53e-dirty
aplay -l                      # card 0: mxsymu818
amixer sset Speaker 12
speaker-test -c 2 -r 44100 -t sine -f 1000 -l 1
sudo alsactl store
```

戻すときは `zImage.orig` と `imx28-pwa7200.dtb.orig` を元の名前に戻します。

## 3. 音楽ファイルを鳴らす

```sh
aplay music.wav
mpg123 music.mp3              # Brainux には入っていないので apt で入れる
sh userspace/play.sh music.wav   # SSH が切れても止まらない（nohup）。途切れは ~/play.log
```

## 4. Wi-Fi（rtl8xxxu66）

PC で、手順 2 と同じビルドを使って:

```sh
sh kernel/rtl8xxxu66/fetch-sources.sh
sh kernel/rtl8xxxu66/build.sh ../linux-brain ../build
```

Brain で（`sudo brain-config nonint do_usb host` で USB をホストにしてから）:

```sh
sudo setsid nohup sh swap-to-rtl8xxxu66.sh rtl8xxxu66.ko &
cat /var/log/wifi-swap.log
nmcli dev wifi connect <SSID> password <パスワード>
```

## 5. MUCOM88

```sh
sh mucom88/build-armel.sh     # PC で
# mucom88/out/ を Brain の ~/mucom88 にコピーして
cd ~/mucom88 && sh mucplay.sh sampl1.muc
```
