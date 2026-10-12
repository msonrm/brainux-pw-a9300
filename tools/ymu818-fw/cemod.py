"""WinCE XIP ROM 内の 1 モジュールをメモリ配置に復元し、エクスポート・インポートを出す。
usage: python3 -I cemod.py IMAGE MODNAME [outfile]
outfile を渡すと vbase から並べたメモリイメージを書き出す。
"""
import struct, sys

img = open(sys.argv[1], 'rb').read()
ROMHDR = 0x1acc380
pf = struct.unpack_from('<I', img, ROMHDR + 8)[0]
nummods = struct.unpack_from('<I', img, ROMHDR + 16)[0]
v2o = lambda va: va - pf

def cstr(buf, o, vbase=None):
    # モジュール内 RVA、絶対 VA、ROM 内アドレスのどれでも読めるようにする
    if vbase is not None and o >= vbase and o - vbase < len(buf):
        o -= vbase
    if buf is not img and (o >= len(buf) or b'\0' not in buf[o:o + 256]):
        buf, o = img, v2o(o)
    return buf[o:buf.index(b'\0', o)].decode('latin1')

mods = {}
for i in range(nummods):
    attr, ftl, fth, size, name, e32, o32, load = struct.unpack_from('<8I', img, ROMHDR + 84 + 32 * i)
    mods[cstr(img, v2o(name)).lower()] = (v2o(e32), v2o(o32))

def load(modname):
    e32, o32 = mods[modname.lower()]
    objcnt = struct.unpack_from('<H', img, e32)[0]
    vbase = struct.unpack_from('<I', img, e32 + 8)[0]
    vsize = struct.unpack_from('<I', img, e32 + 20)[0]
    units = [struct.unpack_from('<II', img, e32 + 36 + 8 * k) for k in range(9)]
    mem = bytearray(vsize + 0x1000)
    for j in range(objcnt):
        vs, rva, ps, dp, real, flags = struct.unpack_from('<6I', img, o32 + 24 * j)
        if dp:
            n = min(vs, ps)
            mem[rva:rva + n] = img[v2o(dp):v2o(dp) + n]
    return vbase, units, mem

def exports(modname):
    vbase, units, mem = load(modname)
    rva, size = units[0]
    if not rva:
        return {}
    (_, _, _, nm, ordbase, nfun, nnames, afun, anames, aords) = struct.unpack_from('<10I', mem, rva)
    out = {}
    for k in range(nnames):
        n = cstr(mem, struct.unpack_from('<I', mem, anames + 4 * k)[0], vbase)
        o = struct.unpack_from('<H', mem, aords + 2 * k)[0]
        out[o + ordbase] = n
    return out

name = sys.argv[2]
vbase, units, mem = load(name)
print('vbase=%#x imp=%s' % (vbase, units[1]))
rva = units[1][0]
while True:
    oft, ts, fwd, nm, ft = struct.unpack_from('<5I', mem, rva)
    if not nm:
        break
    dll = cstr(mem, nm)
    try:
        ex = exports(dll)
    except KeyError:
        ex = {}
    k = 0
    thunks = oft or ft
    while True:
        t = struct.unpack_from('<I', mem, thunks + 4 * k)[0]
        if not t:
            break
        if t & 0x80000000:
            fn = ex.get(t & 0xffff, 'ord%d' % (t & 0xffff))
        else:
            fn = cstr(mem, t + 2)
        print('IAT %#010x  %s!%s' % (vbase + ft + 4 * k, dll, fn))
        k += 1
    rva += 20
if len(sys.argv) > 3:
    open(sys.argv[3], 'wb').write(bytes(mem))
