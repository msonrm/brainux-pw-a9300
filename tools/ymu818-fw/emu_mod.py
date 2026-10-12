"""ymu818_wavdev.dll を Unicorn で動かし、YMU818 への I2C アクセスを記録する。
usage: venv/bin/python -I emu_wav.py IMAGE [steps...]
"""
import struct, sys
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_UNMAPPED, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from unicorn.arm_const import *

IMG = sys.argv[1]
img = open(IMG, 'rb').read()
ROMHDR = 0x1acc380
pf = struct.unpack_from('<I', img, ROMHDR + 8)[0]
nummods = struct.unpack_from('<I', img, ROMHDR + 16)[0]
v2o = lambda va: va - pf

def cstr(o):
    return img[o:img.index(b'\0', o)].decode('latin1')

mods = {}
for i in range(nummods):
    a = struct.unpack_from('<8I', img, ROMHDR + 84 + 32 * i)
    mods[cstr(v2o(a[4])).lower()] = (v2o(a[5]), v2o(a[6]))

def load(name):
    e32, o32 = mods[name.lower()]
    objcnt = struct.unpack_from('<H', img, e32)[0]
    vbase = struct.unpack_from('<I', img, e32 + 8)[0]
    vsize = struct.unpack_from('<I', img, e32 + 20)[0]
    units = [struct.unpack_from('<II', img, e32 + 36 + 8 * k) for k in range(9)]
    secs = []
    for j in range(objcnt):
        vs, rva, ps, dp, real, flags = struct.unpack_from('<6I', img, o32 + 24 * j)
        secs.append((rva, vs, ps, dp, real))
    return vbase, vsize, units, secs

def export_names(name):
    vbase, vsize, units, secs = load(name)
    mem = bytearray(vsize + 0x1000)
    for rva, vs, ps, dp, real in secs:
        if dp:
            n = min(vs, ps); mem[rva:rva + n] = img[v2o(dp):v2o(dp) + n]
    rva = units[0][0]
    if not rva:
        return {}
    (_, _, _, nm, base, nfun, nnames, afun, anames, aords) = struct.unpack_from('<10I', mem, rva)
    out = {}
    for k in range(nnames):
        p = struct.unpack_from('<I', mem, anames + 4 * k)[0]
        if p >= vbase: p -= vbase
        if p < len(mem) and b'\0' in mem[p:p + 128]:
            n = mem[p:mem.index(b'\0', p)].decode('latin1')
        else:
            n = cstr(v2o(p))
        out[struct.unpack_from('<H', mem, aords + 2 * k)[0] + base] = n
    return out

MOD = sys.argv[2].lower()
vbase, vsize, units, secs = load(MOD)
uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
uc.mem_map(vbase, (vsize + 0x10000) & ~0xfff)
for rva, vs, ps, dp, real in secs:
    if dp:
        n = min(vs, ps)
        uc.mem_write(real, img[v2o(dp):v2o(dp) + n])

# ヒープ・スタック・スタブ・偽 MMIO
HEAP, STACK, STUB, MMIO = 0x20000000, 0x30000000, 0x10000000, 0x40000000
uc.mem_map(HEAP, 0x1000000)
uc.mem_map(STACK, 0x100000)
uc.mem_map(STUB, 0x10000)
uc.mem_map(MMIO, 0x100000)
uc.mem_map(0xffff0000, 0x10000)  # KData ページ（0xFFFFC800 付近）
uc.mem_write(STUB, b'\x1e\xff\x2f\xe1' * 0x4000)  # bx lr
heap_ptr = [HEAP + 0x1000]
def alloc(n):
    p = heap_ptr[0]; heap_ptr[0] += (n + 15) & ~15
    return p

