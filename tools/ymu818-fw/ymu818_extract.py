"""自分の Brain の WinCE イメージから YMU818 の手順を抽出し、ドライバ用のファームウェアを作る。

usage: venv/bin/python -I ymu818_extract.py NK_IMAGE OUT.bin [--text OUT.txt]
  NK_IMAGE: 内蔵 eMMC の WinCE パーティション（PW-A9300 では mmcblk0 の sector 2304 から 32MiB）
  ymu818_wavdev.dll を Unicorn で動かし、場面ごとの I2C アクセスを記録する（emu_wav.py が必要）。

ファームウェアの形式（すべてリトルエンディアン）:
  "YMU818SQ" u16 version(=1) u16 nsect
  section: u8 id, u8 0, u16 nops, ops...
  op: 1 W  u16 reg u16 len data[len]   I2C の 1 回の書き込み
      2 R  u16 reg                      読み出し（結果は使わない）
      3 WAIT_SET u16 reg u8 mask        ビットが立つまで待つ
      4 WAIT_CLR u16 reg u8 mask        ビットが消えるまで待つ
      5 DELAY u16 ms
  section id: 1 init, 2 start_spk, 3 stop_spk, 4 amp_on_spk, 5 amp_off_spk,
              6 start_hp, 7 stop_hp, 8 amp_on_hp, 9 amp_off_hp
  amp_on_spk のスピーカー音量レジスタ 0x025 への書き込みは含めない（ドライバが自分の音量を書く）。
  ヘッドホンの音量（0x023、抽出時の WinCE 音量 0x2000 相当）は amp_on_hp にそのまま残る。
"""
import contextlib, io, os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
WAV_INIT, START_DAC, STOP_DAC, WAVMSG = 0xc077331c, 0xc077a094, 0xc077a12c, 0xc077338c
HWCTX = 0x20001040
WODM_SETVOLUME = 17

def scenario(image, hpdet):
    """新しいエミュレータで init → start → amp_on → amp_off → stop を流し、場面ごとの記録を返す"""
    ns = {'__name__': 'emu'}
    sys.argv = ['emu_wav.py', image]
    src = open(os.path.join(HERE, 'emu_wav.py')).read().split("if __name__ == '__main__':")[0]
    with contextlib.redirect_stdout(io.StringIO()):
        exec(src, ns)
    ns['HPDET'][0] = hpdet
    call, alloc, uc, log = ns['call'], ns['alloc'], ns['uc'], ns['log']

    def msg(m, p1):
        b = alloc(20); uc.mem_write(b, struct.pack('<5I', 0, m, 0, p1, 0))
        return call(WAVMSG, b, alloc(4), limit=3_000_000)

    out = {}
    def run(name, fn):
        n = len(log)
        with contextlib.redirect_stdout(io.StringIO()):
            fn()
        out[name] = log[n:]

    ctx = alloc(64); uc.mem_write(ctx, 'Drivers\\Active\\01\0'.encode('utf-16le'))
    run('init', lambda: call(WAV_INIT, ctx, 0))
    run('start', lambda: call(START_DAC, HWCTX))
    run('amp_on', lambda: msg(WODM_SETVOLUME, 0x20002000))
    run('amp_off', lambda: msg(WODM_SETVOLUME, 0))
    run('stop', lambda: call(STOP_DAC, HWCTX, limit=300_000))  # 最後の SAIF 待ちは打ち切る
    return out

def encode(entries, drop_volume=False):
    ops = []
    for e in entries:
        if e[0] == 'w':
            if drop_volume and e[1] == 0x025:
                continue
            ops.append(struct.pack('<BHH', 1, e[1], len(e[2])) + bytes(e[2]))
        elif e[0] == 'r':
            ops.append(struct.pack('<BH', 2, e[1]))
        elif e[0] == 'waitset':
            ops.append(struct.pack('<BHB', 3, e[1], e[2]))
        elif e[0] == 'waitclr':
            ops.append(struct.pack('<BHB', 4, e[1], e[2]))
        elif e[0] == 'delay':
            ops.append(struct.pack('<BH', 5, e[1]))
    return len(ops), b''.join(ops)

def text(entries):
    lines = []
    for e in entries:
        if e[0] == 'w':
            lines.append('W %03x %s' % (e[1], ' '.join('%02x' % d for d in e[2])))
        elif e[0] == 'r':
            lines.append('R %03x' % e[1])
        elif e[0] in ('waitset', 'waitclr'):
            lines.append('WAIT %03x %02x %s' % (e[1], e[2], 'set' if e[0] == 'waitset' else 'clear'))
        elif e[0] == 'delay':
            lines.append('delay %d' % e[1])
    return lines

def main():
    image, outbin = sys.argv[1], sys.argv[2]
    outtxt = sys.argv[sys.argv.index('--text') + 1] if '--text' in sys.argv else None
    spk, hp = scenario(image, 1), scenario(image, 0)
    if text(spk['init']) != text(hp['init']):
        sys.exit('init differs between speaker and headphone runs')
    sections = [(1, 'init', spk['init'], False),
                (2, 'start_spk', spk['start'], False), (3, 'stop_spk', spk['stop'], False),
                (4, 'amp_on_spk', spk['amp_on'], True), (5, 'amp_off_spk', spk['amp_off'], False),
                (6, 'start_hp', hp['start'], False), (7, 'stop_hp', hp['stop'], False),
                (8, 'amp_on_hp', hp['amp_on'], True), (9, 'amp_off_hp', hp['amp_off'], False)]
    blob = b'YMU818SQ' + struct.pack('<HH', 1, len(sections))
    txt = []
    for sid, name, entries, dropvol in sections:
        n, body = encode(entries, dropvol)
        if n == 0:
            sys.exit('section %s is empty' % name)
        blob += struct.pack('<BBH', sid, 0, n) + body
        txt += ['', '## %s' % name] + text(entries)
        print('%-12s %3d ops' % (name, n))
    open(outbin, 'wb').write(blob)
    print('wrote %s (%d bytes)' % (outbin, len(blob)))
    if outtxt:
        open(outtxt, 'w').write('\n'.join(txt).lstrip() + '\n')

if __name__ == '__main__':
    main()
