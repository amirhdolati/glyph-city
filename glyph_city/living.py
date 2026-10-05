"""Bounded pedestrian routines, shop hours and ambient neighborhood events."""
from collections import deque
from dataclasses import dataclass
import math
import random

from .city import SIZE


def shop_open(sign, hour):
    if sign in ('BAR','JAZZ','LOUNGE','18+'):
        return hour>=18 or hour<3
    if sign=='HOTEL': return True
    if sign in ('CAFE','BAKERY','TEA'): return 6<=hour<23
    return 9<=hour<22


NAMES=('Mina','Arman','Roya','Nima','Sara','Kian','Laleh','Omid',
       'Tara','Dara','Yas','Ava')
DESTINATIONS=((48.5,54.5),(72.5,48.5),(60.5,85.5),(24.5,36.5),
              (84.5,36.5),(60.5,60.5))
SHELTERS=((69.5,47.5),(74.5,47.5),(60.5,94.5))


class WalkingNetwork:
    """One validated graph and shared distance fields, never one search/frame."""
    def __init__(self, city):
        self.nodes={(x,y) for y in range(1,SIZE-1) for x in range(1,SIZE-1)
                    if city.walkable(x+.5,y+.5)}
        self.edges={}
        for x,y in sorted(self.nodes):
            self.edges[x,y]=tuple((nx,ny) for nx,ny in
                ((x-1,y),(x,y-1),(x,y+1),(x+1,y))
                if (nx,ny) in self.nodes and
                all(city.walkable(x+.5+(nx-x)*t,y+.5+(ny-y)*t)
                    for t in (.25,.5,.75)))
        self.fields={}

    def nearest(self, point):
        return min(self.nodes,key=lambda n:((n[0]+.5-point[0])**2+
                                            (n[1]+.5-point[1])**2,n))

    def field(self, goal):
        if goal not in self.fields:
            costs={goal:0}; todo=deque([goal])
            while todo:
                node=todo.popleft()
                for other in self.edges[node]:
                    if other not in costs:
                        costs[other]=costs[node]+1; todo.append(other)
            self.fields[goal]=costs
        return self.fields[goal]


@dataclass
class Resident:
    prop: object
    node: tuple
    target: tuple
    next_node: tuple | None = None
    wait: float = 0.0
    routine: object = None
    role: str = ''
    home: tuple = ()
    workplace: tuple = ()
    task: str = ''
    social_until: float = 0.0
    next_chat: float = 0.0
    partner: object = None
    reply_at: float = 0.0
    speech_until: float = 0.0
    followup: str = ''


ROLES = ('barista','gardener','courier','musician','bookseller','photographer','commuter','vendor')
JOBS = {'barista':'serving tea','gardener':'tending flowers','courier':'delivering parcels',
        'musician':'playing music','bookseller':'sorting books','photographer':'taking photos',
        'commuter':'reading','vendor':'arranging the stall'}
EXCHANGES = {
    'barista': (("Your usual? The kettle is ready.", "Yes, and a seat by the window."),
                ("Try the jasmine tea today.", "Just what I needed after that walk."),
                ("The window seat is free again.", "Then I can watch the rain arrive.")),
    'gardener': (("These flowers finally opened.", "The whole path smells like spring."),
                 ("The fountain is low tonight.", "I will bring water before sunrise.")),
    'courier': (("A parcel for you, all dry!", "You made it before the rain."),
                ("The next delivery is across the canal.", "I know a bridge with a dry lamp.")),
    'musician': (("One more song before I go?", "Play the one about the river."),
                 ("Do you hear that train under the bridge?", "I will tune the chorus to it.")),
    'bookseller': (("I saved that book for you.", "Then my evening is sorted."),
                   ("The blue cover has a map inside.", "Good. I have been looking for the long way home.")),
    'photographer': (("Look at the light on the water.", "Wait, the boat is coming into frame."),
                     ("The neon is reflected twice tonight.", "Hold still. The city is posing.")),
    'commuter': (("Taking the long way home?", "There is no hurry tonight."),
                 ("The market is still open.", "Then I have time for one warm cup.")),
    'vendor': (("Fresh tea, last pot of the evening.", "I'll bring a cup to my friend."),
               ("The lanterns look brighter from here.", "They always do after the first rain.")),
}

