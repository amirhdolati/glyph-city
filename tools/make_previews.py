"""Render shareable PNG/GIF previews from the deterministic terminal renderer."""
from pathlib import Path
import argparse
import sys
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from glyph_city.game import make_world, frame
from glyph_city.living import LivingCity
from glyph_city.render import Renderer
from glyph_city.director import Director
from glyph_city.terminal import palette_preview

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs'/'media'
FONT_PATH='/System/Library/Fonts/Menlo.ttc'
try:
    FONT=ImageFont.truetype(FONT_PATH,14)
except OSError:
    FONT=ImageFont.load_default()
CELL_W,CELL_H=9,18


def draw_frame(cells, path=None, truecolor=True):
    if not truecolor:
        cells=palette_preview(cells)
    height=len(cells); width=max(len(row) for row in cells)
    image=Image.new('RGB',(width*CELL_W,height*CELL_H),(5,10,16))
    draw=ImageDraw.Draw(image)
    for y,row in enumerate(cells):
        for x,(char,fg,bg) in enumerate(row):
            left,top=x*CELL_W,y*CELL_H
            draw.rectangle((left,top,left+CELL_W,top+CELL_H),fill=bg)
            if char!=' ':
                draw.text((left,top-2),char,font=FONT,fill=fg)
    if path is not None:
        image.save(path,optimize=True)
    return image


def build_world(hour, weather):
    world=make_world(hour=hour,weather=weather)
    world.life=LivingCity(world)
    world.life.update(world,0)
    world.observing=True; world.show_names=True
    world.camera_bob_enabled=False; world.storm_flash_enabled=False
    return world


def render(world, renderer, director=None):
    if director:
        view=director.view(world)
    else:
        view=world
    return frame(view,renderer,truecolor=True)


def camera_at(shot_index, elapsed):
    director=Director(shot_index)
    director.elapsed=elapsed
    director.pose=director._shot_pose()
    return director


def cinematic(world, renderer, shot_index, elapsed):
    """Render a still from a deliberate City Watch composition."""
    return draw_frame(render(world,renderer,camera_at(shot_index,elapsed)))


def make_stills():
    renderer=Renderer(180,56,.5)
    stills=(('night-rain',build_world(23,'rain'),5,16.0),
            ('day-market',build_world(13,'clear'),2,22.0),
            ('storm-canal',build_world(20,'storm'),3,28.0),
            ('glass-quarter',build_world(18,'mist'),4,12.0),
            ('willow-gardens',build_world(15,'clear'),1,20.0),
            ('rooftop-corner',build_world(19,'clear'),7,24.0),
            ('moonwater-dusk',build_world(18,'clear'),6,65.0),
            ('moonwater-night',build_world(21,'rain'),6,65.0),
            ('bridge-afterglow',build_world(17.5,'clear'),9,28.0))
    for name,world,shot_index,elapsed in stills:
        world.time=24
        image=cinematic(world,renderer,shot_index,elapsed)
        image.save(OUT/(name+'.png'),optimize=True)
        print('Still:',name,flush=True)
    # Match the user's morning avenue view in BOTH actual output palettes.
    avenue=build_world(8.47,'clear'); camera=Director()
    cells=frame(camera.view(avenue),renderer,truecolor=False)
    draw_frame(cells,OUT/'avenue-256.png',truecolor=False)
    draw_frame(frame(camera.view(avenue),renderer),OUT/'avenue-rgb.png')


def make_watch():
    """Twenty seconds of actual City Watch motion, edited into three shots.

    Simulation and playback both run at 10 frames per second. The old preview
    advanced 0.7 seconds per 0.15-second frame, accelerating every movement.
    All captures use the RGB renderer. GIF necessarily reduces the colors;
    a shared palette avoids frame-to-frame palette shimmer. Lossless animated
    WebP retains the RGB output as a companion download.
    """
    renderer=Renderer(144,46,.5)
    fps=10; frames=[]
    for hour,weather,shot,elapsed,seconds in (
            (18,'clear',6,60.,8),
            (17.5,'clear',9,25.,6),
            (21,'rain',6,65.,6)):
        world=build_world(hour,weather)
        world.clock_running=False
        # Let inhabitants settle while retaining the chosen lighting.
        for _ in range(120): world.update(.1,{})
        director=camera_at(shot,elapsed)
        director.next_focus=float('inf')
        for _ in range(seconds*fps):
            world.update(1/fps,{})
            director.update(1/fps,world=world)
            frames.append(draw_frame(render(world,renderer,director)))
        print('Watch shot:',director.shot.name,flush=True)
    frames[0].save(OUT/'city-watch.webp',save_all=True,append_images=frames[1:],
                   duration=100,loop=0,lossless=True,method=4)
    samples=frames[::10]
    atlas=Image.new('RGB',(324,245*len(samples)))
    for index,im in enumerate(samples):
        atlas.paste(im.resize((324,245)),(0,index*245))
    palette=atlas.quantize(colors=256,method=Image.Quantize.MEDIANCUT)
    indexed=[im.quantize(palette=palette,dither=Image.Dither.NONE) for im in frames]
    indexed[0].save(OUT/'city-watch.gif',save_all=True,append_images=indexed[1:],
                    duration=100,loop=0,optimize=False,disposal=1)
    print('Saved 20-second GIF and lossless RGB WebP.',flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--stills-only',action='store_true')
    mode.add_argument('--watch-only',action='store_true')
    args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    if not args.watch_only: make_stills()
    if not args.stills_only: make_watch()


if __name__=='__main__': main()
