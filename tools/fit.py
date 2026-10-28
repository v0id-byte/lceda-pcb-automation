"""fit.py spec.json : search legal placements near target points (board mm). spec: {"rip":[ids], "fixed":{des:[x,y,rot,side]}, "parts":[{"d":des,"t":[x,y],"side":2,"rots":[0,90,180,270],"r":3.0,"step":0.1,"clr":0.2,"court":0.2}]}
pads are taken from current geom (any position) and re-transformed; parts are placed sequentially (each placed part becomes an obstacle)."""
import sys,json,math
import _boot  # noqa: F401
import cfg,pcbgeo,router
from shapely.geometry import box,Point
from shapely import affinity
from shapely.ops import unary_union
from shapely.strtree import STRtree
spec=json.load(open(sys.argv[1])); MM=39.37
g,objs=pcbgeo.load()
comps={c['d']:c for c in g['comps']}
rip=set(spec.get('rip',[]))
movers={p['d'] for p in spec['parts']}|set(spec.get('fixed',{}).keys())
def local_pads(d):
    c=comps[d]; out=[]
    for o in [o for o in objs if o['kind']=='pad' and o.get('ref')==d]:
        s=affinity.translate(o['shape'],-c['x'],-c['y']); s=affinity.rotate(s,-c['r'],origin=(0,0))
        out.append((o['id'].split('.')[1],o['net'],o['layers'],s,len(o['layers'])>1))
    return out
def place_shapes(d,x,y,r,side):
    c=comps[d]; res=[]
    for n,net,layers,s,th in local_pads(d):
        s2=s
        if side!=c['l'] and not th: s2=affinity.scale(s2,-1,1,origin=(0,0))
        s2=affinity.translate(affinity.rotate(s2,r,origin=(0,0)),x,y)
        L=layers if th else [1 if side==1 else 2]
        res.append((n,net,L,s2))
    return res
obst=[o for o in objs if o['id'] not in rip and o['kind']!='pour' and o.get('ref') not in movers and o['net']!='__SLOT']
# courtyards of non-moving comps per side (pad bbox + margin)
court={1:[],2:[]}
for d,c in comps.items():
    if d in movers: continue
    ps=[o for o in objs if o['kind']=='pad' and o.get('ref')==d]
    if not ps: continue
    u=unary_union([o['shape'] for o in ps]); b=u.bounds
    sides=[1,2] if any(len(o['layers'])>1 for o in ps) else [1 if ps[0]['layers'][0]==1 else 2]
    for s in sides: court[s].append(box(*b))
def ok(shapes,side,clr,cm,keep_extra):
    cb=unary_union([s for _,_,_,s in shapes]).bounds; cbox=box(*cb).buffer(cm*MM,join_style=2)
    if not pcbgeo.OUTLINE.buffer(-0.3*MM).contains(cbox): return False,'edge'
    if cbox.intersects(pcbgeo.KEEPOUT): return False,'keepout'
    for cb2 in court[side]+keep_extra.get(side,[]):
        if cbox.intersects(cb2): return False,'court'
    for n,net,L,s in shapes:
        for o in obst:
            if o['net']==net and o['kind']!='pad': continue
            if not set(L)&set(o['layers']): continue
            if o['shape'].distance(s)<max(clr*MM, router.pclr(cfg.CLR+0.2,o['net'])): return False,('cu',o['kind'],o['net'])
    return True,''
placed={}; extra={1:[],2:[]}
for d,(x,y,r,s) in spec.get('fixed',{}).items():
    sh=place_shapes(d,cfg.X(x),cfg.Y(y),r,s); placed[d]=[x,y,r,s]
    for n,net,L,ss in sh: obst.append(dict(kind='pad',id=f'{d}.{n}',net=net,layers=L,shape=ss,ref=d))
    extra[s].append(box(*unary_union([ss for *_,ss in sh]).bounds))
for p in spec['parts']:
    d=p['d']; tx,ty=p['t']; side=p.get('side',2); best=None; rr=p.get('r',3.0); st=p.get('step',0.1)
    cands=[]
    k=int(rr/st)
    for i in range(-k,k+1):
        for j in range(-k,k+1):
            x=tx+i*st; y=ty+j*st
            if math.hypot(x-tx,y-ty)>rr: continue
            cands.append((math.hypot(x-tx,y-ty),x,y))
    cands.sort()
    for dist,x,y in cands:
        for r in p.get('rots',[0,90,180,270]):
            sh=place_shapes(d,cfg.X(x),cfg.Y(y),r,side)
            good,why=ok(sh,side,p.get('clr',0.2),p.get('court',0.15),extra)
            if good: best=(round(x,3),round(y,3),r,side,sh); break
        if best: break
    if not best: print('NOFIT',d); continue
    x,y,r,s,sh=best; placed[d]=[x,y,r,s]
    for n,net,L,ss in sh: obst.append(dict(kind='pad',id=f'{d}.{n}',net=net,layers=L,shape=ss,ref=d))
    extra[s].append(box(*unary_union([ss for *_,ss in sh]).bounds))
    print(d,placed[d],[(n,net,*cfg.mm(ss.centroid.x,ss.centroid.y,2)) for n,net,L,ss in sh])
json.dump(placed,open(spec.get('out',cfg.path('placed.json')),'w'))
