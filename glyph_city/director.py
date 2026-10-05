"""Continuous, collision-aware cinematic observation of the living city."""
from copy import copy
from dataclasses import dataclass
import heapq
import math

from .city import SIZE


@dataclass(frozen=True)
class Shot:
    name: str
    start: tuple
    end: tuple
    target: tuple
    eye: float = 1.72
    lens: float = 66.0
    duration: float = 80.0
    orbit: float = 0.0
    pitch: float = -.015


# Dolly moves are deliberately short. Transit between compositions gets its
# own time and does not consume the quiet observation period.
SHOTS = (
    Shot('Afterlight / the long avenue', (60,78), (60,75), (60,48), duration=90, orbit=.055),
    Shot('Willow / by the fountain', (48,56), (48,54.7), (48,47), 1.4, 74, 80, -.075),
    Shot('Lantern Market / evening tables', (60.5,48), (62,48), (72,48), 1.65, 72, 95, .09),
    Shot('Moonwater / reflections', (60,84), (61,84), (46,91.5), 1.6, 76, 100, -.11),
    Shot('Glass Quarter / skyline', (84,36), (84,34), (84,19), 2.0, 80, 85, .07),
    Shot('Copper Lane / warm windows', (24,36), (26,36), (28,29), 1.65, 70, 90, -.085),
    Shot('Moonwater / aboard the night boat', (30,91.5), (48,91.5), (63,85), 2.1, 72, 100, .105),
)


@dataclass(frozen=True)
class Pose:
    x: float
    y: float
    angle: float
    eye: float
    lens: float
    pitch: float = -.015


def ease(t):
    t=max(0.0,min(1.0,t))
    return t*t*t*(t*(t*6-15)+10)


def angle_delta(start, end):
    return (end-start+math.pi)%math.tau-math.pi


def clear_segment(city, a, b):
    """Camera may float above canal water, but never through a facade."""
    count=max(1,math.ceil(math.dist(a,b)/.2))
    for i in range(count+1):
        t=i/count; x=a[0]+(b[0]-a[0])*t; y=a[1]+(b[1]-a[1])*t
        for ox,oy in ((0,0),(.28,0),(-.28,0),(0,.28),(0,-.28)):
            ix,iy=math.floor(x+ox),math.floor(y+oy)
            if not 1<=ix<SIZE-1 or not 1<=iy<SIZE-1 or city.walls[iy][ix]>=0:
                return False
    return True


def camera_route(city, start, goal):
    """A* through open cells, then retain only visible corridor corners."""
    if city is None or clear_segment(city,start,goal):
        return (start,goal)
    origin=(int(start[0]),int(start[1])); dest=(int(goal[0]),int(goal[1]))
    queue=[(math.dist(origin,dest),0.0,origin)]
    costs={origin:0.0}; parents={}
    reached=False
    while queue:
        _,cost,node=heapq.heappop(queue)
        if cost>costs[node]+1e-9: continue
        if node==dest:
            reached=True; break
        for dx,dy in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(-1,1),(1,-1),(-1,-1)):
            nxt=(node[0]+dx,node[1]+dy)
            if not 1<=nxt[0]<SIZE-1 or not 1<=nxt[1]<SIZE-1: continue
            if city.walls[nxt[1]][nxt[0]]>=0: continue
            a=(node[0]+.5,node[1]+.5); b=(nxt[0]+.5,nxt[1]+.5)
            if not clear_segment(city,a,b): continue
            new=cost+math.hypot(dx,dy)
            if new<costs.get(nxt,math.inf):
                costs[nxt]=new; parents[nxt]=node
                heapq.heappush(queue,(new+math.dist(nxt,dest),new,nxt))
    if not reached: return None
    cells=[dest]
    while cells[-1]!=origin: cells.append(parents[cells[-1]])
    points=[start]+[(x+.5,y+.5) for x,y in reversed(cells)]+[goal]
    route=[start]; index=0
    while index<len(points)-1:
        far=index+1
        for candidate in range(len(points)-1,index,-1):
            if clear_segment(city,points[index],points[candidate]):
                far=candidate; break
        if not clear_segment(city,points[index],points[far]): return None
        route.append(points[far]); index=far
    return tuple(route)


def sample_route(points, progress):
    lengths=[math.dist(a,b) for a,b in zip(points,points[1:])]
    total=sum(lengths); distance=max(0.0,min(1.0,progress))*total
    for a,b,length in zip(points,points[1:],lengths):
        if distance<=length:
            t=distance/max(length,1e-9)
            return (a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t)
        distance-=length
    return points[-1]


