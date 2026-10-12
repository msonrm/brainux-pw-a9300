# MUCOM88 を Brain で鳴らす

[OPEN MUCOM88](https://github.com/onitama/mucom88) は、古代祐三さんが 1987 年に PC-8801 向けに作った MML 音楽ツール MUCOM88 を、公開・継承するプロジェクトです。オリジナルの Z80 のコンパイラと再生ドライバを内蔵の Z80 エミュレーターで動かし、音源チップ YM2608（OPNA）は fmgen で再現します。

**PC-8801 の実機の ROM は要りません。** コンパイラ・ドライバ・音色（`voice.dat`）・ADPCM の音（`mucompcm.bin`）は OPEN MUCOM88 に含まれています。足りないのは YM2608 が内蔵するリズム音（バスドラムなど 6 種類）だけで、ここではメモルさんの「YM2608 風リズム音源音色データ Ver.2.0（2608modoki2）」を使いました。本物のチップから取り出した音ではなく、自由に配布できます（[`mucom88/rhythm/PROVENANCE_2608modoki2.utf8.txt`](../mucom88/rhythm/PROVENANCE_2608modoki2.utf8.txt)）。

## ビルド

```sh
sudo apt install g++-arm-linux-gnueabi     # Debian の PC で
sh mucom88/build-armel.sh                  # onitama/mucom88 2c8adbe を取ってきてパッチを当て、out/ に一式を作る
```

できた `mucom88/out/` を Brain にコピーします。音を出す部分は使わない構成（`OS_SDL=0`）なので、Brain に SDL は要りません。`-static-libstdc++` でリンクしているので、Brain 側の C++ ライブラリの版も問いません。

**Brain では先に unaligned access を fixup にしてください**（[stability.md](stability.md)）。ignore のままだとコンパイルが終わりません。

## パッチの中身（`mucom88/0001-*.patch`）

1. **音を出さない版（dummy osdep）がビルドできない不具合を直した。** 最近足された `SetBreakHook` / `GetBreakStatus` が dummy になく、`GetStatus` のクラス名も `OsDependentSdl` と書き間違えられていた
2. **`-w -` で、WAV ファイルの代わりに音のデータ（ヘッダーなしの 16 ビット・ステレオ・44.1kHz）を標準出力に流せるようにした。** そのあいだ、文字の表示は標準エラーに回す。これを `aplay` に渡せば、作りながら鳴らせる

ファイルに書き出した音と、流した音は 1 バイトも違わないことを確かめました。

## 鳴らす

```sh
cd ~/mucom88
sh mucplay.sh sampl1.muc          # 中身: ./mucom88 -x -w - -c sampl1.muc | aplay -q -t raw -f cd --buffer-time=500000
./mucom88 -x -w out.wav -c sampl1.muc   # WAV に書き出す
```

`-x` は書き出しモード（曲の `#time` の秒数だけ作る。`-l 秒数` で変えられる）です。

## 速さ（PW-A9300、ARM926EJ-S 約 450MHz、浮動小数点の専用回路なし）

30 秒分の音をファイルに書き出す時間:

| 曲 | 時間 | 実時間と比べて |
|---|---|---|
| サンプル 1（古代祐三さん作） | 14.7 秒 | 約 2 倍速 |
| サンプル 2 | 9.2 秒 | 約 3 倍速 |
| サンプル 3 | 3.6 秒 | 約 8 倍速 |

- コンパイルは 0.4〜1.3 秒
- 作りながら鳴らすと、CPU は約 50% 使い、約 50% 空いている。途切れ（underrun）は 3 曲とも 0 回
- 90 秒の曲は、始めてから 91 秒あまりで鳴り終わる（待ち時間はコンパイルのぶんだけ）
- Brain で作った音は、PC の qemu-arm で同じバイナリから作った音と一致した

書き出してから鳴らす方式では、書き出した直後の 16MB の WAV を SD から読みながら鳴らしたとき、0.6 秒の途切れが 1 回ありました。作りながら鳴らす方式なら SD を通りません。

## これから

- MML を Brain の上で書いて、1 キーで鳴らす・止める流れ
- ループ再生（今は `#time` の秒数で止まる）
- ALSA に直接出す osdep（パイプを使わない）
