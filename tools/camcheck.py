"""camcheck.py GERBER_DIR : independent manufacturability check of the exported Gerbers/drills.

Reports (board mm, y down): board size, copper too close to the edge, drill sizes, hole-to-hole and
hole-to-edge spacing, minimum annular rings, solder-mask dams < 0.1 mm, mask openings exposing other
copper, silkscreen on pads / off board, paste outside copper. Writes <dir>_report.json.
Compare with the fab's capability table; LCEDA DRC does not cover all of these."""
import sys, json, math, os
import _boot  # noqa: F401
import camgeo, cfg
from shapely.geometry import Point, Polygon, MultiPolygon
from shapely.ops import unary_union
from shapely.strtree import STRtree
C=os.path.join(sys.argv[1], ''); R={}
bx=lambda x,y:(round(x-cfg.OX/cfg.MIL,2), round(cfg.OY/cfg.MIL-y,2))   # gerber mm -> board mm
def polys(g): return [p for p in getattr(g,'geoms',[g]) if p.geom_type=='Polygon' and not p.is_empty]
ol,_=camgeo.load(C+'Gerber_BoardOutlineLayer.GKO')
inner=max((Polygon(r) for p in polys(ol) for r in p.interiors), key=lambda q:q.area)
B=inner.buffer(0.127,join_style=2); R['board_mm']=[round(B.bounds[2]-B.bounds[0],3), round(B.bounds[3]-B.bounds[1],3)]
CU={'L1':'Gerber_TopLayer.GTL', **{f'In{i}':f'Gerber_InnerLayer{i}.G{i}' for i in range(1,9) if os.path.exists(C+f'Gerber_InnerLayer{i}.G{i}')}, 'L2':'Gerber_BottomLayer.GBL'}
cu={k:camgeo.load(C+v) for k,v in CU.items()}
# 1 copper to edge
edge=B.exterior; R['cu_edge']={}
for k,(g,_) in cu.items():
    near=[p for p in polys(g) if p.distance(edge)<0.2 or not B.buffer(1e-6).contains(p)]
    R['cu_edge'][k]=sorted([(round(p.distance(edge) if B.contains(p.representative_point()) else -1,3), bx(*p.representative_point().coords[0])) for p in near])[:8]
# 2 drills
holes=[]
_,vf=camgeo.load(C+'Drill_PTH_Through_Via.DRL'); vset={(round(h['x'],3),round(h['y'],3)) for h in vf}
_,pf=camgeo.load(C+'Drill_PTH_Through.DRL'); R['pth_file_includes_vias']=sum(1 for h in pf if (round(h['x'],3),round(h['y'],3)) in vset)
for h in pf: holes.append({'k':'via' if (round(h['x'],3),round(h['y'],3)) in vset else 'pth','x':h['x'],'y':h['y'],'d':round(h['dia'],4)})
for h in (camgeo.load(C+'Drill_NPTH_Through.DRL')[1] if os.path.exists(C+'Drill_NPTH_Through.DRL') else []): holes.append({'k':'npth','x':h['x'],'y':h['y'],'d':round(h['dia'],4)})
from collections import Counter
R['drill_sizes']={k:sorted(Counter(h['d'] for h in holes if h['k']==k).items()) for k in ('pth','via','npth')}
pts=[Point(h['x'],h['y']).buffer(h['d']/2,8) for h in holes]; T=STRtree(pts); bad=[]
for i,h in enumerate(holes):
    for j in T.query(pts[i].buffer(0.5)):
        j=int(j)
        if j<=i: continue
        g2=holes[j]; d=math.hypot(h['x']-g2['x'],h['y']-g2['y'])-(h['d']+g2['d'])/2
        lim=0.2 if (h['k']=='via' and g2['k']=='via') else 0.45 if (h['k']!='via' and g2['k']!='via') else 0.2
        if d<lim: bad.append((round(d,3),h['k'],g2['k'],bx(h['x'],h['y'])))
