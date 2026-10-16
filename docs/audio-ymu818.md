# 音: Yamaha YMU818

Brainux で鳴るのは、もとは圧電ブザー（pwm-beeper）だけでした。内蔵スピーカーにつながっている音声 IC を調べ、ALSA のドライバを書きました。

## ハードウェア（PW-A9300）

| 項目 | 値 | どうやって確かめたか |
|---|---|---|
| 音声 IC | Yamaha YMU818 | WinCE のドライバ名（`ymu818_wavdev.dll`） |
| 制御 | I2C0、7 ビットアドレス 0x3A | 実機で応答を確認（reg 0 = 0x3b） |
| レジスタ | 10 ビット。reg < 0x80 は `[0x80\|reg, data...]`、それ以上は `[reg&0x7f, 0x80\|(reg>>7), data...]`（最上位ビットが立ったバイトでアドレスが終わる）。連続書き込みで番号が進む | 逆アセンブル |
| 読み出し | `[0x80\|reg]` を書いてからリピートスタートで 1 バイト読む | 実機 |
| 音声データ | SAIF0（ピン 3_20〜3_23）、送信・マスター、`CTRL=0x801`（I2S、16 ビット） | エミュレーション |
| サンプリング周波数 | 44100 Hz、MCLK 512fs = 22.5792 MHz（PLL0 480MHz を分数分周 3083/65536、CLKCTRL_SAIF0 = 0x00010c0b） | エミュレーション + 実機 |
| リセット | GPIO3_27 を 1 →(10ms)→ 0 →(20ms)→ 1 | エミュレーション |
| ヘッドホン検出 | GPIO2_20。挿していないとき 1（スピーカー経路）。挿すときに接点がばたつく（1 回で約 1800 エッジ） | 実機 |
| スピーカー | モノラル。左右を同じ重みで足す（左だけ・右だけが同じ大きさ、振幅 0.9 の左右同時でも割れない） | 耳 |
| ヘッドホン | ステレオ | 耳 |
| 音量 | スピーカー: reg 0x025 = 0x20 + 0〜27。ヘッドホン: reg 0x023 = 0x60 + 0〜31、0x024 = 0〜31（WinCE は両方に同じ値） | エミュレーション（`emu_volume.py`）+ 実機 |

WinCE のデバイス名 `I2C1:` は「1 個目の I2C」の意味で、ハードウェアの I2C1 ではなく I2C0 でした。

## どうやって調べたか

