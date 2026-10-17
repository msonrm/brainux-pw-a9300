# 安定性: メモリ不足と unaligned access

まとめて入れるスクリプト: [`system/setup-stability.sh`](../system/setup-stability.sh)（`--dry-run` で中身だけ表示）

## 1. unaligned access の値が黙って狂う

### 症状

MUCOM88 のコンパイル（本来 1〜2 秒）が、Brain では 10 分たっても終わらなかった。同じバイナリを PC の qemu-arm で動かすと 0.5 秒で終わる。

### 原因

```
$ cat /proc/cpu/alignment
...
User faults:	0 (ignored)
```

ARMv5（PW-A9300 の ARM926EJ-S）は、境界をまたいだメモリの読み書き（4 バイトの値を 4 の倍数でない番地から読む、など）を CPU だけではできません。Linux はふつう、これをトラップして正しい値に直します（fixup）。ところが Brainux のカーネルは **ignore**（直さない）になっていて、**ずれた番地の値を回転させたもの**がそのまま返ります。エラーにも警告にもなりません。

MUCOM88 はコンパイル中に約 4,000 回そうした読み書きをするので、値が狂ってループから抜けられなくなっていました。qemu-arm は unaligned access を正しく扱うので、PC では再現しません。

### 対策

```sh
echo 2 | sudo tee /proc/cpu/alignment          # 2 = fixup
# 起動時にも: /etc/tmpfiles.d/alignment.conf
w /proc/cpu/alignment - - - - 2
```

fixup にすると、MUCOM88 のコンパイルは 2 秒で終わり、書き出した音は qemu で作ったものと 1 ビットも違わなくなりました。トラップのぶん遅くはなりますが、MUCOM88 の再生中で 1 秒あたり数百回程度なので、影響はわかりません。

**ほかのソフトでも、エラーを出さずに計算を間違えている可能性があります。** Brainux の既定を fixup にすることを提案したいと考えています（[upstream-notes.md](upstream-notes.md)）。

## 2. メモリ不足（RAM 112MB、スワップなし）

### 症状

- 音楽を再生していたら、途中で数十秒途切れた
- Wi-Fi でつないでいると、起動から数分で固まった（そのうち 1 回は OOM の記録あり）

```
Out of memory: Killed process 1091 (apt-get) total-vm:70520kB, anon-rss:51204kB ...
```

### 原因

Debian の自動更新 `apt-daily.timer` / `apt-daily-upgrade.timer` が動かす `apt-get` が、パッケージ一覧の処理に約 50MB 使う。起動して間もなく動くこともあった（OOM の記録が残った回は起動 6 分後）。

### 対策

```sh
sudo systemctl disable --now apt-daily.timer apt-daily-upgrade.timer man-db.timer
```

念のための逃げ場として、128MB のスワップファイルと zswap（追い出すページをメモリの中で圧縮して持つ。SD への書き込みが減る）も入れました。

```sh
sudo dd if=/dev/zero of=/swapfile bs=1M count=128 && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
# zswap: /etc/tmpfiles.d/zswap.conf
w /sys/module/zswap/parameters/enabled - - - - Y
```

`apt` は、使いたいときに手で `sudo apt update` すれば足ります。

## 3. 固まったときの手がかりを残す

固まると、journald のログは書き出される前に消えます（既定の書き出し間隔は 5 分）。調べるあいだは次の二つを入れておくと、直前の様子がわかります。

- `system/etc/systemd/journald.conf.d/sync.conf` … journald を 10 秒ごとに書き出す
- `userspace/brain-watch.sh` + `brain-watch.service` … 10 秒ごとに空きメモリ・スワップ・負荷・Wi-Fi の電波・メモリを多く使うプロセス上位 3 つを `/var/log/brain-watch.log` に 1 行書き、そのつど fsync する（今は電源の様子 `pwr=[...]` も。眠っている間は書かないので、眠りの前後の値から眠っている間の様子は読めない）。`Nice=19` で動かす（2026-10-16 まで `Nice=-5` で、1 回ごとに小さなプログラムを 15 個ほど起こす約 1 秒の間、鳴らしている音が 11.5 秒おきにグシャっと崩れていた。[audio-ymu818.md](audio-ymu818.md)）

