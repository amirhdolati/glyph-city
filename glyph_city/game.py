"""Interactive loop and reproducible offline previews."""
from __future__ import annotations

import argparse
import html
import itertools
import math
from pathlib import Path
import sys
import time
import json

from .city import City, World, WEATHER
from .render import Renderer, cell, map_overlay, help_overlay, overlay
from .save import (AutosaveController, SaveFileError, SaveNotFoundError,
                   SaveSchemaError, SaveStore)
from .settings import SettingsStore
from .interactions import InteractionCandidate, prompt_for, select_candidate
from .journal import BookStory, Journal
from .weather import UmbrellaState, default_shelters
from .terminal import InputState, Terminal, encode
from .photos import PhotoAlbum
from .events import available_events
from .transit import BoatRide
from .director import Director, SHOTS
from .living import LivingCity
from .audio import create_audio


def make_world(seed=17, hour=17.2, weather='clear'):
    world=World(City(seed),clock=hour,weather=WEATHER.index(weather.upper()))
    world.rain=(0,.65,1,0)[world.weather]
    world.cloud=(.15,.8,1,.65)[world.weather]
    world.wet=world.rain
    return world


def frame(world,renderer,minimap=False,help_open=False,map_open=False,fps=0,truecolor=True,
          photo_mode=False,album=None,journal_view=None,input_mode=None,settings_view=None):
    buf=renderer.render_interior(world) if getattr(world,'scene_id','afterlight') != 'afterlight' else renderer.render(world,minimap)
    if getattr(world,'camera_transition',False):
        # Short letterbox bars make an active camera move read as a deliberate
        # cinematic beat, while leaving the actual ray-cast image untouched.
        bars=2 if len(buf)>=20 else 1
        for row in list(range(bars))+list(range(len(buf)-bars,len(buf))):
            for col in range(len(buf[row])):
                buf[row][col]=cell(' ',(0,0,0),(0,0,0))
    if photo_mode:
        return buf
    if help_open: help_overlay(buf)
    elif map_open: map_overlay(buf,world)
    elif album is not None:
        photos, selected = album
        lines=['+----------------------------------------------+',
               '| PHOTO ALBUM                      J / Esc close |',
               '+----------------------------------------------+']
        if not photos:
            lines.append('| No photos yet. Space pauses, P captures.      |')
        else:
            for index, photo in enumerate(photos[:8]):
                marker='>' if index == selected else ' '
                lines.append(f'|{marker} {photo.id[:19]}  {photo.weather:<6} {photo.hour:05.2f} |')
            chosen=photos[min(selected,len(photos)-1)]
            lines.extend(('|                                              |',
                          f'| {chosen.district[:43]:<43}|',
                          f'| {chosen.html_path[:43]:<43}|',
                          '| W/S select; files are in the save photos folder |'))
        lines.append('+----------------------------------------------+')
        overlay(buf,lines)
    elif journal_view is not None:
        entries, selected = journal_view
        lines=['+----------------------------------------------+',
               '| TRAVEL JOURNAL                    K / Esc close |',
               '+----------------------------------------------+']
        if not entries:
            lines.append('| Discover a place or complete a story first.   |')
        else:
            for index, entry in enumerate(entries[:8]):
                marker='>' if index == selected else ' '
                lines.append(f'|{marker} [{entry.status[:4].upper():4}] {entry.title[:34]:<34}|')
            chosen=entries[min(selected,len(entries)-1)]
            lines.extend(('|                                              |',
                          f'| {chosen.text[:43]:<43}|',
                          '| W/S select; M shows the city destination     |'))
        lines.append('+----------------------------------------------+')
        overlay(buf,lines)
    elif settings_view is not None:
        values, selected = settings_view
        labels=('Palette','Truecolor','FPS limit','Render width','Cell aspect',
                'Mouse sensitivity','Camera bob','Night contrast','Storm flash','Volume')
        lines=['+------------------------------------------------+',
               '| SETTINGS                         I / Esc close |',
               '+------------------------------------------------+']
        for index,(label,value) in enumerate(zip(labels,values)):
            marker='>' if index==selected else ' '
            lines.append(f'|{marker} {label:<21} {str(value):>22} |')
        lines.extend(('+------------------------------------------------+',
                      '| Up/Down select   Left/Right edit   Enter toggle |',
                      '| Changes are saved immediately.                  |'))
        overlay(buf,lines)
    cols=renderer.cols
    angle=world.angle%(math.tau)
    compass=('E','SE','S','SW','W','NW','N','NE')[round(angle/(math.pi/4))%8]
    time_str=f'{int(world.clock):02d}:{int(world.clock%1*60):02d}'
    title=f' GLYPH CITY / AFTERLIGHT     {getattr(world,"shot_name",world.city.district(world.x,world.y))}'
    watch='  |  CITY WATCH' if getattr(world,'observing',False) else ''
    status=f' {time_str}  {WEATHER[world.weather]}  {compass}  |  {len(world.visited)}/6 places  {int(world.distance)}m walked{watch}'
    if world.paused: status+='  |  PHOTO PAUSE'
    elif world.lantern: status+='  |  LANTERN'
    rate=f'{fps:02.0f}fps' if fps else 'STILL'
    mode='' if not input_mode else f' {input_mode.upper()}'
    suffix=f' {rate} {"RGB" if truecolor else "256"}{mode} '
    status=status[:max(0,cols-len(suffix))].ljust(max(0,cols-len(suffix)))+suffix
    hint=' WASD Walk  Q/E Turn  Shift Run  I Settings  O Watch  [ ] Camera  U Umbrella  R Rain  Y Time  M Map  H Help  X Exit'
    interaction_hint=getattr(world, 'interaction_hint', '')
    toast_active=bool(world.toast and world.time<world.toast_until)
    if interaction_hint and not help_open and not map_open and not toast_active:
        hint=' '+interaction_hint
    if toast_active and not help_open: hint=' '+world.toast
    life_caption=getattr(getattr(world,'life',None),'caption','')
    if (getattr(world,'observing',False) and life_caption and not help_open
            and not map_open and not toast_active and not interaction_hint):
        hint=' '+life_caption
    header=[cell(ch,(144,213,196),(9,22,29)) for ch in title[:cols].ljust(cols)]
    footer=[cell(ch,(199,204,197),(9,22,29)) for ch in status[:cols].ljust(cols)]
    hintrow=[cell(ch,(133,157,171),(6,15,23)) for ch in hint[:cols].ljust(cols)]
    return [header]+buf+[footer,hintrow]


