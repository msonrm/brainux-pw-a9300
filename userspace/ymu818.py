#!/usr/bin/env python3
"""YMU818 を I2C0 (0x3A) から操作する試験用ツール（Brain 上で root で動かす）。

usage: sudo python3 ymu818.py [--dry-run] [--vol 0xNN] CMD [CMD...]
  probe   レジスタ 0..15 を読む
  reset   GPIO3_27 で 1 →(10ms)→ 0 →(20ms)→ 1 のリセットパルス
  init    WAV_Init の手順          （SAIF0 の MCLK が出ている必要がある）
  start   BSPAudioStartDAC の手順  （同上。PLL ロックを待つ）
  amp     SetVolume(0 -> 非 0)。スピーカーアンプを入れて --vol の音量にする
  mute    SetVolume(-> 0)。アンプを切る
  stop    BSPAudioStopDAC の手順
手順は ymu818_speaker_sequence.txt（WinCE ドライバのエミュレーション結果）から読む。
1 行が I2C の 1 回のやり取りで、WinCE と同じバイト列を送る。
"""
import ctypes, fcntl, os, struct, sys, time

ADDR = 0x3A
SEQ = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'ymu818_speaker_sequence.txt')
SECTIONS = {'init': 'WAV_Init', 'start': 'BSPAudioStartDAC', 'stop': 'BSPAudioStopDAC',
            'amp': 'SetVolume (0 -> nonzero)', 'mute': 'SetVolume (-> 0)'}
VOL_MAX = 0x2a  # 試験中の上限。WinCE の最大は 0x3b

I2C_SLAVE, I2C_RDWR, I2C_M_RD = 0x0703, 0x0707, 0x0001


class I2CMsg(ctypes.Structure):
    _fields_ = [('addr', ctypes.c_uint16), ('flags', ctypes.c_uint16),
                ('len', ctypes.c_uint16), ('buf', ctypes.POINTER(ctypes.c_uint8))]


class I2CRdwr(ctypes.Structure):
    _fields_ = [('msgs', ctypes.POINTER(I2CMsg)), ('nmsgs', ctypes.c_uint32)]


def regaddr(reg):
    """10bit レジスタ番号を、最上位ビットが立ったバイトで終わる形にする"""
    if reg < 0x80:
        return [0x80 | reg]
    return [reg & 0x7f, 0x80 | (reg >> 7)]


class YMU:
    def __init__(self, dry):
        self.dry = dry
        if not dry:
            self.fd = os.open('/dev/i2c-0', os.O_RDWR)
            fcntl.ioctl(self.fd, I2C_SLAVE, ADDR)

    def _xfer(self, msgs):
        arr = (I2CMsg * len(msgs))()
        bufs = []
        for i, (flags, data) in enumerate(msgs):
            b = (ctypes.c_uint8 * len(data))(*data)
            bufs.append(b)
            arr[i] = I2CMsg(ADDR, flags, len(data), b)
        fcntl.ioctl(self.fd, I2C_RDWR, I2CRdwr(arr, len(msgs)))
        return bufs

    def write(self, reg, data):
        print('  W %03x %s' % (reg, ' '.join('%02x' % d for d in data)))
        if not self.dry:
            self._xfer([(0, regaddr(reg) + list(data))])

    def read(self, reg):
        if self.dry:
            print('  R %03x -> (dry)' % reg)
            return 0
        bufs = self._xfer([(0, regaddr(reg)), (I2C_M_RD, [0])])
        v = bufs[1][0]
        print('  R %03x -> %02x' % (reg, v))
        return v

    def wait(self, reg, mask, want_set, timeout_ms=200):
        for _ in range(timeout_ms):
            v = self.read(reg) if not self.dry else (mask if want_set else 0)
            if ((v & mask) == mask) if want_set else not (v & mask):
                return
            time.sleep(0.001)
        raise RuntimeError('timeout: reg %03x bits %02x %s' % (reg, mask, 'set' if want_set else 'clear'))


def load_sections(path):
    secs, cur = {}, None
    for line in open(path):
        line = line.strip()
        if line.startswith('## '):
            cur = line[3:].split(':')[0].strip(); secs[cur] = []
        elif cur and line and not line.startswith('#'):
            secs[cur].append(line.split())
    return secs


def run(ymu, ops, vol):
    for op in ops:
        if op[0] == 'W':
            reg, data = int(op[1], 16), [int(x, 16) for x in op[2:]]
            if reg == 0x025 and len(data) == 1 and data[0] != 0x20:
                data = [vol]
            ymu.write(reg, data)
        elif op[0] == 'R':
            ymu.read(int(op[1], 16))
        elif op[0] == 'WAIT':
            ymu.wait(int(op[1], 16), int(op[2], 16), op[3] == 'set')
        elif op[0] == 'delay':
            time.sleep(int(op[1]) / 1000)


def gpio_reset(dry):
    """GPIO3_27 (gpiochip3 line 27) を出力にしてリセットパルスを出す（GPIO v1 ABI）"""
    print('  reset: GPIO3_27 1 -> 0 -> 1')
    if dry:
        return
    REQ, SET = 0xc16cb403, 0xc040b409
    fd = os.open('/dev/gpiochip3', os.O_RDONLY)
    req = bytearray(struct.pack('64I', 27, *([0] * 63)) + struct.pack('I', 2) +
                    bytes([1] + [0] * 63) + b'ymu818-reset'.ljust(32, b'\0') + struct.pack('Ii', 1, 0))
    fcntl.ioctl(fd, REQ, req)
    lfd = struct.unpack_from('i', req, len(req) - 4)[0]
    for v, ms in ((1, 10), (0, 20), (1, 0)):
        fcntl.ioctl(lfd, SET, bytearray([v] + [0] * 63))
        time.sleep(ms / 1000)
    # 閉じても mxs の GPIO は出力 High のまま残る
    os.close(lfd); os.close(fd)


def main(argv):
    dry = '--dry-run' in argv
    vol = 0x22
    if '--vol' in argv:
        vol = int(argv[argv.index('--vol') + 1], 0)
        argv = [a for i, a in enumerate(argv) if a != '--vol' and (i == 0 or argv[i - 1] != '--vol')]
    if not 0x20 <= vol <= VOL_MAX:
        sys.exit('--vol は 0x20..%#x の範囲で' % VOL_MAX)
    cmds = [a for a in argv if not a.startswith('--')]
    if not cmds:
        sys.exit(__doc__)
    secs = load_sections(SEQ)
    ymu = YMU(dry)
    for c in cmds:
        print('== %s' % c)
        if c == 'probe':
            for r in range(16):
                ymu.read(r)
        elif c == 'reset':
            gpio_reset(dry)
        elif c in SECTIONS:
            run(ymu, secs[SECTIONS[c]], vol)
        else:
            sys.exit('unknown command: %s' % c)


if __name__ == '__main__':
    main(sys.argv[1:])