R['hole_spacing_viol']=sorted(bad)[:15]; R['hole_spacing_n']=len(bad)
R['hole_to_edge']=sorted([(round(Point(h['x'],h['y']).distance(edge)-h['d']/2,3),h['k'],bx(h['x'],h['y'])) for h in holes])[:6]
# 3 annular ring (outer layers, pads/flashes at plated holes)
rings={'pth':[],'via':[]}
for k in ('L1','L2'):
    g,fl=cu[k]; FT=STRtree([f['shape'] for f in fl])
    for h in holes:
        if h['k']=='npth': continue
        c=Point(h['x'],h['y']); best=None
        for j in FT.query(c):
            s=fl[int(j)]['shape']
            if s.contains(c): r=s.exterior.distance(c) if s.geom_type=='Polygon' else s.boundary.distance(c); best=max(best or 0, r-h['d']/2)
        rings[h['k']].append((round(best,3) if best is not None else None,k,bx(h['x'],h['y']),h['d']))
R['ring_min']={k:sorted([r for r in v if r[0] is not None])[:5] for k,v in rings.items()}
R['ring_missing']={k:[r for r in v if r[0] is None][:8] for k,v in rings.items()}
R['ring_missing_n']={k:len([r for r in v if r[0] is None]) for k,v in rings.items()}
# 4 mask dams + mask-to-other-copper
for side,ms,cl,sl,pa in (('top','Gerber_TopSolderMaskLayer.GTS','L1','Gerber_TopSilkscreenLayer.GTO','Gerber_TopPasteMaskLayer.GTP'),('bot','Gerber_BottomSolderMaskLayer.GBS','L2','Gerber_BottomSilkscreenLayer.GBO','Gerber_BottomPasteMaskLayer.GBP')):
    mg,_=camgeo.load(C+ms); op=polys(mg); OT=STRtree(op); dams=[]
    for i,p in enumerate(op):
        for j in OT.query(p.buffer(0.1)):
            j=int(j)
            if j<=i: continue
            d=p.distance(op[j])
            if d<0.1: dams.append((round(d,3),bx(*p.centroid.coords[0])))
    R[side+'_mask_dam_lt0.1']={'n':len(dams),'ex':sorted(dams)[:12]}
    cg,_=cu[cl]; isl=polys(cg); IT=STRtree(isl); exp=[]
    for p in op:
        own=[int(j) for j in IT.query(p) if isl[int(j)].intersects(p)]
        for j in IT.query(p.buffer(0.09)):
            j=int(j)
            if j in own: continue
            d=isl[j].distance(p)
            if d<0.09: exp.append((round(d,3),bx(*p.centroid.coords[0])))
        if len(own)>1: exp.append(('multi-copper-in-opening',bx(*p.centroid.coords[0])))
    R[side+'_mask_to_other_cu']={'n':len(exp),'ex':exp[:12]}
    sg,_=camgeo.load(C+sl); onpad=sg.intersection(mg); R[side+'_silk_on_mask_open']={'area_mm2':round(onpad.area,3),'n':len(polys(onpad)),'ex':[bx(*q.centroid.coords[0]) for q in sorted(polys(onpad),key=lambda q:-q.area)[:12]]}
    off=sg.difference(B); R[side+'_silk_off_board']={'area':round(off.area,3),'ex':[bx(*q.centroid.coords[0]) for q in polys(off)][:8]}
    pg,_=camgeo.load(C+pa); pout=pg.difference(cg.buffer(0.001)); R[side+'_paste_off_copper']={'area':round(pout.area,4),'ex':[bx(*q.centroid.coords[0]) for q in polys(pout) if q.area>1e-4][:8]}
    R[side+'_paste_openings']=len(polys(pg)); R[side+'_mask_openings']=len(op)
json.dump(R,open(C.rstrip('/')+'_report.json','w'),ensure_ascii=False,indent=1,default=str); print(json.dumps(R,ensure_ascii=False,indent=1,default=str))