class Director:
    def __init__(self, index=0):
        self.index=index%len(SHOTS)
        self.elapsed=0.0
        self.held=False
        self.zoom=0.0
        self.subject=None
        self.cycles=0
        self.transition=None
        self.transition_duration=0.0
        self.clock=0.0
        self.subject_since=0.0
        self.next_focus=0.0
        self.subject_route=None
        self._world=None
        self.pose=self._shot_pose()

    @property
    def shot(self):
        return SHOTS[self.index]

    def _shot_pose(self):
        shot=self.shot
        t=ease(self.elapsed/shot.duration)
        x=shot.start[0]+(shot.end[0]-shot.start[0])*t
        y=shot.start[1]+(shot.end[1]-shot.start[1])*t
        heading=math.atan2(shot.target[1]-y,shot.target[0]-x)
        # A very small orbit makes the view feel operated instead of locked
        # to a rail. It returns to neutral at each end of the composition.
        heading += shot.orbit*math.sin(math.pi*2*t)
        pitch=shot.pitch + .012*math.sin(math.pi*t)
        return Pose(x,y,heading,shot.eye,shot.lens,pitch)

    def next(self, world=None):
        return self._switch(1,world)

    def previous(self, world=None):
        return self._switch(-1,world)

    def _switch(self, direction, world=None):
        world=world or self._world
        destination=(self.index+direction)%len(SHOTS)
        goal=SHOTS[destination].start
        # Always capture the actual rendered pose, including a partially
        # completed transition. Repeated manual changes remain continuous.
        start=self.pose
        route=camera_route(world.city if world else None,(start.x,start.y),goal)
        if route is None: return False
        self.index=destination; self.elapsed=0.0; self.subject=None
        self.subject_route=None
        self.cycles+=1
        length=sum(math.dist(a,b) for a,b in zip(route,route[1:]))
        # Keep transfers energetic while still giving the eye one readable
        # beat. Long routes cap at 5.5 seconds instead of taking 20+ seconds.
        self.transition_duration=max(2.0,min(5.5,.9+length/7.0))
        self.transition={'from':start,'route':route,'elapsed':0.0}
        self.next_focus=self.clock+self.transition_duration+12.0
        return True

    def _update_transition(self, dt):
        move=self.transition
        move['elapsed']+=dt
        t=min(1.0,move['elapsed']/self.transition_duration); u=ease(t)
        start=move['from']; goal=self._shot_pose()
        x,y=sample_route(move['route'],u)
        # Explicit shortest-angle interpolation avoids a spin when the look
        # target crosses the camera. Route turns do not jerk the horizon.
        delta=angle_delta(start.angle,goal.angle)
        # Rotate slightly past the new heading, then settle. This gives each
        # cut a deliberate camera-operator feel without an uncontrolled spin.
        sweep=.18*math.sin(math.pi*u)*(1 if delta>=0 else -1)
        self.pose=Pose(x,y,start.angle+delta*u+sweep,
                       start.eye+(goal.eye-start.eye)*u,
                       start.lens+(goal.lens-start.lens)*u,
                       start.pitch+(goal.pitch-start.pitch)*u
                       +.018*math.sin(math.pi*u))
        if t>=1.0: self.transition=None

    def update(self, dt, paused=False, world=None):
        if world is not None: self._world=world
        if paused or self.held: return
        dt=max(0.0,dt); self.clock+=dt
        if self.transition is not None:
            self._update_transition(dt)
            return
        self.elapsed+=dt
        base=self._shot_pose()
        if self.elapsed>=self.shot.duration:
            # Capture the last pose before choosing the next composition.
            self.pose=base
            self.next(world)
            return
        life=getattr(world,'life',None)
        candidate=getattr(life,'focus',None)
        active=bool(candidate and (getattr(candidate,'dialogue','') or
                                   getattr(life,'event_kind','quiet')!='quiet'))
        if (self.subject is None and active and self.clock>=self.next_focus
                and (math.hypot(candidate.x-base.x,candidate.y-base.y)<18
                     or bool(getattr(candidate,'dialogue','')))):
            route=camera_route(world.city,(base.x,base.y),(candidate.x,candidate.y))
            if route:
                self.subject=candidate; self.subject_since=self.clock
                self.subject_route=route
        if self.subject is not None:
            subject=self.subject
            if (self.clock-self.subject_since>22
                    or math.hypot(subject.x-base.x,subject.y-base.y)>32
                    or self.subject_route is None):
                self.subject=None; self.next_focus=self.clock+24
                self.subject_route=None
        target_angle=base.angle
        target_lens=base.lens
        if self.subject is not None:
            target_angle=math.atan2(self.subject.y-base.y,self.subject.x-base.x)
            target_lens=64.0
        # Smooth bounded pan and lens changes for local stories. The camera
        # stays on the authored dolly instead of chasing a distant resident.
        turn=angle_delta(self.pose.angle,target_angle)*(1-math.exp(-dt/2.2))
        turn=max(-dt*.18,min(dt*.18,turn))
        lens=self.pose.lens+(target_lens-self.pose.lens)*(1-math.exp(-dt/3.0))
        camera_x,camera_y=base.x,base.y
        if self.subject is not None and self.subject_route:
            # A restrained 10% dolly gives a live exchange a sense of focus;
            # the route was collision-checked and the blend takes five seconds.
            blend=min(.10,max(0.0,(self.clock-self.subject_since)/50.0))
            camera_x,camera_y=sample_route(self.subject_route,blend)
        self.pose=Pose(camera_x,camera_y,self.pose.angle+turn,base.eye,lens)

    @property
    def exposure(self):
        return 1.0

    def view(self, world):
        # Idempotent: audio and rendering receive exactly the same camera
        # pose, however often either calls view() within a frame.
        view=copy(world); pose=self.pose
        view.x,view.y=pose.x,pose.y
        view.angle=pose.angle; view.pitch=pose.pitch; view.bob=0.0
        view.eye_height=pose.eye
        view.camera_fov=max(45,min(90,pose.lens+self.zoom))
        view.camera_transition=self.transition is not None
        view.shot_name=self.shot.name
        if self.subject is not None:
            view.shot_name=f'{self.subject.name} / {self.subject.role} / {self.subject.activity}'
        view.interaction_hint=''; view.toast=''; view.scene_id='afterlight'; view.lantern=False
        return view
