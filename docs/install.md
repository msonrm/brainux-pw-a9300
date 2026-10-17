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

unaligned access の fixup、apt の自動更新の停止、スワップ 128MB、zswap、画面に出すカーネルのメッセージを重大なものだけにする設定（ログイン画面の上に Wi-Fi の知らせなどが書き込まれて乱れるのを防ぐ）が入り、使わないサービス（brain-config・triggerhappy・e2scrub・cron・avahi・シリアルの getty）を止め、journal を 50MB までにします（[stability.md](stability.md) の 4）。USB ケーブルでつなぐときのサービスは、OTG が peripheral の DTB のときだけ動くようになります。

固まったときの手がかりを残す（調べもの用。なくても動きます）:

```sh
sudo install -D -m 644 system/etc/systemd/journald.conf.d/sync.conf /etc/systemd/journald.conf.d/sync.conf
sudo install -m 755 userspace/brain-watch.sh /usr/local/bin/brain-watch.sh
sudo install -D -m 644 userspace/brain-watch.service /etc/systemd/system/brain-watch.service
sudo systemctl daemon-reload && sudo systemctl restart systemd-journald && sudo systemctl enable --now brain-watch
```

journald を 10 秒ごとに書き出させ、10 秒ごとに空きメモリ・負荷・Wi-Fi の電波などを `/var/log/brain-watch.log` に 1 行残します（[stability.md](stability.md) の 3）。電源の様子も残すには、手順 2 の `brain-power.sh` を入れます。

## 2. カーネル（音声ドライバ・バックライト・蓋・サブ液晶・眠り方）

PC で:

```sh
git clone https://github.com/brain-hackers/linux-brain
cd linux-brain
git checkout a9f534c7
git apply ../brainux-pw-a9300/kernel/0001-ASoC-YMU818-audio-for-Brain-PW-A9300.patch
git apply ../brainux-pw-a9300/kernel/0002-pwm-mxs-drive-inactive-level-before-stop.patch
git apply ../brainux-pw-a9300/kernel/0003-brain-kbd-i2c-lid-switch-and-wakeup.patch
git apply ../brainux-pw-a9300/kernel/0004-drm-tiny-brain-st7586-fix-the-2-bit-pixel-of-each-byte.patch
git apply ../brainux-pw-a9300/kernel/0005-iio-adc-mxs-lradc-adc-only-clear-our-own-interrupt-flags.patch
git apply ../brainux-pw-a9300/kernel/0006-Input-mxs-lradc-ts-only-clear-the-touch-detect-flag.patch
git apply ../brainux-pw-a9300/kernel/0007-ARM-dts-imx28-pwa7200-give-the-bookmark-home-and-dictionary-menu-keys-a-code.patch
git apply ../brainux-pw-a9300/kernel/0008-dmaengine-mxs-dma-do-not-reset-the-block-on-resume.patch
git apply ../brainux-pw-a9300/kernel/0009-ARM-mxs-pm-put-the-DRAM-into-self-refresh-in-suspend-to-mem-on-i.MX28.patch
git apply ../brainux-pw-a9300/kernel/0010-drm-tiny-brain-lq050j1ug01-stop-the-LCDIF-for-suspend-and-recover-a-stuck-transfer.patch
git apply ../brainux-pw-a9300/kernel/0011-spi-mxs-Fix-chipselect-glitch.patch
git apply ../brainux-pw-a9300/kernel/0012-ASoC-ymu818-turn-the-amp-off-for-suspend.patch
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabi- O=../build brain_defconfig
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabi- O=../build -j8 zImage dtbs modules
```

0002 はバックライトを明るさ 0 やサスペンドで本当に消すため、0003 は蓋を閉じたら眠り、開けたら（またはキーで）起きるためのものです（起こすのに使った「入/切」は捨てます）。0004〜0007 はサブ液晶と枠のボタンのためで、subpaneld はこれを前提にしています。0004 はサブ液晶の 3 画素ごとに縦線が出るのを直し、0005・0006 はタッチが押されたまま固まるのを直し（タッチと電池の電圧を読む ADC が割り込みのフラグを取り合っていた）、0007 はメイン液晶の枠のしおり・Home・辞書メニューのボタンに F13〜F15 を割り当てます（DTS の変更なので DTB に入ります。どれも [subpanel.md](subpanel.md)）。0008 は眠って起きたあとも音が出るようにするため、0009 は `deep` で DRAM をセルフリフレッシュにして眠り、眠っていた時間を時計に足すため、0010 はメイン液晶が眠る前に送りを止めて起きたら初期化し直し、送りが止まっても自分で戻るようにするため（どれも [power.md](power.md)）、0011 はサブ液晶の SPI がときどき 10 秒止まるのを直す上流の修正（[subpanel.md](subpanel.md)）、0012 は音を出したまま眠ってもイヤホンにノイズが出ないようにするためのものです（[audio-ymu818.md](audio-ymu818.md)）。0009 は眠り方が `deep` のときだけ働きます（カーネルの既定は s2idle。下の「サスペンド」の設定で `deep` にします）。音だけでよければ 0001 だけでも動きます。

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

