"""Rebuild the original, deterministic PCM sound bank used by the game."""
from pathlib import Path
import sys
import wave

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from glyph_city.audio import ASSET_DIR, Mixer, RATE, np


def write(path, data):
    channels=1 if data.ndim==1 else data.shape[1]
    with wave.open(str(path),'wb') as stream:
        stream.setnchannels(channels)
        stream.setsampwidth(2)
        stream.setframerate(RATE)
        stream.writeframes(np.clip(data*32767,-32767,32767).astype('<i2').tobytes())


def main():
    if np is None:
        raise SystemExit('Install numpy to rebuild the audio bank.')
    ASSET_DIR.mkdir(parents=True,exist_ok=True)
    mixer=Mixer(generate=True)
    for cue,data in mixer.banks.items():
        write(ASSET_DIR/(cue+'.wav'),data)
    for cue,variants in mixer.samples.items():
        for index,data in enumerate(variants,1):
            write(ASSET_DIR/f'{cue}-{index}.wav',data)
    mixer.close()
    print(f'Generated {len(mixer.banks)} stereo loops and '
          f'{sum(map(len,mixer.samples.values()))} Foley variants in {ASSET_DIR}')


if __name__=='__main__':
    main()
