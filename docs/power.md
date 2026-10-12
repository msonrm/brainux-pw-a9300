# CPU クロックと電源

## 今の状態（2026-10-12、Brainux 標準の設定 + このリポジトリのカーネル）

| 項目 | 値 | 読み方 |
|---|---|---|
| CPU | 454.7 MHz 固定（ref_cpu = PLL 480 MHz × 18/19、cpu_pll 分周 1） | `/sys/kernel/debug/clk/clk_summary` |
| HBUS | 151.6 MHz（CPU の 1/3） | 同上 |
| EMI（DRAM） | 196.4 MHz | 同上 |
| VDDD（コア電圧） | 1.55 V（`HW_POWER_VDDDCTRL` = 0x0002071e、TRG = 30） | LRADC ch13 でも 1.557 V |
| VDDIO / VDDA | 3.2 V / 1.79 V | ch10 / ch12 |
| cpufreq | なし（`CONFIG_CPU_FREQ` が無効、imx28.dtsi に OPP もない） | |
| サスペンド | s2idle で動く（下の「サスペンド」）。`deep` は mxs では `cpu_do_idle()`（WFI 1 回）を呼ぶだけで、1 秒ほどで起きてしまう（`arch/arm/mach-mxs/pm.c`） | |
| 電源断 | `poweroff` は syscon-poweroff（`HW_POWER_RESET` に PWD）。電池だけのとき、これで電源が切れ、「入/切」で起動できる（2026-10-12 に確認。起動は WinCE のメニューから Brainux を選ぶいつもの流れ） | |
| 電池残量 | `/sys/class/power_supply` がない。電池の見張りピン（下記）で段階的にわかる | |

- **ハブをつないでいると、5V が来ている。** OTG の電源付きハブが VBUS に 5V を返しており、VDD5V（ch15）が約 4.93 V、`HW_POWER_STS` の VBUSVALID が立っている。電池の減りを測るときは、ハブも USB ケーブルも外す
- **BATT 端子（LRADC ch7）は電池の電圧ではない。** 単 3 アルカリで、電池だけで動かしても 3.38〜3.43 V でほぼ一定、負荷をかけても下がらない（下の測定）。電池を昇圧したあとの一定の電圧が来ていると考えられる。残量の目安にならない
- 5V があるときの電源の経路: `HW_POWER_DCDC4P2` = 0x00c00000（ENABLE_4P2 と ENABLE_DCDC）、`HW_POWER_5VCTRL` = 0x24008113。5V から DCDC に給電できる設定だが、電池からどれだけ取っているかは未確認。ハブをつないだまま一日作業したあと、電池はほぼ空になっていた

- **電池の残量は GPIO4_4・GPIO4_6・GPIO4_7・GPIO4_8 でわかる。** どれも GPIO の入力で、電池が減ると 0 になる。ほぼ空のアルカリ電池で 4 本とも 0、新しいアルカリ電池に替えると 4 本とも 1 になった（2026-10-12、5V はつないだまま）。電圧の数値は取れず、段階だけ。どのピンがどの順で落ちるかは、電池を使い切りながら記録して確かめる
  - `userspace/power/battpins.c`: `HW_PINCTRL_DIN4` を `/dev/mem` から読むだけ（root、何も変えない）。`arm-linux-gnueabi-gcc -O2 -march=armv5te -static` でビルドして `/usr/local/bin/battpins` に置く。libgpiod のコマンドは Brainux に入っていない

`userspace/power/brain-power.sh` が 1 行で出す（root でなければ pins は出ない）。`brain-watch.sh` も 10 秒ごとに同じものを記録する（`pwr=[...]`）。

```
src=5v batt=3412mV 5v=5002mV vddd=1559mV vddio=3216mV pins=1111
```

pins は GPIO4_4・4_6・4_7・4_8 の順。

## 電池だけでの負荷試験（2026-10-12、方法が使えないとわかった）

`userspace/power/loadtest.sh` で、ハブを外して状態を 45 秒ずつ切り替え、BATT 端子の電圧を 1 秒ごとに記録した（後半 30 秒の中央値）。

| 状態 | BATT |
|---|---|
| 基準（バックライト 7/7、サブ 3/3） | 3390 mV |
| メインのバックライトを消す | 3391 mV |
| 基準 | 3392 mV |
| サブのバックライトを消す | 3395 mV |
| 基準 | 3391 mV |
| CPU 100% | 3388 mV |
| 基準 | 3388 mV |
| MUCOM88 の再生（スピーカー） | 3413 mV |
| 基準 | 3388 mV |