サブ液晶・タッチ・ボタン（0004〜0007 を当てたとき）。サブ液晶をタッチパッドと状態の帯にし、メイン液晶の枠のボタンと「入/切」の表示を受け持つ常駐プログラム `subpaneld` を入れます（[subpanel.md](subpanel.md)）。Brainux のカーネルは uinput が無効なので、先に PC で、上と同じビルドから外付けモジュールにします:

```sh
sh kernel/uinput/build.sh ../linux-brain ../build     # kernel/uinput/src/uinput.ko ができる
```

Brain で:

```sh
sudo install -D -m 644 kernel/uinput/src/uinput.ko /usr/lib/modules/$(uname -r)/extra/uinput.ko
sudo depmod -a
sudo install -D -m 644 system/etc/modules-load.d/uinput.conf /etc/modules-load.d/uinput.conf
sudo install -D -m 644 system/etc/udev/rules.d/72-brain-subpanel-seat.rules /etc/udev/rules.d/72-brain-subpanel-seat.rules
sudo install -D -m 644 system/etc/X11/xorg.conf.d/20-subpanel.conf /etc/X11/xorg.conf.d/20-subpanel.conf
sudo install -D -m 755 userspace/subpanel/subpaneld.py /usr/local/bin/subpaneld
sudo install -D -m 644 userspace/subpanel/subpaneld.service /etc/systemd/system/subpaneld.service
sudo systemctl daemon-reload && sudo systemctl enable subpaneld
cp ~/.jwmrc ~/.jwmrc.orig 2>/dev/null; cp system/home/user/.jwmrc ~/.jwmrc
```

udev のルールと X の設定は、X がサブ液晶を開かないようにするもので、X が起動する前に要るので、入れたら再起動します。起動すると、サブ液晶にタッチパッドと右端の状態の帯（音量・明るさ・電池・USB 給電）が出ます。`.jwmrc` は、メイン液晶の枠の Home ボタン（F14）で JWM のメニューを開く設定です（Brainux の設定を読み込んだうえで足す形）。しおり（F13）と辞書メニュー（F15）、枠の右の 7 つのボタンは空けてあります。

サスペンド（0002・0003 を当てたとき）:

```sh
sudo install -D -m 644 system/etc/systemd/sleep.conf.d/brain-sleep-mode.conf /etc/systemd/sleep.conf.d/brain-sleep-mode.conf
sudo install -D -m 644 system/etc/systemd/logind.conf.d/brain-power-key.conf /etc/systemd/logind.conf.d/brain-power-key.conf
sudo install -D -m 644 system/etc/systemd/logind.conf.d/brain-lid.conf /etc/systemd/logind.conf.d/brain-lid.conf
sudo install -D -m 644 system/etc/systemd/logind.conf.d/brain-sleep-delay.conf /etc/systemd/logind.conf.d/brain-sleep-delay.conf
sudo install -D -m 755 system/usr/lib/systemd/system-sleep/brain-subpanel-sleep /usr/lib/systemd/system-sleep/brain-subpanel-sleep
sudo systemctl mask NetworkManager-dispatcher.service
sudo systemctl kill -s HUP systemd-logind
```

1 つ目は眠り方を `deep` にします（0009 で DRAM をセルフリフレッシュにして眠り、眠っていた時間を時計に足します）。0009 を当てていないカーネルでは、`deep` は s2idle とほぼ同じ眠り方で、しかも眠っていた時間が時計から抜けるので（RTC が無効なため）、ファイルの `MemorySleepMode=` を `s2idle` に書き換えてください。次のサスペンドから効きます。2 つ目で「入/切」は、短く押すと眠る・長押しで電源オフになります（Brainux の既定は押すと電源オフ）。短押しで眠らせるのは subpaneld（サブ液晶に円と月を出してから眠りを頼む）なので、subpaneld を入れないときは、ファイルの `HandlePowerKey=ignore` を `suspend` に書き換えてください。3 つ目は、ハブを挿していても蓋を閉じたら眠るようにします（キーボードのマイコンが 5V の出入りを知らせ、動いている間にハブを挿すと logind が「ドッキング中」になって、既定では蓋を無視するため）。起きてから蓋を無視する時間も 30 秒から 5 秒にします。4 つ目と最後の行で、眠るまでの待ちを縮めます（NetworkManager が Wi-Fi を切るのを待つのは 1 秒まで、使っていない dispatcher を止める）。5 つ目は、眠る前にサブ液晶に月を出させます。蓋を閉じるか「入/切」を押すと眠り、蓋を開けるかキーを押すと起きます。

