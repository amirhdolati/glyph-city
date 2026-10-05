"""Small furnished 3D rooms viewed through street-level glass."""
from functools import lru_cache
import math


def intersect(origin, direction, bounds):
    near, far, face = -math.inf, math.inf, 0
    for axis in range(3):
        lo, hi = bounds[axis], bounds[axis+3]
        if abs(direction[axis]) < 1e-9:
            if not lo <= origin[axis] <= hi:
                return None
            continue
        a=(lo-origin[axis])/direction[axis]
        b=(hi-origin[axis])/direction[axis]
        if a>b: a,b=b,a
        if a>near: near,face=a,axis
        far=min(far,b)
        if near>far: return None
    return (near,face) if near>1e-5 else None


@lru_cache(maxsize=512)
def furniture(sign, width, depth):
    boxes=[]
    def box(x,y,z,w,d,h,color):
        boxes.append(((x,y,z,x+w,y+d,z+h),color))
    wood=(151,91,48); seat=(77,109,102)
    adult=sign in ('BAR','LOUNGE','18+')
    if adult:
        # Mature lounge dressing: velvet booths, a back bar and a small
        # abstract stage silhouette. The room reads as nightlife without
        # depicting explicit sexual activity.
        box(width*.08,depth-.8,0,width*.84,.55,1.0,(91,43,58))
        box(width*.13,depth-.97,1.0,width*.74,.12,.08,(247,112,153))
        for x in (width*.22,width*.52,width*.8):
            box(x-.18,depth*.42,0,.36,.55,.62,(97,43,67))
            box(x-.28,depth*.34,.58,.56,.16,.1,(226,104,145))
        box(width*.38,.55,0,width*.24,.12,.12,(231,104,139))
        box(width*.48,.55,.12,.05,.05,1.2,(204,74,118))
        box(width*.34,.55,1.3,width*.32,.06,.06,(255,178,194))
        for x in (width*.16,width*.35,width*.65,width*.84):
            box(x-.03,depth*.38,1.78,.06,.06,.5,(255,181,130))
        return tuple(boxes)
    if sign in ('BOOKS','VINYL','FLORA'):
        for x in (width*.18,width*.55):
            box(x,depth-.45,0,width*.22,.3,1.85,(80,55,37))
            for z in (.35,.8,1.25):
                for j in range(4):
                    box(x+j*width*.05,depth-.52,z,width*.035,.12,.3,
                        ((173,73,57),(177,159,80),(85,142,119),(97,114,167))[j])
    else:
        box(width*.12,depth-.85,0,width*.76,.55,.95,wood)
        box(width*.1,depth-.9,.95,width*.8,.65,.1,(222,180,111))
        for x in (width*.26,width*.7):
            box(x-.4,depth*.4,.72,.8,.65,.1,(218,170,105))
            box(x-.06,depth*.4+.25,0,.12,.12,.72,wood)
            box(x-.32,depth*.4-.45,.38,.55,.4,.1,seat)
            box(x-.32,depth*.4-.48,.4,.55,.07,.52,seat)
            box(x-.3,depth*.4-.42,0,.07,.07,.38,wood)
            box(x+.15,depth*.4-.42,0,.07,.07,.38,wood)
        if sign in ('BAR','LOUNGE','18+','JAZZ'):
            for j in range(6):
                box(width*(.18+j*.1),depth-.55,1.08,.12,.15,.3,
                    (96,166,133) if j%2 else (192,115,75))
    for x in (width*.3,width*.7):
        box(x-.025,depth*.5,2.0,.05,.05,.65,(67,52,37))
        box(x-.22,depth*.5-.16,1.94,.44,.34,.14,(255,218,141))
    return tuple(boxes)


def room_pixel(sign, width, depth, u, z, direction):
    """Trace beyond the pane; walls and furniture occlude one another."""
    origin=(u,0,z)
    # Exit planes of the room (the front opening is not a wall).
    hits=[]
    for axis,plane in ((0,0),(0,width),(1,depth),(2,0),(2,2.7)):
        d=direction[axis]
        if abs(d)<1e-9: continue
        t=(plane-origin[axis])/d
        if t<=1e-5: continue
        point=tuple(origin[i]+direction[i]*t for i in range(3))
        if -1e-6<=point[0]<=width+1e-6 and -1e-6<=point[1]<=depth+1e-6 and -1e-6<=point[2]<=2.700001:
            hits.append((t,axis,point))
    if not hits: return ' ',(174,148,111),(60,48,39)
    distance,axis,point=min(hits)
    if axis==2 and point[2]<.1:
        tile=(int(point[0]*2)+int(point[1]*2))%2
        bg=(88,68,47) if tile else (112,88,61)
        ch=' '; fg=(155,125,86)
        if sign in ('BAR','LOUNGE','18+'):
            bg=(84,36,58) if tile else (112,45,65); fg=(203,84,126)
    elif axis==2:
        ch=' '; fg=(194,172,128); bg=(100,86,62)
    else:
        ch=' '; fg=(207,172,119); bg=(134,104,74) if axis==1 else (96,75,58)
        if sign in ('BAR','LOUNGE','18+'):
            fg=(232,125,158); bg=(91,37,61) if axis==1 else (55,29,52)
        if 1.25<point[2]<1.85 and abs(point[0]-width*.5)<width*.16:
            ch=' '
            fg=(224,182,99); bg=(45,72,69)
    for bounds,color in furniture(sign,width,depth):
        hit=intersect(origin,direction,bounds)
        if hit and hit[0]<distance:
            distance,side=hit
            factor=(.72,.87,1.0)[side]
            bg=tuple(int(v*factor) for v in color)
            fg=tuple(min(255,int(v*1.25)) for v in color)
            # Furniture geometry and face shading carry the shape. A glyph
            # on every surface sample turns chairs and shelves into stripes.
            ch=' '
    return ch,fg,bg
