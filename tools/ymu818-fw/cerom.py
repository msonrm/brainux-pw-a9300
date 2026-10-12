"""WinCE XIP ROM の ROMHDR と TOC を読んでモジュール一覧を出す。
usage: python3 -I cerom.py IMAGE [ECEC_OFFSET]
イメージ先頭（または ECEC の 0x40 手前）を physfirst とみなす。
"""
import struct, sys

img = open(sys.argv[1], 'rb').read()
ecec = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x40
assert img[ecec:ecec+4] == b'ECEC', 'no ECEC'
ptoc = struct.unpack_from('<I', img, ecec + 4)[0]
base = ecec - 0x40

# ROMHDR を仮に physfirst=? として読み、physfirst を求める
def hdr_at(off):
    f = struct.unpack_from('<17I2H3I', img, off)
    keys = ('dllfirst dlllast physfirst physlast nummods ramstart ramfree ramend '
            'copyentries copyoffset proflen profoff numfiles kflags fsram drivglob '
            'drivgloblen cputype miscflags pext trackstart tracklen').split()
    return dict(zip(keys, f))

# ptoc は仮想アドレス。physfirst は ROMHDR 自身に書いてあるので、候補を総当たりせず
# 「ptoc - physfirst + base」で ROMHDR を指すはず、という自己整合で解く
for guess_shift in range(0, len(img), 0x1000):
    pass
# 素直に: ROMHDR.physfirst を使う。まず ptoc の下位ビットから候補オフセットを探す
cands = []
for off in range(0, len(img) - 84, 4):
    if struct.unpack_from('<I', img, off + 8)[0] + (off - base) == ptoc + 0 and False:
        cands.append(off)
# physfirst = ptoc - (romhdr_off - base) となる off を探す
for off in range(base, len(img) - 84, 4):
    physfirst = struct.unpack_from('<I', img, off + 8)[0]
    if physfirst and physfirst + (off - base) == ptoc:
        h = hdr_at(off)
        if 0 < h['nummods'] < 2000 and h['physlast'] > h['physfirst']:
            cands.append(off)
assert cands, 'ROMHDR not found'
roff = cands[0]
h = hdr_at(roff)
pf = h['physfirst']
def v2o(va):
    return va - pf + base
print('ROMHDR@0x%x' % roff, {k: hex(v) for k, v in h.items()})

def cstr(va):
    o = v2o(va)
    e = img.index(b'\0', o)
    return img[o:e].decode('latin1')

toc = roff + 84
mods = []
for i in range(h['nummods']):
    attr, ftl, fth, size, name, e32, o32, load = struct.unpack_from('<8I', img, toc + 32 * i)
    mods.append((cstr(name), size, e32, o32, load))
files_off = toc + 32 * h['nummods']
files = []
for i in range(h['numfiles']):
    attr, ftl, fth, rsize, csize, name, load = struct.unpack_from('<7I', img, files_off + 28 * i)
    files.append((cstr(name), rsize, csize, load))

if len(sys.argv) > 3 and sys.argv[3] == 'o32':
    # 各モジュールの o32 セクション範囲（イメージ内オフセット）
    for name, size, e32, o32, load in mods:
        objcnt = struct.unpack_from('<H', img, v2o(e32))[0]
        for j in range(objcnt):
            vsize, rva, psize, dataptr, realaddr, flags = struct.unpack_from('<6I', img, v2o(o32) + 24 * j)
            if dataptr:
                print('%-24s sec%d rva=%06x vsize=%06x psize=%06x file=0x%08x flags=%08x' %
                      (name, j, rva, vsize, psize, v2o(dataptr), flags))
else:
    for m in mods:
        print('MOD  %-28s size=%8d e32=0x%x' % (m[0], m[1], v2o(m[2])))
    for f in files:
        print('FILE %-28s real=%8d comp=%8d at=0x%x' % (f[0], f[1], f[2], v2o(f[3])))
