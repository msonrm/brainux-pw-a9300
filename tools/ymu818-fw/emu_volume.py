"""WinCE の WODM_SETVOLUME をいろいろな値で流し、音量レジスタへの書き込みを調べる（2026-10-13）。
usage: venv/bin/python -I tools/ymu818-fw/emu_volume.py nk_part.bin [--sweep]
  スピーカー（検出ピン 1）とヘッドホン（0）で、init → start のあと SETVOLUME を順に送る。
  値は WinCE の waveOutSetVolume と同じ形（下位 16 ビット = 左、上位 = 右）。
"""
import contextlib, io, os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
WAV_INIT, START_DAC, WAVMSG = 0xc077331c, 0xc077a094, 0xc077338c
HWCTX = 0x20001040
WODM_SETVOLUME = 17

def env(image, hpdet):
    ns = {'__name__': 'emu'}
    sys.argv = ['emu_wav.py', image]
    src = open(os.path.join(HERE, 'emu_wav.py')).read().split("if __name__ == '__main__':")[0]
    with contextlib.redirect_stdout(io.StringIO()):
        exec(src, ns)
    ns['HPDET'][0] = hpdet
    return ns

def main():
    image = sys.argv[1]
    if '--sweep' in sys.argv:
        vols = [0xffff] + [x for x in range(0, 0x10000, 0x400)] + [0xffff]
    else:
        vols = [0x00000000, 0x08000800, 0x10001000, 0x20002000, 0x40004000, 0x80008000,
                0xc000c000, 0xffffffff, 0x0000ffff, 0xffff0000, 0x2000ffff, 0xffff2000,
                0x00002000, 0x20000000, 0x20002000]
    for hpdet, name in ((1, 'speaker'), (0, 'headphone')):
        ns = env(image, hpdet)
        call, alloc, uc, log = ns['call'], ns['alloc'], ns['uc'], ns['log']
        def msg(m, p1):
            b = alloc(20); uc.mem_write(b, struct.pack('<5I', 0, m, 0, p1, 0))
            return call(WAVMSG, b, alloc(4), limit=3_000_000)
        ctx = alloc(64); uc.mem_write(ctx, 'Drivers\\Active\\01\0'.encode('utf-16le'))
        with contextlib.redirect_stdout(io.StringIO()):
            call(WAV_INIT, ctx, 0)
            call(START_DAC, HWCTX)
        print('== %s' % name)
        for v in vols:
            n = len(log)
            with contextlib.redirect_stdout(io.StringIO()):
                msg(WODM_SETVOLUME, v)
            ws = ['%03x:%s' % (e[1], ' '.join('%02x' % d for d in e[2]))
                  for e in log[n:] if e[0] == 'w']
            print('  %08x  %s' % (v, '  '.join(ws) or '(no write)'))

if __name__ == '__main__':
    main()
