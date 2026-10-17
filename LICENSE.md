# ライセンス

ディレクトリごとに異なります。

| 対象 | ライセンス |
|---|---|
| `kernel/`（`*.patch`、`rtl8xxxu66/`・`uinput/` のパッチ・スクリプト。取ってくる rtl8xxxu・uinput のソースを含む） | GPL-2.0（Linux カーネルに従う。`ymu818.c` は GPL-2.0-only、`mxs-ymu818.c` は GPL-2.0-or-later。`0011` は上流の Linux の修正で、作者はパッチの From: の人） |
| `mucom88/0001-*.patch` | CC BY-NC-SA 4.0（OPEN MUCOM88 に従う。https://github.com/onitama/mucom88 の license.txt を参照） |
| `mucom88/rhythm/` | 作者（メモルさん）の配布条件に従う（`PROVENANCE_2608modoki2.utf8.txt`。配布・組み込み自由） |
| `docs/`、`README.md` | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/deed.ja)（© 2026 msonrm）。文書の中のコマンドやコードの例は、MIT License としても使えます |
| 上記以外（`tools/`、`userspace/`、`system/`、`mucom88/*.sh`） | MIT License（下記） |

---

MIT License

Copyright (c) 2026 msonrm

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
