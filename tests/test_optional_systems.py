import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from glyph_city.audio import create_audio
from glyph_city.events import available_events
from glyph_city.game import export_html, frame, make_world
from glyph_city.render import Renderer
from glyph_city.scenes import portal_for
from glyph_city.transit import BoatRide
from glyph_city.vertical import elevation_at
from glyph_city.director import Director, SHOTS
from glyph_city.living import LivingCity, shop_open
from glyph_city.photos import PhotoAlbum
from glyph_city.terminal import encode
from glyph_city.journal import Journal


class OptionalSystemsChecks(unittest.TestCase):
    def test_events_are_time_gated(self):
        self.assertTrue(available_events(19))
        self.assertFalse(available_events(3))

    def test_silent_audio_never_blocks(self):
        audio=create_audio(volume=.5)
        self.assertIn(audio.play('rain'), (True,False))
        audio.stop()

    def test_scene_portal_and_transit_roundtrip(self):
        self.assertEqual(portal_for('afterlight',69.5,42.5).to_scene,'cafe')
        ride=BoatRide(); self.assertTrue(ride.board('canal_north'))
        ride.update(18); self.assertEqual(ride.disembark(),'canal_south')

    def test_cafe_scene_has_independent_walk_bounds_and_frame(self):
        world=make_world(); world.scene_id='cafe'; world.x,world.y=8,10
        world.update(1.0,{'w'})
        self.assertGreater(world.y,2); self.assertLessEqual(world.y,10)
        self.assertEqual(len(frame(world,Renderer(64,20))),23)

    def test_vertical_sample_is_bounded(self):
        self.assertEqual(elevation_at(84.5,36.5),2.0)
        self.assertEqual(elevation_at(10,10),0.0)

    def test_director_cycles_smooth_shots_without_mutating_player(self):
        world=make_world(); original=(world.x,world.y)
        director=Director(); view=director.view(world)
        self.assertEqual(view.scene_id,'afterlight')
        self.assertEqual((world.x,world.y),original)
        director.elapsed=director.shot.duration-.01; director.update(.1)
        self.assertEqual(director.index,1)
        self.assertEqual(len(SHOTS),7)

    def test_director_eases_into_a_live_npc_event(self):
        world=make_world(); life=LivingCity(world); world.life=life
        subject=life.residents[0].prop; subject.dialogue='The kettle is ready.'; life.focus=subject
        director=Director(); origin=(director.view(world).x,director.view(world).y)
        director.update(.2,world=world)
        view=director.view(world)
        self.assertIs(director.subject,subject)
        self.assertNotEqual((view.x,view.y),origin)
        self.assertIn(subject.name,view.shot_name)

    def test_living_city_uses_shelter_and_named_residents(self):
        world=make_world(weather='rain'); living=LivingCity(world)
        self.assertTrue(living.residents)
        self.assertTrue(all(getattr(item.prop,'name','') for item in living.residents))
        living.update(world,.2)
        self.assertTrue(any(item.prop.activity in ('walking','sheltering','resting','chatting')
                            for item in living.residents))
        self.assertTrue(shop_open('LOUNGE',22)); self.assertFalse(shop_open('CAFE',3))

    def test_living_city_stages_a_multi_step_public_event(self):
        world=make_world(); living=LivingCity(world); world.life=living
        living.next_event=0
        world.update(.2,{})
        self.assertIsNotNone(living.public_event)
        first=living.caption
        world.update(8,{})
        self.assertNotEqual(living.caption,first)
        self.assertTrue(living.history)

    def test_photo_album_writes_metadata_and_reloads(self):
        world=make_world(hour=23, weather='rain')
        cells=Renderer(64,20).render(world)
        with TemporaryDirectory() as directory:
            album=PhotoAlbum(Path(directory))
            photo=album.capture(world,cells,export_html=export_html,
                                 encode_ansi=encode,aspect=.5,truecolor=True)
            self.assertTrue((Path(directory)/photo.html_path).is_file())
            self.assertEqual(album.entries()[0].id,photo.id)

    def test_journal_overlay_renders_selected_destination(self):
        world=make_world(); journal=Journal()
        entry=journal.record('park',kind='landmark',title='Willow Gardens',
                             text='A quiet place.',target=(48,50),status='complete')
        cells=frame(world,Renderer(64,20),journal_view=((entry,),0))
        self.assertEqual(len(cells),23)
        self.assertTrue(any('JOURNAL' in ''.join(cell[0] for cell in row) for row in cells))


if __name__ == '__main__':
    unittest.main()
