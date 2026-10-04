"""Regression checks for city traversal, terminal output, and terminal ownership."""
import collections
import hashlib
import json
import math
import os
from pathlib import Path
import re
import select
import subprocess
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace

from glyph_city.city import City, Prop, World, SIZE
from glyph_city.game import frame, make_world, start_menu, _interaction_visible
from glyph_city.render import (REFLECTION_MASK, WETNESS_MASK, Renderer,
                               fog_factor, reflection_noise, reflection_tick,
                               shadow_band, local_light, window_interior)
from glyph_city.interiors import room_pixel
from glyph_city.save import SaveStore
from glyph_city.terminal import Event, FrameSnapshot, Input, InputState, dirty_rows, dirty_spans, encode, encode_delta

ROOT=Path(__file__).resolve().parents[1]


class CityChecks(unittest.TestCase):
    def test_interaction_visibility_rejects_walls(self):
        city=City()
        self.assertFalse(_interaction_visible(city,70.5,39.5,70.5,42.5))
        self.assertTrue(_interaction_visible(city,69.5,40.0,69.5,42.5))

    def test_original_snapshot_is_unchanged(self):
        folder=ROOT/'legacy/v1'
        manifest=json.loads((folder/'snapshot.json').read_text())
        for name,digest in manifest['files'].items():
            self.assertEqual(hashlib.sha256((folder/name).read_bytes()).hexdigest(),digest,name)

    def test_every_landmark_is_reachable_on_foot(self):
        city=City(); start=(60,78); visited={start}; todo=collections.deque([start])
        while todo:
            x,y=todo.popleft()
            for nx,ny in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
                if (nx,ny) not in visited and city.walkable(nx+.5,ny+.5):
                    visited.add((nx,ny)); todo.append((nx,ny))
        for p in city.landmarks:
            self.assertIn((int(p.x),int(p.y)),visited,p.name)
        self.assertGreater(len(visited),4000)

    def test_walking_slides_at_walls_without_entering_them(self):
        city=City(); w=World(city,x=56.6,y=74,angle=math.pi)
        self.assertTrue(city.walkable(w.x,w.y))
        for _ in range(80):
            w.update(.1,{'w'},sprint=True)
            self.assertTrue(city.walkable(w.x,w.y))
        self.assertGreaterEqual(w.x,56.24)
        y=w.y
        for _ in range(10): w.update(.1,{'w','a'})
        self.assertGreater(w.y,y)  # slide down the facade while forward is blocked

    def test_time_weather_and_photo_pause(self):
        w=make_world(hour=23.99);w.weather=1
        for _ in range(100): w.update(.1,{})
        self.assertLess(w.clock,1)
        self.assertGreater(w.rain,.6);self.assertGreater(w.wet,.5)
        w.paused=True
        before=(w.time,w.clock,w.rain,w.wet)
        w.update(.1,{'w'})
        self.assertEqual(before,(w.time,w.clock,w.rain,w.wet))

    def test_reflection_noise_is_world_stable_and_slowly_animated(self):
        # A fixed camera/world position must not hash against screen cells or
        # the continuously changing clock value on every frame.
        seed = City().seed
        self.assertEqual(reflection_tick(4.01), reflection_tick(4.49))
        first = reflection_noise(60.25, 78.75, seed, reflection_tick(4.01))
        second = reflection_noise(60.25, 78.75, seed, reflection_tick(4.49))
        self.assertEqual(first, second)
        self.assertNotEqual(
            first,
            reflection_noise(60.75, 78.75, seed, reflection_tick(4.01)),
        )
        self.assertNotEqual(reflection_tick(4.01), reflection_tick(4.51))

    def test_reflection_and_wetness_masks_exclude_grass(self):
        self.assertNotIn('g', REFLECTION_MASK)
        self.assertNotIn('g', WETNESS_MASK)
        for tile in ('w', 'r', 'p', 'b'):
            self.assertGreater(REFLECTION_MASK[tile], 0)
            self.assertGreater(WETNESS_MASK[tile], 0)

    def test_fog_is_smooth_and_shadow_band_is_deterministic(self):
        values=[fog_factor(distance,48) for distance in (0,8,16,32,48,80)]
        self.assertEqual(values,sorted(values))
        self.assertEqual(values[0],0)
        self.assertLessEqual(values[-1],.88)
        self.assertEqual(shadow_band(12.4,38.2,17),shadow_band(12.4,38.2,17))

    def test_local_light_keeps_dusk_and_night_lamps_visible(self):
        self.assertGreater(local_light(.8,1.0),local_light(.8,.2))
        self.assertGreater(local_light(.6,.8),.6)

    def test_window_interiors_are_deterministic_and_shop_specific(self):
        cafe=window_interior('CAFE',17,2,1,.8)
        bar=window_interior('BAR',17,2,1,.8)
        self.assertEqual(cafe,window_interior('CAFE',17,2,1,.8))
        self.assertNotEqual(cafe,bar)

    def test_ground_floor_room_has_depth_and_furniture(self):
        wall=room_pixel('CAFE',8,4,2,1.4,(0,1,0))
        counter=room_pixel('CAFE',8,4,2,1.0,(0,1,0))
        self.assertNotEqual(wall[2],counter[2])
        adult=room_pixel('18+',8,4,2,1.0,(0,1,0))
        self.assertGreater(adult[2][0],adult[2][1])
        self.assertGreater(adult[2][2],adult[2][1])

    def test_sprite_lod_switches_by_projected_size_and_distance(self):
        renderer = Renderer(80, 24)
        tree = Prop(60.0, 78.0, 'tree')
        self.assertEqual(renderer.sprite_lod(tree, 12.0), 1)
        self.assertEqual(renderer.sprite_lod(tree, 44.0), 0)
        # Main moving/landmark-like props retain their authored glyphs.
        self.assertEqual(renderer.sprite_lod(Prop(60.0, 78.0, 'person'), 44.0), 1)

    def test_sprite_lod_hysteresis_is_stable_near_threshold(self):
        renderer = Renderer(80, 24)
        tree = Prop(60.0, 78.0, 'tree')
        self.assertEqual(renderer.sprite_lod(tree, 44.0), 0)
        # Entering detail needs the lower distance threshold, so small camera
        # changes around the exit threshold do not make the glyph shimmer.
        self.assertEqual(renderer.sprite_lod(tree, 41.0), 0)
        self.assertEqual(renderer.sprite_lod(tree, 39.0), 1)
        self.assertEqual(renderer.sprite_lod(tree, 40.5), 1)