差は 1 LSB（1.8 mV）程度で、負荷を区別できない。電池の本当の電圧を読む方法が見つかるまで、この方法は使えない。LRADC の ch0・ch1・ch3・ch5・ch6 は今 0 付近で、どれかに電池が（分圧の切り替えなどを経て）つながっている可能性がある

- ハブを戻したとき、rtl8xxxu66 の初期化が失敗した（`rtl8xxxu_writeN: Failed to write block at addr: 1e00` → `probe … failed with error -11`）。Brain 自体は動き続けていたが、Wi-Fi はつながらなかった。抜き差しをやり直すか、モジュールを入れ直せば戻るはず（未確認）

## サスペンド（2026-10-12、動いた）

蓋を閉じると眠り、開けると 1 秒以内に起きる。キーを押しても起きる。カーネルのパッチ 2 つと設定 1 つ（[install.md](install.md) の手順 2）。

| 何が足りなかったか | 直し方 |
|---|---|
| 蓋の開閉は、キーボードのマイコン（I2C0 の 0x28）からスイッチのコード 3 で届いていた（閉じると on、開けると off）。`brain-kbd-i2c` はこれを「液晶をタブレットの形に回した」として捨てていた。GPIO には変化なし | `kernel/0003`: DT の `lid-switch-code = <3>` で、そのコードを `SW_LID` として出す。systemd-logind が蓋を閉じたら眠らせる（既定の `HandleLidSwitch=suspend`） |
| キーボードのマイコンの割り込みが起床に使われていなかった | `kernel/0003`: DT に `wakeup-source`。キーと蓋を開けたときの割り込みで起きる |
| `deep` で眠ると 1 秒で起きた（起こす合図でない割り込みでも WFI から戻る） | `system/etc/systemd/sleep.conf.d/brain-s2idle.conf` で s2idle にする。起こす合図が来るまで眠り続けた |
| 眠ってもメイン液晶のバックライトが消えなかった。明るさ 0 でも変わらない（1 だとほぼ消える） | `kernel/0002`: i.MX28 の PWM は、止めると最後の出力レベルを保ったままになる。明るさ 7（デューティ 100%）から止めると点きっぱなし。止める前に出力を消灯側に固定し、2 周期待ってから止める |

確かめたこと（PW-A9300、電源付きハブ・Wi-Fi 子機をつないだまま）:

- `systemctl suspend` → 約 25 秒眠り、キーで起きた。眠っている間、メインのバックライトは消えていた
- 蓋を閉じる → 約 8 秒後に眠った（NetworkManager などの準備に数秒かかる）→ 約 14 秒後に蓋を開けた瞬間に起きた。journal は `Lid closed.` → `PM: suspend entry (s2idle)` → `Lid opened.` → `PM: suspend exit`
- 起きたあと、Wi-Fi 子機（ハブの先）は USB のリセットを経て数秒でつながり直した
- 明るさ 0 で、メインのバックライトが消えた

わかったこと・罠:

- **この機種の s2idle は時計を止めない。** `CONFIG_CPU_IDLE` が無効なので（`kernel/sched/idle.c` の `cpuidle_not_available` の道を通る）、s2idle は「プロセスを止め、デバイスを眠らせ、WFI で待つ」だけで、CLOCK_MONOTONIC も CLOCK_BOOTTIME も進み続ける。眠っていた時間は時計の差では測れない。`userspace/power/sleepwatch.py` は 1 秒ごとのループの間が空いたことで測る。タイマーの割り込みでも CPU はときどき WFI から出る（すぐまた眠る）ので、眠っている間の電力はもっと下げられる余地がある
- `systemctl suspend` は眠るのを待たずに戻る。スクリプトで「起きたら」を書くときは注意
- journal の時刻: 眠る直前のカーネルのメッセージ（`Freezing ...` など）は、起きたあとに journald が読むので、起きた時刻が付く
- メインのバックライトの DT（`imx28-brain.dtsi`）にある `enable_gpios` は綴りが違い（`pwm-backlight` が読むのは `enable-gpios`）、使われていない。GPIO3_5 を 1 にするとバックライトがさらに明るくなった。点灯のピンではなく、バックライトの電流のモードを切り替えるピン（linux-brain PR #36 で「current-mode」として割り当てられたもの。綴りの違いで今は使われていない）。消費電力が増えるので、理由がなければ触らない
- 蓋の試験のあと開けたまま置いていたら、バックライトが消え、キーで 1 秒以内に戻った。サスペンドではない（journal に眠った記録がなく、`sleepwatch.py` も止まらずに動き続けていた）。X のスクリーンセーバー（600 秒で画面を消す）と DPMS（600 秒）が有効なので、最後のキー操作から 10 分で X が消したもの。蓋を開けたことは X の操作に数えられない。Brainux には `xset` がないので、libX11 の `XGetScreenSaver` と libXext の `DPMSGetTimeouts` を python の ctypes から呼んで確かめた
- 「入/切」ボタン（`KEY_POWER`）: Brainux の既定では押すと電源が切れる。`system/etc/systemd/logind.conf.d/brain-power-key.conf` で、短く押すと眠る（`HandlePowerKey=suspend`）、長押し（約 5 秒）で電源オフ（`HandlePowerKeyLongPress=poweroff`）にした。`sudo systemctl kill -s HUP systemd-logind` で再起動なしに効く
  - 試した結果: 短く押す → 約 5 秒後に眠った（NetworkManager の待ち合わせが 5 秒で打ち切られるまで待つ）→ もう一度押す → 起きた
  - 長押し: 5 秒で `Power key pressed long.` となり電源オフが始まる。電源が実際に切れるまでさらに 10 秒ほどかかるので、押している側には 5 秒より長く感じる
