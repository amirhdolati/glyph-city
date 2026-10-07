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
    # Four-level steps retain dark gradients without excessive ANSI churn.
    return ch, (fg[0]&252,fg[1]&252,fg[2]&252), (bg[0]&252,bg[1]&252,bg[2]&252)


ART = {
    'tree': (('   .-oo-.   ',' .o*oooo*o. ','(ooo*oooooo)'," `oo*ooo*-' ",'    Y|     ','    ||     ','   /__\\    '),2.6,4.2),
    'lamp': (('  ___  ',' /___\\ ',' | o | ','  \\|/  ','   |   ','   |   ','   |   ','  _|_  '),.75,3.8),
    'bench': ((' _______ ','|=======|','|_______|',' ||   || '),1.9,.9),
    'flowers': ((' * . * ','\\|/*|/','[=====]',' \\___/ '),1.1,.85),
    'fountain': (('    .    ','  . | .  ',' . \\|/ . ','  \\ | /  ',' ~~~|~~~ ','(=======)',' \\_____/ '),2.8,2.3),
    'rail': (('___________','| | | | | |','|_|_|_|_|_|'),4,.9),
    'stall': (('  /=====\\  ',' /_|_|_|_\\ ',' |  TEA  | ',' | c c c | ',' |=======| ',' | |   | | '),2.6,2.2),
    # People use a wider silhouette so they remain legible in rain and at
    # terminal sizes where a one-column body disappears into facade texture.
    'person': (('  o  ',' /|\\ ',' /|\\ ',' / \\ '),.86,2.05),
    'car': (('   _____   ','  /__|__\\  ',' /_______\\ ','|O==[ ]==O|',' \\_______/ ','  []   []  '),1.8,1.35),
    'boat': (('     |      ','  ___|___   ',' | [] [] |  ','_|_______|_ ','\\_________/ ',' ~-~-~-~-~  '),3.5,1.5),
}

# The few marks that identify an object survive when its projected size is
# too small for the detailed drawing. These are actual silhouettes, not dots.
COMPACT_ART = {
    'tree': (' ,^, ', '(;*;)', '  Y  ', ' /|\\ '),
    'lamp': ('[_]', ' | ', '_|_'),
    'bench': ('[===]', ' |_| '),
    'flowers': ('*;*', '[_]'),
    'fountain': (' \\|/ ', '(~~~)', ' \\_/ '),
    'rail': ('=====', '| | |'),
    'stall': ('/===\\', '|TEA|', '|___|'),
    'car': ('/[_]\\', 'O===O', '[] []'),
    'boat': (' _|_ ', '|[]|_', '\\___/'),
}

# Close views use more authored information, rather than magnifying the
# seven-row crown or repeating the same bench slat across several rows.
DETAIL_ART = {
    'tree': (
        '        .--.         ',
        '    .-o*;.o;-.       ',
        '  .;o;:*o;.*o;-.     ',
        ' .o*;o.;o:;o.*o;.    ',
        '(;o.;*o;:o;.;o*;o)   ',
        '(o;:*o.;o:*;o.;*;.)  ',
        ' `o;.;o*;o.;*o;:o;\'  ',
        '  `-o;:*o.;o;*o-\'    ',
        '     `-;\\|/;-\'      ',
        '        \\|/          ',
        '         ||          ',
        '         |:          ',
        '         ||          ',
        '        /|\\          ',
        '      _/___\\_        ',
    ),
    'bench': (
        ' .-----------------. ',
        ' |=================| ',
        ' |-----------------| ',
        ' |=================| ',
        '/|_________________|\\',
        '|___________________|',
        '  ||             ||  ',
        ' _||_           _||_ ',
    ),
    'flowers': (
        '   *     .    *   ',
        ' . |  *  | . / . ',
        '  \\| / \\|/|/ /  ',
        '   \\|/  |/ |/   ',
        ' .--------------. ',
        ' |==============| ',
        '  \\ : . : . : /  ',
        '   \\_________/   ',
    ),
    'fountain': (
        '          .          ',
        '       .  |  .       ',
        '     .  \\ | /  .     ',
        '    .    \\|/    .    ',
        '   .   .--|--.   .   ',
        '       \\__|__/       ',
        '    .     |     .    ',
        '  .    .  |  .    .  ',
        ' .-----------------. ',
        '( ~ ~ ~ ~ | ~ ~ ~ ~ )',
        ' \\=================/ ',
        '  \\_______________/  ',
    ),
}

