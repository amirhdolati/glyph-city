"""Checks for readable sprites, occlusion, and the optional object guide."""
import math
import unittest

from glyph_city.game import make_world
from glyph_city.city import Prop
from glyph_city.interiors import furniture
from glyph_city.render import Renderer, sprite_character
from glyph_city.terminal import color256, palette_rgb, palette_preview, encode


class VisualIdentityChecks(unittest.TestCase):
    def test_blue_sky_stays_blue_in_256_colors(self):
        for source in ((52,92,132),(56,100,148),(85,120,158),(132,169,211)):
            with self.subTest(source=source):
                r,g,b=palette_rgb(color256(source))
                self.assertLess(r,g)
                self.assertLess(g,b)

    def test_fixed_palette_roundtrips_without_dither_or_color_drift(self):
        for index in range(16,256):
            rgb=palette_rgb(index)
            self.assertEqual(palette_rgb(color256(rgb)),rgb)

    def test_256_preview_matches_terminal_escape_colors(self):
        fg,bg=(180,140,90),(52,92,132)
        cells=[[('A',fg,bg)]]
        preview=palette_preview(cells)
        self.assertEqual(preview,[[('A',palette_rgb(color256(fg)),palette_rgb(color256(bg)))]])
        ansi=encode(cells,False)
        self.assertIn('38;5;'+str(color256(fg)),ansi)
        self.assertIn('48;5;'+str(color256(bg)),ansi)

    def test_pedestrian_head_is_not_repeated_at_fractional_projections(self):
        world=make_world(hour=12,weather='clear')
        world.x,world.y,world.angle=60,78,-math.pi/2
        for distance in (6,12,16,20):
            for offset in (0,.2,.7):
                with self.subTest(distance=distance,offset=offset):
                    p=Prop(60+offset,78-distance,'person')
                    world.city.props=[p]
                    renderer=Renderer(112,35)
                    buf=renderer.render(world)
                    heads=sum(ch=='o' and renderer._sprite_owner[r][c]==id(p)
                              for r,row in enumerate(buf) for c,(ch,_,_) in enumerate(row))
                    self.assertEqual(heads,1)

    def test_magnified_eye_is_one_glyph_and_pole_is_continuous(self):
        eye=[sprite_character(('o',),x+.5,1.5,7,3)[0] for x in range(7)]
        self.assertEqual(eye.count('o'),1)
        pole=[sprite_character(('|',),3.5,y+.5,7,6)[0] for y in range(6)]
        self.assertEqual(pole,['|']*6)

    def test_shops_have_distinct_identifying_objects(self):
        for sign,material in (('BOOKS','book'),('VINYL','record'),
                              ('FLORA','flower'),('HOTEL','pillow'),
                              ('CAFE','cup'),('RAMEN','bowl')):
            with self.subTest(sign=sign):
                self.assertIn(material,{box[2] for box in furniture(sign,8,4)})

    def test_rain_preserves_signs_and_object_features(self):
        renderer=Renderer(60,20)
        renderer.world=make_world(hour=23,weather='storm')
        renderer.horizon=9
        renderer.buffer=[[('A',(180,140,90),(10,20,30))]*60 for _ in range(20)]
        before=[row[:] for row in renderer.buffer]
        renderer._weather()
        self.assertEqual(renderer.buffer,before)

    def test_labels_exclude_fully_occluded_objects(self):
        renderer=Renderer(60,20)
        renderer.buffer=[[(' ',(0,0,0),(0,0,0))]*60 for _ in range(20)]
        renderer.depth=[[100]*60 for _ in range(20)]
        renderer._sprite_owner=[[None]*60 for _ in range(20)]
        renderer._sprite_owner[10][30]=2
        renderer._labels=[(8,30,10,'Hidden resident','',1),
                          (4,30,10,'Visible resident','',2)]
        renderer._draw_labels()
        text='\n'.join(''.join(c[0] for c in row) for row in renderer.buffer)
        self.assertIn('Visible resident',text)
        self.assertNotIn('Hidden resident',text)

    def test_guide_is_optional_and_works_without_watch_names(self):
        world=make_world(hour=15,weather='clear')
        world.x,world.y,world.angle=48,56,-math.pi/2
        world.show_names=False
        renderer=Renderer(120,40)
        plain=renderer.render(world)
        world.identify=True
        guide=renderer.render(world)
        text='\n'.join(''.join(c[0] for c in row) for row in guide)
        self.assertIn('B IDENTIFY',text)
        self.assertIn('Wooden bench',text)
        self.assertNotIn('B IDENTIFY',''.join(c[0] for row in plain for c in row))
        self.assertTrue(all(32<=ord(c[0])<127 for row in guide for c in row))


if __name__=='__main__':
    unittest.main()
