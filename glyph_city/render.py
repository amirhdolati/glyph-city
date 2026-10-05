"""Perspective ray casting and colored, single-column ASCII materials."""
from __future__ import annotations

import math
from .city import SIZE
from .interiors import room_pixel

FOV = math.radians(76)
FAR = 78.0
EYE = 1.72
TAU = math.tau

# Surface masks keep rain response and facade reflections tied to the material
# under the projected pixel.  Grass deliberately has no wet sheen or facade
# reflection; roads, paving and bridges can catch a reduced wet highlight.
WETNESS_MASK = {'w': .35, 'r': 1.0, 'p': .72, 'b': .82}
REFLECTION_MASK = {'w': 1.0, 'r': .82, 'p': .42, 'b': .58}

# Only small, repeatable decorations use the first LOD.  Buildings, signs,
# landmarks, lamps, people, cars and the boat keep their authored glyphs.
LOD_KINDS = frozenset(('tree', 'flowers', 'rail', 'bench'))
LOD_ENTER_HEIGHT = 2.40
LOD_EXIT_HEIGHT = 1.75
LOD_ENTER_DISTANCE = 40.0
LOD_EXIT_DISTANCE = 43.0
LOD_ART = {
    'tree': (('^',), 1.05, 1.0),
    'flowers': (('*',), .55, .5),
    'rail': (('=',), 1.15, .28),
    'bench': (('_',), 1.0, .35),
}

# Tiny interior glimpses keep windows from reading as generic checkerboard
# lights.  They are intentionally abstract: at terminal scale a few props and
# a counter are more readable than detailed sprites.
INTERIOR_ART = {
    'CAFE': ('o=', (245, 183, 101)),
    'BAKERY': ('o=', (249, 196, 118)),
    'RAMEN': ('~=', (245, 155, 91)),
    'JAZZ': ('~|', (197, 146, 241)),
    'VINYL': ('()', (180, 206, 239)),
    'BOOKS': ('[]', (188, 226, 177)),
    'FLORA': ('**', (236, 143, 184)),
    'HOTEL': ('==', (214, 177, 127)),
    'BAR': ('o|', (239, 131, 167)),
    'LOUNGE': ('@~', (244, 121, 173)),
    '18+': ('@~', (244, 121, 173)),
}


def window_interior(sign, seed, bay, story, level):
    """Return a deterministic one-cell interior glimpse and its warm color."""
    key=str(sign).upper()
    mark, color=INTERIOR_ART.get(key, ('o+', (239, 174, 100)))
    index=(int(bay*7)+story*3+int(level*11)+seed)%len(mark)
    return mark[index], color


def mix(a, b, t):
    t = 0.0 if t<0 else 1.0 if t>1 else t
    return (int(a[0]+(b[0]-a[0])*t), int(a[1]+(b[1]-a[1])*t), int(a[2]+(b[2]-a[2])*t))


def scale(color, factor):
    factor=max(0,factor)
    return (min(255,int(color[0]*factor)),min(255,int(color[1]*factor)),min(255,int(color[2]*factor)))


def grain(x, y, seed=0):
    return ((x*374761393 + y*668265263 + seed*144269) ^ (x*y*1274126177)) & 65535


def reflection_tick(time):
    """Quantize animated reflection noise so adjacent frames stay stable."""
    return int(time * 2.0)


def reflection_noise(x, y, seed, tick):
    """World-space, slowly animated noise for a reflection cell."""
    return grain(math.floor(x * 2.0), math.floor(y * 2.0), seed + tick * 7919)


def fog_factor(distance, visibility, ceiling=.88):
    """Return a smooth, monotonic fog amount for a world-space distance."""
    if visibility <= 0:
        return ceiling
    return min(ceiling, max(0.0, distance / visibility) ** 1.5)


def shadow_band(x, y, seed):
    """Return a stable, subtle world-space shading band."""
    band = grain(math.floor(x / 3.0), math.floor(y / 3.0), seed) % 17
    return .9 if band < 2 else 1.0


def terrain_relief(x, y, seed):
    """Return a smooth, world-locked height and ridge value for the ground.

    A smooth field gives nearby ASCII marks a shared direction and shadow;
    hashing every cell independently would look like TV static.
    """
    phase=seed*.017
    wave=math.sin(x*1.35+y*.72+phase)*.55
    cross=math.cos(x*.48-y*1.08-phase*.7)*.30
    height=.5+.5*(wave+cross)
    slope=math.cos(x*1.35+y*.72+phase)*.55 - math.sin(x*.48-y*1.08-phase*.7)*.30
    return max(0.0,min(1.0,height)), max(-1.0,min(1.0,slope))


def local_light(glow, night, lantern=False):
    """Map authored lamp glow to readable local illumination.

    The previous pass multiplied glow directly by night, which made lamps
    disappear at dusk and left the foreground too flat at night. Keep the
    source deterministic while giving nearby pools a visible warm lift.
    """
    value=max(0.0,min(1.0,float(glow)))
    return max(value * (0.72 + 1.18*max(0.0,min(1.0,night))),
               .18 if lantern else 0.0)


def cell(ch, fg, bg):
    # Small palette steps make color runs cheaper without changing glyph width.
    return ch, (fg[0]&248,fg[1]&248,fg[2]&248), (bg[0]&248,bg[1]&248,bg[2]&248)


