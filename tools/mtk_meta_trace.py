#!/usr/bin/env python3
"""Trace MTK IMetadata::IEntry construction in llvm-objdump output.

Usage: mtk_meta_trace.py <disasm.txt> (<tag-hex> [<tag-hex> ...] | all)
Prints, per function, every IEntry(tag) built and the values pushed into it,
with the instruction address that materializes each value (for patching).
"""
import re, sys

dis_path = sys.argv[1]
ALL = sys.argv[2:] == ['all']
tags = set() if ALL else {int(t, 16) for t in sys.argv[2:]}
FUNC = re.compile(r'^([0-9a-f]+) <(.+)>:$')
INS = re.compile(r'^\s*([0-9a-f]+):\s+(\S+)\s*(.*?)\s*(?://.*)?$')
IMM = lambda s: int(s.lstrip('#'), 0)

func, regs, entry, out = None, {}, None, []

def reg(r):
    return r.replace('x', 'w') if r.startswith('x') else r

for line in open(dis_path):
    line = line.rstrip('\n')
    m = FUNC.match(line)
    if m:
        func, regs, entry = m.group(2), {}, None
        continue
    m = INS.match(line)
    if not m or func is None:
        continue
    addr, op, args = int(m.group(1), 16), m.group(2), m.group(3)
    a = [x.strip() for x in re.split(r',(?![^\[]*\])', args)] if args else []
    try:
        if op == 'mov' and len(a) == 2:
            src = a[1]
            if src.startswith('#'):
                regs[reg(a[0])] = (IMM(src), addr)
            elif reg(src) == 'wzr':
                regs[reg(a[0])] = (0, addr)
            elif reg(src) in regs:
                regs[reg(a[0])] = regs[reg(src)]
            else:
                regs.pop(reg(a[0]), None)
        elif op == 'movk' and len(a) == 3 and reg(a[0]) in regs:
            sh = int(a[2].split('#')[1])
            v = regs[reg(a[0])][0] & ~(0xffff << sh) | (IMM(a[1]) << sh)
            regs[reg(a[0])] = (v, addr)
        elif op in ('add', 'sub') and len(a) == 3 and a[2].startswith('#') and reg(a[1]) in regs:
            v = regs[reg(a[1])][0] + (IMM(a[2]) if op == 'add' else -IMM(a[2]))
            regs[reg(a[0])] = (v & 0xffffffff, addr)
        elif op == 'strb' and entry is not None:
            r = reg(a[0])
            entry['pending'] = (0, addr) if r == 'wzr' else regs.get(r, ('?', addr))
        elif op in ('str', 'stur') and entry is not None and a[0][0] in 'wx':
            r = reg(a[0])
            entry['pending'] = (0, addr) if r == 'wzr' else regs.get(r, ('?', addr))
        elif op == 'bl':
            if 'IEntry::IEntry(unsigned int)' in args or '_ZN5NSCam9IMetadata6IEntryC1Ej' in args:
                t = regs.get('w1', (None,))[0]
                entry = {'tag': t, 'addr': addr, 'vals': [], 'pending': None} if (ALL and t is not None) or t in tags else None
            elif entry is not None and ('push_back' in args or 'IEntry9push_back' in args):
                entry['vals'].append(entry['pending'] or ('?', addr))
                entry['pending'] = None
            elif entry is not None and ('IMetadata::update' in args or 'IMetadata6update' in args):
                out.append((func, entry))
                entry = None
            for r in [k for k in regs if k in ('w0','w1','w2','w3','w4','w5','w6','w7','w8','w9','w10','w11','w12','w13','w14','w15','w16','w17')]:
                regs.pop(r)
        elif op in ('ldr', 'ldur', 'ldrb', 'ldp', 'adrp', 'adr', 'orr', 'and', 'eor', 'lsl', 'lsr', 'csel', 'cset', 'madd', 'mul') and a:
            regs.pop(reg(a[0]), None)
    except (ValueError, IndexError):
        pass

for func, e in out:
    vals = ' '.join(f"{v}@{a:#x}" if isinstance(v, int) else f"?@{a:#x}" for v, a in e['vals'])
    print(f"{func}\n    IEntry({e['tag']:#x}) @ {e['addr']:#x}: [{vals}]")
