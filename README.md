# brainux-pw-a9300

シャープの電子辞書 Brain **PW-A9300** で動く [Brainux](https://github.com/brain-hackers/buildbrain)（Debian 13 + Linux 6.1）を、ふだん使える機械にするための材料です。目標は Brainux そのものの改善（できたものは brain-hackers に還元したい）で、その上に「MML を書いてすぐ鳴らす機械」のような専用機を載せます。

いま入っているもの:

- **音**: 内蔵スピーカーとイヤホンを鳴らす ALSA ドライバ（音声 IC は Yamaha YMU818）
- **Wi-Fi**: TP-Link TL-WN725N（RTL8188EUS）を安定して使うドライバ（Linux 6.6 の rtl8xxxu を 6.1 向けに外付けモジュール化）
- **安定性**: メモリ不足で固まる問題と、unaligned access の値が黙って狂う問題への対策。キーを押し続けながら音を鳴らし始めたり止めたりすると、メイン液晶のタッチが効かなくなる問題の修正
- **サスペンド**: 蓋と「入/切」で眠り、DRAM をセルフリフレッシュにして深く眠る
- **電源**: 電池の残量（4 段階）と電圧、USB の 5V から取れる電流の上限、動いている最中にハブを挿し直しても 5V から取る、電源を切ったあと「入/切」で起動する
- **サブ液晶**: キーボードの下の小さな液晶をタッチパッドと状態の表示にする常駐プログラム `subpaneld`
- **メイン液晶**: ペンで押してもカーソルが飛ばないタッチの扱い（`subpaneld`）と、X を DRM（`modesetting`）で描いて画面の書き換えを 1 秒 20 回の上限から外す設定。画面を消している間と眠っている間は、パネルの電源とバックライトを切る
- **MUCOM88**: [OPEN MUCOM88](https://github.com/onitama/mucom88) を Brain 向けにクロスビルドし、MML をその場でコンパイルして鳴らす

> **これはテストです。** 個人が自分の 1 台（PW-A9300）で試した自前ビルドで、brain-hackers の公式な成果物ではありません。ほかの機種では確かめていません。カーネルや DTB の差し替えは自己責任で、元のファイルを必ず残してください。

> [!WARNING]
> **Brainux や linux-brain に、音（YMU818）や電源まわりのコードを書こうとしている方は、次のファイルを読まないでください。**
> 逆アセンブルで知ったこと（レジスタの番地や書き込む値、手順の順番など）を使っているか、逆アセンブルをした環境で書いたものです。読んでから書いたコードは、クリーンに書いたと説明できなくなります。
>
> この注意は、Brainux の方針（DLL の逆アセンブルを根拠にしたコードにはクリーンルームの手順が要る）に合わせるためのものです。ここにはシャープのプログラムもデータも入っていません。逆アセンブルしたコードを写したり、別の言語に書き移したりしたものもありません。コードは、調べてわかった仕組みと、Freescale などの GPL のコードを手本に、一から書いています（YMU818 の設定手順は、各自が自分の Brain から取り出します）。
>
> - 音: [`kernel/0001`](kernel/0001-ASoC-YMU818-audio-for-Brain-PW-A9300.patch)、[`kernel/0012`](kernel/0012-ASoC-ymu818-turn-the-amp-off-for-suspend.patch)、[`tools/ymu818-fw/`](tools/ymu818-fw/)、`userspace/saif.c`・`ymu818.py`・`run-test.sh`、[docs/audio-ymu818.md](docs/audio-ymu818.md)
> - 電源: [`kernel/0009`](kernel/0009-ARM-mxs-pm-put-the-DRAM-into-self-refresh-in-suspend-to-mem-on-i.MX28.patch)、`userspace/power/` の `battpins.c`・`battvolt.c`・`battcheck.py`・`brain-5v-ilimit.c`・`ramp4p2.c`・`brain-mcu-off`・`brain-power.sh`・`vbuswatch.py`、`userspace/subpanel/subpaneld.py` の電池の段階の部分、[docs/power-wince.md](docs/power-wince.md)
>
> これ以外のファイル（ほかのカーネルのパッチ、Wi-Fi、`system/`、`mucom88/`、subpaneld のほかの部分など）には、WinCE の解析を使っていません。

## 今の状態（2026-10-20）

| 項目 | 状態 |
|---|---|
| 音 | 内蔵スピーカー（モノラル）とイヤホン（ステレオ）で鳴る。再生中に抜き差しすると切り替わる。プチノイズ・途切れなし。止めてすぐ鳴らし直しても途切れない。鳴らしたまま眠っても雑音が出ない |
| Wi-Fi | 電源付き USB ハブ + OTG ケーブル経由で、20 分の負荷試験を通過。起きたあとに子機が戻らなければ、ハブのポートの電源を入れ直してつなぎ直す |
| サスペンド・電源オフ | 蓋を閉じるか「入/切」を短く押すと眠り、蓋を開けるかキーを押すと起きる。「入/切」を 5 秒長押しすると電源が切れ、もう一度「入/切」を押すと起動する（電池だけのとき。ハブがあると切れずに WinCE から起動し直す）。眠り方は `deep`（DRAM をセルフリフレッシュにし、PLL も止める。眠っていた時間は時計に足す）。新しいアルカリ電池で 10 時間眠っても、電池の見張りのピンは下がらなかった（s2idle では 5 時間半で 1 段下がった） |
| 電池・USB 給電 | 電池の残量は 4 段階、電圧は LRADC で読める（換算の比は未決）。USB の 5V から取る電流の上限を 480 mA に上げ、動いている最中や眠っている間にハブを挿したら i.MX28 の 4P2 を立ち上げ直す（しないと電池から取り続ける）。CPU クロック・持ち時間は未測定（[docs/power.md](docs/power.md)、電池と 5V の電流は [docs/power-wince.md](docs/power-wince.md)） |
| サブ液晶（キーボードの下、240×120）・タッチ・ボタン | `subpaneld` が、タッチパッド（なぞる・タップ・長押し）、右端に印刷されたボタン（音量・明るさ・クリア）、状態の帯（音量・明るさ・電池・USB 給電）、メイン液晶の枠の 11 個のボタン、「入/切」の長押しの表示を受け持つ。鳴らしているアプリに頼まれたら、蓋を閉じても眠らない（[docs/subpanel.md](docs/subpanel.md)） |
| メイン液晶（480×320）・タッチ | ペンで押してもカーソルが飛ばない（離す直前の跳ねを捨てる）。デスクトップのメニューが押したとおりに出る。X は `modesetting` ドライバ（`kernel/0016`）で描き、カーソルが 1 秒 20 回の書き換えの上限なく動く。窓の移動・リサイズはまだ重い（[docs/subpanel.md](docs/subpanel.md)）。X が画面を消したとき（何も触らないと約 10 分）と眠っている間は、パネルの電源（GPIO0_27）とバックライトを切り、つけ直すときはノイズを見せずに戻る（`kernel/0017`・`0018`。電流は未測定。[docs/power.md](docs/power.md)）。起動のときに X が画面のバッファを取れずに止まったことが 1 回あり、CMA を 4 MB 取っておくようにした（`kernel/0019`、[docs/stability.md](docs/stability.md)） |
| キーボード | キーを押し続けながら音を鳴らし始めたり止めたりしても落ちない（`kernel/0013`。前は、同じ I2C0 にいる音のチップと読み書きが重なるとカーネルが `scheduling while atomic` を出し、メイン液晶のタッチが再起動まで効かなくなった） |
| MUCOM88 | サンプル曲 3 曲を、作りながら途切れなく再生できる。CPU 使用率は約 50% |

## 中身

| ディレクトリ | 内容 | ライセンス |
|---|---|---|
| [`kernel/`](kernel/) | linux-brain（a9f534c7）に当てるパッチ 19 本。YMU818 ドライバ（0001・0012）、バックライトの消灯（0002）、蓋とサスペンドからの起床（0003）、サブ液晶とタッチ（0004〜0006）、枠のキー（0007）、眠り方（0008 DMA・0009 DRAM のセルフリフレッシュ・0010 メイン液晶）、SPI（0011。上流の v6.8 の修正を持ってきたもの）、キーボードの割り込み（0013）、音を止めてすぐ鳴らし直す（0014 上流の ALSA の修正・0015 DMA）、メイン液晶を X の `modesetting` で使えるようにする（0016）、画面を消している間と眠っている間にメイン液晶の電源とバックライトを切る（0017 ドライバ・0018 DTS）、CMA を取っておき、カーネルの版の名前に `-pwa9300` をつける（0019 defconfig） | GPL-2.0 |
| [`kernel/rtl8xxxu66/`](kernel/rtl8xxxu66/) | Linux 6.6 の rtl8xxxu を取ってきて 6.1 向けに直すスクリプトとパッチ | GPL-2.0 |
| [`kernel/uinput/`](kernel/uinput/) | uinput を外付けモジュールとして作るスクリプト（`subpaneld` が使う） | GPL-2.0 |
| [`tools/ymu818-fw/`](tools/ymu818-fw/) | 自分の Brain の WinCE から YMU818 の設定手順（ファームウェア）を取り出すツール | MIT |
| [`userspace/`](userspace/) | `subpaneld`、電源の道具（5V の電流の上限と 4P2 の立ち上げ直し、電源を切ったあと「入/切」で起動するための知らせ、電池の見張りと電圧、眠りの記録）、ドライバなしの試し鳴らし、再生・診断・負荷試験のスクリプト | MIT |
| [`system/`](system/) | Brainux の設定（安定化、蓋と電源キー、眠り方、サブ液晶とメイン液晶の X の設定、JWM のキーと窓の動かし方、Wi-Fi のつなぎ直し、音のスレッドの優先度） | MIT |
| [`mucom88/`](mucom88/) | OPEN MUCOM88 へのパッチ、クロスビルド、再生スクリプト、リズム音源 | パッチは CC BY-NC-SA 4.0（上流に従う）。リズム音源は作者の配布条件に従う |
| [`docs/`](docs/) | 調べたことの記録と手順 | CC BY 4.0 |

詳しくは [LICENSE.md](LICENSE.md)。

**シャープのデータは入っていません。** YMU818 の設定手順（係数を含む）はシャープの WinCE ドライバの中にあるので、各自が自分の Brain から取り出して使います（[docs/audio-ymu818.md](docs/audio-ymu818.md)）。

**WinCE の解析について。** 音と電源の一部は、シャープの WinCE のドライバを逆アセンブルし、エミュレーターで動かして調べた結果を使っています。音は `ymu818_wavdev.dll` を、電源は電池・電源のドライバと WinCE の本体を調べました。解析とコードを書くことは、同じ環境で coding agent（Claude Code）と進め、分けて行う手順（クリーンルーム）は踏んでいません。brain-hackers は 2026-10 に、DLL の逆アセンブルを根拠にしたコードにはクリーンルームの手順が要る、という方針を示しました。なので、ここのコードのうち該当するものは Brainux に提案しません。何を得てどこに使ったかは、[docs/audio-ymu818.md](docs/audio-ymu818.md) の「どうやって調べたか」と、[docs/power-wince.md](docs/power-wince.md) の「WinCE の解析との関係」に書いています。

## 文書

- [docs/install.md](docs/install.md) … 入れ方（順番どおりに）
- [docs/audio-ymu818.md](docs/audio-ymu818.md) … 音声 IC の調べ方とドライバ。WinCE の解析とつながるので、Brainux にコードを書く方は読まないでください
- [docs/wifi-rtl8188eu.md](docs/wifi-rtl8188eu.md) … Wi-Fi が固まった原因と rtl8xxxu66
- [docs/stability.md](docs/stability.md) … メモリ不足と unaligned access、使わないサービス、鳴らしている音が崩れるとき（優先度）、止めてすぐ鳴らし直すと途切れるとき（DMA）、起動のときに X が立ち上がらないとき（CMA）、ext4 のエラーの直し方
- [docs/power.md](docs/power.md) … CPU クロック、電源、サスペンド、画面を消している間と眠っている間のメイン液晶の電源とバックライト
- [docs/power-wince.md](docs/power-wince.md) … 電源のうち WinCE の解析とつながる部分（5V から取る電流と 4P2、電池の見張りピンと電圧、電源を切ったあと「入/切」で起動する、deep を作る `kernel/0009`）。Brainux にコードを書く方は読まないでください
- [docs/subpanel.md](docs/subpanel.md) … サブ液晶・タッチ・ボタンと `subpaneld`、メイン液晶のタッチと画面の書き換え
- [docs/mucom88.md](docs/mucom88.md) … MUCOM88 のビルドと速さ

## 謝辞

- [brain-hackers](https://github.com/brain-hackers) の Brainux、linux-brain、buildbrain
- brain-hackers の [Scrapbox](https://scrapbox.io/brain-hackers/) の記録。電池の電圧の読み方は「PW-A9300」のページによります。YMU818 には「YMU818b メモ」という先行の記録があります（こちらの解析はそれに頼っていません。[docs/audio-ymu818.md](docs/audio-ymu818.md)）
- OPEN MUCOM88（古代祐三さん、おにたま（ONION software）さん、ほか）、fmgen（cisc さん）
- YM2608 風リズム音源音色データ 2608modoki2（メモルさん）
- Linux の rtl8xxxu（Jes Sorensen さん、ほか）
