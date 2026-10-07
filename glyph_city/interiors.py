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
    def box(x,y,z,w,d,h,color,material="wood"):
        boxes.append(((x,y,z,x+w,y+d,z+h),color,material))
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
    if sign in ('BOOKS','VINYL'):
        for x in (width*.18,width*.55):
            box(x,depth-.45,0,width*.22,.3,1.85,(80,55,37))
            for z in (.35,.8,1.25):
                for j in range(4):
                    box(x+j*width*.05,depth-.52,z,width*.035,.12,.3,
                        ((173,73,57),(177,159,80),(85,142,119),(97,114,167))[j],
                        'record' if sign=='VINYL' else 'book')
    elif sign=='FLORA':
        for x in (width*.18,width*.43,width*.7):
            box(x-.18,depth*.48,0,.36,.4,.48,(161,92,62),'pot')
            box(x-.025,depth*.48,.48,.05,.06,.8,(95,159,91),'stem')
            box(x-.3,depth*.48,.95,.6,.25,.42,(128,192,116),'leaves')
            box(x-.13,depth*.43,1.36,.26,.22,.19,(233,143,168),'flower')
    elif sign=='HOTEL':
        box(width*.16,depth*.35,0,width*.42,depth*.5,.45,wood)
        box(width*.16,depth*.35,.45,width*.42,depth*.5,.2,(175,179,167),'linen')
        box(width*.19,depth*.70,.65,width*.35,.34,.15,(230,219,189),'pillow')
        box(width*.69,depth*.62,0,.55,.5,.7,wood)
        box(width*.83,depth*.7,.7,.05,.06,.5,(191,169,126),'stem')
        box(width*.83-.2,depth*.7-.1,1.1,.45,.3,.16,(244,201,125),'light')
    else:
        box(width*.12,depth-.85,0,width*.76,.55,.95,wood)
        box(width*.1,depth-.9,.95,width*.8,.65,.1,(222,180,111))
        for x in (width*.26,width*.7):
            box(x-.4,depth*.4,.72,.8,.65,.1,(218,170,105))
            box(x-.06,depth*.4+.25,0,.12,.12,.72,wood)
            box(x-.32,depth*.4-.45,.38,.55,.4,.1,seat,'cloth')
            box(x-.32,depth*.4-.48,.4,.55,.07,.52,seat,'cloth')
            box(x-.3,depth*.4-.42,0,.07,.07,.38,wood)
            box(x+.15,depth*.4-.42,0,.07,.07,.38,wood)
            box(x-.12,depth*.4+.12,.82,.22,.18,.2,(229,211,174),
                'bowl' if sign=='RAMEN' else 'cup')
        if sign in ('BAR','LOUNGE','18+','JAZZ'):
            for j in range(6):
                box(width*(.18+j*.1),depth-.55,1.08,.12,.15,.3,
                    (96,166,133) if j%2 else (192,115,75))
    for x in (width*.3,width*.7):
        box(x-.025,depth*.5,2.0,.05,.05,.65,(67,52,37))
        box(x-.22,depth*.5-.16,1.94,.44,.34,.14,(255,218,141),'light')
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
        ch='.' if tile else ' '; fg=(155,125,86)
        if sign in ('BAR','LOUNGE','18+'):
            bg=(84,36,58) if tile else (112,45,65); fg=(203,84,126)
    elif axis==2:
        ch=' '; fg=(194,172,128); bg=(100,86,62)
    else:
        ch=' '; fg=(207,172,119); bg=(134,104,74) if axis==1 else (96,75,58)
        if sign in ('BAR','LOUNGE','18+'):
            fg=(232,125,158); bg=(91,37,61) if axis==1 else (55,29,52)
        if 1.25<point[2]<1.85 and abs(point[0]-width*.5)<width*.16:
            # A framed wall print: broad surfaces remain quiet instead of
            # magnifying the letter O into a rectangle of repeated symbols.
            edge=min(point[2]-1.25,1.85-point[2])
            side_edge=width*.16-abs(point[0]-width*.5)
            ch='-' if edge<.05 else '|' if side_edge<.05 else ' '
            fg=(224,182,99); bg=(45,72,69)
    emitting=False
    for bounds,color,material in furniture(sign,width,depth):
        hit=intersect(origin,direction,bounds)
        if hit and hit[0]<distance:
            distance,side=hit
            factor=(.72,.87,1.0)[side]
            bg=tuple(int(v*factor) for v in color)
            fg=tuple(min(255,int(v*1.25)) for v in color)
            point=tuple(origin[i]+direction[i]*distance for i in range(3))
            emitting=material=='light'
            # Identify the furniture material, instead of filling an entire
            # cafe with T glyphs or every lounge surface with O glyphs.
            if material=='book': ch='|' if side!=2 else '-'
            elif material=='record':
                u=(point[0]-bounds[0])/(bounds[3]-bounds[0])
                v=(point[2]-bounds[2])/(bounds[5]-bounds[2])
                radius=math.hypot(u-.5,v-.5)
                ch='=' if side==2 else '.' if radius<.14 else ' '
                if side!=2 and .14<=radius<.43:
                    bg=tuple(int(value*.24) for value in color)
            elif material=='leaves': ch='*' if int(point[0]*9)%3==0 else ';'
            elif material=='flower': ch='*'
            elif material=='stem': ch='|'
            elif material=='pot': ch='_' if side==2 else ':'
            elif material in ('linen','pillow'): ch='_' if side==2 else '='
            elif material=='cloth': ch=':' if int(point[0]*5)%3==0 else ' '
            elif material=='light': ch='-' if side==2 else '_'
            elif material=='cup': ch='o' if side==2 else 'c'
            elif material=='bowl': ch='~' if side==2 else 'u'
            else:
                # Thin legs and shelf edges have structure; broad wood
                # surfaces use sparse grain and do not become glyph blocks.
                thin=bounds[3]-bounds[0]<.2
                ch='|' if thin else '-' if side==2 else ':' if int(point[2]*12)%5==0 else ' '
    # Room depth, ceiling bounce and warm pendant pools stay in world space.
    # Large flat tan panes previously hid the silhouette of the furniture.
    if not emitting:
        px,py,pz=point
        lamp=min((px-width*f)**2+(py-depth*.5)**2+(pz-1.95)**2
                 for f in (.3,.7))
        illumination=.50+.40/(1+lamp*.65)
        illumination*=.85+.15*max(0,min(1,pz/2.0))
        bg=tuple(int(v*illumination) for v in bg)
        fg=tuple(int(v*(illumination+.12)) for v in fg)
    return ch,fg,bg
