# Wi-Fi: TL-WN725N（RTL8188EUS）

## つなぎ方

PW-A9300 の USB（mini-B）は 1 つだけです。DTB の `dr_mode` を `host` にし（`sudo brain-config` → Interface Options → USB、または `sudo brain-config nonint do_usb host`）、次のようにつなぎました。

```
Brain ── OTG ケーブル（USB mini-B ⇔ USB-A）── 電源付き USB ハブ ── TL-WN725N
```

- ハブ: SUNEAST SE-RU3HUBA4A3（AC アダプター付き）。Brain は乾電池で動くので、子機の電源はハブからとる
- 子機: TP-Link TL-WN725N v2/v3（USB ID `0bda:8179`、RTL8188EUS）
- ファームウェア: `rtlwifi/rtl8188eufw.bin`（Debian の firmware-realtek、または linux-firmware）
- `wpasupplicant` が Brainux に入っていなかったので、Debian の armel パッケージを別の PC で取得し、署名を確かめて入れた
- 2.4GHz のアクセスポイントが要る（スマートフォンのテザリングで確認）

ホストモードのあいだは、USB ケーブルで PC につなぐ使い方（USB ガジェットの Ethernet）はできません。

## 何が起きたか

### 1. Linux 6.1 の rtl8xxxu は RTL8188EU を知らない

RTL8188EU に対応したのは Linux 6.3 からです。そこで、まず staging の `r8188eu` をモジュールで入れました。接続も SSH もインターネットもすぐ使えました。

### 2. ところが、起動から 4〜20 分で完全に固まる

画面もキーボードも止まり、ログには何も残りませんでした。調べていくと、二つの原因が重なっていました。

- **メモリ不足。** Debian の自動更新（apt-daily）が起動の数分後に動き、`apt-get` が約 50MB 使う。RAM 112MB・スワップなしの Brain では足りず、OOM killer が動いた記録が 1 回分残っていた。→ [stability.md](stability.md)
- **r8188eu そのもの。** メモリの対策をしたあとも、起動から 19 分で固まった。10 秒ごとに状態を記録する仕組み（`userspace/brain-watch.sh`）を入れておいたので、直前の空きメモリは 75MB と十分だったことがわかった

### 3. 犯人は「子機が USB から抜けて戻ること」

Linux 6.6 の rtl8xxxu を 6.1 で動かしてみると（下記）、20 分の負荷試験の途中でこう記録されました。

```
usb 1-1-port3: disabled by hub (EMI?), re-enabling...
usb 1-1.3: USB disconnect, device number 3
```

ハブが、ノイズなどで信号が乱れたと判断して、子機のポートを一度止めていました。rtl8xxxu はこれを普通に受け止め、12 秒でつなぎ直しました。r8188eu で固まったときのログにも「子機が消えてまた現れた」記録があったので、**staging の r8188eu は、この抜き差しの後始末でシステムごと固まっていた**と考えています。r8188eu では、何もしていないときの load average が常に 1 を超えていたことも、rtl8xxxu（約 0.3）との違いでした。

## rtl8xxxu66: Linux 6.6 の rtl8xxxu を 6.1 で使う

6.6 のドライバを 6.1 のカーネルでビルドすると、エラーは 1 か所だけでした。

- `ieee80211_handle_wake_tx_queue` は 6.2 で mac80211 に入った関数。6.1 では `.wake_tx_queue` の行を外せば、従来の送信経路で動く

さらに、カーネルに組み込まれている 6.1 の rtl8xxxu とぶつからないよう、ドライバ名を `rtl8xxxu66` にしました。これで**カーネルを作り直さず、外付けのモジュールとして足せます**。SD カードの差し替えも再起動も要りません。

```sh
cd kernel/rtl8xxxu66
sh fetch-sources.sh                       # kernel.org から v6.6 のソースを取り、チェックサムを確かめてパッチを当てる
sh build.sh <linux-brain のソース> <ビルド出力>   # 今動いているカーネルと同じビルドが必要（vermagic を合わせる）
```

Brain での載せ替え（Wi-Fi 越しでも安全なように、90 秒以内につながらなければ r8188eu に自動で戻す）:

```sh
sudo setsid nohup sh swap-to-rtl8xxxu66.sh rtl8xxxu66.ko &
cat /var/log/wifi-swap.log
```

スクリプトは `.ko` を `/usr/lib/modules/$(uname -r)/extra/` に入れ、`/etc/modprobe.d/r8188eu-blacklist.conf` で r8188eu を止めます。次に起動したときからは rtl8xxxu66 が自動で使われます。

## 負荷試験の結果（rtl8xxxu66）

`userspace/wifi-stress.sh` を PC 側で 20 分動かしました。2 秒ごとの ping、1 分ごとの SSH の接続、3 回に 1 回 5MB の転送です。

| 項目 | 結果 |
|---|---|
| SSH | 17 回すべて成功（1 回 8〜9 秒。Brain は鍵交換が重い） |
| 5MB の転送 | 5 回すべてチェックサム一致 |
| ping | 599 回中 589 回応答。途切れ 1 回（14 秒、上のハブのポート停止） |

## 気づいたこと

- rtl8xxxu66 の送信処理（`rtl8xxxu_fill_txdesc_v3`）は、カーネル内で unaligned access を起こしている（`/proc/cpu/alignment` の System が増える）。カーネルが補正しているので動作は正しいが、少し無駄がある
- 接続時に `Limiting TX power to 0 (-128 - 0) dBm as advertised by ...` と出る。通信はできている
- rtl8xxxu66 には眠る・起きるの処理（suspend・resume）がない。起きるたびに USB の層がドライバを外して子機をリセットし、初期化をやり直す。それがときどきファームウェアの書き込みで失敗し（`rtl8xxxu_writeN: Failed to write block at addr: 1d00` → `probe ... failed with error -11`）、Wi-Fi が来なくなる。ハブの抜き差しでも同じ失敗が出る。子機を挿し直せば戻る。起きたときと、動いている最中にハブを挿したときは、`brain-wifi-reprobe`（[install.md](install.md) の手順 2 のサスペンド。ハブを挿したときは brain-5v-ilimit が起こす）が、子機のハブのポートの電源を 8 秒切って自動でやり直す（`authorized` の付け直しでは、ドライバはつくがビーコンを受けず戻らなかった。2026-10-15、[power.md](power.md)）
- 電源を切る時間は 2 秒では足りないことがある（2026-10-17）。ハブを挿したあと、2〜3 秒切っては -11 が 4 回続き（やり直しの 2 回と手の抜き差し 1 回を含む）、9 秒抜いていたら戻った。8 秒にし、試すのを 3 回まで、見張るのを 90 秒にした。延ばしたあと（15:00:19 にハブを挿す → 15:00:20 に -11 → 15:00:29〜37 の 8 秒切る → 15:00:39 にドライバがつく）、1 回で戻り、挿してから約 40 秒で SSH が通った
