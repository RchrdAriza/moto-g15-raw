#!/usr/bin/env python3
"""Build patched libmtkcam_metastore.so for Moto G15 (lamu) from the stock vendor copy.

Usage: make_patch.py <stock.so> <out.so>

Rear (S5KJNSSQ, camera 0):
  1. availableCapabilities: mov w8,#9 -> mov w8,#3   (CONSTRAINED_HIGH_SPEED -> RAW)
  2. stream candidate #44 (BLOB 1024x768 -> RAW16 4080x3072): its format/width/height stores
     become `bl` into caves that store 0x20 / 4080 / 3072 to the push_back buffer [sp,#0x90].
Front (SC820CS, camera 1):
  3. availableCapabilities [0 1 2 5 6] has no spare slot, so the last push (6) goes through a cave
     that does push_back(6) itself and leaves 3 in the buffer for the original push_back:
     caps become [0 1 2 5 6 3].
  4. stream candidate #21 (BLOB 1024x768 -> RAW16 3264x2448), same store-cave trick on [sp,#0x30].
Caves live in the zero padding after .plt (0x65de0); the exec PT_LOAD is grown to cover them.
"""
import hashlib, struct, sys

STOCK = 'd4d71c54fbf12a925313ed166c793c48d433c550006a7fc0c6d3de3836f09b13'
CAVE = 0x65de0
EXEC_FILESZ = 0x51de0
PUSH_BACK_U8_PLT = 0x654e0

def u32(x): return struct.pack('<I', x)
def bl(src, dst): return u32(0x94000000 | (((dst - src) >> 2) & 0x3ffffff))

def put(b, off, old, new):
    assert b[off:off+len(old)] == old, f'{off:#x}: {b[off:off+len(old)].hex()} != {old.hex()}'
    b[off:off+len(new)] = new

# mov x16,#imm; str x16,[sp,#off]; ret  (x16 is PLT scratch, clobbered by the next bl anyway)
def store_cave(imm, sp_off):
    return u32(0xd2800000 | (imm << 5) | 16) + u32(0xf9000000 | ((sp_off // 8) << 10) | (31 << 5) | 16) + u32(0xd65f03c0)

src, dst = sys.argv[1], sys.argv[2]
b = bytearray(open(src, 'rb').read())
assert hashlib.sha256(b).hexdigest() == STOCK, 'not the expected stock library'

cave = CAVE
def add_cave(code):
    global cave
    at = cave
    put(b, at, bytes(len(code)), code)
    cave += len(code)
    return at

# 1. rear caps
put(b, 0x2f02c, u32(0x52800128), u32(0x52800068))            # mov w8,#9 -> mov w8,#3

# 2 + 4. RAW16 stream candidates
for site, old, imm, sp_off in [(0x31f88, 0xf9004bf5, 0x20, 0x90),    # rear  str x21 (fmt 33) -> RAW16
                               (0x31f9c, 0xf9004bf7, 4080, 0x90),    # rear  str x23 (1024)   -> 4080
                               (0x31fb0, 0xf9004bf8, 3072, 0x90),    # rear  str x24 (768)    -> 3072
                               (0x37b34, 0xf9001bf4, 0x20, 0x30),    # front str x20 (fmt 33) -> RAW16
                               (0x37b48, 0xf9001bf4, 3264, 0x30),    # front str x20 (1024)   -> 3264
                               (0x37b5c, 0xf9001bf6, 2448, 0x30)]:   # front str x22 (768)    -> 2448
    put(b, site, u32(old), bl(site, add_cave(store_cave(imm, sp_off))))

# 3. front caps: replaces `strb w27,[sp,#0x30]` at 0x36880 (x0 = entry, x1 = sp+0x30 on entry)
at = cave
front_caps = (u32(0xa9bf07fe)            # stp  x30, x1, [sp, #-16]!
              + u32(0x3900003b)          # strb w27, [x1]          (6 = BURST_CAPTURE)
              + bl(at + 8, PUSH_BACK_U8_PLT)
              + u32(0xa8c107fe)          # ldp  x30, x1, [sp], #16
              + u32(0xd10143a0)          # sub  x0, x29, #0x50
              + u32(0x52800070)          # mov  w16, #3            (RAW)
              + u32(0x39000030)          # strb w16, [x1]
              + u32(0xd65f03c0))         # ret  -> caller's bl push_back pushes 3
put(b, 0x36880, u32(0x3900c3fb), bl(0x36880, add_cave(front_caps)))

grow = (cave - CAVE + 0xf) & ~0xf
e_phoff, = struct.unpack_from('<Q', b, 0x20)
e_phentsize, e_phnum = struct.unpack_from('<HH', b, 0x36)
for i in range(e_phnum):
    ph = e_phoff + i * e_phentsize
    p_type, p_flags = struct.unpack_from('<II', b, ph)
    p_offset, p_vaddr, p_paddr, p_filesz, p_memsz = struct.unpack_from('<QQQQQ', b, ph + 8)
    if p_type == 1 and p_flags & 1:   # PT_LOAD, PF_X
        assert (p_offset, p_filesz, p_memsz) == (0x14000, EXEC_FILESZ, EXEC_FILESZ)
        struct.pack_into('<QQ', b, ph + 32, EXEC_FILESZ + grow, EXEC_FILESZ + grow)
        break
else:
    sys.exit('exec PT_LOAD not found')

open(dst, 'wb').write(b)
print(f'caves {CAVE:#x}..{cave:#x}, PT_LOAD +{grow:#x}')
print('patched sha256', hashlib.sha256(b).hexdigest())
