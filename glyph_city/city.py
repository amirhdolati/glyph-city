"""Deterministic city layout, landmarks, and walking simulation."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

SIZE = 120
AVENUES = (12, 36, 60, 84, 108)
WEATHER = ('CLEAR', 'RAIN', 'STORM', 'MIST')
MATERIALS = ((181, 108, 81), (107, 151, 153), (195, 176, 134),
             (123, 134, 160), (161, 118, 141), (123, 153, 124))
SHOPS = ('CAFE', 'BOOKS', 'JAZZ', 'FLORA', 'HOTEL', 'RAMEN', 'VINYL', 'BAKERY',
         'BAR', 'LOUNGE', '18+')
NEONS = ((255, 169, 99), (102, 229, 218), (245, 133, 181), (180, 171, 255))


@dataclass
class Building:
    x0: int
    y0: int
    x1: int
    y1: int
    stories: int
    color: tuple
    sign: str
    neon: tuple
    seed: int

    @property
    def height(self):
        return self.stories * 2.8 + .35


@dataclass
class Prop:
    x: float
    y: float
    kind: str
    color: tuple = (190, 170, 140)
    phase: float = 0.0
    route: tuple = ()
    speed: float = 0.0
    name: str = ''
    activity: str = ''
    umbrella: bool = False
    role: str = ''
    dialogue: str = ''


@dataclass
class Landmark:
    x: float
    y: float
    name: str
    description: str


class City:
    def __init__(self, seed=17):
        self.seed = seed
        self.rng = random.Random(seed)
        self.tiles = [['g'] * SIZE for _ in range(SIZE)]
        self.walls = [[-1] * SIZE for _ in range(SIZE)]
        self.buildings = []
        self.props = []
        self.glow = [[0.0] * SIZE for _ in range(SIZE)]
        self.landmarks = [
            Landmark(48, 50, 'Willow Gardens', 'A fountain, old trees, and a quiet place to breathe.'),
            Landmark(72, 48, 'Lantern Market', 'Tea stalls and little shops that glow after sunset.'),
            Landmark(24, 36, 'Copper Lane', 'Brick facades, bookshops, and the smell of coffee.'),
            Landmark(60, 85, 'Moonwater Canal', 'Watch the city lights drift across the water.'),
            Landmark(84, 24, 'Glass Quarter', 'Tall blue towers beneath a slowly changing sky.'),
            Landmark(60, 60, 'Afterlight Crossing', 'Every long walk starts somewhere.'),
        ]
        self._layout()
        self.obstacles = {}
        radii={'tree':.3,'lamp':.1,'bench':.3,'fountain':.8,'flowers':.25,'stall':.65}
        for p in self.props:
            if p.kind in radii:
                self.obstacles.setdefault((int(p.x),int(p.y)),[]).append((p.x,p.y,radii[p.kind]))

    def _building(self, x0, y0, x1, y1, stories=None, sign=None):
        if x1 <= x0 or y1 <= y0:
            return
        if any(self.tiles[y][x] == 'w' for y in range(y0, y1) for x in range(x0, x1)):
            return
        rng = self.rng
        stories = stories or rng.choice((2, 2, 3, 3, 4, 5))
        if x0 > 80 and y0 < 40:
            stories += 2
        b = Building(x0, y0, x1, y1, stories, rng.choice(MATERIALS),
                     sign or rng.choice(SHOPS), rng.choice(NEONS), rng.randrange(10000))
        index = len(self.buildings)
        self.buildings.append(b)
        for y in range(y0, y1):
            for x in range(x0, x1):
                self.walls[y][x] = index

    def _layout(self):
        rng = self.rng
        for y in range(SIZE):
            for x in range(SIZE):
                distance = min(min(abs(x-a) for a in AVENUES), min(abs(y-a) for a in AVENUES))
                self.tiles[y][x] = 'r' if distance <= 2 else 'p' if distance <= 4 else 'g'
                if 88 <= y <= 94:
                    self.tiles[y][x] = 'b' if any(abs(x-a) <= 4 for a in AVENUES) else 'w'
                elif 85 <= y <= 97:
                    self.tiles[y][x] = 'p' if distance > 2 else 'r'

        for by in (-12,) + AVENUES:
            for bx in (-12,) + AVENUES:
                x0, x1 = max(2, bx+5), min(SIZE-2, bx+20)
                y0, y1 = max(2, by+5), min(SIZE-2, by+20)
                if (bx, by) == (36, 36):
                    for y in range(y0, y1):
                        for x in range(x0, x1):
                            self.tiles[y][x] = 'p' if abs(x-48) <= 1 or abs(y-48) <= 1 else 'g'
                    for x, y in ((43,43),(53,43),(43,53),(53,53),(45,42),(51,42),(45,54),(51,54)):
                        self.props.append(Prop(x+.5, y+.5, 'tree'))
                    self.props.extend((Prop(48,48,'fountain'), Prop(45,46,'bench'),
                                       Prop(51,50,'bench'), Prop(46,51,'flowers')))
                    continue
                if (bx, by) == (60, 36):
                    for y in range(y0, y1):
                        for x in range(x0, x1): self.tiles[y][x] = 'p'
                    for x, sign in ((65,'TEA'), (70,'RAMEN'), (75,'VINYL')):
                        self._building(x,41,x+4,46,1,sign)
                        self._building(x,51,x+4,56,2,rng.choice(SHOPS))
                        self.props.append(Prop(x+1,49,'stall',rng.choice(NEONS)))
                    continue
                mx, my = (x0+x1)//2, (y0+y1)//2
                for xa, xb in ((x0,mx-1),(mx+1,x1)):
                    for ya, yb in ((y0,my-1),(my+1,y1)):
                        self._building(xa,ya,xb,yb)
                for y in range(y0,y1):
                    for x in range(x0,x1):
                        if self.walls[y][x] < 0 and self.tiles[y][x] == 'g':
                            self.tiles[y][x] = 'p'

        # Tree-lined promenades, warm lamps, and flowers along the sidewalks.
        for a in AVENUES:
            for p in range(7, SIZE-5, 10):
                for x, y in ((a-3.5,p+.5),(p+.5,a+3.5)):
                    if not self.solid(x,y):
                        self.props.append(Prop(x,y,'lamp'))
                        self._light(x,y)
            for p in range(18, SIZE-5, 24):
                x, y = a+3.7, p+.5
                if not self.solid(x,y): self.props.append(Prop(x,y,'tree'))
        for x in range(5,SIZE-5,8):
            if all(abs(x-a)>4 for a in AVENUES):
                self.props.extend((Prop(x,86.5,'rail'),Prop(x,96.5,'rail')))
        for x, y in ((57,57),(63,57),(57,63),(63,63)):
            self.props.append(Prop(x,y,'flowers'))
        for _ in range(32):
            a = rng.choice(AVENUES)
            y = rng.uniform(5,SIZE-5)
            x = a + rng.choice((-3.3,3.3))
            self.props.append(Prop(x,y,'person',rng.choice(NEONS),rng.random()*100,
                                   (x,5.5,x,SIZE-5.5),rng.uniform(.35,.7)))
        for a in (12,60,108):
            for lane in (-1,1):
                self.props.append(Prop(a+lane, rng.uniform(5,SIZE-5), 'car',
                                       rng.choice(NEONS), rng.random()*100,
                                       (a+lane,3,a+lane,SIZE-3), lane*2.3))
        self.props.append(Prop(44,91.5,'boat',(120,200,212),12,(5,91.5,115,91.5),.8))

    def _light(self, x, y):
        for yy in range(max(0,int(y)-5),min(SIZE,int(y)+6)):
            for xx in range(max(0,int(x)-5),min(SIZE,int(x)+6)):
                k = max(0,1-math.hypot(xx+.5-x,yy+.5-y)/5)
                self.glow[yy][xx] = max(self.glow[yy][xx],k*k)

    def solid(self, x, y):
        if not 1 <= x < SIZE-1 or not 1 <= y < SIZE-1:
            return True
        ix, iy = int(x), int(y)
        return self.walls[iy][ix] >= 0 or self.tiles[iy][ix] == 'w'

    def walkable(self, x, y):
        if any(self.solid(x+dx,y+dy) for dx,dy in ((.24,0),(-.24,0),(0,.24),(0,-.24))):
            return False
        ix,iy=int(x),int(y)
        for yy in range(iy-1,iy+2):
            for xx in range(ix-1,ix+2):
                for px,py,radius in self.obstacles.get((xx,yy),()):
                    if (px-x)**2+(py-y)**2<(radius+.24)**2: return False
        return True

    def district(self, x, y):
        if y > 80: return 'MOONWATER / RIVERSIDE'
        if 39<x<57 and 39<y<57: return 'WILLOW GARDENS'
        if 63<x<81 and 39<y<57: return 'LANTERN MARKET'
        if x>80 and y<40: return 'THE GLASS QUARTER'
        if x<40: return 'COPPER LANE / OLD TOWN'
        return 'AFTERLIGHT / GRAND AVENUE'


@dataclass
class World:
    city: City
    x: float = 60.0
    y: float = 78.0
    angle: float = -math.pi / 2
    pitch: float = 0.0
    clock: float = 17.2
    weather: int = 0
    time: float = 0.0
    velocity_x: float = 0.0
    velocity_y: float = 0.0
    distance: float = 0.0
    bob: float = 0.0
    rain: float = 0.0
    wet: float = 0.0
    cloud: float = .15
    paused: bool = False
    clock_running: bool = True
    lantern: bool = False
    visited: set = field(default_factory=set)
    story_flags: set = field(default_factory=set)
    event_flags: set = field(default_factory=set)
    scene_id: str = 'afterlight'
    toast: str = 'Welcome to Afterlight. Take the long way home.'
    toast_until: float = 8.0
    observing: bool = False
    life: object = field(default=None,repr=False,compare=False)
    show_names: bool = False
    season: str = 'summer'
    camera_bob_enabled: bool = True
    night_contrast: float = 1.0
    storm_flash_enabled: bool = True

    def message(self, text):
        self.toast, self.toast_until = text, self.time + 5

    def update(self, dt, keys, sprint=False):
        if not self.paused:
            self.time += dt
            if self.clock_running: self.clock = (self.clock + dt/30) % 24
            self.rain += ((0,.65,1,0)[self.weather]-self.rain)*min(1,dt*1.8)
            self.cloud += ((.15,.8,1,.65)[self.weather]-self.cloud)*min(1,dt*.7)
            self.wet += (self.rain-self.wet)*min(1,dt*(.4 if self.rain>self.wet else .045))
            for p in self.city.props:
                if p.route:
                    x0,y0,x1,y1 = p.route
                    span = math.hypot(x1-x0,y1-y0)
                    offset = (self.time*p.speed+p.phase) % (2*span)
                    progress = (offset if offset<span else 2*span-offset)/span
                    p.x = x0 + (x1-x0)*progress
                    p.y = y0 + (y1-y0)*progress
            if self.life is not None:
                self.life.update(self,dt)
        if self.observing:
            self.velocity_x=self.velocity_y=self.bob=0
            return
        self.angle += (('e' in keys)-('q' in keys))*dt*1.65
        if self.paused:
            self.velocity_x=self.velocity_y=0
            return
        forward = ('w' in keys)-('s' in keys)
        strafe = ('d' in keys)-('a' in keys)
        speed = 5.0 if sprint else 2.8
        norm = max(1,math.hypot(forward,strafe))
        ca, sa = math.cos(self.angle), math.sin(self.angle)
        target_x = (ca*forward-sa*strafe)*speed/norm
        target_y = (sa*forward+ca*strafe)*speed/norm
        if self.scene_id != 'afterlight':
            self.x=max(2.0,min(16.0,self.x+target_x*dt))
            self.y=max(2.0,min(10.0,self.y+target_y*dt))
            self.velocity_x=self.velocity_y=0
            return
        k = 1-math.exp(-dt*12)
        self.velocity_x += (target_x-self.velocity_x)*k
        self.velocity_y += (target_y-self.velocity_y)*k
        ox,oy = self.x,self.y
        # Substeps keep fast movement from crossing walls after a slow frame.
        steps = max(1,math.ceil(math.hypot(self.velocity_x,self.velocity_y)*dt/.15))
        for _ in range(steps):
            nx = self.x+self.velocity_x*dt/steps
            if self.city.walkable(nx,self.y): self.x=nx
            ny = self.y+self.velocity_y*dt/steps
            if self.city.walkable(self.x,ny): self.y=ny
        moved = math.hypot(self.x-ox,self.y-oy)
        self.distance += moved
        self.bob = (math.sin(self.distance*6)*min(.035,moved/max(dt,.001)*.012)
                    if self.camera_bob_enabled else 0.0)
        for index, landmark in enumerate(self.city.landmarks):
            if index not in self.visited and math.hypot(self.x-landmark.x,self.y-landmark.y)<3.5:
                self.visited.add(index)
                self.message(f'DISCOVERED {landmark.name}  /  {landmark.description}')