def _menu_frame(cols, rows, selected, has_save, message=''):
    """Build the small boot menu as ordinary terminal cells."""
    bg=(7,18,27); fg=(202,218,211); accent=(144,213,196); muted=(123,157,166)
    lines=[''] * max(1, rows)
    content=[
        'GLYPH CITY / AFTERLIGHT',
        'a quiet walk through a changing city',
        '',
        ('> ' if selected == 0 else '  ') + 'Continue' + ('' if has_save else '  [no save]'),
        ('> ' if selected == 1 else '  ') + 'New Walk',
        ('> ' if selected == 2 else '  ') + 'Settings  (preferences loaded)',
        '',
        'W/S or arrows  Move    Enter  Select    Esc  Quit',
    ]
    if message:
        content += ['', message]
    top=max(0,(rows-len(content))//2)
    out=[]
    for r in range(rows):
        text=content[r-top] if top <= r < top+len(content) else ''
        color=accent if r-top == 0 else muted if r-top in (1,7) else fg
        out.append([cell(ch,color,bg) for ch in text[:cols].ljust(cols)])
    return out


SETTING_FIELDS=('palette','truecolor','fps','max_width','aspect',
                'mouse_sensitivity','camera_bob','night_contrast','storm_flash','volume')


def adjust_setting(settings, index, direction):
    """Return settings with one field changed by one left/right step."""
    from dataclasses import replace
    field=SETTING_FIELDS[max(0,min(len(SETTING_FIELDS)-1,index))]
    direction=-1 if direction<0 else 1
    value=getattr(settings,field)
    if field=='palette':
        cycle=('auto','256','truecolor'); value=cycle[(cycle.index(value)+direction)%len(cycle)]
    elif field in ('truecolor','camera_bob','storm_flash'):
        value=not value
    elif field=='fps': value=max(5,min(60,value+direction*5))
    elif field=='max_width': value=max(40,min(240,value+direction*10))
    elif field=='aspect': value=max(.25,min(1,round(value+direction*.05,2)))
    elif field=='mouse_sensitivity': value=max(.004,min(.06,round(value+direction*.004,3)))
    elif field=='night_contrast': value=max(.5,min(2,round(value+direction*.1,1)))
    elif field=='volume': value=max(0,min(1,round(value+direction*.1,1)))
    return replace(settings,**{field:value})


def start_menu(terminal, args, store=None):
    """Run the interactive boot menu and return a newly selected World.

    This function deliberately owns no gameplay input state.  It consumes and
    flushes all events while modal, so a held movement key cannot leak into
    the first simulation frame.  ``None`` means the user chose to quit.
    """
    store=store or SaveStore(getattr(args, 'save_path', None))
    settings_store=SettingsStore(getattr(args, 'settings_path', None))
    has_save=store.path.exists() or store.backup_path.exists()
    selected=0 if has_save else 1
    notice=''
    terminal.clear()
    while True:
        cols, rows=terminal.size()
        terminal.draw(_menu_frame(max(1, cols), max(4, rows), selected, has_save, notice), 1, 1, delta=True)
        events=terminal.events()
        for index, event in enumerate(events):
            key=event.key
            if key in ('exit', 'escape'):
                return None
            if event.release or event.repeat:
                continue
            if key in ('w','up'):
                selected=(selected-1) % 3
            elif key in ('s','down'):
                selected=(selected+1) % 3
            elif key in ('n',):
                selected=1
            elif key in ('enter','\r','\n','photo'):
                if selected == 0:
                    try:
                        return store.load_world()
                    except SaveNotFoundError:
                        has_save=False
                        selected=1
                        notice='No saved walk found. Choose New Walk to begin.'
                    except (SaveSchemaError, SaveFileError) as exc:
                        selected=1
                        notice=f'Could not continue: {exc}. Choose New Walk.'
                elif selected == 1:
                    return make_world(args.seed, args.hour, args.weather)
                else:
                    current=settings_store.load()
                    from dataclasses import replace
                    palette={'auto':'256','256':'truecolor','truecolor':'auto'}[current.palette]
                    settings_store.save(replace(current,palette=palette))
                    notice=f'Settings saved: palette={palette}. Reopen the game to apply it.'
            elif key in ('r','y'):
                # Keep the long-standing preview/PTY smoke-test shortcut:
                # weather/time commands can start a fresh walk immediately.
                # Movement keys remain modal navigation and are never leaked.
                terminal.menu_events=events[index:]
                return make_world(args.seed, args.hour, args.weather)
            # Any other key is intentionally consumed by the modal menu.
        time.sleep(.03)


def _interaction_candidates(world):
    """Return the deterministic interaction set for the current walk."""
    if getattr(world, 'scene_id', 'afterlight') == 'cafe':
        return (InteractionCandidate('cafe_exit', 'scene:afterlight', 'Leave the cafe',
                                      8.0, 10.0, radius=3.0, priority=100),)
    candidates=list(BookStory.candidates(world.story_flags, world.clock))
    candidates.extend((
        InteractionCandidate('bench_willow', 'rest', 'Rest on the Willow bench', 45, 46,
                             radius=2.8, priority=15),
        InteractionCandidate('canal_view', 'look', 'Look across Moonwater Canal', 60, 85,
                             radius=3.2, priority=10),
        InteractionCandidate('cafe_door', 'scene:cafe', 'Enter the Moonwater cafe',
                             69.5, 42.5, radius=2.8, priority=30),
        InteractionCandidate('market_seller', 'talk:seller', 'Talk to the bookseller',
                             72.0, 48.0, radius=3.0, priority=20),
        InteractionCandidate('market_sign', 'read:sign', 'Read the market sign',
                             70.5, 39.5, radius=2.5, priority=5),
    ))
    for event in available_events(world.clock, getattr(world, 'event_flags', set())):
        candidates.append(InteractionCandidate('event_'+event.id, 'event:'+event.id,
                             event.title, event.target[0], event.target[1],
                             radius=3.0, priority=40))
    candidates.extend(InteractionCandidate('boat_'+stop, 'boat:'+stop,
                                           'Board the canal boat', x, y, radius=3.0,
                                           priority=25)
                      for stop,x,y in (('canal_north',60.,85.),('canal_south',60.,96.)))
    return candidates


def _interaction_visible(city, player_x, player_y, target_x, target_y):
    """Reject prompts hidden behind a building or the canal."""
    distance=math.hypot(target_x-player_x,target_y-player_y)
    samples=max(1,math.ceil(distance/.2))
    for step in range(1,samples):
        ratio=step/samples
        if city.solid(player_x+(target_x-player_x)*ratio,
                      player_y+(target_y-player_y)*ratio):
            return False
    return True


def _selected_interaction(world):
    if world.scene_id=='boat':
        return None
    return select_candidate(world.x,world.y,world.angle,_interaction_candidates(world),
                            line_of_sight=lambda px,py,tx,ty:
                            _interaction_visible(world.city,px,py,tx,ty)
                            if world.scene_id=='afterlight' else True)


def _journal_entries(journal):
    return journal.entries()


def play(args):
    settings=SettingsStore(getattr(args, 'settings_path', None)).load()
    if getattr(args, 'fps', 24) == 24: args.fps=settings.fps
    if getattr(args, 'max_width', 160) == 160: args.max_width=settings.max_width
    if getattr(args, 'aspect', None) is None: args.aspect=settings.aspect
    input_state=InputState(); help_open=False; map_open=False; minimap=False; mouse=False; mouse_last=None
    album_open=False; album_entries=(); album_selected=0
    settings_open=False; settings_selected=0
    journal_open=False; journal_entries=(); journal_selected=0; capture_requested=False
    mouse_at=0; sensitivity=.018
    if not args.palette and not args.truecolor:
        color=False if settings.palette == '256' else True if settings.palette == 'truecolor' else None
    else:
        color=False if args.palette else True if args.truecolor else None
    with Terminal(color) as terminal:
        store=SaveStore(getattr(args, 'save_path', None))
        photo_album=PhotoAlbum(store.path.parent / 'photos')
        world=start_menu(terminal,args,store)
        if world is None:
            return
        world.camera_bob_enabled=settings.camera_bob
        world.night_contrast=settings.night_contrast
        world.storm_flash_enabled=settings.storm_flash
        audio=create_audio(volume=settings.volume)
        autosave=AutosaveController(store)
        boat=BoatRide(); settings_store=SettingsStore(getattr(args,'settings_path',None))
        settings=settings_store.load()
        shelters=default_shelters(); umbrella=UmbrellaState()
        journal=Journal()
        for step in BookStory.steps:
            if step.flag in world.story_flags:
                journal.record('story_'+step.id, kind='story', title=step.title,
                               text=step.text, target=step.target, status='complete')
        world.life=LivingCity(world)
        director=Director()
        if getattr(args,'watch',False):
            world.observing=True; world.show_names=True
        for photo in photo_album.entries():
            journal.record('photo_'+photo.id,kind='photo',title=photo.district,
                           text=f'{photo.weather} at {photo.hour:05.2f}',status='complete',
                           metadata={'path':photo.html_path})
        last_progress=(frozenset(world.visited),frozenset(world.story_flags))
        menu_events=getattr(terminal,'menu_events',[])
        terminal.menu_events=[]
        previous_size=None; renderer=None; last=time.perf_counter(); fps=24.; next_weather=120.
        while True:
            started=time.perf_counter(); dt=min(.1,started-last); last=started
            events=menu_events or terminal.events()
            menu_events=[]
            for event in events:
                if event.mouse is not None:
                    if mouse and mouse_last is not None and started-mouse_at<.35:
                        dx,dy=event.mouse[0]-mouse_last[0],event.mouse[1]-mouse_last[1]
                        if abs(dx)<35 and abs(dy)<20:
                            world.angle+=dx*sensitivity
                            world.pitch=max(-.35,min(.35,world.pitch+dy*sensitivity*.45))
                    mouse_last=event.mouse; mouse_at=started
                    continue
                key=event.key
                if key=='focus-out':
                    input_state.apply(event,started); world.velocity_x=world.velocity_y=0
                    mouse_last=None
                    continue
                if settings_open:
                    if event.release or event.repeat:
                        continue
                    if key in ('escape','exit','i'):
                        settings_open=False; input_state.clear(); continue
                    if key in ('up','w'): settings_selected=max(0,settings_selected-1); continue
                    if key in ('down','s'): settings_selected=min(9,settings_selected+1); continue
                    if key in ('left','right','a','d','enter','return'):
                        direction=-1 if key in ('left','a') else 1
                        field=SETTING_FIELDS[settings_selected]
                        settings=adjust_setting(settings_store.load(),settings_selected,direction)
                        settings_store.save(settings)
                        if field in ('max_width','aspect'): previous_size=None
                        args.fps=settings.fps; args.max_width=settings.max_width; args.aspect=settings.aspect
                        sensitivity=settings.mouse_sensitivity; terminal.truecolor=(settings.palette=='truecolor' or (settings.palette=='auto' and settings.truecolor))
                        world.camera_bob_enabled=settings.camera_bob
                        world.night_contrast=settings.night_contrast
                        world.storm_flash_enabled=settings.storm_flash
                        audio.set_volume(settings.volume)
                        world.message(f'{field.replace("_"," ").title()}: {getattr(settings,field)}')
                        continue
                    continue
                if album_open or journal_open:
                    if event.release or event.repeat:
                        continue
                    if key in ('j','k','exit'):
                        album_open=False; journal_open=False; input_state.clear()
                    elif key=='w':
                        if album_open: album_selected=max(0,album_selected-1)
                        else:
                            journal_selected=max(0,journal_selected-1)
                            world.journal_target=journal_entries[journal_selected].target if journal_entries else None
                    elif key=='s':
                        if album_open: album_selected=min(max(0,len(album_entries)-1),album_selected+1)
                        else:
                            journal_selected=min(max(0,len(journal_entries)-1),journal_selected+1)
                            world.journal_target=journal_entries[journal_selected].target if journal_entries else None
                    continue
                if key=='exit' or key=='x':
                    if not event.release:
                        autosave.save_on_exit(world)
                        audio.close()
                        return
                if key in ('w','a','s','d','q','e'):
                    chord_before=input_state.legacy_chord
                    input_state.apply(event,started)
                    if not chord_before and input_state.legacy_chord:
                        world.message('Legacy chord mode: movement stops when input stops. V brakes now.')
                    continue
                if key=='o':
                    world.observing=not world.observing
                    world.show_names=world.observing
                    world.message('City Watch: live simulation.' if world.observing else 'Walk mode: controls restored.')
                    input_state.clear()
                    continue
                if key=='i':
                    settings_open=True; settings_selected=0; input_state.clear(); help_open=map_open=False
                    continue
                if key in ('[',']') and world.observing:
                    if key==']': director.next(world)
                    else: director.previous(world)
                    continue
                if key=='n' and world.observing:
                    director.next(world); continue
                if key in ('shift-left','shift-right'):
                    input_state.apply(event,started)
                    continue
                if event.release or event.repeat: continue
                if key in ('enter','\\r','\\n'):
                    candidate=_selected_interaction(world)
                    if candidate is not None:
                        if candidate.action.startswith('scene:'):
                            world.scene_id=candidate.action.split(':',1)[1]
                            if world.scene_id == 'cafe':
                                world.x,world.y=8.0,10.0
                                world.message('The cafe is warm and quiet. Enter at the door to leave.')
                            else:
                                world.x,world.y=69.0,44.0
                                world.message('Rain and city light return through the door.')
                            autosave.request(world,'scene-transition')
                        elif candidate.action.startswith('event:'):
                            event_id=candidate.action.split(':',1)[1]
                            event=next((item for item in available_events(world.clock, getattr(world,'event_flags',set())) if item.id==event_id),None)
                            if event:
                                world.event_flags.add(event.id)
                                world.message(event.text)
                                autosave.request(world,'event-complete')
                        elif candidate.action.startswith('boat:'):
                            stop_id=candidate.action.split(':',1)[1]
                            if boat.board(stop_id):
                                world.message('Boarded the canal boat. Enter again to disembark.')
                                world.scene_id='boat'
                                world.x,world.y=60.,89.
                                autosave.request(world,'transit-board')
                        elif candidate.action == 'talk:seller':
                            world.message('Bookseller: the canal keeps what the market forgets.')
                            world.story_flags.add('seller_hint')
                            autosave.request(world,'seller-dialog')
                        elif candidate.action == 'read:sign':
                            world.message('Lantern Market / tea, books, and warm windows.')
                        elif candidate.action == 'rest':
                            world.sitting=not getattr(world,'sitting',False)
                            world.message('You sit and listen to the rain.' if world.sitting else 'You stand up.')
                        elif candidate.action.startswith('story:'):
                            step_id=candidate.action.split(':',1)[1]
                            text=BookStory.complete(world.story_flags,step_id)
                            step=next(step for step in BookStory.steps if step.id==step_id)
                            journal.record('story_'+step.id,kind='story',title=step.title,
                                           text=step.text,target=step.target,status='complete')
                            world.message(text)
                        else:
                            journal.record(candidate.id,kind='place',title=candidate.label,
                                           text=f'Visited {candidate.label}.',status='complete')
                            world.message(f'{candidate.label}.')
                    continue
                if key=='h':
                    help_open=not help_open; map_open=False; input_state.clear()
                elif key=='m':
                    map_open=not map_open; help_open=False; input_state.clear()
                elif key=='tab': minimap=not minimap
                elif key=='l':
                    mouse=not mouse; mouse_last=None; terminal.mouse(mouse)
                    world.message(f'Mouse look {"on" if mouse else "off"}. L toggles it.')
                elif key=='c': terminal.truecolor=not terminal.truecolor
                elif key=='t':
                    world.clock_running=not world.clock_running
                    world.message('Clock running.' if world.clock_running else 'Clock paused. Y skips three hours.')
                elif key=='y': world.clock=(world.clock+3)%24
                elif key=='n':
                    world.weather=(world.weather+1)%len(WEATHER); next_weather=world.time+150
                    world.message(f'Weather changing to {WEATHER[world.weather].lower()}.')
                elif key=='r':
                    world.weather=0 if world.weather in (1,2) else 1; next_weather=world.time+150
                    world.message('Rain is arriving.' if world.weather==1 else 'The rain is clearing.')
                elif key=='f': world.lantern=not world.lantern
                elif key=='u':
                    umbrella=umbrella.toggled()
                    exposure=shelters.exposure(world.x,world.y,world.rain,umbrella=umbrella)
                    world.message('Umbrella open.' if umbrella.open else 'Umbrella closed.')
                    if exposure.shelter_id:
                        world.message(f"{exposure.shelter_id.replace('_',' ').title()} / rain {exposure.intensity:.0%}.")
                elif key=='photo':
                    world.paused=not world.paused
                    input_state.clear_movement()
                    world.velocity_x=world.velocity_y=0
                elif key=='p':
                    if world.paused:
                        capture_requested=True
                    else:
                        world.message('Press Space to pause the scene, then P to capture.')
                elif key=='j':
                    album_entries=photo_album.entries(); album_selected=0; album_open=True
                    journal_open=False; help_open=map_open=False; input_state.clear()
                elif key=='k':
                    journal_entries=_journal_entries(journal); journal_selected=0; journal_open=True
                    world.journal_target=journal_entries[0].target if journal_entries and journal_entries[0].target else None
                    album_open=False; help_open=map_open=False; input_state.clear()
                elif key=='v':
                    input_state.clear_movement()
                    world.velocity_x=world.velocity_y=0
                    world.message('Movement stopped.')
                elif key=='home':
                    world.x,world.y,world.angle,world.pitch=60.,78.,-math.pi/2,0.
                    world.velocity_x=world.velocity_y=world.bob=0
                elif key in ('=','+'): sensitivity=min(.06,sensitivity*1.2)
                elif key in ('-','_'): sensitivity=max(.004,sensitivity/1.2)
            held,shifts=input_state.snapshot(started)
            director.update(dt,world.paused,world)
            if world.scene_id == 'boat':
                boat.update(dt)
                if boat.progress >= 1.0:
                    destination=boat.disembark(); world.scene_id='afterlight'
                    world.x,world.y=(60.,96.) if destination=='canal_south' else (60.,85.)
                    world.message('The boat has arrived. Enter near the dock to continue walking.')
            if world.paused:
                world.velocity_x=world.velocity_y=0
                world.update(dt,{key: value for key,value in held.items() if key in 'qe'})
            elif not help_open and not map_open and not album_open and not journal_open and not settings_open and world.scene_id != 'boat':
                sprint=bool(shifts) or any(shift for key,(_,shift) in held.items()
                                          if key in 'wasd')
                world.update(dt,held,sprint)
            else:
                # Menus stop walking immediately; ambience and the clock continue.
                world.velocity_x=world.velocity_y=0
                world.update(dt,{})
            audio.scene(world, director.view(world) if world.observing else world, dt)
            audio.update(dt)
            progress=(frozenset(world.visited),frozenset(world.story_flags))
            if progress != last_progress:
                for index in sorted(progress[0] - last_progress[0]):
                    landmark=world.city.landmarks[index]
                    journal.record('landmark_'+str(index),kind='landmark',title=landmark.name,
                                   text=landmark.description,target=(landmark.x,landmark.y),
                                   status='complete')
                autosave.request(world,'discovery-or-story-progress')
                last_progress=progress
            autosave.maybe_save()
            world.interaction_hint=prompt_for(_selected_interaction(world))
            if world.time>=next_weather:
                world.weather=(0,1,0,3,1,2)[int(world.time//120)%6]
                world.rain=(0,.65,1,0)[world.weather]
                world.cloud=(.15,.8,1,.65)[world.weather]
                world.wet=world.rain
                next_weather=world.time+120
                world.message(f'The sky is turning {WEATHER[world.weather].lower()}.')
            tcols,trows=terminal.size()
            size=(min(tcols,args.max_width),min(trows,64))
            if (tcols,trows)!=previous_size:
                terminal.clear(); previous_size=(tcols,trows)
                renderer=Renderer(max(1,size[0]),max(1,size[1]-3),args.aspect or terminal.aspect())
            if tcols<40 or trows<16:
                text=' Enlarge terminal to at least 40 x 16. X exits.'
                small=[[cell(ch,(218,211,188),(9,20,29)) for ch in text[:tcols].ljust(tcols)]]
                terminal.draw(small,1,1,delta=True)
            else:
                if capture_requested:
                    try:
                        photo=photo_album.capture(world,renderer.render_interior(world) if world.scene_id != 'afterlight' else renderer.render(world,False),
                                                  export_html=export_html,encode_ansi=encode,
                                                  aspect=args.aspect or terminal.aspect(),
                                                  truecolor=terminal.truecolor)
                        journal.record('photo_'+photo.id,kind='photo',title=photo.district,
                                       text=f'{photo.weather} at {photo.hour:05.2f}',
                                       status='complete',metadata={'path':photo.html_path})
                        world.message(f'Photo saved: {photo.html_path}  /  J opens album.')
                    except OSError as exc:
                        world.message(f'Photo could not be saved: {exc}')
                    capture_requested=False
                view=director.view(world) if world.observing else world
                settings_values=(settings.palette,settings.truecolor,settings.fps,settings.max_width,
                                 settings.aspect,settings.mouse_sensitivity,settings.camera_bob,
                                 settings.night_contrast,settings.storm_flash,settings.volume)
                buf=frame(view,renderer,minimap,help_open,map_open,fps,terminal.truecolor,
                          album=(album_entries,album_selected) if album_open else None,
                          journal_view=(journal_entries,journal_selected) if journal_open else None,
                          input_mode=input_state.mode,
                          settings_view=(settings_values,settings_selected) if settings_open else None)
                terminal.draw(buf,max(1,(tcols-size[0])//2+1),max(1,(trows-size[1])//2+1),delta=True)
            spent=time.perf_counter()-started
            delay=max(0,1/args.fps-spent)
            if delay: time.sleep(delay)
            fps=fps*.9+.1/max(time.perf_counter()-started,.001)


def export_html(buf,path,aspect=.5):
    rows=[]
    for row in buf:
        spans=[]
        for (fg,bg),cells in itertools.groupby(row,key=lambda c:(c[1],c[2])):
            chars=''.join(ch for ch,_,_ in cells)
            color='#%02x%02x%02x'%fg; back='#%02x%02x%02x'%bg
            spans.append(f'<span style="color:{color};background:{back}">{html.escape(chars)}</span>')
        rows.append(''.join(spans))
    content='\n'.join(rows)
    ratio=.602/aspect
    font_rule=f'font-size:min(14px,calc((100vw - 48px) / {len(buf[0])*.602:.3f}));line-height:{ratio:.4f};'
    path.write_text('<!doctype html><html lang="en"><meta charset="utf-8">'
        '<title>Glyph City / Afterlight</title><style>'
        '*{box-sizing:border-box}body{margin:0;background:#050c13;display:grid;place-items:center;min-height:100vh}'
        'pre{font-family:Menlo,Consolas,monospace;'+font_rule+'letter-spacing:0;'
        'white-space:pre;margin:24px;padding:0;box-shadow:0 24px 100px #0008;font-variant-ligatures:none}'
        f'span{{font:inherit;display:inline-block;height:{ratio:.4f}em;vertical-align:top}}</style><pre>'+content+'</pre></html>')


def profile_preview(args):
    """Run a deterministic offline render benchmark and print JSON metrics."""
    cols, rows = map(int, args.size.lower().split('x'))
    world=make_world(args.seed,args.hour,args.weather)
    renderer=Renderer(cols,rows,args.aspect or .5)
    render_times=[]; encode_times=[]; update_times=[]
    for index in range(max(1,args.profile_frames)):
        start=time.perf_counter(); world.update(1/max(1,args.fps),{})
        update_times.append(time.perf_counter()-start)
        start=time.perf_counter(); buf=renderer.render(world); render_times.append(time.perf_counter()-start)
        start=time.perf_counter(); encode(buf,not args.palette); encode_times.append(time.perf_counter()-start)
    def stats(values):
        ordered=sorted(values); n=len(ordered)
        return {'mean_ms':round(sum(values)/n*1000,3),
                'median_ms':round(ordered[n//2]*1000,3),
                'p95_ms':round(ordered[min(n-1,int(n*.95))]*1000,3)}
    print(json.dumps({'frames':len(render_times),'size':f'{cols}x{rows}',
                      'time':args.hour,'weather':args.weather,
                      'update':stats(update_times),'render':stats(render_times),
                      'encode':stats(encode_times)},sort_keys=True))


def main(argv=None):
    parser=argparse.ArgumentParser(description='Glyph City: Afterlight — take the long way home.')
    parser.add_argument('--classic',action='store_true',help='launch the exact preserved original game')
    parser.add_argument('--seed',type=int,default=17,help='reproducible city seed')
    parser.add_argument('--time',dest='hour',default='dusk',help='dawn, day, dusk, night, or an hour from 0 to 24')
    parser.add_argument('--weather',choices=('clear','rain','storm','mist'),default='clear')
    colors=parser.add_mutually_exclusive_group()
    colors.add_argument('--256',dest='palette',action='store_true',help='use the xterm 256-color palette')
    colors.add_argument('--truecolor',action='store_true',help='use 24-bit RGB color')
    parser.add_argument('--fps',type=int,default=24,help='frame limit (default: 24)')
    parser.add_argument('--max-width',type=int,default=160,help='maximum render columns (default: 160)')
    parser.add_argument('--aspect',type=float,help='cell width / cell height, e.g. 0.5')
    parser.add_argument('--shot',action='store_true',help='export HTML and ANSI previews without a terminal')
    parser.add_argument('--watch',action='store_true',help='start in zero-player City Watch mode')
    parser.add_argument('--profile',action='store_true',help='print offline update/render/encode timings as JSON')
    parser.add_argument('--profile-frames',type=int,default=60,help='number of frames for --profile')
    parser.add_argument('--output',type=Path,default=Path('previews/afterlight.html'))
    parser.add_argument('--save-path',type=Path,help='override the interactive save file location')
    parser.add_argument('--settings-path',type=Path,help='override the user settings file location')
    parser.add_argument('--size',default='120x40',help='preview columns x scene rows')
    args=parser.parse_args(argv)
    named={'dawn':6.3,'day':12.,'dusk':17.2,'night':23.}
    try: args.hour=named[args.hour] if args.hour in named else float(args.hour)
    except ValueError: parser.error('--time must be dawn/day/dusk/night or an hour from 0 to 24')
    if not 0<=args.hour<=24: parser.error('--time hour must be from 0 to 24')
    if not 5<=args.fps<=60: parser.error('--fps must be from 5 to 60')
    if not 40<=args.max_width<=240: parser.error('--max-width must be from 40 to 240')
    if args.aspect is not None and not .25<=args.aspect<=1: parser.error('--aspect must be from 0.25 to 1')
    if args.profile:
        if args.profile_frames < 1 or args.profile_frames > 10000: parser.error('--profile-frames must be from 1 to 10000')
        try: cols,rows=map(int,args.size.lower().split('x'))
        except ValueError: parser.error('--size must be COLSxROWS')
        if not 40<=cols<=240 or not 13<=rows<=100: parser.error('--size must be COLSxROWS, between 40x13 and 240x100')
        profile_preview(args)
    elif args.shot:
        try:
            cols,rows=map(int,args.size.lower().split('x'))
            if not 40<=cols<=240 or not 13<=rows<=100: raise ValueError
        except ValueError: parser.error('--size must be COLSxROWS, between 40x13 and 240x100')
        world=make_world(args.seed,args.hour,args.weather)
        world.time=2.5
        buf=frame(world,Renderer(cols,rows,args.aspect or .5),truecolor=not args.palette)
        path=args.output.resolve().with_suffix('.html'); path.parent.mkdir(parents=True,exist_ok=True)
        export_html(buf,path,args.aspect or .5)
        path.with_suffix('.ans').write_text(encode(buf,not args.palette))
        print(path)
        print(path.with_suffix('.ans'))
    else:
        try: play(args)
        except KeyboardInterrupt: pass
        except RuntimeError as exc:
            print(f'Glyph City: {exc}',file=sys.stderr)
            return 1
    return 0