# インポートをスタブに差し替える
stubs = {}
rva = units[1][0]
mem_hdr = bytes(uc.mem_read(vbase, (vsize + 0x10000) & ~0xfff))
k = 0
while True:
    oft, ts, fwd, nm, ft = struct.unpack_from('<5I', mem_hdr, rva)
    if not nm:
        break
    p = nm if nm < 0x20000 else nm - vbase
    dll = mem_hdr[p:mem_hdr.index(b'\0', p)].decode()
    try:
        ex = export_names(dll)
    except KeyError:
        ex = {}
    t = oft or ft
    i = 0
    while True:
        v = struct.unpack_from('<I', mem_hdr, t + 4 * i)[0]
        if not v:
            break
        fn = ex.get(v & 0xffff, 'ord%d' % (v & 0xffff)) if v & 0x80000000 else \
            mem_hdr[v + 2:mem_hdr.index(b'\0', v + 2)].decode()
        addr = STUB + 4 * k
        stubs[addr] = fn
        uc.mem_write(vbase + ft + 4 * i, struct.pack('<I', addr))
        i += 1; k += 1
    rva += 20

def R(r): return uc.reg_read(r)
def ret(v=0, v1=None):
    uc.reg_write(UC_ARM_REG_R0, v & 0xffffffff)
    if v1 is not None: uc.reg_write(UC_ARM_REG_R1, v1 & 0xffffffff)
def wstr(p, maxn=200):
    b = uc.mem_read(p, maxn * 2)
    s = b.decode('utf-16le', 'replace')
    return s.split('\0')[0]
def arg(n):
    if n < 4: return R([UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3][n])
    return struct.unpack('<I', uc.mem_read(R(UC_ARM_REG_SP) + 4 * (n - 4), 4))[0]

def wfmt(fmt, base):
    out, i, n = '', 0, base
    while i < len(fmt):
        c = fmt[i]
        if c != '%':
            out += c; i += 1; continue
        j = i + 1
        while j < len(fmt) and fmt[j] in '0123456789-#l.': j += 1
        t = fmt[j] if j < len(fmt) else ''
        spec = fmt[i:j + 1].replace('l', '')
        a = arg(n); n += 1
        if t in 'dxXuc':
            if t == 'd' and a & 0x80000000: a -= 1 << 32
            out += (spec % a) if t != 'c' else chr(a)
        elif t in 'sS':
            out += wstr(a) if a else '(null)'
        elif t == '%':
            out += '%'; n -= 1
        else:
            out += spec
        i = j + 1
    return out

log = []
regs = {}   # YMU818 レジスタの模型（書いた値を覚え、読み出しに返す）
REAL = [0x3b, 0xff, 0xff, 0xff, 0x0f, 0x68, 0x1e, 0x62, 0x0f, 0xe0, 0xe0, 0, 0, 0, 0, 0x02]
for r, v in enumerate(REAL): regs[r] = v
handles = [0x100]
HPDET = [0]
threads = []
mmio_maps = []
quiet = {'EnterCriticalSection', 'LeaveCriticalSection', 'InitializeCriticalSection', 'DeleteCriticalSection'}

