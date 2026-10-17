# brainux-pw-a9300

シャープの電子辞書 Brain **PW-A9300** で動く [Brainux](https://github.com/brain-hackers/buildbrain)（Debian 13 + Linux 6.1）を、ふだん使える機械にするための材料です。目標は Brainux そのものの改善（できたものは brain-hackers に還元したい）で、その上に「MML を書いてすぐ鳴らす機械」のような専用機を載せます。音楽のエンジンは、PC-98 の音楽ドライバ PMD を本物の 8086 のコードのまま動かす pmd-hle（別のリポジトリ）です。

いま入っているもの:

- **音**: 内蔵スピーカーとイヤホンを鳴らす ALSA ドライバ（音声 IC は Yamaha YMU818）
- **Wi-Fi**: TP-Link TL-WN725N（RTL8188EUS）を安定して使うドライバ（Linux 6.6 の rtl8xxxu を 6.1 向けに外付けモジュール化）
- **安定性**: メモリ不足で固まる問題と、unaligned access の値が黙って狂う問題への対策
- **サスペンド**: 蓋と「入/切」で眠り、DRAM をセルフリフレッシュにして深く眠る
- **電源**: 電池の残量（4 段階）と電圧、USB の 5V から取れる電流の上限、動いている最中にハブを挿し直しても 5V から取る
- **サブ液晶**: キーボードの下の小さな液晶をタッチパッドと状態の表示にする常駐プログラム `subpaneld`
- **MUCOM88**: [OPEN MUCOM88](https://github.com/onitama/mucom88) を Brain 向けにクロスビルドし、MML をその場でコンパイルして鳴らす

> **これはテストです。** 個人が自分の 1 台（PW-A9300）で試した自前ビルドで、brain-hackers の公式な成果物ではありません。ほかの機種では確かめていません。カーネルや DTB の差し替えは自己責任で、元のファイルを必ず残してください。

## 今の状態（2026-10-16）

| 項目 | 状態 |
|---|---|
| 音 | 内蔵スピーカー（モノラル）とイヤホン（ステレオ）で鳴る。再生中に抜き差しすると切り替わる。プチノイズ・途切れなし。鳴らしたまま眠っても雑音が出ない |
| Wi-Fi | 電源付き USB ハブ + OTG ケーブル経由で、20 分の負荷試験を通過。起きたあとに子機が戻らなければ、ハブのポートの電源を入れ直してつなぎ直す |
| サスペンド | 蓋を閉じるか「入/切」を短く押すと眠り、蓋を開けるかキーを押すと起きる。眠り方は `deep`（DRAM をセルフリフレッシュにし、PLL も止める。眠っていた時間は時計に足す）。新しいアルカリ電池で 10 時間眠っても、電池の見張りのピンは下がらなかった（s2idle では 5 時間半で 1 段下がった） |
| 電池・USB 給電 | 電池の残量は 4 段階、電圧は LRADC で読める（換算の比は未決）。USB の 5V から取る電流の上限を 480 mA に上げ、動いている最中や眠っている間にハブを挿したら i.MX28 の 4P2 を立ち上げ直す（しないと電池から取り続ける）。CPU クロック・持ち時間は未測定（[docs/power.md](docs/power.md)） |
| サブ液晶（キーボードの下、240×120）・タッチ・ボタン | `subpaneld` が、タッチパッド（なぞる・タップ・長押し）、右端に印刷されたボタン（音量・明るさ・クリア）、状態の帯（音量・明るさ・電池・USB 給電）、メイン液晶の枠の 11 個のボタン、「入/切」の長押しの表示を受け持つ。鳴らしているアプリに頼まれたら、蓋を閉じても眠らない（[docs/subpanel.md](docs/subpanel.md)） |
| MUCOM88 | サンプル曲 3 曲を、作りながら途切れなく再生できる。CPU 使用率は約 50% |
| PMD（pmd-hle） | フォルダの曲を一覧から聴ける。イヤホンなら蓋を閉じたまま聴ける。CPU 使用率は約 16% |

## 中身

| ディレクトリ | 内容 | ライセンス |
|---|---|---|
| [`kernel/`](kernel/) | linux-brain（a9f534c7）に当てるパッチ 12 本。YMU818 ドライバ（0001・0012）、バックライトの消灯（0002）、蓋とサスペンドからの起床（0003）、サブ液晶とタッチ（0004〜0006）、枠のキー（0007）、眠り方（0008 DMA・0009 DRAM のセルフリフレッシュ・0010 メイン液晶）、SPI（0011。上流の v6.8 の修正を持ってきたもの） | GPL-2.0 |
| [`kernel/rtl8xxxu66/`](kernel/rtl8xxxu66/) | Linux 6.6 の rtl8xxxu を取ってきて 6.1 向けに直すスクリプトとパッチ | GPL-2.0 |
| [`kernel/uinput/`](kernel/uinput/) | uinput を外付けモジュールとして作るスクリプト（`subpaneld` が使う） | GPL-2.0 |
| [`tools/ymu818-fw/`](tools/ymu818-fw/) | 自分の Brain の WinCE から YMU818 の設定手順（ファームウェア）を取り出すツール | MIT |
| [`userspace/`](userspace/) | `subpaneld`、電源の道具（5V の電流の上限と 4P2 の立ち上げ直し、電池の見張りと電圧、眠りの記録）、ドライバなしの試し鳴らし、再生・診断・負荷試験のスクリプト | MIT |
| [`system/`](system/) | Brainux の設定（安定化、蓋と電源キー、眠り方、サブ液晶の X の設定、Wi-Fi のつなぎ直し、音のスレッドの優先度） | MIT |
| [`mucom88/`](mucom88/) | OPEN MUCOM88 へのパッチ、クロスビルド、再生スクリプト、リズム音源 | パッチは CC BY-NC-SA 4.0（上流に従う）。リズム音源は作者の配布条件に従う |
| [`docs/`](docs/) | 調べたことの記録と手順 | MIT |

詳しくは [LICENSE.md](LICENSE.md)。

**シャープのデータは入っていません。** YMU818 の設定手順（係数を含む）はシャープの WinCE ドライバの中にあるので、各自が自分の Brain から取り出して使います（[docs/audio-ymu818.md](docs/audio-ymu818.md)）。

## 文書

- [docs/install.md](docs/install.md) … 入れ方（順番どおりに）
- [docs/audio-ymu818.md](docs/audio-ymu818.md) … 音声 IC の調べ方とドライバ
- [docs/wifi-rtl8188eu.md](docs/wifi-rtl8188eu.md) … Wi-Fi が固まった原因と rtl8xxxu66
- [docs/stability.md](docs/stability.md) … メモリ不足と unaligned access
- [docs/power.md](docs/power.md) … CPU クロック、電源、電池、サスペンド
- [docs/subpanel.md](docs/subpanel.md) … サブ液晶・タッチ・ボタンと `subpaneld`
- [docs/mucom88.md](docs/mucom88.md) … MUCOM88 のビルドと速さ
- [docs/upstream-notes.md](docs/upstream-notes.md) … brain-hackers と OPEN MUCOM88 に伝えたいこと（下書き）
- [docs/blog-draft.md](docs/blog-draft.md) … 記事の下書き

## 謝辞

- [brain-hackers](https://github.com/brain-hackers) の Brainux、linux-brain、buildbrain
- OPEN MUCOM88（古代祐三さん、おにたま（ONION software）さん、ほか）、fmgen（cisc さん）
- YM2608 風リズム音源音色データ 2608modoki2（メモルさん）
- Linux の rtl8xxxu（Jes Sorensen さん、ほか）