RAIN_EXCHANGES = {
    'barista': ("Close the door behind you.", "I will. The street is turning silver."),
    'gardener': ("The leaves are drinking tonight.", "And the roots will remember it."),
    'courier': ("Keep this under the awning.", "I have one more dry street to cross."),
    'musician': ("The rain is keeping time.", "Then I will follow its rhythm."),
    'bookseller': ("The paper smells like wet pavement.", "That is how I know the storm is near."),
    'photographer': ("Do not move. Look at the puddle.", "It has the whole skyline in it."),
    'commuter': ("You can wait here a while.", "The long way is better under cover."),
    'vendor': ("Two cups beneath the awning?", "Two cups, and one story each."),
}

FAREWELLS = {
    'barista': "I will keep the kettle warm for you.",
    'gardener': "Come back tomorrow; the buds should open.",
    'courier': "See you after my last delivery.",
    'musician': "I will save that song for next time.",
    'bookseller': "Tell me what you think of the ending.",
    'photographer': "I will show you the picture next time.",
    'commuter': "Walk with me again tomorrow?",
    'vendor': "I will save you a cup tomorrow.",
}


class LivingCity:
    def __init__(self, world):
        self.network=WalkingNetwork(world.city)
        self.destinations=tuple(self.network.nearest(p) for p in DESTINATIONS)
        self.shelters=tuple(self.network.nearest(p) for p in SHELTERS)
        self.rng=random.Random(world.city.seed+917)
        self.residents=[]
        occupied=set()
        for i,prop in enumerate(p for p in world.city.props if p.kind=='person'):
            node=self.destinations[i%len(self.destinations)]
            # Start visibly distributed along a valid corridor.
            for _ in range(i%9):
                neighbors=self.network.edges[node]
                if neighbors: node=self.rng.choice(neighbors)
            # Several residents used to land on the same start node. Their
            # large close-up sprites then became one unreadable bright mass.
            # Pick the nearest free node on the validated walking graph.
            if node in occupied:
                pending=deque([node]); seen=set()
                while pending:
                    candidate=pending.popleft()
                    if candidate in seen: continue
                    seen.add(candidate)
                    if candidate not in occupied:
                        node=candidate; break
                    pending.extend(sorted(self.network.edges[candidate]))
            occupied.add(node)
            prop.x,prop.y=node[0]+.5,node[1]+.5
            prop.route=()
            prop.name=NAMES[i%len(NAMES)]+(' '+str(i//len(NAMES)+1) if i>=len(NAMES) else '')
            prop.activity='walking'
            role=ROLES[i%len(ROLES)]
            work_index={'barista':1,'gardener':0,'courier':5,'musician':2,
                        'bookseller':3,'photographer':2,'commuter':4,'vendor':1}[role]
            prop.role=role
            self.residents.append(Resident(prop,node,node,role=role,
                home=node,workplace=self.destinations[work_index]))
        self.next_event=15.0
        self.event_until=0.0
        self.event_kind='quiet'
        self.caption='The city is waking up. Stay awhile.'
        self.next_greeting=0.0
        self.next_social=4.0
        self.focus=None
        self.history=deque(maxlen=32)
        self.encounters=0
        self.met_pairs=set()
        self.public_event=None
        self.public_phase=-1
        self.public_next=0.0

    def update(self, world, dt):
        if world.paused: return
        raining=world.rain>.4
        # Reserve occupied cells and the next segment; people queue rather than overlap.
        reserved={r.node:id(r) for r in self.residents}
        reserved.update({r.next_node:id(r) for r in self.residents if r.next_node})
        for i,resident in enumerate(self.residents):
            p=resident.prop
            if world.time>resident.speech_until: p.dialogue=''
            if resident.reply_at and world.time>=resident.reply_at:
                resident.reply_at=0
                if resident.partner:
                    partner,line=resident.partner
                    resident.partner=None
                    p.dialogue=''
                    partner.prop.dialogue=line; partner.speech_until=world.time+6
                    partner.prop.activity='chatting'
                    self.focus=partner.prop
                    self.caption=f'{partner.prop.name}: "{line}"'
                    self.history.append(self.caption)
                    if resident.followup:
                        partner.reply_at=world.time+4
                        partner.partner=(resident,resident.followup)
                        resident.followup=''
            if world.time<resident.social_until:
                continue
            # Offset shifts avoid the entire population turning at the same instant.
            hour=(world.clock+(i%4)*.3)%24
            working=(8<=hour<18) if resident.role not in ('musician','vendor') else (16<=hour<23)
            period='work' if working else 'home' if hour<6 or hour>=23 else 'leisure'
            routine=(period,raining)
            if resident.routine!=routine:
                if raining and resident.role not in ('courier','photographer'):
                    reachable=[g for g in self.shelters if resident.node in self.network.field(g)]
                    resident.target=min(reachable,key=lambda g:self.network.field(g)[resident.node]) if reachable else resident.node
                    resident.task='sheltering'
                elif period=='work':
                    resident.target=resident.workplace; resident.task=JOBS[resident.role]
                elif period=='home':
                    resident.target=resident.home; resident.task='resting'
                else:
                    resident.target=self.destinations[(i+int(world.clock//2))%len(self.destinations)]
                    resident.task=('watching the river','reading','drinking tea')[i%3]
                resident.routine=routine; resident.wait=0
            p.umbrella=raining
            if resident.next_node is None and resident.node==resident.target:
                p.activity=resident.task
                resident.wait+=dt
                if resident.role in ('courier','photographer') and period=='work' and resident.wait>18+i%11:
                    resident.target=self.destinations[(self.destinations.index(resident.target)+1)%len(self.destinations)]
                    resident.wait=0
                continue
            if resident.next_node is None:
                field=self.network.field(resident.target)
                choices=[n for n in self.network.edges[resident.node]
                         if field.get(n,10**6)<field.get(resident.node,10**6) and n not in reserved]
                if not choices:
                    p.activity='waiting'; resident.wait+=dt
                    # A occupied destination can be served from the adjacent cell.
                    if field.get(resident.node,999)<=2:
                        p.activity=resident.task
                    elif resident.wait>5:
                        side=[n for n in self.network.edges[resident.node] if n not in reserved]
                        if side: choices=[self.rng.choice(side)]
                    if not choices: continue
                resident.next_node=min(choices,key=lambda n:(field.get(n,10**6),n))
                reserved[resident.next_node]=id(resident); resident.wait=0
            nx,ny=resident.next_node
            dx,dy=nx+.5-p.x,ny+.5-p.y
            remaining=math.hypot(dx,dy)
            step=min(remaining,dt*(.65+i%4*.10)*(1.15 if raining else 1))
            if remaining>1e-8:
                p.x+=dx/remaining*step; p.y+=dy/remaining*step
            if remaining<=step+1e-8:
                resident.node=resident.next_node; resident.next_node=None
            p.activity='walking'
        if world.time>=self.next_social:
            self.next_social=world.time+self.rng.uniform(7,13)
            candidates=[r for r in self.residents if world.time>=r.next_chat and r.next_node is None]
            self.rng.shuffle(candidates)
            for speaker in candidates:
                partner=next((r for r in candidates if r is not speaker and
                    math.hypot(r.prop.x-speaker.prop.x,r.prop.y-speaker.prop.y)<3.5),None)
                if partner:
                    lines=self.rng.choice(EXCHANGES[speaker.role])
                    if raining: lines=RAIN_EXCHANGES[speaker.role]
                    pair=tuple(sorted((speaker.prop.name,partner.prop.name)))
                    opening=lines[0]
                    if pair in self.met_pairs:
                        opening=f"Good to see you, {partner.prop.name}. "+opening
                    self.met_pairs.add(pair)
                    speaker.prop.dialogue=opening; speaker.speech_until=world.time+5
                    speaker.reply_at=world.time+4; speaker.partner=(partner,lines[1])
                    speaker.followup=FAREWELLS[speaker.role]
                    for r in (speaker,partner):
                        r.social_until=world.time+15; r.next_chat=world.time+self.rng.uniform(55,100)
                        r.prop.activity='chatting'
                    self.encounters+=1; self.focus=speaker.prop
                    self.caption=f'{speaker.prop.name}: "{opening}"'
                    self.history.append(self.caption)
                    break
        if world.time>=self.next_event:
            self._start_public_event(world)
        if world.time>=self.event_until and self.public_event is None:
            self.event_kind='quiet'
        if self.public_event and world.time>=self.public_next:
            self._advance_public_event(world)
        if not world.observing and world.scene_id=='afterlight' and world.time>self.next_greeting:
            for r in self.residents:
                if math.hypot(r.prop.x-world.x,r.prop.y-world.y)<2:
                    flag='met:'+r.prop.name
                    familiar=flag in world.story_flags
                    world.story_flags.add(flag)
                    world.message(r.prop.name+(': Good to see you again.' if familiar else ': Evening. Enjoy the city.'))
                    self.next_greeting=world.time+25
                    break

    def _start_public_event(self, world):
        """Start a small staged scene that can be watched from a camera shot."""
        # A public event may interrupt a walk; the selected people pause at the
        # next visible beat instead of requiring a rare idle frame.
        available=list(self.residents)
        if len(available)<2: return
        kind=self.rng.choice(('delivery','street_music','shared_umbrella','blackout'))
        if kind=='delivery':
            first=next((r for r in available if r.role=='courier'),available[0])
            second=self.rng.choice([r for r in available if r is not first])
            script=((first,'delivering a parcel',f'{first.prop.name}: I kept this dry for you.'),
                    (second,'receiving a parcel',f'{second.prop.name}: I thought it was lost in the rain.'),
                    (first,'waving goodbye',f'{first.prop.name}: The next delivery is across the canal.'))
        elif kind=='street_music':
            first=next((r for r in available if r.role=='musician'),available[0])
            second=self.rng.choice([r for r in available if r is not first])
            script=((first,'playing music',f'{first.prop.name}: One song before the market closes.'),
                    (second,'listening',f'{second.prop.name}: Stay for the river song.'),
                    (first,'packing an instrument',f'{first.prop.name}: Thank you. Good night, Afterlight.'))
        elif kind=='shared_umbrella':
            first=self.rng.choice(available); second=self.rng.choice([r for r in available if r is not first])
            script=((first,'offering an umbrella',f'{first.prop.name}: There is room under here.'),
                    (second,'sharing an umbrella',f'{second.prop.name}: Then let us take the long way.'),
                    (first,'walking together',f'{first.prop.name}: The rain makes the lights beautiful.'))
        else:
            first=self.rng.choice(available); second=self.rng.choice([r for r in available if r is not first])
            script=((first,'looking up',f'{first.prop.name}: Did the whole street just go dark?'),
                    (second,'using a phone light',f'{second.prop.name}: Give it a moment. Listen to the rain.'),
                    (first,'watching lights return',f'{first.prop.name}: There they are.'))
        # Public scenes take over their actors without an old chat replying
        # halfway through the new scene.
        actors={id(actor) for actor,_,_ in script}
        for resident in self.residents:
            if id(resident) in actors or (resident.partner and id(resident.partner[0]) in actors):
                resident.reply_at=0; resident.partner=None; resident.followup=''
        self.public_event={'kind':kind,'script':script}
        self.public_phase=-1; self.public_next=world.time
        self.event_kind=kind; self.event_until=world.time+25
        self.next_event=world.time+self.rng.uniform(48,82)
        self._advance_public_event(world)

    def _advance_public_event(self, world):
        if not self.public_event: return
        self.public_phase+=1
        script=self.public_event['script']
        if self.public_phase>=len(script):
            self.public_event=None; self.event_kind='quiet'; self.focus=None
            return
        actor,activity,line=script[self.public_phase]
        actor.prop.activity=activity; actor.prop.dialogue=line
        actor.speech_until=world.time+7; actor.social_until=world.time+7
        self.focus=actor.prop
        self.caption=line; self.history.append(line)
        self.public_next=world.time+7.5