ART = {
    'tree': ((' .---. ','/     \\','\\_____/','   |   ','   |   ','  /_\\  '),2.6,4.2),
    'lamp': (('  ___  ',' /___\\ ',' | o | ','  \\|/  ','   |   ','   |   ','   |   ','  _|_  '),.75,3.8),
    'bench': ((' _______ ','|=======|','|_______|',' ||   || '),1.9,.9),
    'flowers': ((' * . * ','\\|/*|/','[=====]',' \\___/ '),1.1,.85),
    'fountain': (('    .    ','  . | .  ',' . \\|/ . ','  \\ | /  ',' ~~~|~~~ ','(=======)',' \\_____/ '),2.8,2.3),
    'rail': (('___________','| | | | | |','|_|_|_|_|_|'),4,.9),
    'stall': (('  /---\\  ',' /     \\ ',' | tea | ',' |_____| '),2.6,2.2),
    # People use a wider silhouette so they remain legible in rain and at
    # terminal sizes where a one-column body disappears into facade texture.
    'person': (('  o  ',' /|\\ ',' /|\\ ',' / \\ '),.86,2.05),
    'car': (('  _____  ',' /_____\\ ','|o_____o|',' |_| |_| '),1.8,1.35),
    'boat': (('     |     ','  ___|__   ',' /______\\  ',' \\______/  ',' ~~~~~~~~  '),3.5,1.5),
}

PERSON_COLORS = {
    'barista': (245, 165, 105),
    'gardener': (145, 218, 151),
    'courier': (239, 193, 116),
    'musician': (204, 151, 246),
    'bookseller': (145, 194, 238),
    'photographer': (239, 142, 187),
    'commuter': (196, 205, 214),
    'vendor': (245, 173, 104),
}


