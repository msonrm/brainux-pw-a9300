# サブ液晶・タッチ・ボタン（PW-A9300）

2026-10-12 に実機で確かめたこと。MML でよく使う記号をサブ液晶に並べ、タッチで入力する構想の下調べ。

## サブ液晶（キーボードの下）

- ST7586、240×120、4 階調グレー、SPI（ssp2 = `spi1.0`）。WinCE 側のドライバは `EDNA2_slcd_ST7586.dll`
- Linux 側は brain-hackers の DRM ドライバ `brain-st7586`（`drivers/gpu/drm/tiny/brain-st7586.c`）。`/dev/fb1`（`brain-st7586drm`、XRGB8888、1 行 960 バイト、1 画面 115200 バイト）
- **起動したままでは何も映らない。** Linux はサブ液晶の画面を一度も有効にしておらず、WinCE が最後に描いた画面（「スーパー大辞林3.0」など）が残っている
  - Xorg が `/dev/dri/card1` を GPU として追加し、systemd-logind 経由で DRM master を握る。このため fbdev からのモード設定・更新は `EBUSY` で断られる（`FBIOPAN_DISPLAY` も同じ）
  - 確かめ方: `sudo cat /sys/kernel/debug/dri/1/clients`（master が `y`）、`/sys/kernel/debug/dri/1/state` の `active=0`
  - 参考: PW-G5200 では書き込み + `FBIOPAN_DISPLAY` で映った（momoji-san「Brainのサブディスプレイ」 https://momoji-san.hateblo.jp/entry/2026/09/21/194153）。X が握っていなければその方法で足りるはず
- **映した方法（再起動なし）**: 文字のコンソールに切り替えて X に master を手放させ、そのあいだに fbdev でモード設定する。X に戻ってもサブ液晶は有効のまま

  ```sh
  sudo python3 userspace/subpanel/chvt.py 3      # chvt の代わり（kbd パッケージが入っていない）
  python3 userspace/subpanel/fbshow.py /dev/fb1 palette.raw   # FB_ACTIVATE_FORCE でモード設定してから書く
  sudo python3 userspace/subpanel/chvt.py 2      # X に戻る（X の VT は /sys/class/tty/tty0/active で確認）
  ```

  一度有効になれば、あとは `/dev/fb1` に書くだけで更新される（video グループなら sudo 不要）
- 恒久的にするなら（未適用）: Xorg に card1 を追加させない（`Section "ServerFlags"` に `Option "AutoAddGPU" "false"`）。X の再起動が要る
- 向き: `fb1` の左上がサブ液晶の左上（DTS の `rotation = <180>` で合っている）
- `userspace/subpanel/mkpalette.py` が記号表（8 列 × 3 段、1 マス 30×40 px）を作る。Chromebook 側で Pillow を使って作り、raw を送る（Brain には Pillow がない）

## タッチパネル

| 液晶 | 入力デバイス | 備考 |
|---|---|---|
| サブ液晶 | `mxs-lradc-ts`（event0、i.MX28 内蔵の LRADC による抵抗膜） | WinCE 側は `EDNA2_TouchSub.dll` |
| メイン液晶 | `SX8654 I2C Touchscreen`（event3、I2C0 の 0x48、実体は SX8650） | DTS の名前は `lcd_touchscreen_i2c` |

サブ液晶の 4 隅（生の値）:

| | x | y |
|---|---|---|
| 左上 | 356 | 3685 |
| 右上 | 3435 | 3635 |
| 右下 | 3420 | 700 |
| 左下 | 380 | 830 |

- x は左→右で増える。y は上→下で減る。おおよそ `px = (x - 356) * 240 / 3080`、`py = (3685 - y) * 120 / 2920`
- 記号表を出した状態で「@」（左上のマス）を押すと (477, 3209) → (9, 20) px で、正しく 1 段目 1 列目に入った
- 押した瞬間と離す瞬間に値が少し跳ねる（離す直前の 1〜2 サンプルを捨てるとよい）。圧力（ABS_PRESSURE）も出る
- 今は両方とも Xorg の evdev がマウスとして使っている（サブ液晶を触ると、メイン画面のカーソルが絶対位置に飛ぶ）。記号入力に使うなら Xorg に無視させる（`MatchProduct "mxs-lradc-ts"` + `Option "Ignore" "true"`）
- `/etc/X11/xorg.conf.d/99-calibrator.conf` の較正値は `MatchDriver "evdev"` なので両方に当たっている

## ボタン

キーボードのマイコン（I2C0 の 0x28）が返す生のコード。`brain-kbd-i2c` を外して直接読んだ（`userspace/subpanel/inputlog.py`）。

| ボタン | コード | 今の割り当て（DTS の keymap） |
|---|---|---|
| 入/切 | 0x01 | `KEY_POWER`（Brainux の既定では logind が電源を切る。このリポジトリの設定では短く押すと眠る） |
| 音声 | 0x06 | `KEY_LEFTCTRL` |
| しおり | 0x25 | なし（ドライバが黙って捨てる） |
| Home | 0x24 | なし |
| 辞書メニュー | 0x2b | なし |
| 記号 | 0x0c | 記号面への切り替え（`symbol-keycode`） |

- 割り当てのないキーは DTS の `keymap` に 1 行足せば使える（例: `<0x25 KEY_F1>`）。DTB の差し替えだけで済み、カーネルは作り直さなくてよい
- 記号面で打てるのは数字と `` ` = \ ; ' [ ] , . / `` だけ。MML でよく使う `@ < > & ^ { } # +` などはない → サブ液晶の記号表で補う
- 外している間は `KEY_POWER` が logind に届かないので、入/切を押しても電源は切れない（実機で確認）

## 記号表を入力にするには（未着手）

- タッチ → マス → 文字、の変換をする常駐プログラムを作り、キー入力として流す。どのエディタでも使える
- キー入力を作るには uinput が要るが、今のカーネルは `CONFIG_INPUT_UINPUT` が無効。rtl8xxxu66 と同じく外付けモジュールでビルドできるはず
- X の上で使うだけなら、uinput なしで `xdotool` 相当（XTest）で送る手もある

## ツール（`userspace/subpanel/`）

| ファイル | 用途 |
|---|---|
| `mkpalette.py` | 記号表の raw（と PNG の見本）を作る。Pillow が要る |
| `fbshow.py` | fbdev にモード設定してから raw を書く |
| `chvt.py` | VT を切り替える（kbd の chvt の代わり） |
| `inputlog.py` | キーボードのドライバを外して生のコードを読み、タッチと一緒に記録する。終わると戻す。二重起動はしない |