PROP_NAMES = {'tree':'Tree / leafy canopy', 'lamp':'Street lamp',
              'bench':'Wooden bench', 'flowers':'Flower planter',
              'fountain':'Fountain', 'rail':'Canal railing',
              'stall':'Tea stall', 'car':'Car', 'boat':'Canal boat'}
GROUND_NAMES = {'r':'Road / asphalt', 'p':'Sidewalk / paving stones',
                'g':'Grass', 'b':'Bridge / wooden deck', 'w':'Canal / water'}
SHOP_NAMES = {'CAFE':'Cafe', 'BAKERY':'Bakery', 'RAMEN':'Ramen restaurant',
              'TEA':'Tea shop', 'BOOKS':'Bookshop', 'VINYL':'Record shop',
              'FLORA':'Florist', 'HOTEL':'Hotel', 'JAZZ':'Jazz club',
              'BAR':'Bar', 'LOUNGE':'Lounge', '18+':'Nightclub'}


def sprite_character(art, x, y, width, height):
    """Scale strokes, but draw eyes, leaves and lettering only once per cell.

    A slash becomes a diagonal through its enlarged cell instead of a block
    of //////. Thin rails and poles keep their single-character weight.
    """
    aw=max(map(len,art)); ah=len(art)
    u=x*aw/width; v=y*ah/height
    ac=min(aw-1,max(0,int(u))); ar=min(ah-1,max(0,int(v)))
    ch=art[ar][ac] if ac<len(art[ar]) else ' '
    cw,chh=width/aw,height/ah
    if cw>1.0:
        center=(ac+.5)*cw
        if ch in '/\\':
            center=(ac+(1-(v-ar) if ch=='/' else v-ar))*cw
        if ch not in (' ','-','_','=') and not -.5<=x-center<.5:
            return ' ',ar
    if chh>1.0 and ch not in (' ','|','/', '\\',':'):
        if not -.5<=y-(ar+.5)*chh<.5:
            return ' ',ar
    return ch,ar

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
        self._sun_cache = {}
        self._sun_key = None

    def _light_at(self, x, y):
        """Bilinear lamp falloff: no square patches as the camera drifts."""
        x=max(0.0,min(SIZE-1.001,x-.5)); y=max(0.0,min(SIZE-1.001,y-.5))
        ix,iy=int(x),int(y); u,v=x-ix,y-iy
        grid=self.city.glow
        return ((grid[iy][ix]*(1-u)+grid[iy][ix+1]*u)*(1-v)
                +(grid[iy+1][ix]*(1-u)+grid[iy+1][ix+1]*u)*v)

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
        sun_key=(id(city),round(world.clock*10))
        if sun_key!=self._sun_key:
            self._sun_key=sun_key; self._sun_cache.clear()
        sun_az=(world.clock-6)/24*TAU
        self.sun_direction=(math.cos(sun_az),math.sin(sun_az))
        self.sun_slope=max(.18,elevation*.9)
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
        self._labels = []
        self._sprite_owner = [[None]*cols for _ in range(rows)]
        self._emission = []
        ground_tiles = [[None]*cols for _ in range(rows)]
        ground_coords = [[None]*cols for _ in range(rows)]
        ray_hits = []
        top = mix((4,8,22),(52,92,132),day)
        low = mix((14,25,43),(169,192,206),day)
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
                    density=max(0.0,min(1.0,(cloud-(1.1-world.cloud*.75))*.85))
                    density*=max(0.0,1-((ratio-.47)/.34)**2)
                    if density>0:
                        # Smooth cloud density avoids hard rectangular banks.
                        cloud_color=mix((54,68,88),(207,215,218),day)
                        cbg=mix(bg,cloud_color,density*(.20+.18*world.cloud))
                        fg=mix(cbg,cloud_color,.22)
                        if .05<density<.16 and grain(int(az*90),int(ratio*40),city.seed)%7==0:
                            ch='~'
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
            ray_hits.append(hits)
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
                    if emits and self.night>.15:
                        self._emission.append((r,c,dist,fg,.035))
        self._roofs(rays,ray_hits)
        self._reflections(rays,ray_hits,ground_tiles,ground_coords)
        self._building_edges()
        self._signs(ca,sa)
        self._contact_shadows(ca,sa,ground_tiles)
        for prop in sorted(city.props,key=lambda p: -((p.x-world.x)**2+(p.y-world.y)**2)):
            self._sprite(prop,ca,sa)
        self._halation()
        self._weather()
        self._grade()
        self._draw_labels()
        if getattr(world,'identify',False):
            self._identify_overlay(ray_hits,ground_tiles)
        if minimap: self._minimap()
        return buf

    def _roofs(self, rays, hits):
        """Intersect roof planes so elevated shots see solid buildings."""
        if self.eye<=3.15: return
        for c,(dx,dy) in enumerate(rays):
            for entry,_,bid,_,_ in hits[c]:
                b=self.city.buildings[bid]
                if b.height>=self.eye: continue
                start=max(0,math.ceil(self.horizon-.5))
                end=min(self.rows,math.ceil(self.horizon+(self.eye-b.height)*self.fy/entry))
                for r in range(start,end):
                    offset=r+.5-self.horizon
                    if offset<=0: continue
                    distance=(self.eye-b.height)*self.fy/offset
                    if distance>=self.depth[r][c]: continue
                    x=self.world.x+dx*distance; y=self.world.y+dy*distance
                    if not (b.x0<=x<b.x1 and b.y0<=y<b.y1): continue
                    edge=min(x-b.x0,b.x1-x,y-b.y0,b.y1-y)
                    ch='_' if edge<.18 else '-' if y%1.8<.075 else '.' if grain(int(x*3),int(y*3),b.seed)%19==0 else ' '
                    color=mix(b.color,(77,95,112),.65)
                    bg=scale(color,.32+.48*self.day)
                    fg=scale(color,.65+.5*self.day)
                    fog=fog_factor(distance,self.visibility)
                    self.buffer[r][c]=cell(ch,mix(fg,self.fog,fog),mix(bg,self.fog,fog*.65))
                    self.depth[r][c]=distance; self.surface[r][c]=bid

    def _halation(self):
        """A bounded glow around lights, clipped by foreground geometry."""
        if self.night<.15: return
        glow={}
        for r,c,z,color,amount in self._emission:
            if self.depth[r][c]<z-.12: continue
            for dy,dx,falloff in ((0,-1,1),(0,1,1),(-1,0,.7),(1,0,.7),
                                  (0,-2,.35),(0,2,.35)):
                y,x=r+dy,c+dx
                if not (0<=x<self.cols and 0<=y<self.rows): continue
                if self.depth[y][x]<z-.35: continue
                strength=amount*falloff*self.night
                prior=glow.get((y,x))
                if prior is None or strength>prior[0]: glow[y,x]=(strength,color)
        for (y,x),(amount,color) in glow.items():
            ch,fg,bg=self.buffer[y][x]
            self.buffer[y][x]=cell(ch,mix(fg,color,amount),mix(bg,color,amount))

    def _contact_shadows(self, ca, sa, tiles):
        """Small soft ground shadows anchor props without obscuring paving."""
        radii={'tree':1.15,'lamp':.28,'bench':.9,'flowers':.5,
               'fountain':1.25,'stall':1.15,'person':.28,'car':.9}
        for p in self.city.props:
            radius=radii.get(p.kind)
            if radius is None: continue
            dx,dy=p.x-self.world.x,p.y-self.world.y
            z=dx*ca+dy*sa
            if z<1 or z>28: continue
            x=self.cols/2+(-dx*sa+dy*ca)*self.fx/z
            y=self.horizon+self.eye*self.fy/z
            rx=max(1.,radius*self.fx/z)
            ry=max(.6,self.eye*self.fy*radius/(z*z))
            for r in range(max(0,math.floor(y-ry)),min(self.rows,math.ceil(y+ry))):
                for c in range(max(0,math.floor(x-rx)),min(self.cols,math.ceil(x+rx))):
                    if self.surface[r][c]>=0 or tiles[r][c] in (None,'w'): continue
                    d=((c+.5-x)/rx)**2+((r+.5-y)/ry)**2
                    if d>=1: continue
                    ch,fg,bg=self.buffer[r][c]
                    shade=1-(1-d)*(.12+.06*self.day)
                    self.buffer[r][c]=cell(ch,scale(fg,shade),scale(bg,shade))

    def _identify_overlay(self, ray_hits, ground_tiles):
        """Give the viewer a quiet readable key for the current composition."""
        center=min(self.cols-1,max(0,self.cols//2))
        objects=[]
        if ray_hits and ray_hits[center]:
            _,_,bid,*_=ray_hits[center][0]
            building=self.city.buildings[bid]
            objects.append(SHOP_NAMES.get(building.sign,building.sign.title()))
        row=min(self.rows-1,max(0,int(self.horizon+5)))
        tile=ground_tiles[row][center] if ground_tiles else None
        if tile in GROUND_NAMES:
            objects.append(GROUND_NAMES[tile])
        if objects:
            text='  /  '.join(objects)
        else:
            text='Look around: named objects are highlighted'
        line=(' B IDENTIFY  |  '+text+'  |  B closes ').center(self.cols)
        overlay(self.buffer,[line[:self.cols]],0,0,(228,220,172),(18,25,31))

    def _draw_labels(self):
        """Label only visible objects and leave room between captions."""
        occupied=set()
        visible={owner for row in self._sprite_owner for owner in row if owner is not None}
        labels=(item for item in sorted(self._labels) if item[-1] in visible)
        count=0
        for z,sx,top,label,speech,owner in labels:
            if count>=8: break
            text=label[:max(1,min(32,self.cols-2))]
            x=max(1,min(self.cols-len(text)-1,round(sx-len(text)/2)))
            for y in (math.floor(top)-1,math.floor(top)-2):
                if not 2<=y<self.rows-1: continue
                cells={(xx,yy) for yy in (y-1,y,y+1)
                       for xx in range(max(0,x-1),min(self.cols,x+len(text)+1))}
                if cells & occupied: continue
                if any(self.depth[y][xx]<z-.1 for xx in range(x,x+len(text))): continue
                overlay(self.buffer,[text],x,y,(215,226,210),(17,27,33))
                occupied.update(cells)
                count+=1
                if speech and y>2:
                    quote=('"'+speech+'"')[:self.cols-2]
                    qx=max(1,min(self.cols-len(quote)-1,round(sx-len(quote)/2)))
                    if all(self.depth[y-1][xx]>=z-.1 for xx in range(qx,qx+len(quote))):
                        overlay(self.buffer,[quote],qx,y-1,(242,209,161),(17,27,33))
                        occupied.update((xx,yy) for yy in (y-2,y-1,y) for xx in range(qx,qx+len(quote)))
                break

    def _reflections(self, rays, hits, tiles, coords):
        """Trace the city from a camera mirrored below the ground plane.

        Reuse the wall rays; the reflected height is sampled independently
        of the visible facade, so even offscreen windows reflect correctly.
        Water always reflects. Pavement reveals the reflection in puddles.
        """
        w=self.world
        for r in range(max(0,int(self.horizon)+1),self.rows):
            slope=(r+.5-self.horizon)/self.fy
            for c in range(self.cols):
                tile=tiles[r][c]
                if self.surface[r][c]>=0 or tile not in REFLECTION_MASK: continue
                wet=1.0 if tile=='w' else w.wet
                if wet<.04 or coords[r][c] is None: continue
                x,y=coords[r][c]
                wave=math.sin(y*3.2+x*.65-w.time*.65)
                ripple=.5+.5*wave
                pool=.5+.28*math.sin(x*1.7+y*.47)+.22*math.sin(y*2.1-x*.6)
                strength=REFLECTION_MASK[tile]*wet
                strength*=.52+.24*ripple if tile=='w' else .08+.62*pool*pool
                # Water bends the reflected columns; pavement stays still.
                rc=max(0,min(self.cols-1,c+round(wave*1.2))) if tile=='w' else c
                dx,dy=rays[rc]
                ground_dist=self.depth[r][c]
                for dist,side,bid,hx,hy in hits[rc]:
                    if dist<ground_dist-.05: continue
                    b=self.city.buildings[bid]
                    z=slope*dist-self.eye
                    if z>b.height: continue
                    if z<0: break
                    u=(hy-b.y0 if dx>0 else b.y1-hy) if side==0 else (b.x1-hx if dy>0 else hx-b.x0)
                    span=b.y1-b.y0 if side==0 else b.x1-b.x0
                    ch,fg,bg,emits=self._facade(b,u,z,span,side,dist)
                    if .35<z<2.08 and .22<u<span-.22:
                        fg=mix((241,183,112),b.neon,.25)
                        bg=scale(fg,.22); emits=True
                    old,ofg,obg=self.buffer[r][c]
                    alpha=strength*(.64 if emits else .28)*(1-min(.65,dist/110))
                    tint=mix(bg,fg,.5 if emits else .15)
                    mark=old
                    if old in (' ','.',':','~','-') and emits and strength>.13:
                        mark='~' if tile=='w' and ripple>.58 else '-' if pool>.52 else '.'
                    self.buffer[r][c]=cell(mark,mix(ofg,fg,alpha),mix(obg,tint,alpha*.85))
                    break

    def _grade(self):
        """A quiet edge falloff keeps attention inside the composition."""
        for r,row in enumerate(self.buffer):
            vy=((r+.5)/self.rows-.48)*2
            for c,(ch,fg,bg) in enumerate(row):
                vx=((c+.5)/self.cols-.5)*2
                vignette=1-.12*max(0,vx*vx+vy*vy-.35)
                row[c]=cell(ch,scale(fg,vignette),scale(bg,vignette))

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
        light = local_light(self._light_at(x,y),night,w.lantern and dist<9)
        bases = {'r':(43,53,65),'p':(125,122,113),'g':(45,91,68),'b':(119,103,82),'w':(34,84,103)}
        base = bases[tile]
        # Material motifs stay in world space; their contrast fades with
        # distance rather than filling the horizon with tiny texture glyphs.
        # Keep a readable middle-distance band: ASCII fades gradually through
        # the street instead of disappearing immediately after the foreground.
        detail=max(0.0,min(1.0,(34.0-dist)/20.0))
        motif=grain(math.floor(x*2),math.floor(y*2),self.city.seed)
        joint=min(.18,max(.055,dist/max(self.fx,1.0)*.55))
        relief,ridge=terrain_relief(x,y,self.city.seed)
        # A soft directional key light makes the relief readable without
        # turning every foreground cell into a bright outline.
        sun_angle=(w.clock-6.0)/24.0*TAU
        key=math.cos(x*1.35+y*.72+sun_angle)+math.sin(x*.48-y*1.08-sun_angle*.7)
        relief_light=max(-1.0,min(1.0,key*.5+ridge*.35))
        if tile=='w':
            ripple=math.sin(x*.65+y*.45+w.time*.55)
            bg=mix(scale(base,.19+.65*day),self.fog,.22)
            fg=mix(bg,(115,164,177),.18+.24*max(0,ripple))
            bg=mix(bg,fg,max(0,ripple)*.18)
            # Broad, sparse wave crests leave most of the water quiet.
            if dist<24 and detail>.2:
                ch='~' if ripple>.72 else '-' if ripple>.22 else '.' if ripple<-.72 else ' '
            else:
                ch='~' if dist<34 and ripple>.985 else ' '
        else:
            shade=shadow_band(x,y,self.city.seed)
            sun=self._ground_sun(ix,iy) if day>.2 else 1.
            shade*=.72+.28*sun
            bg=scale(base,(.27+.60*day)*shade)
            fg=scale(base,(.58+.58*day)*shade)
            if sun<1:
                bg=mix(bg,(29,43,61),(1-sun)*day*.18)
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
                py=y%1.2
                px=(x+(math.floor(y/1.2)%2)*1.0)%2.0
                horizontal=py<joint
                vertical=px<joint
                ch='+' if horizontal and vertical else '_' if horizontal else '|' if vertical else ' '
                block=grain(math.floor((x+(math.floor(y/1.2)%2)*1.0)/2.0),
                            math.floor(y/1.2),self.city.seed)
                bg=scale(bg,.97+(block%3)*.03)
                fg=mix(fg,(168,153,122),.18)
                if not (horizontal or vertical) and detail>.25:
                    ch='.' if relief<.18 else ':' if relief>.84 else ' '
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
                if dist<20 and relief>.84 and motif%3==0: ch=':'
                elif dist<18 and relief<.17 and motif%3==0: ch='.'
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
                bg=mix(bg,(117,83,48),min(.58,light*.42))
                fg=mix(fg,(233,182,108),min(.78,light*.68))
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

    def _ground_sun(self, x, y):
        """Cached building shadows give the street a directional light source."""
        key=(x,y)
        if key in self._sun_cache: return self._sun_cache[key]
        sx,sy=self.sun_direction
        light=1.
        for distance in (2,4,7,11,16):
            ix,iy=math.floor(x+.5+sx*distance),math.floor(y+.5+sy*distance)
            if not (0<=ix<SIZE and 0<=iy<SIZE): break
            bid=self.city.walls[iy][ix]
            if bid>=0 and self.city.buildings[bid].height>distance*self.sun_slope:
                light=.15; break
        self._sun_cache[key]=light
        return light

    def _shop_glass(self,b,u,z,span,depth,direction,dist):
        door=abs(u-span/2)
        if door<.44 and z<1.95:
            ch='|' if door>.32 else '_' if z<.5 or z>1.82 else '|' if .20<u-span/2<.26 and .9<z<1.14 else ' '
            return ch,(187,173,139),(19,30,36),False
        panes=max(1,round(span/3))
        pane=span/panes
        seam=min(u%pane,pane-u%pane)
        if seam<.075 or z<.29 or z>2.055:
            return ('|' if seam<.075 else '-',(139,165,167),(25,36,41),False)
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
        reflection=.06+.24*grazing**3
        fg=mix(fg,(131,174,191),reflection)
        bg=mix(bg,self.fog,reflection)
        # Vertical framing and a recessed transom turn an opaque rectangle
        # into a storefront with glass, structural piers and a display sill.
        if seam<.15:
            return '|',scale(b.color,.65+.35*self.day),scale(b.color,.22),False
        if 1.77<z<1.84:
            return '-',scale(b.neon,.42),(27,35,41),False
        # Recessed pane edges and a sill give glass thickness and scale.
        edge=min(1.0,seam/.19,max(0.0,(z-.35)/.18))
        bg=scale(bg,.60+.40*edge)
        if seam<.085:
            ch='|'; fg=(80,111,122); bg=scale(bg,.55)
        elif z<.47:
            ch='_'; fg=(151,134,106); bg=scale(bg,.65)
        elif z>1.94:
            ch='_'; fg=scale(b.neon,.60); bg=scale(bg,.70)
        elif .47<z<.65:
            ch='='; fg=scale(b.neon,.45); bg=scale(bg,.7)
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
        sx,sy=self.sun_direction
        normal=(1 if self.world.y>b.y1 else -1) if side else (1 if self.world.x>b.x1 else -1)
        facing=max(0.,normal*(sy if side else sx))
        shade=(.60+.55*day)*(.77+.33*facing)
        if self.world.lantern: shade+=max(0,1-dist/9)*.38
        base=mix(b.color,(224,153,101),self.sunset*.2)
        base=mix(base,(220,192,149),day*facing*.15)
        base=mix(base,(85,111,140),day*(1-facing)*.16)
        fg,bg=scale(base,shade),scale(base,shade*(.40+.10*day))
        bay=u%1.65; story=int(z/2.8); level=z%2.8
        facade_detail=max(0.0,min(1.0,(42.0-dist)/24.0))
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
                glow=mix((241,183,111),b.neon,.12)
                # Each room has a stable exposure, curtains and a dark sill.
                room_gain=.62+(window_seed%7)*.045
                fg=scale(glow,room_gain)
                bg=scale(glow,(.19+.10*night)*room_gain)
                ch=' '
                if facade_detail>.32:
                    if bay<.49 or bay>1.16:
                        ch='|'; fg=scale(glow,.46); bg=scale(bg,.68)
                    elif level<1.04:
                        ch='_'; fg=scale(glow,.48); bg=scale(bg,.55)
                    elif window_seed%4==0 and .72<bay<1.0 and level<1.50:
                        ch='i'; fg=scale(glow,.23)
                    elif level>1.75:
                        ch='-'; fg=scale(glow,.75)
                    else:
                        ch='+' if abs(bay-.825)<.13 else ':'
                        fg=scale(glow,.75)
                emits=True
            else:
                ch='/' if facade_detail>.48 and abs(bay-.4-level*.18)<.065 else ' '
                fg=mix((63,107,134),self.fog,.25); bg=scale(fg,.26+.045*level)
        elif story==0 and abs(u-span/2)<.42 and z<1.9:
            ch='|' if abs(u-span/2)>.3 else '_' if z<.35 else ' '
            fg=scale(b.neon,.45); bg=(14,18,24)
        else:
            ch=' '
            if facade_detail>.35:
                # Brick courses, stone joints and pilasters follow world
                # coordinates, with quiet mortar rather than random speckle.
                course=int(z/.28)
                if z%.28<.035:
                    ch='-'; fg=mix(bg,fg,.36)
                elif (u+(course%2)*.36)%.72<.045:
                    ch=':'; fg=mix(bg,fg,.32)
                elif grain(int(u*7),int(z*7),b.seed)%7<2:
                    ch='.'; fg=mix(bg,fg,.58)
                if u<.15 or u>span-.15:
                    ch='|'; fg=scale(base,shade*1.18)
                bg=scale(bg,.92+.08*math.sin(u*.7+b.seed))
        if hx is not None and hy is not None and not emits:
            ix,iy=math.floor(hx),math.floor(hy)
            if 0<=ix<SIZE and 0<=iy<SIZE:
                # Street lamps graze only the lower facade. The source stays
                # in world space, so camera motion cannot make it shimmer.
                bounce=local_light(self._light_at(hx,hy),night)*math.exp(-max(0,z)/4)
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
                        self._emission.append((r,c,self.depth[r][c],b.neon,.075))

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
        art,width,height = ART[p.kind]
        projected=height*self.fy/z
        if p.kind!='person' and (lod==0 or projected<len(art)*.72):
            art=COMPACT_ART.get(p.kind,art)
        elif p.kind in DETAIL_ART and projected>=len(DETAIL_ART[p.kind])*.8:
            art=DETAIL_ART[p.kind]
        person_scale=1.0
        close_detail=False
        if p.kind=='person':
            pose=int(self.world.time*2.4+p.phase)%2
            close_detail=projected>=6
            role=getattr(p,'role','')
            activity=getattr(p,'activity','')
            if close_detail:
                art=(' .-. ',' (o) ',' /|\\ ',' |:| ',' / \\ ','_/ \\_')
                width=.90; height=1.95
                # Props remain visible up close, when they matter most.
                if activity in ('reading','sorting books') or role=='bookseller':
                    art=(' .-. ',' (o) ',' /[=]',' | | ',' / \\ ','_/ \\_')
                elif activity=='playing music' or role=='musician':
                    art=(' .-. ',' (o) ',' /|D ',' |/o ',' / \\ ','_/ \\_')
                elif activity=='taking photos' or role=='photographer':
                    art=(' .-. ',' (o) ','-[o]-',' |:| ',' / \\ ','_/ \\_')
                elif role=='courier':
                    art=(' ___ ',' (o) ',' /|[]',' |:[]',' / \\ ','_/ \\_')
                elif role in ('barista','vendor'):
                    art=(' ___ ',' (o) ',' /|c ',' [#] ',' / \\ ','_/ \\_')
                if p.umbrella:
                    art=(' .---. ','/_____\\','   o | ','  /|\\| ','  |:|  ','  / \\  ',' _/ \\_ ')
                    width=1.25; height=2.25
            else:
                art=(' o ','/|\\','/ \\'); width=.72; height=1.85
                if p.umbrella:
                    art=('/^\\',' o|','/| ','/ \\'); width=1.0; height=2.2
                elif activity in ('reading','sorting books'):
                    art=(' o ','[=]','/ \\')
                elif activity=='playing music':
                    art=(' o ','/|D','/ \\')
                elif activity=='taking photos':
                    art=(' o ','[o]','/ \\')
            if activity=='tending flowers' and not p.umbrella:
                art=(' o_','/|/','/ \\'); height=1.2
            elif activity=='walking' and not p.umbrella:
                art=art[:-1]+((' /|' if pose else '|\\ ').center(len(art[-1])),)
            # Near pedestrians keep a readable full silhouette instead of
            # turning into cropped columns as they pass the watch camera.
            person_scale=min(1.0,min(float(len(art)),self.rows*.4)/(height*self.fy/z))
            width*=person_scale; height*=person_scale
        aw=max(map(len,art)); ah=len(art)
        sx=self.cols/2+lateral*self.fx/z
        bottom=self.horizon+self.eye*self.fy/z*person_scale
        pw,ph=width*self.fx/z,height*self.fy/z
        if p.kind=='person':
            # Preserve a single face and accessory instead of repeating eyes.
            pw=min(max(pw,float(aw) if ph>=ah else 3.0 if ph>=2.5 else 1.0),ph*aw/ah*1.1)
        left,top=sx-pw/2,bottom-ph
        if left>=self.cols or left+pw<0: return
        visible=0
        # Sample only pixel centers INSIDE the projected rectangle. Clamping
        # samples outside it duplicated the first row (especially NPC heads).
        for r in range(max(0,math.ceil(top-.5)),min(self.rows,math.ceil(bottom-.5))):
            ar=min(ah-1,max(0,int((r+.5-top)/ph*ah)))
            for c in range(max(0,math.ceil(left-.5)),min(self.cols,math.ceil(left+pw-.5))):
                ac=min(aw-1,max(0,int((c+.5-left)/pw*aw)))
                ch=art[ar][ac] if ac<len(art[ar]) else ' '
                solid=(p.kind=='bench' and ar<ah-2 or
                       p.kind=='fountain' and ar>=ah-3 or
                       p.kind=='flowers' and ar>=ah//2)
                if solid:
                    line=art[ar]
                    solid=len(line)-len(line.lstrip())<=ac<len(line.rstrip())
                if p.kind in ('lamp','car','boat','stall','person','bench','fountain','rail'):
                    ch,_ = sprite_character(art,c+.5-left,r+.5-top,pw,ph)
                if p.kind=='tree' and ar>=(9 if ah==15 else 4 if ah>4 else 2):
                    ch,_ = sprite_character(art,c+.5-left,r+.5-top,pw,ph)
                if (ch==' ' and not solid) or z>self.depth[r][c]+.05: continue
                visible+=1
                color=p.color
                if p.kind=='tree':
                    canopy=ar<(9 if ah==15 else 4 if ah>4 else 2)
                    color=(103,163,109) if canopy else (160,119,77)
                    if canopy:
                        light=.78+.26*(1-ac/max(1,aw-1))+.12*(1-ar/max(1,ah-1))
                        color=scale(color,light)
                elif p.kind=='lamp': color=(255,209,123) if ar<(3 if ah>3 else 1) else (145,160,173)
                elif p.kind=='fountain': color=(128,196,215) if ar<(10 if ah==12 else 5 if ah>3 else 1) else (164,174,181)
                elif p.kind=='bench': color=(175,124,81)
                elif p.kind=='rail': color=(111,135,148)
                elif p.kind=='flowers':
                    color=((238,158,183) if ch in '*.' else (112,167,103)) if ar<(4 if ah==8 else 2) else (171,126,91)
                elif p.kind=='car':
                    color=(235,220,163) if ch in 'Oo' else (99,158,183) if ar==1 else (76,82,95) if ar==ah-1 else p.color
                elif p.kind=='boat':
                    color=(117,191,209) if ar==ah-1 or ch in '[]' else (188,148,101)
                elif p.kind=='stall':
                    color=(241,206,148) if ar==2 else p.color if ar<2 else (179,133,85)
                elif p.kind=='person':
                    role_color=PERSON_COLORS.get(getattr(p,'role',''),p.color)
                    if p.umbrella:
                        # The canopy catches sky light; the body stays a
                        # distinct role color beneath it.
                        color=(mix(role_color,(184,209,217),.35) if ar<(2 if close_detail else 1) else
                               (240,196,156) if ar==(2 if close_detail else 1) else role_color)
                    elif close_detail:
                        color=((48,34,45) if ar==0 else
                               (255,214,175) if ar==1 else role_color)
                    else:
                        color=(255,214,175) if ar==0 else role_color
                luminous=(p.kind=='lamp' and ch in 'oO') or (p.kind=='car' and ch in 'oO')
                factor=(1 if luminous else .94 if p.kind=='person'
                        else min(1.1,.52+.48*self.day+.22*self._light_at(p.x,p.y)))
                fog_amount=.20 if p.kind=='person' else .55
                color=mix(scale(color,factor),self.fog,min(.75,z/self.visibility)*fog_amount)
                bg=self.buffer[r][c][2]
                # Shade the object itself instead of boxing every character
                # in black, which made crowns and faces look like stickers.
                if solid:
                    bg=mix(bg,scale(color,.28 if p.kind=='fountain' else .32),.92)
                elif p.kind=='tree' and canopy:
                    bg=mix(bg,scale(color,.23),.72)
                elif p.kind=='person':
                    bg=mix(bg,scale(color,.18),.65)
                else:
                    bg=mix(bg,scale(color,.16),.40)
                self.buffer[r][c]=cell(ch,color,bg)
                self.depth[r][c]=z
                self._sprite_owner[r][c]=id(p)
                if luminous:
                    self._emission.append((r,c,z,color,.15))
        focus=getattr(getattr(self.world,'life',None),'focus',None)
        identify=getattr(self.world,'identify',False)
        if (visible and not getattr(self.world,'camera_transition',False)
                and ((identify and z<28 and ph>=1.2)
                     or (p is focus and getattr(self.world,'show_names',False)))):
            if p.kind=='person':
                name=p.name or 'Resident'
                detail=p.activity or p.role
                label=name+(' / '+detail if detail else '')
            else:
                label=PROP_NAMES.get(p.kind,p.kind.title())
            self._labels.append((z,sx,top,label,p.dialogue if p is focus else '',id(p)))
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
                # Keep rain from erasing identifying features and sign text.
                if ch not in (' ','.',':','~'): continue
                self.buffer[y][x]=cell('/' if w.weather==2 else '|',mix(fg,(151,181,204),.48),bg)
                if y>self.horizon+2 and i%7==0:
                    self.buffer[y][x]=cell('.',(121,163,183),bg)

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
        '|  B          Identify objects / materials              |',
        '|  C          Color mode         Home           Return  |',
        '|  H          Close this guide   X / Esc / Ctrl-C Exit  |',
        '|                                                      |',
        '|  Discover six places. No timer. No destination needed.|',
        '+------------------------------------------------------+',
    ])