起きたあと Wi-Fi が戻らないことへの手当て（手順 4 の rtl8xxxu66 を入れたとき）:

```sh
sudo install -D -m 755 system/usr/local/bin/brain-wifi-reprobe /usr/local/bin/brain-wifi-reprobe
sudo install -D -m 755 system/usr/lib/systemd/system-sleep/brain-wifi-reprobe /usr/lib/systemd/system-sleep/brain-wifi-reprobe
```

rtl8xxxu66 には眠る・起きるの処理がなく、起きるたびに子機の初期化をやり直します。それがときどきファームウェアの書き込みで失敗し（`probe of 1-1.3:1.0 failed with error -11`）、Wi-Fi が来なくなります。起きてから 90 秒の間に、ドライバのついていない子機を見つけたら、子機がつながっているハブのポートの電源を 8 秒切って戻します（子機を挿し直すのと同じ。3 回まで）。動いている最中にハブを挿したときは、下の brain-5v-ilimit が同じものを起こします。ハブはポートの電源をまとめて切るので、同じハブにつないだほかの機器も一緒に切れます。やったことは `journalctl -u brain-wifi-reprobe` に出ます。

5V（ハブ・USB 給電）から電気を取る手当て（Chromebook でビルドして Brain に送る）:

```sh
arm-linux-gnueabi-gcc -O2 -march=armv5te -static -o brain-5v-ilimit userspace/power/brain-5v-ilimit.c
# Brain で
sudo install -D -m 755 brain-5v-ilimit /usr/local/bin/brain-5v-ilimit
sudo install -D -m 644 userspace/power/brain-5v-ilimit.service /etc/systemd/system/brain-5v-ilimit.service
sudo systemctl daemon-reload && sudo systemctl enable --now brain-5v-ilimit
```

起動したときに、5V から取れる電流の上限を 480 mA に上げます（WinCE が 100 mA のまま残すことがあり、足りない分は電池から取られます）。そのあと常駐し、動いている最中や眠っている間にハブを挿したら、i.MX28 の 4P2（5V から作る電源）を立ち上げ直します。i.MX28 は 5V の抜き差しのたびにソフトで電源の経路を切り替える作りで、Linux にはその処理がないため、手当てしないと挿し直したあとも電池から取り続けます（[power-wince.md](power-wince.md)）。続けて、Wi-Fi の子機の初期化が失敗していれば `brain-wifi-reprobe` でやり直します。効いたかは `journalctl -u brain-5v-ilimit` に出ます（前後の 5V の読みで判定）。

電池の電圧と、5V があるのに電池が減っていないかの確かめ（調べもの用。brain-watch（[stability.md](stability.md)）の記録に電池の電圧を足します）:

```sh
arm-linux-gnueabi-gcc -O2 -march=armv5te -static -o battpins userspace/power/battpins.c
arm-linux-gnueabi-gcc -O2 -march=armv5te -static -o battvolt userspace/power/battvolt.c
# Brain で
sudo install -m 755 battpins battvolt /usr/local/bin/
sudo install -m 755 userspace/power/brain-power.sh /usr/local/bin/brain-power.sh
sudo install -m 755 userspace/power/battcheck.py /usr/local/bin/battcheck
sudo battcheck        # 直近 10 分。分を渡せる（sudo battcheck 30）
```

`battvolt` は電池の電圧を LRADC で読みます（[power-wince.md](power-wince.md)）。`battcheck` は brain-watch の記録から、5V がある間に電池の電圧が下がり続けていないかを判定します。

蓋と 5V の知らせの記録（調べもの用。なくても動きます）:

```sh
sudo install -D -m 755 userspace/power/lidlog.py /usr/local/bin/brain-lidlog
sudo install -D -m 644 userspace/power/brain-lidlog.service /etc/systemd/system/brain-lidlog.service
sudo systemctl daemon-reload && sudo systemctl enable --now brain-lidlog
```

キーボードのマイコンから届く蓋と 5V の知らせを、カーネルが受けた時刻つきで `journalctl -u brain-lidlog` に残します。打ったキーは残しません。

## 3. 音楽ファイルを鳴らす

```sh
aplay music.wav
mpg123 music.mp3              # Brainux には入っていないので apt で入れる
sh userspace/play.sh music.wav   # SSH が切れても止まらない（nohup）。途切れは ~/play.log
```

音を鳴らすアプリが、自分の音のスレッドの優先度を上げられるようにします（subpaneld がサブ液晶を描く間に音が崩れないように。[stability.md](stability.md)）。次のログインから効きます。

```sh
sudo install -D -m 644 system/etc/security/limits.d/90-brain-audio.conf /etc/security/limits.d/90-brain-audio.conf
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