class TerminalChecks(unittest.TestCase):
    def test_start_menu_new_walk_and_continue(self):
        class FakeTerminal:
            def __init__(self, events): self.events_left=list(events)
            def clear(self): pass
            def size(self): return 80,24
            def draw(self,*args,**kwargs): pass
            def events(self):
                return [self.events_left.pop(0)] if self.events_left else []

        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'save.json'
            args=SimpleNamespace(save_path=path,seed=41,hour=12.,weather='clear')
            created=start_menu(FakeTerminal([Event('\r')]),args)
            self.assertEqual(created.city.seed,41)
            store=SaveStore(path)
            store.save_world(created)
            continued=start_menu(FakeTerminal([Event('\r')]),args,store)
            self.assertEqual(continued.city.seed,41)

    @staticmethod
    def apply_cells(screen, ansi):
        r=c=0;i=0
        while i<len(ansi):
            if ansi[i]=='\x1b':
                match=re.match(r'\x1b\[([0-9;]*)([Hm])',ansi[i:])
                if match:
                    if match[2]=='H': r,c=(int(n)-1 for n in match[1].split(';'))
                    i+=match.end();continue
                sgr=re.match(r'\x1b\[[0-9;]*m',ansi[i:])
                if sgr:
                    i+=sgr.end();continue
                raise AssertionError(f'unexpected ANSI sequence at {ansi[i:]!r}')
            if not (0<=r<len(screen) and 0<=c<len(screen[r])):
                raise AssertionError(f'write outside screen at {(r,c)}')
            screen[r][c]=ansi[i];c+=1;i+=1
        return screen

    def test_delta_snapshot_skips_unchanged_and_patches_exact_spans(self):
        old=[[('A',(255,0,0),(0,0,0)),('B',(255,0,0),(0,0,0)),('C',(255,0,0),(0,0,0)),
              ('D',(255,0,0),(0,0,0))],
             [(' ',(255,255,255),(0,0,0)),('x',(0,255,0),(0,0,0)),(' ',(255,255,255),(0,0,0)),
              (' ',(255,255,255),(0,0,0))]]
        changed=[row[:] for row in old]
        changed[0][1]=(' ',(255,255,255),(0,0,0))
        changed[0][3]=('Z',(0,0,255),(10,10,10))
        changed[1][1]=('y',(0,255,0),(0,0,0))
        self.assertEqual(dirty_rows(old,old),[])
        self.assertEqual(dirty_spans(old,changed),[(0,1,2),(0,3,4),(1,1,2)])
        cache=FrameSnapshot()
        first=cache.encode(old,True,1,1)
        screen=[['?']*4 for _ in old]
        self.apply_cells(screen,first)
        self.assertEqual([''.join(row) for row in screen],['ABCD',' x  '])
        self.assertEqual(cache.encode(old,True,1,1),'')
        delta=cache.encode(changed,True,1,1)
        written=re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', delta)
        self.assertEqual(len(written),3)
        self.apply_cells(screen,delta)
        self.assertEqual([''.join(row) for row in screen],['A CZ',' y  '])

    def test_delta_snapshot_resize_and_invalidation_force_full_frame(self):
        first=[[('a',(255,255,255),(0,0,0)),('b',(255,255,255),(0,0,0))]]
        resized=[[('c',(255,255,255),(0,0,0)),('d',(255,255,255),(0,0,0)),('e',(255,255,255),(0,0,0))],
                 [('f',(255,255,255),(0,0,0)),('g',(255,255,255),(0,0,0)),('h',(255,255,255),(0,0,0))]]
        cache=FrameSnapshot()
        cache.encode(first)
        full=cache.encode(resized)
        self.assertEqual(full,encode(resized))
        screen=[['?']*3 for _ in resized]
        self.apply_cells(screen,full)
        self.assertEqual([''.join(row) for row in screen],['cde','fgh'])
        cache.invalidate()
        self.assertTrue(cache.encode(resized))
        self.assertEqual(encode_delta(resized,[[row[0],row[1],row[2]] for row in resized]),'')

    def test_input_state_keeps_enhanced_chord_until_each_release(self):
        state=InputState()
        state.apply(Input().feed(b'\x1b[119;1:1u',now=1)[0],1)
        state.apply(Input().feed(b'\x1b[100;1:1u',now=1.1)[0],1.1)
        held,shifts=state.snapshot(2)
        self.assertEqual(set(held),{'w','d'})
        self.assertFalse(shifts)
        state.apply(Input().feed(b'\x1b[100;1:3u',now=2.1)[0],2.1)
        held,_=state.snapshot(2.1)
        self.assertEqual(set(held),{'w'})
        state.apply(Input().feed(b'\x1b[119;1:3u',now=2.2)[0],2.2)
        self.assertEqual(state.snapshot(2.2)[0],{})

    def test_input_state_focus_out_clears_keys_and_shifts(self):
        state=InputState()
        reader=Input()
        for payload in (b'\x1b[119;1:1u',b'\x1b[57441;1:1u'):
            state.apply(reader.feed(payload)[0],1)
        self.assertTrue(state.snapshot(1)[0])
        self.assertTrue(state.snapshot(1)[1])
        self.assertTrue(state.apply(Event('focus-out'),2))
        self.assertEqual(state.snapshot(2),({},set()))

    def test_legacy_chord_does_not_drop_first_key_and_has_brake(self):
        state=InputState()
        state.apply(Event('w'),1.0)
        state.apply(Event('d'),1.1)
        held,_=state.snapshot(1.2)
        self.assertEqual(set(held),{'w','d'})
        self.assertTrue(state.legacy_chord)
        held,_=state.snapshot(10.0)
        self.assertEqual(set(held),set())
        state.clear_movement()
        self.assertEqual(state.snapshot(10.0),({},set()))

    def test_legacy_turn_does_not_latch_or_refresh_walk(self):
        state=InputState()
        state.apply(Event('w'),1.0)
        state.apply(Event('q'),1.1)
        held,_=state.snapshot(1.2)
        self.assertEqual(set(held),{'w','q'})
        held,_=state.snapshot(1.5)
        self.assertEqual(set(held),set())

    def test_turn_repeat_keeps_walk_chord_without_latching_turn(self):
        state=InputState()
        state.apply(Event('w'),1.0)
        state.apply(Event('d'),1.1)
        state.apply(Event('q'),1.2)
        held,_=state.snapshot(1.3)
        self.assertEqual(set(held),{'w','d','q'})
        state.apply(Event('d'),1.5)
        held,_=state.snapshot(1.6)
        self.assertEqual(set(held),{'w','d'})

    def test_shift_is_independent_from_walking_and_release(self):
        state=InputState()
        reader=Input()
        state.apply(reader.feed(b'\x1b[119;1:1u')[0],1)
        state.apply(reader.feed(b'\x1b[57441;1:1u')[0],1.01)
        held,shifts=state.snapshot(2)
        self.assertIn('w',held)
        self.assertEqual(shifts,{'shift-left'})
        state.apply(reader.feed(b'\x1b[57441;1:3u')[0],2.01)
        self.assertEqual(state.snapshot(2.01)[1],set())
        self.assertFalse(state.snapshot(2.01)[0]['w'][1])

    def test_real_frames_round_trip_to_exact_terminal_cells(self):
        for hour,weather in ((12,'clear'),(23,'rain')):
            w=make_world(hour=hour,weather=weather)
            buf=frame(w,Renderer(80,21))
            expected=[''.join(c[0] for c in row) for row in buf]
            for mode in (True,False):
                ansi=encode(buf,mode); screen=[['?']*80 for _ in range(24)]
                r=c=i=0
                while i<len(ansi):
                    if ansi[i]=='\x1b':
                        m=re.match(r'\x1b\[([0-9;]*)([Hm])',ansi[i:])
                        self.assertIsNotNone(m)
                        if m[2]=='H': r,c=(int(n)-1 for n in m[1].split(';'))
                        i+=m.end()
                    else:
                        self.assertTrue(0<=r<24 and 0<=c<80,(r,c))
                        self.assertTrue(32<=ord(ansi[i])<=126)
                        screen[r][c]=ansi[i];c+=1;i+=1
                self.assertEqual([''.join(row) for row in screen],expected)

    def test_fragmented_and_enhanced_keyboard_events(self):
        reader=Input()
        self.assertEqual(reader.feed(b'\x1b[119;2:',now=1),[])
        event=reader.feed(b'1u',now=1.01)[0]
        self.assertEqual(event.key,'w');self.assertTrue(event.shift and event.enhanced)
        self.assertTrue(reader.feed(b'\x1b[119;2:3u')[0].release)
        self.assertTrue(reader.feed(b'\x1b[1;1:3A')[0].release)
        self.assertEqual(reader.feed(b'\x1b[99;5u')[0].key,'exit')
        self.assertEqual(reader.feed(b'\x1b[6;16;8tW')[0].key,'w')
        self.assertEqual(reader.feed(b'\x1b[O')[0].key,'focus-out')
        self.assertEqual(reader.feed(b'\x1b[57360u'),[])  # Num Lock must not teleport the player.
        reader.feed(b'\x1b',now=2)
        self.assertEqual(reader.feed(now=2.1)[0].key,'exit')

    @unittest.skipUnless(os.name=='posix','requires a POSIX pseudo terminal')
    def test_live_play_resize_controls_and_terminal_restoration(self):
        import fcntl,pty,struct,termios
        master,slave=pty.openpty()
        old=termios.tcgetattr(slave)
        def resize(cols,rows):
            fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',rows,cols,cols*8,rows*16))
        resize(80,24)
        env=dict(os.environ,TERM='xterm-256color',COLORTERM='')
        proc=subprocess.Popen([sys.executable,'main.py','--256'],cwd=ROOT,
                              stdin=slave,stdout=slave,stderr=slave,env=env,close_fds=True)
        captured=bytearray()
        def until(needle,timeout=5):
            block=bytearray(); deadline=time.monotonic()+timeout
            while time.monotonic()<deadline:
                if select.select([master],[],[],.05)[0]:
                    data=os.read(master,65536);block.extend(data);captured.extend(data)
                    if needle in block: return bytes(block)
                if proc.poll() is not None: break
            self.fail(f'missing {needle!r}; exit={proc.poll()}; tail={bytes(block[-500:])!r}')
        try:
            until(b'\x1b[?2026l')
            os.write(master,b'ry')
            until(b'RAIN')
            resize(100,30);until(b'\x1b[30;1H')
            os.write(master,b'h');until(b'Close this guide')
            os.write(master,b'h')
            resize(30,10);until(b'Enlarge terminal')
            resize(80,24);until(b'\x1b[24;1H')
            os.write(master,b'\x03')
            until(b'\x1b[?1049l')
            proc.wait(timeout=3)
            self.assertEqual(proc.returncode,0)
            restored=termios.tcgetattr(slave)
            # BSD may mark buffered input for retyping when canonical mode returns.
            pending=getattr(termios,'PENDIN',0)
            restored[3]&=~pending;old[3]&=~pending
            self.assertEqual(restored,old)
            self.assertNotIn(b'Traceback',captured)
        finally:
            if proc.poll() is None: proc.kill();proc.wait()
            os.close(master);os.close(slave)


if __name__=='__main__': unittest.main()