def stub_call(fn):
    lr = R(UC_ARM_REG_LR)
    if fn == 'NKDbgPrintfW':
        s = wfmt(wstr(arg(0)), 1).rstrip()
        log.append(('dbg', s)); print('  [dbg]', s)
        ret(0)
    elif fn in ('LocalAlloc',):
        p = alloc(arg(1)); uc.mem_write(p, b'\0' * arg(1)); ret(p)
    elif fn == '??2@YAPAXI@Z':
        p = alloc(arg(0)); uc.mem_write(p, b'\0' * arg(0)); ret(p)
    elif fn == 'HalAllocateCommonBuffer':
        n = arg(1); p = alloc(n + 0x1000); ret(p)
        pa = arg(2)
        if pa: uc.mem_write(pa, struct.pack('<Q', p))
    elif fn == 'MmMapIoSpace':
        pa = arg(0); n = arg(2)
        p = MMIO + 0x2000 * len(mmio_maps)
        mmio_maps.append((pa, p, n)); print('  MmMapIoSpace phys=%#x size=%#x -> %#x' % (pa, n, p))
        ret(p)
    elif fn == 'memset':
        uc.mem_write(arg(0), bytes([arg(1) & 0xff]) * arg(2)); ret(arg(0))
    elif fn == 'memcpy':
        uc.mem_write(arg(0), bytes(uc.mem_read(arg(1), arg(2)))); ret(arg(0))
    elif fn == 'memcmp':
        a = bytes(uc.mem_read(arg(0), arg(2))); b = bytes(uc.mem_read(arg(1), arg(2)))
        ret((a > b) - (a < b))
    elif fn == 'wcscpy':
        s = wstr(arg(1)) + '\0'; uc.mem_write(arg(0), s.encode('utf-16le')); ret(arg(0))
    elif fn == '__rt_udiv':
        d, n = arg(0), arg(1)
        ret(n // d if d else 0, n % d if d else 0)
    elif fn == '__rt_udiv64by64':
        d = arg(0) | arg(1) << 32; n = arg(2) | arg(3) << 32
        q = n // d if d else 0
        ret(q & 0xffffffff, q >> 32)
    elif fn == '__rt_sdiv64by64':
        d = arg(0) | arg(1) << 32; n = arg(2) | arg(3) << 32
        if d >> 63: d -= 1 << 64
        if n >> 63: n -= 1 << 64
        q = int(n / d) if d else 0
        q &= (1 << 64) - 1
        ret(q & 0xffffffff, q >> 32)
    elif fn in ('CreateEventW', 'CreateThread', 'I2COpenHandle', 'timeSetEvent'):
        h = handles[0]; handles[0] += 1
        if fn == 'CreateThread':
            threads.append((arg(2), arg(3))); print('  CreateThread start=%#x param=%#x' % (arg(2), arg(3)))
        ret(h)
    elif fn in ('WaitForSingleObject', 'WaitForMultipleObjects'):
        ret(0x102)  # WAIT_TIMEOUT
    elif fn in ('KernelIoControl', 'InterruptInitialize', 'CloseHandle', 'EventModify',
                'CeSetThreadPriority', 'DisableThreadLibraryCalls', 'QueryPerformanceFrequency',
                'QueryPerformanceCounter', 'InterruptDone', 'I2CCloseHandle'):
        if fn == 'KernelIoControl':
            print('  KernelIoControl code=%#x' % arg(0))
        ret(1)
    elif fn in ('OpenDeviceKey', 'RegQueryValueExW'):
        if fn == 'RegQueryValueExW': print('  RegQueryValueExW', wstr(arg(1)))
        ret(0 if fn == 'OpenDeviceKey' else 2)
    elif fn == 'DDKGpioReadDataPin':
        print('  DDKGpioReadDataPin(%#x) -> %d' % (arg(0), HPDET[0]))
        log.append(('gpioread', arg(0), HPDET[0]))
        uc.mem_write(arg(1), struct.pack('<I', HPDET[0])); ret(1)
    elif fn.startswith('DDK'):
        print('  %s(%s)' % (fn, ', '.join('%#x' % arg(i) for i in range(4))))
        log.append(('ddk', fn, [arg(i) for i in range(4)]))
        ret(1)
    else:
        if fn not in quiet:
            print('  stub', fn, ', '.join('%#x' % arg(i) for i in range(4)))
        ret(0)
    uc.reg_write(UC_ARM_REG_PC, lr)

def ymu_write(reg, data):
    for k, d in enumerate(data):
        regs[reg + k] = d
    log.append(('w', reg, list(data)))
    print('  YMU W reg=%03x' % reg, ' '.join('%02x' % d for d in data))

WR1, WRN, RD = 0xc077d110, 0xc077d1c4, 0xc077d2a8
DELAY = 0xc0779794  # RTC ミリ秒カウンタで空回りする待ち関数
WAITSET, WAITCLR = 0xc0783050, 0xc07830d0  # 読み出し直後の比較（ビット待ち）
MSLEEP = 0xc0774370  # KData を見て Sleep か StallExecution で待つ関数
def hook_code(uc_, addr, size, ud):
    if STUB <= addr < STUB + 0x10000:
        stub_call(stubs.get(addr, 'unknown@%#x' % addr)); return
    if addr == WR1:
        ymu_write(arg(0), [arg(1) & 0xff]); ret(0); uc.reg_write(UC_ARM_REG_PC, R(UC_ARM_REG_LR))
    elif addr == WRN:
        ymu_write(arg(0), list(uc.mem_read(arg(1), arg(2)))); ret(0); uc.reg_write(UC_ARM_REG_PC, R(UC_ARM_REG_LR))
    elif addr == WAITSET:
        reg, mask = R(UC_ARM_REG_SL), R(UC_ARM_REG_R9) & 0xff
        log.append(('waitset', reg, mask)); print('  WAIT reg=%03x bits %02x set' % (reg, mask))
        regs[reg] = regs.get(reg, 0) | mask
        uc.reg_write(UC_ARM_REG_R0, R(UC_ARM_REG_R0) | mask)
    elif addr == WAITCLR:
        reg, mask = R(UC_ARM_REG_R9), R(UC_ARM_REG_R8) & 0xff
        log.append(('waitclr', reg, mask)); print('  WAIT reg=%03x bits %02x clear' % (reg, mask))
        regs[reg] = regs.get(reg, 0) & ~mask
        uc.reg_write(UC_ARM_REG_R0, R(UC_ARM_REG_R0) & ~mask)
    elif addr in (DELAY, MSLEEP):
        log.append(('delay', arg(0))); print('  delay %d ms' % arg(0))
        uc.reg_write(UC_ARM_REG_PC, R(UC_ARM_REG_LR))
    elif addr == RD:
        v = regs.get(arg(0), 0)
        log.append(('r', arg(0), v)); print('  YMU R reg=%03x -> %02x' % (arg(0), v))
        ret(v); uc.reg_write(UC_ARM_REG_PC, R(UC_ARM_REG_LR))

uc.hook_add(UC_HOOK_CODE, hook_code, begin=STUB, end=STUB + 0x10000)


auto = []
def bad(uc_, access, addr, size, value, ud):
    page = addr & ~0xfff
    uc.mem_map(page, 0x1000); auto.append(page)
    print('  automap %#x (pc=%#x)' % (page, R(UC_ARM_REG_PC)))
    return True
def auto_w(uc_, access, addr, size, value, ud):
    if any(p <= addr < p + 0x1000 for p in auto):
        print('  AUTO W %#010x = %#010x (pc=%#x)' % (addr, value & 0xffffffff, R(UC_ARM_REG_PC)))
uc.hook_add(UC_HOOK_MEM_WRITE, auto_w)
uc.hook_add(UC_HOOK_MEM_UNMAPPED, bad)
from unicorn import UC_HOOK_MEM_WRITE
def mmio_w(uc_, access, addr, size, value, ud):
    for pa, va, n in mmio_maps:
        if va <= addr < va + 0x2000:
            log.append(('mmio', pa + addr - va, value))
            print('  MMIO W %#010x = %#010x' % (pa + addr - va, value & 0xffffffff))
            return
uc.hook_add(UC_HOOK_MEM_WRITE, mmio_w, begin=MMIO, end=MMIO + 0x100000)

RET_MAGIC = STUB + 0xfff0
def call(fn, *args, limit=20_000_000):
    sp = STACK + 0x100000 - 0x1000
    regsx = [UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3]
    extra = list(args[4:])
    sp -= 4 * len(extra)
    for i, a in enumerate(extra):
        uc.mem_write(sp + 4 * i, struct.pack('<I', a))
    for r, a in zip(regsx, args):
        uc.reg_write(r, a)
    uc.reg_write(UC_ARM_REG_SP, sp)
    uc.reg_write(UC_ARM_REG_LR, RET_MAGIC)
    uc.emu_start(fn, RET_MAGIC, count=limit)
    if R(UC_ARM_REG_PC) != RET_MAGIC:
        print('!! stopped early at pc=%#x' % R(UC_ARM_REG_PC))
    return R(UC_ARM_REG_R0)

