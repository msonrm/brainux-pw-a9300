# brainux-pw-a9300

シャープの電子辞書 Brain **PW-A9300** で動く [Brainux](https://github.com/brain-hackers/buildbrain)（Debian 13 + Linux 6.1）を、ふだん使える機械にするための材料です。目標は Brainux そのものの改善（できたものは brain-hackers に還元したい）で、その上に MUCOM88 機やポメラのようなエディタといった「専用機」を載せることも視野に入れています。

いま入っているもの:

- **音**: 内蔵スピーカーを鳴らす ALSA ドライバ（音声 IC は Yamaha YMU818）
- **Wi-Fi**: TP-Link TL-WN725N（RTL8188EUS）を安定して使うドライバ（Linux 6.6 の rtl8xxxu を 6.1 向けに外付けモジュール化）
- **安定性**: メモリ不足で固まる問題と、unaligned access の値が黙って狂う問題への対策
- **MUCOM88**: [OPEN MUCOM88](https://github.com/onitama/mucom88) を Brain 向けにクロスビルドし、MML をその場でコンパイルして内蔵スピーカーで鳴らす

> **これはテストです。** 個人が自分の 1 台（PW-A9300）で試した自前ビルドで、brain-hackers の公式な成果物ではありません。ほかの機種では確かめていません。カーネルや DTB の差し替えは自己責任で、元のファイルを必ず残してください。

## 今の状態（2026-10-12）

| 項目 | 状態 |
|---|---|
| 音（WAV / MP3） | 内蔵スピーカーで再生できる。プチノイズ・途切れなし。ヘッドホン経路は未確認 |
| Wi-Fi | 電源付き USB ハブ + OTG ケーブル経由で、20 分の負荷試験を通過 |
| MUCOM88 | サンプル曲 3 曲を、作りながら途切れなく再生できる。CPU 使用率は約 50% |
| サスペンド | 蓋を閉じるか「入/切」を短く押すと眠り、蓋を開けるかキーを押すと 1 秒以内に起きる（s2idle）。眠っている間の電池の減りは未測定 |
| CPU クロック・電池残量 | 調査中。電池残量は 4 段階で読める（[docs/power.md](docs/power.md)） |
| サブ液晶（キーボード下、240×120）・タッチ・ボタン | 表示・タッチ・ボタンのコードを確認（[docs/subpanel.md](docs/subpanel.md)）。MML の記号表として入力に使うのは未着手 |

## 中身

| ディレクトリ | 内容 | ライセンス |
|---|---|---|
| [`kernel/`](kernel/) | linux-brain（a9f534c7）に当てるパッチ（YMU818 ドライバ、バックライトの消灯、蓋のスイッチとサスペンドからの起床） | GPL-2.0 |
| [`kernel/rtl8xxxu66/`](kernel/rtl8xxxu66/) | Linux 6.6 の rtl8xxxu を取ってきて 6.1 向けに直すスクリプトとパッチ | GPL-2.0 |
| [`tools/ymu818-fw/`](tools/ymu818-fw/) | 自分の Brain の WinCE から YMU818 の設定手順（ファームウェア）を取り出すツール | MIT |
| [`userspace/`](userspace/) | ドライバなしの試し鳴らし、再生・診断・負荷試験のスクリプト | MIT |
| [`system/`](system/) | 安定化の設定（alignment、apt の timer、スワップ、zswap） | MIT |
| [`mucom88/`](mucom88/) | OPEN MUCOM88 へのパッチ、クロスビルド、再生スクリプト、リズム音源 | パッチは CC BY-NC-SA 4.0（上流に従う）。リズム音源は作者の配布条件に従う |
| [`docs/`](docs/) | 調べたことの記録と手順 | — |

**シャープのデータは入っていません。** YMU818 の設定手順（係数を含む）はシャープの WinCE ドライバの中にあるので、各自が自分の Brain から取り出して使います（[docs/audio-ymu818.md](docs/audio-ymu818.md)）。

## 文書

- [docs/install.md](docs/install.md) … 入れ方（順番どおりに）
- [docs/audio-ymu818.md](docs/audio-ymu818.md) … 音声 IC の調べ方とドライバ
- [docs/wifi-rtl8188eu.md](docs/wifi-rtl8188eu.md) … Wi-Fi が固まった原因と rtl8xxxu66
- [docs/stability.md](docs/stability.md) … メモリ不足と unaligned access
- [docs/mucom88.md](docs/mucom88.md) … MUCOM88 のビルドと速さ
- [docs/upstream-notes.md](docs/upstream-notes.md) … brain-hackers と OPEN MUCOM88 に伝えたいこと（下書き）
- [docs/blog-draft.md](docs/blog-draft.md) … 記事の下書き

## 謝辞

- [brain-hackers](https://github.com/brain-hackers) の Brainux、linux-brain、buildbrain
- OPEN MUCOM88（古代祐三さん、おにたま（ONION software）さん、ほか）、fmgen（cisc さん）
- YM2608 風リズム音源音色データ 2608modoki2（メモルさん）
- Linux の rtl8xxxu（Jes Sorensen さん、ほか）
