// Gerber + drill zip as base64 (decode with tools/cam_export.py). Rebuild pours first.
await pcb();
const f = await eda.pcb_ManufactureData.getGerberFile(ARGS.name || 'gerber');
if (!f) return null;
const b = new Uint8Array(await f.arrayBuffer()); let s = '';
for (let i = 0; i < b.length; i += 0x8000) s += String.fromCharCode.apply(null, b.subarray(i, i + 0x8000));
return { name: f.name, size: b.length, b64: btoa(s) };
