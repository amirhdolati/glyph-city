"""Render shareable PNG/GIF previews from the deterministic terminal renderer."""
from pathlib import Path
import math
import sys
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from glyph_city.game import make_world, frame
from glyph_city.living import LivingCity
from glyph_city.render import Renderer
from glyph_city.director import Director

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs'/'media'
FONT_PATH='/System/Library/Fonts/Menlo.ttc'
try:
    FONT=ImageFont.truetype(FONT_PATH,14)
except OSError:
    FONT=ImageFont.load_default()
CELL_W,CELL_H=9,18


def draw_frame(cells, path):
    height=len(cells); width=max(len(row) for row in cells)
    image=Image.new('RGB',(width*CELL_W,height*CELL_H),(5,10,16))
    draw=ImageDraw.Draw(image)
    for y,row in enumerate(cells):
        for x,(char,fg,bg) in enumerate(row):
            left,top=x*CELL_W,y*CELL_H
            draw.rectangle((left,top,left+CELL_W,top+CELL_H),fill=bg)
            if char!=' ':
                draw.text((left,top-2),char,font=FONT,fill=fg)
    image.save(path,optimize=True)
    return image


def build_world(hour, weather):
    world=make_world(hour=hour,weather=weather)
    world.life=LivingCity(world)
    world.observing=True; world.show_names=True
    return world


def render(world, renderer, director=None):
    if director:
        director.update(0.7,world=world)
        view=director.view(world)
    else:
        view=world
    return frame(view,renderer,truecolor=True)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    renderer=Renderer(96,28,.5)
    stills=(('night-rain',build_world(23,'rain')),
            ('day-market',build_world(12,'clear')),
            ('storm-canal',build_world(20,'storm')))
    for name,world in stills:
        draw_frame(render(world,renderer),OUT/(name+'.png'))
    world=build_world(21,'rain'); director=Director(); frames=[]
    for _ in range(32):
        world.update(.7,{})
        frames.append(draw_frame(render(world,renderer,director),OUT/'_frame.png').copy())
    frames[0].save(OUT/'city-watch.gif',save_all=True,append_images=frames[1:],duration=180,loop=0,optimize=False)
    (OUT/'_frame.png').unlink(missing_ok=True)


if __name__=='__main__': main()
