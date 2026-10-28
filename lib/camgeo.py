"""camgeo.py: Gerber/Excellon -> shapely (mm, Gerber coords). load(path) -> (geom, flashes)"""
import math, pickle, os, warnings
warnings.filterwarnings('ignore')
from gerbonara import GerberFile, ExcellonFile
from gerbonara.utils import MM
import gerbonara.graphic_primitives as gp
from shapely.geometry import Point, LineString, Polygon, box
from shapely.ops import unary_union
from shapely import affinity
def arcpts(x1,y1,x2,y2,cx,cy,cw,n=None):
    a1=math.atan2(y1-cy,x1-cx); a2=math.atan2(y2-cy,x2-cx); r=math.hypot(x1-cx,y1-cy)
    if cw:
        if a2>=a1: a2-=2*math.pi
    else:
        if a2<=a1: a2+=2*math.pi
    if abs(x1-x2)<1e-9 and abs(y1-y2)<1e-9: a2=a1+(-2*math.pi if cw else 2*math.pi)
    k=n or max(8,int(abs(a2-a1)/(math.pi/32)))
    return [(cx+r*math.cos(a1+(a2-a1)*i/k), cy+r*math.sin(a1+(a2-a1)*i/k)) for i in range(k+1)]
def prim2shape(p):
    if isinstance(p,gp.Circle): return Point(p.x,p.y).buffer(p.r,resolution=16)
    if isinstance(p,gp.Line):
        if p.width<=0: return None
        return LineString([(p.x1,p.y1),(p.x2,p.y2)]).buffer(p.width/2,resolution=8) if (p.x1,p.y1)!=(p.x2,p.y2) else Point(p.x1,p.y1).buffer(p.width/2,resolution=8)
    if isinstance(p,gp.Arc):
        pts=arcpts(p.x1,p.y1,p.x2,p.y2,p.cx+p.x1 if False else p.cx,p.cy,p.clockwise)
        return LineString(pts).buffer(p.width/2,resolution=8)
    if isinstance(p,gp.Rectangle):
        b=box(-p.w/2,-p.h/2,p.w/2,p.h/2); b=affinity.rotate(b,p.rotation,origin=(0,0),use_radians=True); return affinity.translate(b,p.x,p.y)
    if isinstance(p,gp.ArcPoly):
        pts=[]; out=list(p.outline); ac=list(p.arc_centers) if p.arc_centers else []
        for i in range(len(out)):
            a=out[i]; b=out[(i+1)%len(out)]
            c=ac[i] if i<len(ac) else None
            if c is None: pts.append(a)
            else:
                cw,(cx,cy)=c; pts+=arcpts(a[0],a[1],b[0],b[1],cx,cy,cw)[:-1]
        if len(pts)<3: return None
        poly=Polygon(pts)
        return poly if poly.is_valid else poly.buffer(0)
    raise TypeError(type(p))
def load(path):
    ck=path+'.pkl'
    if os.path.exists(ck) and os.path.getmtime(ck)>os.path.getmtime(path): return pickle.load(open(ck,'rb'))
    f=(ExcellonFile if path.upper().endswith('.DRL') else GerberFile).open(path)
    geom=Polygon(); batch=[]; cur_dark=True; flashes=[]
    def flush():
        nonlocal geom,batch
        if batch:
            u=unary_union(batch); geom=geom.union(u) if cur_dark else geom.difference(u); batch=[]
    for o in f.objects:
        dark=getattr(o,'polarity_dark',True)
        if dark!=cur_dark: flush(); cur_dark=dark
        shp=[s for s in (prim2shape(p) for p in o.to_primitives(MM)) if s is not None and not s.is_empty]
        if not shp: continue
        u=unary_union(shp)
        if type(o).__name__=='Flash':
            ap=o.aperture; dia=getattr(ap,'diameter',None)
            flashes.append({'x':o.x,'y':o.y,'shape':u,'dia':dia,'plated':getattr(ap,'plated',None)})
        batch.append(u)
    flush()
    res=(geom,flashes); pickle.dump(res,open(ck,'wb')); return res
