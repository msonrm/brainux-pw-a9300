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
| ヘッドホン検出 | GPIO2_20。挿していないとき 1（スピーカー経路） | 実機 |
| スピーカー | モノラル | 耳 |

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

- `sound/soc/codecs/ymu818.c` … コーデックドライバ。レジスタの手順はソースに書かず、ファームウェアファイル `ymu818-brain.bin` から読む。最初の再生のときに読み込み、リセット → 初期化を流す。再生開始（prepare）でヘッドホン検出ピンを見て開始とアンプ ON、停止（shutdown）でアンプ OFF と停止
- `sound/soc/mxs/mxs-ymu818.c` … マシンドライバ（mxs-sgtl5000.c がもと）。再生のみ
- `imx28-pwa7200.dts` … I2C0 に `yamaha,ymu818`、sgtl5000 を無効、sound ノードを差し替え。PW-A7200 系のほかの機種は未確認
- `brain_defconfig` … `CONFIG_SND_SOC_MXS_YMU818=y`

ALSA のカード名は `mxs_ymu818`。音量は `Speaker Playback Volume`（0〜27、既定 12）です。

```sh
aplay -l
amixer sset Speaker 12
speaker-test -c 2 -r 44100 -t sine -f 1000 -l 1
sudo alsactl store   # 起動時の alsactl init が 21 にするので、好みの値を保存しておく
```

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

`emu_wav.py` と `ymu818_extract.py` には、PW-A9300 の WinCE イメージの中の番地（関数の位置など）が書いてあります。ほかの機種では番地が違うはずなので、そのままでは動きません。

## 残っていること

- ヘッドホン経路は試していない（ファームウェアには手順が入っている）
- 録音（SAIF1）は未対応
- ほかの機種（PW-A7200 系の兄弟機）は未確認
- WinCE の音声ドライバには電池が弱ったときのイベント（AUDIO_LOW_BATTERY_EVENT）があり、何か対処しているらしい
