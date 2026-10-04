"""Cinematic observation without changing the saved player's position."""
from copy import copy
from dataclasses import dataclass
import math
import random


@dataclass(frozen=True)
class Shot:
    name: str
    start: tuple
    end: tuple
    target: tuple
    eye: float = 1.72
    lens: float = 66.0
    duration: float = 42.0


SHOTS = (
    Shot('Afterlight / the long avenue', (60,78), (60,75), (60,48)),
    Shot('Willow / by the fountain', (48,56), (48,54.7), (48,47), 1.4, 74),
    Shot('Lantern Market / evening tables', (60.5,48), (62,48), (72,48), 1.65, 72),
    Shot('Moonwater / reflections', (60,84), (61,84), (46,91.5), 1.6, 76),
    Shot('Glass Quarter / skyline', (84,36), (84,34), (84,19), 2.0, 80),
    Shot('Copper Lane / warm windows', (24,36), (26,36), (28,29), 1.65, 70),
    Shot('Moonwater / aboard the night boat', (30,91.5), (48,91.5), (63,85), 2.1, 72),
)


class Director:
    def __init__(self, index=0):
        self.index=index % len(SHOTS)
        self.elapsed=0.0
        self.held=False
        self.zoom=0.0
        self.rng=random.Random(817)
        self.subject=None
        self.anchor=None
        self.follow_offset=(6.0,0.0)
        self.follow_from=None
        self.follow_started=0.0
        self.cycles=0

    @property
    def shot(self):
        return SHOTS[self.index]

    def next(self):
        self.index=(self.index+1)%len(SHOTS)
        self.elapsed=0.0
        self.subject=None
        self.anchor=None
        self.follow_from=None
        self.cycles+=1

    def update(self, dt, paused=False, world=None):
        if paused or self.held:
            return
        changed=False
        self.elapsed+=max(0.0,dt)
        while self.elapsed>=self.shot.duration:
            remainder=self.elapsed-self.shot.duration
            self.next()
            self.elapsed=remainder
            changed=True
        if world is not None:
            life=getattr(world,'life',None)
            candidate=getattr(life,'focus',None)
            active=bool(candidate and (getattr(candidate,'dialogue','') or
                                       getattr(life,'event_kind','quiet')!='quiet'))
            if active and candidate is not self.subject:
                self._begin_follow(world,candidate)
            elif self.subject is not None and not active and self.elapsed-self.follow_started>14:
                self.subject=None; self.anchor=None; self.follow_from=None

    def _begin_follow(self, world, subject):
        """Choose a walkable shoulder and ease into a live event."""
        base=self._shot_position()
        for angle in (self.rng.random()*math.tau,0,math.pi/2,math.pi,3*math.pi/2):
            x=subject.x+math.cos(angle)*6; y=subject.y+math.sin(angle)*6
            if all(world.city.walkable(x+(subject.x-x)*t/16,
                                      y+(subject.y-y)*t/16) for t in range(16)):
                self.subject=subject; self.anchor=(x,y)
                self.follow_offset=(math.cos(angle)*6,math.sin(angle)*6)
                self.follow_from=base; self.follow_started=self.elapsed
                return

    def _shot_position(self):
        shot=self.shot; t=min(1,self.elapsed/shot.duration); t=t*t*(3-2*t)
        return (shot.start[0]+(shot.end[0]-shot.start[0])*t,
                shot.start[1]+(shot.end[1]-shot.start[1])*t)

    @property
    def exposure(self):
        # Brief dip at a cut, no rapid flashes or movement through buildings.
        if self.held: return 1.0
        return min(1.0, .18+self.elapsed/1.2,
                   .18+(self.shot.duration-self.elapsed)/1.2)

    def view(self, world):
        view=copy(world)
        shot=self.shot
        view.x,view.y=self._shot_position()
        if self.subject is not None:
            blend=min(1.0,max(0.0,(self.elapsed-self.follow_started)/4.0))
            blend=blend*blend*(3-2*blend)
            target_x=self.subject.x+self.follow_offset[0]
            target_y=self.subject.y+self.follow_offset[1]
            view.x += (target_x-view.x)*blend
            view.y += (target_y-view.y)*blend
            target=(self.subject.x,self.subject.y)
        else:
            target=shot.target
        view.angle=math.atan2(target[1]-view.y,target[0]-view.x)
        view.pitch=-.015
        view.bob=0.0
        view.eye_height=shot.eye
        view.camera_fov=max(45,min(90,shot.lens+self.zoom))
        view.shot_name=shot.name
        if self.subject is not None:
            view.shot_name=f'{self.subject.name} / {self.subject.role} / {self.subject.activity}'
            view.camera_fov=60
        view.interaction_hint=''
        view.toast=''
        view.scene_id='afterlight'
        view.lantern=False
        return view