1. 内蔵 eMMC（`/dev/mmcblk0`）の WinCE 領域（sector 2304 から 32MiB）を読み取り専用でコピーした
2. XIP ROM のモジュール一覧（`tools/ymu818-fw/cerom.py`）から `ymu818_wavdev.dll` を見つけ、インポートとエクスポートを調べた（`cemod.py`）
3. [Unicorn](https://www.unicorn-engine.org/) でドライバそのものを ARM のまま動かし（`emu_wav.py`）、I2C・GPIO・SAIF・クロックへのアクセスを順番どおりに記録した。初期化（`WAV_Init`）、再生開始（`BSPAudioStartDAC`）、停止（`BSPAudioStopDAC`）、音量（`WODM_SETVOLUME`）の場面ごとに取った
4. 記録をもとに、まずユーザー空間から `/dev/mem` と `/dev/i2c-0` を直接たたいて鳴らした（`userspace/saif.c`、`ymu818.py`、`run-test.sh`）
5. 鳴ったので、カーネルの ASoC ドライバにした

実機でわかったこと:

- SAIF0 の FIFO は 4 フレームしかない（44.1kHz で約 90 マイクロ秒分）。PIO で送るなら実時間優先度が要り、`sched_rt_runtime_us` の休み（1 秒ごとに 50ms）も外す必要があった。DMA を使うカーネルドライバではこの問題は起きない
- DMA_PREQ は PIO では当てにならない（FIFO が一度空になると立たない）
- 起動直後の Brainux では、評価ボード用の sgtl5000 のマシンドライバが SAIF0 を 256fs で動かしたまま失敗している。DTS で sgtl5000 を無効にした
- スピーカーアンプは「音量を 0 から上げる」手順で入る（WinCE の SetVolume の動きのまま）

## ドライバ

パッチ: [`kernel/0001-ASoC-YMU818-audio-for-Brain-PW-A9300.patch`](../kernel/0001-ASoC-YMU818-audio-for-Brain-PW-A9300.patch)（linux-brain a9f534c7 = Brainux 2026-03-25 のカーネルに当てる）

- `sound/soc/codecs/ymu818.c` … コーデックドライバ。レジスタの手順はソースに書かず、ファームウェアファイル `ymu818-brain.bin` から読む。最初の再生のときに読み込み、リセット → 初期化を流す。再生開始（prepare）でヘッドホン検出ピンを見て開始とアンプ ON、停止（shutdown）でアンプ OFF と停止。検出ピンの割り込みで、再生中に挿す・抜くと出力先を切り替える（0.2 秒落ち着くのを待つ。待つあいだは割り込みを止める）。ジャックの状態は ALSA の `Headphone Jack` と入力デバイス（SW_HEADPHONE_INSERT）で知らせる
- `sound/soc/mxs/mxs-ymu818.c` … マシンドライバ（mxs-sgtl5000.c がもと）。再生のみ
- `imx28-pwa7200.dts` … I2C0 に `yamaha,ymu818`、sgtl5000 を無効、sound ノードを差し替え。PW-A7200 系のほかの機種は未確認
- `brain_defconfig` … `CONFIG_SND_SOC_MXS_YMU818=y`

ALSA のカードは `mxs_ymu818`（`-c mxsymu818`）。

| コントロール | 範囲 | ドライバの既定 | 起動時の `alsactl init` |
|---|---|---|---|
| `Speaker Playback Volume` | 0〜27 | 12 | 21 |
| `Headphone Playback Volume` | 0〜31 | 8 | 24（イヤホンには大きい） |
| `Headphone Jack`（iface=CARD、読み取りのみ） | on / off | | |

音量はどちらも再生中に変えられ、使っていない側の値は覚えておいて、切り替わったときに書きます。

```sh
aplay -l
amixer -c mxsymu818 sset Speaker 12
amixer -c mxsymu818 sset Headphone 8
amixer -c mxsymu818 cget iface=CARD,name='Headphone Jack'
speaker-test -D hw:mxsymu818 -c 2 -r 44100 -t sine -f 440 -l 1
sudo alsactl store   # alsactl init の値は大きいので、好みの値を保存しておく
```

確かめたこと（2026-10-13、耳で）: イヤホンは左右が別に鳴り、スピーカーは無音。音量はどちらも段階ごとに大きくなる（イヤホンは 12/31 でもきつくない、スピーカーは 24/27 でも割れない）。再生中に抜くとスピーカー、挿すとイヤホンに、ほぼすぐ切り替わり雑音はない。音量を大きく変えた瞬間にごく小さな雑音が乗る（不快ではない）。

## ファームウェアを自分の Brain から取り出す

YMU818 の設定手順には、シャープのドライバに入っている係数（イコライザーなど）が含まれます。配布できないので、各自が自分の Brain から作ります。

1. Brain で WinCE 領域を読み取り専用でコピーする（書き込みはしません）

   ```sh
   sudo dd if=/dev/mmcblk0 of=nk_part.bin bs=512 skip=2304 count=65536
   ```

2. PC に持ってきて、Unicorn を入れた Python で取り出す

   ```sh
   python3 -m venv venv && venv/bin/pip install unicorn
   venv/bin/python -I tools/ymu818-fw/ymu818_extract.py nk_part.bin ymu818-brain.bin --text ymu818-brain.txt
   ```

3. `ymu818-brain.bin` を Brain の `/usr/lib/firmware/` に置く

音量の値とレジスタの対応は `emu_volume.py` で調べました（`--sweep` で細かく刻む）。

`emu_wav.py`・`ymu818_extract.py`・`emu_volume.py` には、PW-A9300 の WinCE イメージの中の番地（関数の位置など）が書いてあります。ほかの機種では番地が違うはずなので、そのままでは動きません。

### 鳴らしたまま眠るとき（`kernel/0012`、2026-10-16）

- 0012 の前は、PCM を開いたまま眠ると、眠っている間じゅうイヤホンに激しいノイズが出た（pmd-hle の再生器で、止めた曲を開いたまま蓋を閉じたら、眠りに入ったところから。SDL は止めている間も PCM を開いたまま無音を送るので、aplay や MUCOM88 でも、開いたまま眠れば同じはず。スピーカーでは試していない）。カードは YMU818 の PLL のために SAIF0 の MCLK を出しっぱなしにしていて、`deep` では PLL0 が止まる。アンプが入ったままクロックだけが止まっていた。またカードに PM の処理がなく、起きたあと PCM が prepare し直されるか（アンプが入り直すか）はアンダーランしだいだった
- 0012: コーデックに眠るときの処理を足し、鳴らしていればアンプを切って止める（`ymu818_stop`）。カードに ASoC の標準の PM（`snd_soc_pm_ops`）を付け、眠る前に PCM を止め、起きたら必ず prepare し直す（そこでアンプが入り直す）
- 確かめたこと（#18、2026-10-16、本人がイヤホンで）: 曲を止めて（PCM は開いたまま）蓋を閉じ、眠っている間にノイズが出ない。開けて続きから鳴らすと、イヤホンで続きから鳴る
- 眠っている間にイヤホンを挿すと Brain が起きる（2026-10-16、本人。ログでは、起きた直後に挿さったという知らせが来ている）。i.MX28 の `deep` は WFI で待つので、起こす設定（wakeup）をしていない割り込みでも、ハードウェアで生きていれば起きる。検出ピンの割り込みはその一つ。抜いても起きるかは見ていない

## 残っていること

- 音量を変えた瞬間のごく小さな雑音（ゼロクロスでの切り替えなどがあるかは未調査）
- 録音（SAIF1）は未対応
- ほかの機種（PW-A7200 系の兄弟機）は未確認
- WinCE の音声ドライバには電池が弱ったときのイベント（AUDIO_LOW_BATTERY_EVENT）があり、何か対処しているらしい