- **起こしたときの「入/切」を捨てる（`kernel/0003` に含む）。** 起こした押下がそのまま logind に届くと、新しい「眠れ」（押し続ければ「電源オフ」）と取られうる。logind は長押しを設定していると、短押しかどうかを離した時点で決める。0003 の前の試験では、起こした押下は離した時点でまだサスペンドの後始末中（`Operation 'suspend' finished.` の 3 秒前）だったので無視されていたが、3 秒以上押してから離せば眠り直す計算だった
  - 0003 では、サスペンドに入るときに構え、起きて最初の「入/切」の押下を離すまで捨てる。ほかのキーが押されるか、起きてから 1 秒たてば構えを解く（蓋で起きたときに、次の「入/切」を捨てないため）
  - 確かめたこと: 眠らせ、「入/切」を 3〜4 秒押し続けてから離して起こす → 眠り直さない。journal にも起こした押下は出ない。そのあと短く押す → ふつうに眠る
- 眠っている間にどれだけ電池が減るかは未測定

## CPU クロックを変える手がかり

- クロックの木は分周で下げられる: `cpu_pll` の分周（`HW_CLKCTRL_CPU` の DIV_CPU、6 ビット）を変えれば 454.7 / 227.4 / 151.6 / … MHz。`mxs_clk_div` は `set_rate` を持つ
- HBUS は CPU から分周しているので、CPU を下げると HBUS（DMA・LCD・SD などのバス）も下がる。LCD のちらつき・音の途切れに注意
- 2015 年に上流へ i.MX23/28 の cpufreq-dt 対応（VDDD などの mxs レギュレーター + OPP）が提案されている。OPP は 261.8 / 360 / 392.7 / 454.7 MHz を 1.35 / 1.35 / 1.45 / 1.55 V。レビューで「EMI が 196 MHz を超えるなら VDDD を 1.55 V より下げない」という指摘あり。NXP のフォーラムには 454.7 MHz 以外で固まったという報告もある
- 電圧を下げないと、クロックを下げても省電力の効きは小さい（アイドル時は WFI で止まっているので、もともと CPU はあまり食っていない）

## 進め方（案）

1. 測り方: 電池の見張りピンが落ちるまでの時間で比べる（粗いが実際の持ち時間がわかる。USB 電流計はない）
2. 何が電気を食っているかを先に見る（バックライト、Wi-Fi、CPU の負荷）
3. CPU クロック: 電圧はそのままで分周だけ下げ、安定するか見る → VDDD も下げる
4. サスペンド: 蓋と入/切で眠って起きるところまでできた（上）。眠っている間の電池の減りは、テスターがないと測る手間が大きいので保留
5. 電池残量: 見張りピンの 4 段階を Linux の power_supply として見せる（小さなドライバか、ユーザー空間で）

## ツール（`userspace/power/`）

| ファイル | 用途 |
|---|---|
| `brain-power.sh` | 電源の状態を 1 行で出す（5V の有無、各電圧、電池の見張りピン） |
| `battpins.c` | 電池の見張りピン（GPIO4_4/4_6/4_7/4_8）を読む |
| `loadtest.sh` | 電池だけで負荷を切り替えて BATT 端子を記録する（BATT が電池の電圧でないとわかった試験） |
| `sleeptest.sh` | 明るさ 0 で消えるか、`systemctl suspend` で眠ってキーで起きるかを順に試す |
| `sleepwatch.py` | 眠っていた時間と蓋の開閉を記録する（root 不要、nohup で動かしてあとでログを読む） |
| `swlog.py`・`gpiowatch.py` | 蓋の開閉がどこに出るかを探したときの記録用（入力イベント・GPIO の変化） |
| `bltest.sh` | 0002 の前にバックライトを調べた記録（GPIO3_5 に直接書くので、理由がなければ動かさない） |