class Renderer:
    def __init__(self, cols, rows, aspect=.5):
        self.cols, self.rows = cols, rows
        self.aspect=aspect
        self.fx = cols/(2*math.tan(FOV/2))
        self.fy = self.fx*aspect
        self.camera_x = [(c+.5-cols/2)/self.fx for c in range(cols)]
        # Keyed by the stable Prop object identity.  A renderer is recreated
        # on resize, which also clears this frame-local hysteresis state.
        self._sprite_lod = {}

    def sprite_lod(self, prop, distance):
        """Return 0 for compact distant decoration art, 1 for full art.

        The decision uses projected height and distance in world space.  The
        separate enter/exit thresholds keep a prop from changing glyph shape
        when camera motion leaves it near a single threshold.
        """
        if prop.kind not in LOD_KINDS:
            return 1
        _, _, full_height = ART[prop.kind]
        projected_height = full_height * self.fy / max(distance, .35)
        previous = self._sprite_lod.get(id(prop), 1)
        if previous:
            level = 0 if (projected_height < LOD_EXIT_HEIGHT
                           or distance > LOD_EXIT_DISTANCE) else 1
        else:
            level = 1 if (projected_height >= LOD_ENTER_HEIGHT
                          and distance < LOD_ENTER_DISTANCE) else 0
        self._sprite_lod[id(prop)] = level
        return level

    def render(self, world, minimap=False):
        self.world = world
        self.city = city = world.city
        cols, rows = self.cols, self.rows
        fov=math.radians(getattr(world,'camera_fov',math.degrees(FOV)))
        self.fx=cols/(2*math.tan(fov/2))
        self.fy=self.fx*self.aspect if hasattr(self,'aspect') else self.fx*.5
        self.camera_x=[(c+.5-cols/2)/self.fx for c in range(cols)]
        elevation = math.sin((world.clock-6)/24*TAU)
        self.day = day = max(0,min(1,(elevation+.12)*1.65))
        contrast=max(.5,min(2.0,float(getattr(world,'night_contrast',1.0))))
        self.night=max(0.0,min(1.0,.5+(1-day-.5)*contrast))
        self.sunset = max(0,1-abs(elevation)/.4)*(1-world.cloud*.6)
        self.fog = mix((12,23,40),(105,142,162),day)
        self.fog = mix(self.fog,(161,102,107),self.sunset*.5)
        self.fog = mix(self.fog,(95,117,130),world.cloud*.35)
        # Keep weather atmosphere while preserving silhouettes and window edges.
        self.visibility = 52 if world.weather == 3 else 62 if world.weather == 2 else FAR
        eye = getattr(world,'eye_height',EYE)+world.bob
        self.eye = eye
        self.horizon = horizon = rows*.47+world.pitch*rows+world.bob*self.fy*.16
        ca, sa = math.cos(world.angle), math.sin(world.angle)
        rays = [(ca-sa*x,sa+ca*x) for x in self.camera_x]
        self.buffer = buf = [[(' ',(0,0,0),(0,0,0)) for _ in range(cols)] for _ in range(rows)]
        self.depth = depths = [[FAR*2]*cols for _ in range(rows)]
        self.surface = [[-1]*cols for _ in range(rows)]
        ground_tiles = [[None]*cols for _ in range(rows)]
        ground_coords = [[None]*cols for _ in range(rows)]
        reflection_depth = [[FAR*2]*cols for _ in range(rows)]
        reflection_tick_value = reflection_tick(world.time)
        top = mix((4,8,22),(38,83,124),day)
        low = mix((14,25,43),(157,185,185),day)
        low = mix(low,(231,143,115),self.sunset*.8)
        top, low = mix(top,self.fog,world.cloud*.45),mix(low,self.fog,world.cloud*.5)
        flash=0.0
        if (world.weather==2 and getattr(world,'storm_flash_enabled',True)):
            pulse=math.sin(world.time*1.71+13.0)**28
            flash=max(0.0,(pulse-.72)/.28)
            if flash:
                top=mix(top,(185,198,204),flash*.32)
                low=mix(low,(210,205,191),flash*.24)
        for r in range(rows):
            if r+.5 < horizon:
                ratio = max(0,min(1,(r+.5)/max(1,horizon)))
                bg = mix(top,low,ratio)
                for c in range(cols):
                    az = world.angle+math.atan(self.camera_x[c])
                    cloud = (math.sin(az*5+world.time*.008+ratio*6)
                             +.5*math.sin(az*13-ratio*11+world.time*.015))
                    ch, fg, cbg = ' ',scale(bg,1.2),bg
                    if .17 < ratio < .76 and cloud > 1.1-world.cloud*.75:
                        fg = mix(bg,(206,199,186),.22+.28*day)
                        # Cloud mass reads through its color, not a sheet of
                        # repeated dots and tildes behind the buildings.
                        cbg = mix(bg,fg,.28)
                    elif self.night>.6 and world.cloud<.5:
                        star = grain(int((az%TAU)*135),int(ratio*65),self.city.seed)
                        if star%127==0:
                            ch,fg = ('+' if star%5==0 else '.'),(179,198,222)
                    buf[r][c] = cell(ch,fg,cbg)
            else:
                dist = eye*self.fy/max(.1,r+.5-horizon)
                for c,(dx,dy) in enumerate(rays):
                    wx,wy = world.x+dx*dist,world.y+dy*dist
                    buf[r][c] = self._ground(wx,wy,dist,r,c)
                    ground_coords[r][c] = (wx,wy)
                    ix,iy = math.floor(wx),math.floor(wy)
                    if 0 <= ix < SIZE and 0 <= iy < SIZE:
                        ground_tiles[r][c] = city.tiles[iy][ix]
                    depths[r][c] = dist
        self._celestial(elevation)
        for c,(dx,dy) in enumerate(rays):
            hits = self._cast(world.x,world.y,dx,dy)
            # Visit near surfaces first; shade distant cells only if visible.
            for dist,side,bid,hx,hy in hits:
                b = city.buildings[bid]
                top_r = max(0,math.floor(horizon-(b.height-eye)*self.fy/dist))
                bottom_r = min(rows-1,math.ceil(horizon+eye*self.fy/dist))
                if side == 0:
                    u = hy-b.y0 if dx>0 else b.y1-hy
                    span = b.y1-b.y0
                else:
                    u = b.x1-hx if dy>0 else hx-b.x0
                    span = b.x1-b.x0
                for r in range(top_r,bottom_r+1):
                    z = eye+(horizon-r-.5)*dist/self.fy
                    if not 0<=z<=b.height or dist>depths[r][c]+.02: continue
                    level=z%2.8
                    if (int(z/2.8)==0 and .35<level<2.08
                            and .22<u<span-.22):
                        normal=abs(dx if side==0 else dy)
                        tangent=(dy if dx>0 else -dy) if side==0 else (-dx if dy>0 else dx)
                        depth=min(4.5,(b.x1-b.x0) if side==0 else (b.y1-b.y0))
                        ch,fg,bg,emits=self._shop_glass(
                            b,u,z,span,depth,(tangent,normal,(z-eye)/dist),dist)
                    else:
                        ch,fg,bg,emits = self._facade(b,u,z,span,side,dist,hx,hy)
                    buf[r][c] = cell(ch,fg,bg)
                    depths[r][c] = dist
                    self.surface[r][c] = bid
                    # The projected reflection lands on the ground cell below
                    # this wall pixel. Gate it by that ground material so a
                    # bright window cannot paint a reflection over grass.
                    rr = round(horizon+(z+eye)*self.fy/dist)
                    if emits and world.wet>.05 and 0 <= rr < rows:
                        tile = ground_tiles[rr][c]
                        strength = REFLECTION_MASK.get(tile, 0.0)
                        coords = ground_coords[rr][c]
                        if strength and coords is not None:
                            rx,ry = coords
                            if (self.surface[rr][c]<0 and dist<reflection_depth[rr][c]
                                    and dist<32
                                    and reflection_noise(rx,ry,city.seed,reflection_tick_value)%9<2):
                                oldch,oldfg,oldbg = buf[rr][c]
                                # Reflections are glints on the pavement, not
                                # a second opaque wall. Preserve lane marks,
                                # sprites and existing road texture.
                                if oldch in (' ','.',':','~'):
                                    alpha = world.wet*strength*(.045+.11*self.night)
                                    buf[rr][c] = cell(oldch,
                                                      mix(oldfg,fg,alpha),
                                                      mix(oldbg,fg,alpha*.22))
                                    reflection_depth[rr][c] = dist
        self._building_edges()
        self._signs(ca,sa)
        for prop in sorted(city.props,key=lambda p: -((p.x-world.x)**2+(p.y-world.y)**2)):
            self._sprite(prop,ca,sa)
        self._weather()
        if minimap: self._minimap()
        return buf

    def _building_edges(self):
        """Add a restrained silhouette line where a projected wall ends.

        Dense window glyphs can otherwise make two adjacent facades read as a
        single noisy rectangle. Edges are drawn only on empty facade cells, so
        glass interiors and signs retain their authored detail.
        """
        for r in range(self.rows):
            for c in range(self.cols):
                bid=self.surface[r][c]
                if bid<0: continue
                left=c==0 or self.surface[r][c-1]!=bid
                right=c==self.cols-1 or self.surface[r][c+1]!=bid
                top=r==0 or self.surface[r-1][c]!=bid
                ch,fg,bg=self.buffer[r][c]
                if self.depth[r][c] > 24:
                    continue
                if not (top or (left and c%3==0) or (right and c%3==0)) or ch not in (' ','.',':','-'):
                    continue
                b=self.city.buildings[bid]
                edge=mix(fg,(226,213,171),.34 if top else .22)
                self.buffer[r][c]=cell('=' if top else '|',edge,bg)

    def render_interior(self, world):
        """Render the bounded cafe room without invoking the outdoor ray caster."""
        bg=(28,18,20); wall=(151,104,88); trim=(219,165,105); floor=(82,58,48)
        buf=[[cell(' ',wall,bg) for _ in range(self.cols)] for _ in range(self.rows)]
        horizon=max(2,int(self.rows*.42))
        for r in range(horizon,self.rows):
            shade=max(.45,1-(r-horizon)/max(1,self.rows-horizon)*.4)
            for c in range(self.cols):
                buf[r][c]=cell('.' if (r+c)%5 else ':',tuple(int(v*shade) for v in trim),floor)
        for c in range(self.cols):
            buf[horizon][c]=cell('=',trim,bg)
        title=' CAFE / WARM WINDOWS / MOONWATER '
        for c,ch in enumerate(title[:self.cols]): buf[2][c]=cell(ch,trim,bg)
        objects=[(max(1,self.cols//2-12),horizon+5,'[  COUNTER  ]'),
                 (max(1,self.cols//2-24),horizon+9,'(  table  )'),
                 (min(self.cols-16,self.cols//2+10),horizon+9,'[ window ]')]
        for x,y,text in objects:
            if 0<=y<self.rows:
                for c,ch in enumerate(text):
                    if 0<=x+c<self.cols: buf[y][x+c]=cell(ch,trim,floor)
        return buf

    def _cast(self, x, y, dx, dy):
        mx,my = int(x),int(y)
        sx,sy = (1 if dx>=0 else -1),(1 if dy>=0 else -1)
        ddx,ddy = abs(1/dx) if dx else 1e20, abs(1/dy) if dy else 1e20
        tx = ((mx+1-x) if sx>0 else (x-mx))*ddx
        ty = ((my+1-y) if sy>0 else (y-my))*ddy
        seen,hits = set(),[]
        for _ in range(180):
            if tx<ty:
                dist,side=tx,0; tx+=ddx; mx+=sx
            else:
                dist,side=ty,1; ty+=ddy; my+=sy
            if dist>FAR or not 0<=mx<SIZE or not 0<=my<SIZE: break
            bid = self.city.walls[my][mx]
            if bid>=0 and bid not in seen:
                seen.add(bid)
                hits.append((max(.05,dist),side,bid,x+dx*dist,y+dy*dist))
                if len(hits)>=12: break
        return hits

    def _ground(self, x, y, dist, r, c):
        day,night,w = self.day,self.night,self.world
        ix,iy = math.floor(x),math.floor(y)
        if not 0<=ix<SIZE or not 0<=iy<SIZE or dist>FAR:
            return cell(' ',scale(self.fog,.9),scale(self.fog,.7))
        tile = self.city.tiles[iy][ix]
        h = grain(int(x*9),int(y*9),self.city.seed)
        light = local_light(self.city.glow[iy][ix],night,w.lantern and dist<9)
        bases = {'r':(58,68,78),'p':(108,106,99),'g':(45,91,68),'b':(119,103,82),'w':(34,84,103)}
        base = bases[tile]
        # Material motifs stay in world space; their contrast fades with
        # distance rather than filling the horizon with tiny texture glyphs.
        # Keep a readable middle-distance band: ASCII fades gradually through
        # the street instead of disappearing immediately after the foreground.
        detail=max(0.0,min(1.0,(34.0-dist)/20.0))
        motif=grain(math.floor(x*2),math.floor(y*2),self.city.seed)
        joint=min(.12,max(.045,dist/max(self.fx,1.0)*.35))
        relief,ridge=terrain_relief(x,y,self.city.seed)
        # A soft directional key light makes the relief readable without
        # turning every foreground cell into a bright outline.
        sun_angle=(w.clock-6.0)/24.0*TAU
        key=math.cos(x*1.35+y*.72+sun_angle)+math.sin(x*.48-y*1.08-sun_angle*.7)
        relief_light=max(-1.0,min(1.0,key*.5+ridge*.35))
        if tile=='w':
            ripple=math.sin(x*.65+y*.45+w.time*.55)
            bg=mix(scale(base,.28+.72*day),self.fog,.18)
            fg=mix(bg,(141,184,184),.24+.22*max(0,ripple))
            bg=mix(bg,fg,max(0,ripple)*.18)
            # Broad, sparse wave crests leave most of the water quiet.
            if dist<24 and detail>.2:
                ch='~' if ripple>.72 else '-' if ripple>.22 else '.' if ripple<-.72 else ' '
            else:
                ch='~' if dist<34 and ripple>.985 else ' '
        else:
            shade=shadow_band(x,y,self.city.seed)
            bg=scale(base,(.27+.60*day)*shade)
            fg=scale(base,(.58+.58*day)*shade)
            ch=' '
            if tile=='g' and dist<32:
                cadence=2 if detail>.65 else 4 if detail>.35 else 8
                if relief>.73 and motif%cadence==0: ch='^'
                elif relief<.25 and motif%(cadence+1)==0: ch=','
                elif detail>.35 and motif%(cadence+2)==0: ch=(',',"'",';')[motif%3]
                fg=scale((74,131,83),.3+.65*day)
            elif tile=='p' and dist<32:
                # Offset rectangular paving joints make sidewalks distinct
                # from asphalt without coating every stone in punctuation.
                py=y%.9
                px=(x+(math.floor(y/.9)%2)*.8)%1.6
                horizontal=py<joint
                vertical=px<joint
                ch='+' if horizontal and vertical else '_' if horizontal else '|' if vertical else ' '
                block=grain(math.floor((x+(math.floor(y/.9)%2)*.8)/1.6),
                            math.floor(y/.9),self.city.seed)
                bg=scale(bg,.97+(block%3)*.03)
                fg=mix(fg,(168,153,122),.18)
                if not (horizontal or vertical) and detail>.25:
                    ch='.' if relief<.28 else ':' if relief>.72 else ' '
                    fg=mix(fg,(212,198,160),.16*detail)
                # A thin curb and occasional drain locate the road edge.
                curb_x=((ix>0 and self.city.tiles[iy][ix-1]=='r' and x%1<.12)
                        or (ix<SIZE-1 and self.city.tiles[iy][ix+1]=='r' and x%1>.88))
                curb_y=((iy>0 and self.city.tiles[iy-1][ix]=='r' and y%1<.12)
                        or (iy<SIZE-1 and self.city.tiles[iy+1][ix]=='r' and y%1>.88))
                if curb_x or curb_y:
                    ch='#' if grain(ix,iy,self.city.seed)%13==0 else '|' if curb_x else '_'
                    fg=scale((181,175,158),.48+.52*day)
            elif tile=='b' and dist<32:
                # Bridge boards and nails, in contrast to sidewalk joints.
                ch='=' if y%1.4<joint else ('#' if relief>.78 and dist<18 else
                    '.' if dist<20 and motif%23==0 else ' ')
                fg=mix(fg,(178,144,100),.25)
            elif tile=='r' and dist<32:
                if dist<20 and relief>.78: ch=':'
                elif dist<18 and relief<.22: ch='.'
                else: ch='.' if dist<24 and motif%23==0 else ' '
                ax=abs(x%24-12); ay=abs(y%24-12)
                if ax<.09 and int(y/1.7)%3<2 and ay>3:
                    ch='|'; fg=scale((230,190,111),.5+.5*day)
                elif ay<.09 and int(x/1.7)%3<2 and ax>3:
                    ch='-'; fg=scale((230,190,111),.5+.5*day)
                elif ((3.0<ay<4.1 and ax<2.1) or (3.0<ax<4.1 and ay<2.1)):
                    # Crossings are light bands instead of noisy equals.
                    bg=mix(bg,scale((187,188,168),.35+.65*day),.35)
                    ch='=' if dist<24 and (int(x*2)+int(y*2))%2==0 else ' '
            if light:
                bg=mix(bg,(134,97,55),min(.86,light*.78))
                fg=mix(fg,(246,194,112),min(.92,light*.92))
            wetness = WETNESS_MASK.get(tile, 0.0)
            if w.wet>.03 and wetness:
                wet = w.wet * wetness
                bg=mix(bg,scale(bg,.62),wet)
                if h%17<3:
                    fg=mix(fg,self.fog,wet*.6)
            if w.lantern and dist<9:
                beam=max(0,1-dist/9)*max(0,1-abs(c-self.cols/2)/(self.cols*.38))
                fg=mix(fg,(234,205,140),beam*.6)
                bg=mix(bg,(115,93,49),beam*.35)
        # Apply a restrained raised-edge highlight and a pooled shadow to the
        # material block. It is strongest near the camera and fades smoothly.
        ridge_tone=(.88+.16*relief_light*detail)
        fg=scale(fg,ridge_tone)
        if relief_light<-.25:
            bg=scale(bg,1.0+.10*relief_light*detail)
        fg=mix(bg,fg,detail)
        fog=fog_factor(dist,self.visibility)
        return cell(ch,mix(fg,self.fog,fog*.72),mix(bg,self.fog,fog*.52))

    def _shop_glass(self,b,u,z,span,depth,direction,dist):
        panes=max(1,round(span/3))
        pane=span/panes
        seam=min(u%pane,pane-u%pane)
        if seam<.035 or z<.29 or z>2.055:
            return ('|' if seam<.035 else '-',(139,165,167),(25,36,41),False)
        if dist<28:
            ch,fg,bg=room_pixel(b.sign,span,depth,u,z,direction)
            # Preserve a few recognizable interior marks at middle distance,
            # while thinning the furniture so panes remain transparent.
            if dist>=18 and grain(int(u*9),int(z*9),b.seed)%3:
                ch=' '
        else:
            ch,fg,bg=' ',(174,148,111),(60,48,39)
        length=math.hypot(direction[0],direction[1])
        grazing=1-direction[1]/max(length,1e-6)
        reflection=.025+.11*grazing**3
        fg=mix(fg,(131,174,191),reflection)
        bg=mix(bg,self.fog,reflection)
        # A narrow continuous streak leaves most of the view transparent.
        if abs((u/pane)%1-(.2+z*.08))<.012:
            fg=mix(fg,(203,225,230),.32)
            bg=mix(bg,(144,185,195),.12)
        fog=fog_factor(dist,self.visibility)*.35
        return ch,mix(fg,self.fog,fog),mix(bg,self.fog,fog),True

    def _facade(self, b, u, z, span, side, dist, hx=None, hy=None):
        day,night = self.day,self.night
        # Keep near wall edges above the night fog floor so building shapes
        # read as planes instead of dissolving into the background.
        shade=(.58+.64*day)*(1 if side else .90)
        if self.world.lantern: shade+=max(0,1-dist/9)*.38
        base=mix(b.color,(224,153,101),self.sunset*.2)
        fg,bg=scale(base,shade),scale(base,shade*(.36+.10*day))
        bay=u%1.65; story=int(z/2.8); level=z%2.8
        facade_detail=max(0.0,min(1.0,(34.0-dist)/18.0))
        window_seed=grain(int(u/1.65),story,b.seed)
        emits=False
        if b.height-z<.23:
            ch='='; fg=scale(base,shade*1.35)
        elif level<.13:
            ch='-'; fg=scale(base,shade*1.2)
        elif facade_detail>.18 and (level<.24 or level>2.58):
            # Floor slabs give tall flat faces a readable vertical scale.
            ch='-' if window_seed%3 else '='
            fg=scale(base,shade*.98)
        elif story==0 and 2.15<z<2.5 and abs(u-span/2)<len(b.sign)*.26:
            ch='-'; fg=scale(b.neon,.5); bg=scale(b.neon,.14); emits=True
        elif .18<bay<1.48 and .48<level<2.24:
            lit=(window_seed%100)<(18+night*42)
            # Frames and room surfaces use color blocks. Filling every pane
            # with furniture glyphs used to obscure the building silhouette.
            edge=bay<.36 or bay>1.30 or level<.82 or level>1.98
            if edge:
                ch='|' if facade_detail>.48 and .82<level<1.98 else '-' if facade_detail>.28 else ' '
                fg=scale(base,shade*.82); bg=scale((24,29,38),.8)
            elif lit:
                glow=mix((255,190,92),b.neon,.2)
                glass=mix((20,27,38),glow,.26+.12*night)
                fg=scale(glow,.9+.3*night); bg=scale(glass,.78)
                if facade_detail>.68:
                    ch='O' if window_seed%5 else 'o'
                elif facade_detail>.32:
                    ch='o' if window_seed%3 else ' '
                else:
                    ch=' '
                emits=True
            else:
                ch='.' if facade_detail>.48 and window_seed%3==0 else ' '
                fg=mix((49,89,119),self.fog,.25); bg=scale(fg,.25)
        elif story==0 and abs(u-span/2)<.42 and z<1.9:
            ch='|' if abs(u-span/2)>.3 else 'D' if facade_detail>.35 else '.'
            fg=scale(b.neon,.45); bg=(14,18,24)
        else:
            ch=' '
        if hx is not None and hy is not None and not emits:
            ix,iy=math.floor(hx),math.floor(hy)
            if 0<=ix<SIZE and 0<=iy<SIZE:
                # Street lamps graze only the lower facade. The source stays
                # in world space, so camera motion cannot make it shimmer.
                bounce=local_light(self.city.glow[iy][ix],night)*math.exp(-max(0,z)/6)
                fg=mix(fg,(230,166,99),min(.44,bounce*.34))
                bg=mix(bg,(105,68,43),min(.31,bounce*.22))
        fog=fog_factor(dist,self.visibility,.72)
        if emits:
            # Lit windows are the focal points of the facade. Keep their
            # glass and interior silhouettes legible through rain and mist.
            fog*=.22 if dist<24 else .38
        return ch,mix(fg,self.fog,fog),mix(bg,self.fog,fog*.62),emits

    def _signs(self,ca,sa):
        for bid,b in enumerate(self.city.buildings):
            faces=[]
            w=self.world
            if w.x<b.x0: faces.append((b.x0,(b.y0+b.y1)/2,b.y1-b.y0))
            elif w.x>b.x1: faces.append((b.x1,(b.y0+b.y1)/2,b.y1-b.y0))
            if w.y<b.y0: faces.append(((b.x0+b.x1)/2,b.y0,b.x1-b.x0))
            elif w.y>b.y1: faces.append(((b.x0+b.x1)/2,b.y1,b.x1-b.x0))
            for x,y,span in faces:
                dx,dy=x-w.x,y-w.y
                z=dx*ca+dy*sa
                if z<1 or z>32 or span*self.fx/z<len(b.sign)+2: continue
                cx=round(self.cols/2+(-dx*sa+dy*ca)*self.fx/z)
                r=round(self.horizon-(2.32-self.eye)*self.fy/z-.5)
                if not 0<=r<self.rows: continue
                for i,ch in enumerate(b.sign):
                    c=cx-len(b.sign)//2+i
                    if 0<=c<self.cols and self.surface[r][c]==bid:
                        self.buffer[r][c]=cell(ch,b.neon,scale(b.neon,.13))

    def _celestial(self, elevation):
        w=self.world
        # Celestial bodies keep a world bearing as the player turns.
        sun_az=-(w.clock-6)/12*math.pi
        moon=self.day<.2
        az=sun_az+ (math.pi if moon else 0)
        delta=(az-w.angle+math.pi)%TAU-math.pi
        if abs(delta)>FOV/2+.1 or w.cloud>.65: return
        x=round(self.cols/2+math.tan(delta)*self.fx)
        height=abs(elevation) if moon else max(0,elevation)
        y=round(self.horizon-height*self.rows*.9-3)
        art=(' .-. ','(   )',' `-\' ') if moon else (' \\|/ ','- @ -',' /|\\ ')
        color=(188,206,222) if moon else (255,219,143)
        for ar,line in enumerate(art):
            for ac,ch in enumerate(line):
                xx,yy=x+ac-2,y+ar-1
                if ch!=' ' and 0<=xx<self.cols and 0<=yy<self.rows:
                    self.buffer[yy][xx]=cell(ch,color,self.buffer[yy][xx][2])

    def _sprite(self, p, ca, sa):
        if p.kind=='boat' and self.city.tiles[int(p.y)][int(p.x)]=='b': return
        dx,dy=p.x-self.world.x,p.y-self.world.y
        z=dx*ca+dy*sa
        if z<.35 or z>48: return
        lateral=-dx*sa+dy*ca
        lod = self.sprite_lod(p, z)
        art,width,height = LOD_ART[p.kind] if lod == 0 else ART[p.kind]
        person_scale=1.0
        if p.kind=='person':
            pose=int(self.world.time*3+p.phase)%2
            if p.umbrella:
                art=(' .---. ','/_____\\','|  o  |','  /|\\  ','  / \\  '); width=1.08; height=2.2
            elif p.activity=='walking':
                art=('  o  ',' /|\\ ',' /|  ' if pose else '  |\\ ',' / \\ ')
            elif p.activity in ('reading','sorting books'):
                art=('  o  ',' [=] ','  |  ',' / \\ ')
            elif p.activity=='playing music':
                art=('  o  ',' /|D ',' /|  ',' / \\ ')
            elif p.activity=='taking photos':
                art=('  o  ',' [o] ','  |  ',' / \\ ')
            elif p.activity=='tending flowers':
                art=('   ',' o_','/|/','/ \\'); height=1.2
            # Use one small readable face at very close range. More elaborate
            # hair and eye art multiplied across terminal cells and made the
            # whole fixed camera composition noisy.
            close_detail=height*self.fy/max(z,.35)>=10.0
            if close_detail and p.umbrella:
                art=(' .-. ','/___\\',' (o) ',' /|\\ ',' / \\ ')
            elif close_detail:
                art=(' ^ ','(o)','/|\\','/ \\ ')
                width=.82; height=1.95
            # Crowd LOD keeps a fixed composition readable. Far residents
            # remain visible as moving beacons, while only nearby residents
            # spend cells on faces and clothing detail.
            if z>30:
                art=('.' if not p.umbrella else '-',); width=.42; height=.72
            elif z>16 and not close_detail:
                if p.umbrella:
                    art=(' .-. ','| o |',' /|\\ ',' / \\ '); width=.82; height=1.65
                else:
                    art=(' o ','/|\\','/ \\'); width=.62; height=1.55
            projected=height*self.fy/max(z,.35)
            max_person_height=min(10.0,self.rows*.45)
            if projected>max_person_height:
                scale_factor=max_person_height/projected
                width*=scale_factor; height*=scale_factor
                person_scale=scale_factor
        aw=max(map(len,art)); ah=len(art)
        sx=self.cols/2+lateral*self.fx/z
        # Compress the whole near-person projection around the horizon.
        # Shrinking only its height would push its face below the screen.
        bottom=self.horizon+self.eye*self.fy/z*person_scale
        pw,ph=width*self.fx/z,height*self.fy/z
        if p.kind=='person':
            # Terminal cells are tall: unrestricted horizontal magnification
            # repeats each eye/hair glyph and makes faces look like fences.
            pw=min(pw,ph*aw/ah*1.2)
        left,top=sx-pw/2,bottom-ph
        if left>=self.cols or left+pw<0: return
        for r in range(max(0,math.floor(top)),min(self.rows,math.ceil(bottom))):
            ar=min(ah-1,max(0,int((r+.5-top)/ph*ah)))
            for c in range(max(0,math.floor(left)),min(self.cols,math.ceil(left+pw))):
                ac=min(aw-1,max(0,int((c+.5-left)/pw*aw)))
                ch=art[ar][ac] if ac<len(art[ar]) else ' '
                if ch==' ' or z>self.depth[r][c]+.05: continue
                color=p.color
                if p.kind=='tree': color=(96,148,104) if ar<3 else (137,105,74)
                elif p.kind=='lamp': color=(255,209,123) if ar<3 else (114,127,139)
                elif p.kind=='fountain': color=(128,196,215) if ar<5 else (136,147,155)
                elif p.kind=='bench': color=(175,124,81)
                elif p.kind=='rail': color=(111,135,148)
                elif p.kind=='flowers': color=(230,139,163) if ar<2 else (150,125,103)
                elif p.kind=='person':
                    role_color=PERSON_COLORS.get(getattr(p,'role',''),p.color)
                    if p.umbrella:
                        # The canopy catches sky light; the body stays a
                        # distinct role color beneath it.
                        color=((245,250,255) if ar<2 else
                               (48,34,45) if close_detail and ar==2 else role_color)
                    elif close_detail:
                        color=((48,34,45) if ar==0 else
                               (255,214,175) if ar==1 else role_color)
                    else:
                        color=(255,214,175) if ar==0 else role_color
                luminous=(p.kind=='lamp' and ar<3) or (p.kind=='car' and ch=='o')
                if p.kind=='person' and p.umbrella and ar<2: luminous=True
                factor=(1 if luminous else .94 if p.kind=='person'
                        else .4+.6*self.day)
                fog_amount=.20 if p.kind=='person' else .55
                color=mix(scale(color,factor),self.fog,min(.75,z/self.visibility)*fog_amount)
                bg=self.buffer[r][c][2]
                self.buffer[r][c]=cell(ch,color,mix(bg,(6,12,20),.82 if p.kind=='person' else .6))
                self.depth[r][c]=z
        focus=getattr(getattr(self.world,'life',None),'focus',None)
        # Keep the watch overlay readable: only the active speaker gets a
        # label. Distant names used to pile into a
        # single line and hide the actual people underneath.
        show_label=(p is focus)
        if (getattr(self.world,'show_names',False)
                and not getattr(self.world,'camera_transition',False)
                and getattr(p,'name','') and ph>=2 and show_label):
            label=(p.name+' / '+p.activity)[:32] if z<12 else p.name[:12]
            label_y=max(0,min(self.rows-1,math.floor(top)-1))
            label_x=round(sx-len(label)/2)
            for index,char in enumerate(label):
                xx=label_x+index
                if 0<=xx<self.cols and self.depth[label_y][xx]>=z-.1:
                    self.buffer[label_y][xx]=cell(char,(218,232,221),(17,29,34))
            if p.dialogue and (p is focus or z<14) and label_y>0:
                speech='"'+p.dialogue+'"'
                speech=speech[:self.cols-2]
                start=max(0,min(self.cols-len(speech),round(sx-len(speech)/2)))
                for index,char in enumerate(speech):
                    if self.depth[label_y-1][start+index]>=z-.1:
                        self.buffer[label_y-1][start+index]=cell(char,(245,211,158),(17,29,34))
        if p.kind=='lamp' and self.night>.3:
            cx,cy=round(sx),round(top+ph*.2)
            for oy,ox in ((0,-1),(0,1),(-1,0),(1,0)):
                xx,yy=cx+ox,cy+oy
                if 0<=xx<self.cols and 0<=yy<self.rows and self.depth[yy][xx]>=z-.1:
                    ch,fg,bg=self.buffer[yy][xx]
                    self.buffer[yy][xx]=cell(ch,mix(fg,(246,193,111),.22),mix(bg,(181,121,59),.18*self.night))

    def _weather(self):
        w=self.world
        if w.rain>.02:
            count=int(self.cols*self.rows*w.rain*.06)
            tick=w.time*(21+8*w.rain)
            for i in range(count):
                x=int((i*73.13-tick*.33)%self.cols)
                y=int((i*37.79+tick*(1+(i%3)*.25))%self.rows)
                ch,fg,bg=self.buffer[y][x]
                self.buffer[y][x]=cell('/' if w.weather==2 else '|',mix(fg,(151,181,204),.6),bg)
                if y>self.horizon+2 and i%7==0:
                    self.buffer[y][x]=cell('.',(121,163,183),bg)
        if w.weather==2 and w.time%19<.12:
            for r,row in enumerate(self.buffer):
                for c,(ch,fg,bg) in enumerate(row):
                    self.buffer[r][c]=cell(ch,mix(fg,(213,223,240),.5),mix(bg,(125,145,170),.3))

    def _minimap(self):
        if self.cols<72 or self.rows<24: return
        width,height=19,11; x0=self.cols-width-2; y0=1
        lines=['+'+'-'*(width-2)+'+']
        for r in range(height-2):
            line='|'
            for c in range(width-2):
                x=int(self.world.x+(c-(width-3)/2)*1.8)
                y=int(self.world.y+(r-(height-3)/2)*3.6)
                ch=' '
                if 0<=x<SIZE and 0<=y<SIZE:
                    ch='#' if self.city.walls[y][x]>=0 else {'r':'.','p':' ','g':',','w':'~','b':'='}[self.city.tiles[y][x]]
                if c==(width-3)//2 and r==(height-3)//2: ch='@'
                line+=ch
            lines.append(line+'|')
        lines.append('+'+'-'*(width-2)+'+')
        overlay(self.buffer,lines,x0,y0,(124,199,187),(9,21,29))


def overlay(buf, lines, x=None, y=None, fg=(218,211,188), bg=(10,19,29)):
    rows,cols=len(buf),len(buf[0])
    width=max(map(len,lines),default=0)
    if x is None: x=max(0,(cols-width)//2)
    if y is None: y=max(0,(rows-len(lines))//2)
    for r,line in enumerate(lines):
        for c,ch in enumerate(line.ljust(width)):
            if 0<=y+r<rows and 0<=x+c<cols:
                buf[y+r][x+c]=cell(ch,fg,bg)


def map_overlay(buf,world):
    rows,cols=len(buf),len(buf[0]); mw=min(60,cols-4); mh=min(25,rows-9)
    if mw<8 or mh<5:
        overlay(buf,[' A taller window is needed for the map. ', ' M closes the map. '])
        return
    lines=['+'+'-'*mw+'+', '|'+ ' AFTERLIGHT / CITY MAP '.center(mw)+'|']
    for r in range(mh):
        line=''
        for c in range(mw):
            x,y=min(SIZE-1,int(c*SIZE/mw)),min(SIZE-1,int(r*SIZE/mh))
            ch='#' if world.city.walls[y][x]>=0 else {'r':'.','p':' ','g':',','w':'~','b':'='}[world.city.tiles[y][x]]
            for i,p in enumerate(world.city.landmarks):
                if int(p.x*mw/SIZE)==c and int(p.y*mh/SIZE)==r: ch=str(i+1)
            target=getattr(world,'journal_target',None)
            if target is not None and int(target[0]*mw/SIZE)==c and int(target[1]*mh/SIZE)==r:
                ch='X'
            if int(world.x*mw/SIZE)==c and int(world.y*mh/SIZE)==r: ch='@'
            line+=ch
        lines.append('|'+line+'|')
    lines.append('+'+'-'*mw+'+')
    for a,b in ((0,1),(2,3),(4,5)):
        left=f'{a+1} {world.city.landmarks[a].name}'
        right=f'{b+1} {world.city.landmarks[b].name}'
        lines.append((left.ljust(mw//2)+right)[:mw])
    lines.append(' @ You   X Journal target   # Buildings   ~ Water   M Close')
    overlay(buf,lines,fg=(131,207,188))


def help_overlay(buf):
    overlay(buf,[
        '+------------------------------------------------------+',
        '|           G L Y P H   C I T Y : AFTERLIGHT             |',
        '|                 Take the long way home.              |',
        '|                                                      |',
        '|  W A S D    Walk / strafe       Q E / arrows   Turn    |',
        '|  Shift      Sprint             L              Mouse   |',
        '|  R          Rain on / off      N              Weather |',
        '|  Y          Skip three hours   T              Clock   |',
        '|  F          Pocket lantern     Space          Pause   |',
        '|  P          Capture photo      J              Album   |',
        '|  K          Travel journal     Enter          Interact|',
        '|  Tab        Mini map           M              Map     |',
        '|  C          Color mode         Home           Return  |',
        '|  H          Close this guide   X / Esc / Ctrl-C Exit  |',
        '|                                                      |',
        '|  Discover six places. No timer. No destination needed.|',
        '+------------------------------------------------------+',
    ])
