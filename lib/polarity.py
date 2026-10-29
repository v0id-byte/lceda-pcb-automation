"""Which pads carry a polarity mark. Shared by assembly_drawing.py and polarity_silk.py.

  pin1  pin 1 of ICs, transistors, connectors, switches and anything with more than two pads
  +     pin 1 of LCSC electrolytic footprints (CAP-SMD_BD...)
  K     the pin named K / CATHODE in the schematic (the PCB netlist leaves pin names empty)
Bidirectional footprints ('...-BI') get no mark."""
import json
import eda

POLAR = ('U', 'Q', 'D', 'LED', 'J', 'CN', 'SW')


class Rules:
    def __init__(self, parts, pads):
        """parts: comp_bbox.js result; pads: pcbgeo pad objects."""
        r = eda.run('netlist_sch.js', 120)
        if not r.get('success'):
            raise SystemExit(f"netlist_sch.js failed: {r.get('error')}")
        t = json.loads(r['result']['text'])
        self.pin = {(c['props'].get('Designator'), n): (v.get('name') or '').upper()
                    for c in t['components'].values() if isinstance(c, dict) and 'props' in c
                    for n, v in c.get('pinInfoMap', {}).items()}
        self.fp = {f['d']: f['fp'] for f in parts}
        self.has_k = {d for (d, n), name in self.pin.items() if name in ('K', 'CATHODE')}
        self.npads = {}
        for p in pads:
            self.npads[p['ref']] = self.npads.get(p['ref'], 0) + 1

    def mark(self, ref, n):
        """'' | 'pin1' | '+' | 'K' for pad number n of part ref."""
        fp = self.fp.get(ref, '')
        if fp.endswith('-BI'):
            return ''
        if fp.startswith('CAP-SMD_BD'):
            return '+' if n == '1' else ''
        if ref in self.has_k:
            return 'K' if self.pin.get((ref, n)) in ('K', 'CATHODE') else ''
        return 'pin1' if n in ('1', 'A1') and (self.npads.get(ref, 0) > 2 or ref.startswith(POLAR)) else ''
