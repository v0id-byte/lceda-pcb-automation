"""cam_export.py OUT_DIR [--name PREFIX] [--no-silk] : rebuild pours, then write Gerber zip (+ unpacked dir), BOM and CPL.

LCEDA's zip stores Chinese member names in GBK without the UTF-8 flag; they are re-decoded here.
--no-silk leaves the silkscreen layers (GTO/GBO) out of the zip, for a board ordered without
silkscreen; pair it with assembly_drawing.py, and with polarity_silk.py if the fab should still see polarity marks. Afterwards run camcheck.py OUT_DIR/gerber."""
import argparse, base64, io, json, os, zipfile
import _boot  # noqa: F401
import eda

ap = argparse.ArgumentParser(); ap.add_argument('out'); ap.add_argument('--name', default='board'); ap.add_argument('--no-silk', action='store_true')
a = ap.parse_args(); os.makedirs(os.path.join(a.out, 'gerber'), exist_ok=True)
print('rebuild', eda.run('rebuild_pours.js', 600).get('success'))
g = eda.run('gerber.js', 600, {'name': a.name})['result']
z = base64.b64decode(g['b64'])
SILK = ('.GTO', '.GBO')
if a.no_silk:   # rebuild the zip without the silkscreen members, raw names and data unchanged
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(z)) as Z, zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as O:
        for i in Z.infolist():
            if i.filename.upper().endswith(SILK):
                print('left out', i.filename); continue
            O.writestr(i, Z.read(i))
    z = buf.getvalue()
open(os.path.join(a.out, f'{a.name}_gerber.zip'), 'wb').write(z)
with zipfile.ZipFile(io.BytesIO(z)) as Z:
    for i in Z.infolist():
        nm = i.filename
        if not i.flag_bits & 0x800:
            try:
                nm = nm.encode('cp437').decode('gbk')
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
        if not i.is_dir():
            open(os.path.join(a.out, 'gerber', os.path.basename(nm)), 'wb').write(Z.read(i))
m = eda.run('bom_cpl.js', 300)['result']
for k, tag in (('getBomFile', 'BOM'), ('getPickAndPlaceFile', 'CPL')):
    if isinstance(m.get(k), dict):
        open(os.path.join(a.out, f'{a.name}_{tag}.xlsx'), 'wb').write(base64.b64decode(m[k]['b64']))
print(sorted(os.listdir(a.out)), sorted(os.listdir(os.path.join(a.out, 'gerber'))))
