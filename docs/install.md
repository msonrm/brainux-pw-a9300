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

unaligned access の fixup、apt の自動更新の停止、スワップ 128MB、zswap、画面に出すカーネルのメッセージを重大なものだけにする設定（ログイン画面の上に Wi-Fi の知らせなどが書き込まれて乱れるのを防ぐ）が入ります。

## 2. カーネル（音声ドライバ・バックライト・蓋）

PC で:

```sh
git clone https://github.com/brain-hackers/linux-brain
cd linux-brain
git checkout a9f534c7
git apply ../brainux-pw-a9300/kernel/0001-ASoC-YMU818-audio-for-Brain-PW-A9300.patch
git apply ../brainux-pw-a9300/kernel/0002-pwm-mxs-drive-inactive-level-before-stop.patch
git apply ../brainux-pw-a9300/kernel/0003-brain-kbd-i2c-lid-switch-and-wakeup.patch
git apply ../brainux-pw-a9300/kernel/0008-dmaengine-mxs-dma-do-not-reset-the-block-on-resume.patch
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabi- O=../build brain_defconfig
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabi- O=../build -j8 zImage dtbs modules
```

0002 はバックライトを明るさ 0 やサスペンドで本当に消すため、0003 は蓋を閉じたら眠り、開けたら（またはキーで）起きるためのものです（起こすのに使った「入/切」は捨てます）、0008 は眠って起きたあとも音が出るようにするためのものです（[power.md](power.md)）。音だけでよければ 0001 だけでも動きます。

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
amixer sset Headphone 8       # 起動時の alsactl init が 24 にする。イヤホンには大きい
speaker-test -c 2 -r 44100 -t sine -f 1000 -l 1
sudo alsactl store
```

戻すときは `zImage.orig` と `imx28-pwa7200.dtb.orig` を元の名前に戻します。

サスペンド（0002・0003 を当てたとき）:

```sh
sudo install -D -m 644 system/etc/systemd/sleep.conf.d/brain-s2idle.conf /etc/systemd/sleep.conf.d/brain-s2idle.conf
sudo install -D -m 644 system/etc/systemd/logind.conf.d/brain-power-key.conf /etc/systemd/logind.conf.d/brain-power-key.conf
sudo systemctl kill -s HUP systemd-logind
```

1 つ目は眠り方を s2idle にします（`deep` だと 1 秒ほどで起きてしまう）。次のサスペンドから効きます（`/sys/power/mem_sleep` は起動直後 `s2idle [deep]` で、systemd が眠るときに `[s2idle]` へ切り替えます）。2 つ目で「入/切」は、短く押すと眠る・長押しで電源オフになります（Brainux の既定は押すと電源オフ）。蓋を閉じるか「入/切」を押すと眠り、蓋を開けるかキーを押すと起きます。

起きたあと Wi-Fi が戻らないことへの手当て（手順 4 の rtl8xxxu66 を入れたとき）:

```sh
sudo install -D -m 755 system/usr/local/bin/brain-wifi-reprobe /usr/local/bin/brain-wifi-reprobe
sudo install -D -m 755 system/usr/lib/systemd/system-sleep/brain-wifi-reprobe /usr/lib/systemd/system-sleep/brain-wifi-reprobe
```

rtl8xxxu66 には眠る・起きるの処理がなく、起きるたびに子機の初期化をやり直します。それがときどきファームウェアの書き込みで失敗し（`probe of 1-1.3:1.0 failed with error -11`）、Wi-Fi が来なくなります。起きてから 30 秒の間に、ドライバのついていない子機を見つけたら、USB の `authorized` を 0→1 にして初期化をやり直させます（子機を挿し直すのと同じ）。やったことは `journalctl -u brain-wifi-reprobe` に出ます。

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
