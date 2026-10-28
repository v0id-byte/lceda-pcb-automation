"""Run JS in the open LCEDA Pro session from Python (thin wrapper around bin/eda.sh)."""
import json
import os
import subprocess
import tempfile
import cfg

EDA_SH = os.path.join(cfg.ROOT, 'bin', 'eda.sh')
JS = os.path.join(cfg.ROOT, 'js')


def run(js_file, timeout=120, args=None):
    """Run a JS file; returns the parsed {"success","result","error"} dict."""
    if not os.path.isabs(js_file) and not os.path.exists(js_file):
        js_file = os.path.join(JS, js_file)
    cmd = [EDA_SH, js_file, str(timeout)] + ([json.dumps(args)] if args is not None else [])
    out = subprocess.run(cmd, capture_output=True, text=True).stdout
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {'success': False, 'result': None, 'error': out[-2000:]}


def run_code(code, timeout=120, args=None):
    """Run a JS source string (async function body; `return` gives the result)."""
    d = cfg.path('.tmp')
    os.makedirs(d, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', suffix='.js', dir=d, delete=False) as f:
        f.write(code)
    try:
        return run(f.name, timeout, args)
    finally:
        os.unlink(f.name)


def items_js(net, items, w, via=None):
    """JS lines that create planned items (('T',L,x1,y1,x2,y2[,w]) / ('V',x,y), mil) on the PCB."""
    via = via or cfg.VIA
    n = json.dumps(net)
    lines = ['await pcb();', 'const r=[];']
    for it in items:
        if it[0] == 'T':
            ww = it[6] if len(it) > 6 else w
            lines.append(f'r.push((await eda.pcb_PrimitiveLine.create({n},{it[1]},{it[2]:.4f},{it[3]:.4f},{it[4]:.4f},{it[5]:.4f},{ww})).primitiveId);')
        else:
            lines.append(f'r.push((await eda.pcb_PrimitiveVia.create({n},{it[1]:.4f},{it[2]:.4f},{via[0]},{via[1]})).primitiveId);')
    lines.append('return r;')
    return lines


def commit_items(net, items, w, via=None, log=True):
    res = run_code('\n'.join(items_js(net, items, w, via)))
    if log:
        with open(cfg.path('commit-log.jsonl'), 'a') as f:
            f.write(json.dumps({'net': net, 'w': w, 'items': items, 'res': res}) + '\n')
    return res


def delete_js(ids):
    return [f'for(const i of {json.dumps(list(ids))}){{ if(await eda.pcb_PrimitiveLine.get(i)) await eda.pcb_PrimitiveLine.delete([i]);'
            ' else if(await eda.pcb_PrimitiveVia.get(i)) await eda.pcb_PrimitiveVia.delete([i]); }']


def refresh(rebuild=False):
    """Optionally rebuild all pours, then re-export geom.json + poured.json into the work dir."""
    if rebuild:
        r = run('rebuild_pours.js', 600)
        if not r.get('success'):
            raise SystemExit(f'rebuild failed: {r}')
    for js, out in (('export_geom.js', 'geom.json'), ('export_poured.js', 'poured.json')):
        r = run(js, 600)
        if not r.get('success'):
            raise SystemExit(f'{js} failed: {r.get("error")}')
        json.dump(r, open(cfg.path(out), 'w'))
