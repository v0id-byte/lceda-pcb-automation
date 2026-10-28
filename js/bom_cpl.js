// BOM and pick-and-place (CPL) files as base64 xlsx.
await pcb();
const M = eda.pcb_ManufactureData; const o = {};
async function grab(fn) { try { const f = await M[fn](); if (!f) return null; const b = new Uint8Array(await f.arrayBuffer()); let s = '';
  for (let i = 0; i < b.length; i += 0x8000) s += String.fromCharCode.apply(null, b.subarray(i, i + 0x8000));
  return { name: f.name, size: b.length, b64: btoa(s) }; } catch (e) { return 'ERR ' + e; } }
for (const fn of ['getBomFile', 'getPickAndPlaceFile']) o[fn] = await grab(fn);
return o;