Wi-Fi が固まった件は、これで「メモリ不足ではない」と切り分けられました。

## 4. 使わないものを止める

Brainux の起動は、カーネル 4 秒のあとユーザー空間に 1 分 32 秒かかっていました（2026-10-17、`systemd-analyze`）。CPU が 1 つで遅いので、同時に起動するものが多いほど全体が延びます。中身を読んで、何もしていないものを止めました（`setup-stability.sh` の 5）。

| 止めたもの | 起動にかかっていた時間 | 理由 |
|---|---|---|
| `brain-config.service` | 17 秒 | CPU のガバナーを ondemand にするだけ。このカーネルには cpufreq がない（[power.md](power.md)）。そのうえ Shift を見るため `thd --dump` で入力デバイスを全部 1 秒開く |
| `triggerhappy.service`・`.socket` | 6.7 秒、常駐 1.5MB | 割り当て（`/etc/triggerhappy/triggers.d/`）が空。入力デバイスを全部開いていた |
| `e2scrub_reap.service`・`e2scrub_all.timer` | 20 秒 | LVM のスナップショットで ext4 を調べる仕組み。ルートは LVM ではない |
| `cron.service` | 常駐 2MB | `/etc/cron.daily` などの中身は、どれも systemd があれば何もしない（タイマーが代わりに動く） |
| `avahi-daemon.service`・`.socket` | 16 秒、常駐 3MB | `brain.local` の名前で見つけてもらう仕組み。IP でつないでいる |
| `serial-getty@ttyAMA0.service` | 常駐 1.9MB | 基板のシリアル端子のログイン。カーネルの引数 `console=ttyAMA0` から generator が作るので、disable では止まらず mask した |

USB ケーブルでつなぐための `ethernet_gadget.service`（15 秒）と `networking.service`（20 秒、ifupdown が上げるのは usb0 だけ）は、OTG が host の DTB（Wi-Fi で使うとき）では毎回失敗していました。消すと USB ケーブルの逃げ道がなくなるので、ガジェットの口（`/sys/class/udc/ci_hdrc.0`）があるときだけ動くようにしました（`system/etc/systemd/system/*.service.d/brain-only-peripheral.conf`）。

journal は上限がなく、SD に 203MB たまっていました。`system/etc/systemd/journald.conf.d/brain-size.conf` で 50MB までにしました。

止めたあと再起動すると、ユーザー空間は 1 分 32 秒 → 1 分 16 秒（全体で 1 分 37 秒 → 1 分 20 秒）になった。USB ケーブル用の 2 つは条件が合わず飛ばされ、Wi-Fi はつながり、失敗したユニットはなかった（2026-10-17）。いま長いのは、最初の 40 秒あまりで SD のパーティションのデバイスが揃うまで（`systemd-udev-trigger` 19 秒）で、ここは止めるものではなく、遅い CPU で udev が全部のデバイスを処理する時間。

残したもの: NetworkManager・wpa_supplicant（Wi-Fi）、timesyncd・fake-hwclock（RTC がないので時刻を保つ）、tty1 の getty（X が壊れたときに文字の画面でログインする逃げ道。ly は tty2）、logrotate・fstrim・dpkg-db-backup のタイマー（1 日か 1 週に 1 回）、brain-watch（固まったときの手がかり）。

## 5. その他の注意

- 固まって電源を切ると、直前に書いたファイルが **0 バイト**になっていることがある（ext4 のデータがまだ書き出されていなかった）。大事なファイルを書いたら `sync`
- Chromebook（Crostini）から SD カードの ext4 に `cp` で書いたファイルが 0 バイトになったことがあった。書いたら fsync し、読み返して確かめる。SD はファイルアプリで「取り出し」てから抜く
- Brain の sshd は鍵交換に数秒かかり、負荷が高いと 10 秒を超える。`ssh -o ConnectTimeout=40` にする。`scp` は途中で止まることがあったので、`ssh brain 'cat > f' < f` で送ってチェックサムを比べた
- 大きなファイルを Wi-Fi で送るときは、速さを抑えると安定した（`userspace/throttle.py`、100〜300KB/s）
