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
- `userspace/brain-watch.sh` + `brain-watch.service` … 10 秒ごとに空きメモリ・スワップ・負荷・Wi-Fi の電波・メモリを多く使うプロセス上位 3 つを `/var/log/brain-watch.log` に 1 行書き、そのつど fsync する

Wi-Fi が固まった件は、これで「メモリ不足ではない」と切り分けられました。

## 4. その他の注意

- 固まって電源を切ると、直前に書いたファイルが **0 バイト**になっていることがある（ext4 のデータがまだ書き出されていなかった）。大事なファイルを書いたら `sync`
- Chromebook（Crostini）から SD カードの ext4 に `cp` で書いたファイルが 0 バイトになったことがあった。書いたら fsync し、読み返して確かめる。SD はファイルアプリで「取り出し」てから抜く
- Brain の sshd は鍵交換に数秒かかり、負荷が高いと 10 秒を超える。`ssh -o ConnectTimeout=40` にする。`scp` は途中で止まることがあったので、`ssh brain 'cat > f' < f` で送ってチェックサムを比べた
- 大きなファイルを Wi-Fi で送るときは、速さを抑えると安定した（`userspace/throttle.py`、100〜300KB/s）
