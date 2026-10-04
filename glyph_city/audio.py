"""Continuous stereo soundscape. No per-cue processes, polling gaps or WAV loops."""
from dataclasses import dataclass
import math
import os
import sys
import threading
import subprocess
import tempfile
import wave
import shutil

try:
    import numpy as np
except ImportError:
    np = None

RATE = 24000


def spatial_gain(listener, x, y, radius=14):
    dx, dy = x-listener.x, y-listener.y
    distance = math.hypot(dx, dy)
    pan = (-dx*math.sin(listener.angle)+dy*math.cos(listener.angle))/max(distance, .1)
    gain = 1/(1+(distance/radius)**2)
    if distance>radius*5: gain=0
    return gain, max(-1, min(1, pan))


@dataclass
class SilentAudio:
    volume: float = 1.0
    muted: bool = False
    reason: str = 'Audio disabled'

    def play(self, cue, *, intensity=1.0): return False
    def start_loop(self, cue, *, intensity=1.0): return False
    def update(self, dt): pass
    def scene(self, world, listener, dt): pass
    def stop(self, cue=None): pass
    def close(self): self.stop()
    def set_volume(self, value): self.volume=max(0.,min(1.,float(value)))
    def __enter__(self): return self
    def __exit__(self, *args): self.close()


class Mixer(SilentAudio):
    """An independently clocked mixer; the game only supplies source locations."""
    def __init__(self, volume=1., muted=False):
        super().__init__(volume, muted, '')
        self.rng=np.random.default_rng(901)
        self.lock=threading.Lock()
        self.cursor=0
        self.targets={}
        self.gains={}
        self.voices=[]
        self.cooldowns={}
        self.clock=0.
        self.next_detail=2.
        self.last_scene=None
        self.status='streaming'
        self.backend=None
        # Independent prime-length textures prevent a short repeating pattern.
        self.banks={name:self.texture(seconds, low, high) for name,seconds,low,high in (
            ('rain',29,180,5500),('wind',31,35,650),('water',37,90,1700),
            ('traffic',23,45,380),('leaves',19,600,3500))}

    def texture(self, seconds, low, high):
        n=RATE*seconds
        frequencies=np.fft.rfftfreq(n,1/RATE)
        response=(frequencies/(frequencies+low))**2/(1+(frequencies/high)**3)
        response/=np.sqrt(np.maximum(frequencies,40))
        channels=[]
        for _ in range(2):
            spectrum=np.fft.rfft(self.rng.normal(size=n))*response
            values=np.fft.irfft(spectrum,n)
            values*=.11/max(float(np.std(values)),.001)
            channels.append(values)
        return np.column_stack(channels).astype('float32')

    def set_sources(self, sources):
        with self.lock:
            self.targets=dict(sources)

    def render(self, frames):
        """Also usable offline; gain ramps persist across every callback boundary."""
        output=np.zeros((frames,2),dtype='float32')
        with self.lock:
            targets=dict(self.targets)
            voices=self.voices
            self.voices=[]
        indices=self.cursor+np.arange(frames)
        for name in self.gains.keys() | targets.keys():
            cue, gain, pan=targets.get(name, (name.split(':')[0],0.,0.))
            if cue not in self.banks: continue
            target=np.array([math.sqrt((1-pan)/2),math.sqrt((1+pan)/2)])*gain
            previous=self.gains.get(name,np.zeros(2))
            # 350 ms response: no clicks on camera cuts or weather transitions.
            envelope=target+(previous-target)*np.exp(-np.arange(1,frames+1)[:,None]/(RATE*.35))
            self.gains[name]=envelope[-1]
            bank=self.banks[cue]
            modulation=.87+.13*np.sin(indices/RATE*.31+len(name))
            output+=bank[indices%len(bank)]*envelope*modulation[:,None]
        remaining=[]
        for data,offset,gain,pan in voices:
            count=min(frames,len(data)-offset)
            output[:count,0]+=data[offset:offset+count]*gain*math.sqrt((1-pan)/2)
            output[:count,1]+=data[offset:offset+count]*gain*math.sqrt((1+pan)/2)
            if offset+count<len(data): remaining.append((data,offset+count,gain,pan))
        with self.lock:
            self.voices=remaining+self.voices
        self.cursor+=frames
        return np.tanh(output*(0 if self.muted else self.volume)).astype('float32')

    def trigger(self, cue, gain=.3, pan=0):
        # No speech-like beeps: conversations are text, while Foley stays environmental.
        durations={'step':.22,'wetstep':.3,'door':.6,'bird':.65,'bell':2.4,'music':1.9,'thunder':5.0}
        if cue not in durations or gain<=.005: return False
        n=int(RATE*durations[cue]); t=np.arange(n)/RATE
        noise=self.rng.normal(size=n)
        if cue in ('step','wetstep','door','thunder'):
            width={'step':25,'wetstep':9,'door':55,'thunder':190}[cue]
            filtered=np.convolve(noise,np.ones(width)/math.sqrt(width),'same')
            decay={'step':25,'wetstep':17,'door':8,'thunder':.9}[cue]
            data=filtered*np.exp(-t*decay)*.10
        elif cue=='bird':
            frequency=self.rng.uniform(1700,2700)
            data=np.sin(2*math.pi*(frequency*t+350*t*t))*np.sin(math.pi*t/t[-1])**4*.045
        else:
            frequency=self.rng.choice([196.,220.,261.63,293.66,329.63])
            data=sum(np.sin(2*math.pi*frequency*ratio*t)*level*np.exp(-t*decay)
                     for ratio,level,decay in ((1,.09,2),(2.01,.025,3),(3.98,.01,6)))
        data*=np.minimum(1,t/.008)
        data[-min(n,240):]*=np.linspace(1,0,min(n,240))
        with self.lock:
            if len(self.voices)>=16: return False
            self.voices.append((data.astype('float32'),0,gain,pan))
        return True

    def play(self, cue, *, intensity=1.): return self.trigger(cue,intensity)
    def start_loop(self, cue, *, intensity=1.):
        if cue not in self.banks: return False
        with self.lock: self.targets[cue]=(cue,intensity,0.)
        return True

    def scene(self, world, listener, dt):
        self.clock+=dt
        interior=listener.scene_id not in ('afterlight','boat')
        sources={'rain':('rain',world.rain*(.12 if interior else .65),0.),
                 'wind':('wind',.025 if interior else .08+world.cloud*.1,0.)}
        nearby=[]
        if not interior:
            for index,p in enumerate(world.city.props):
                cue='water' if p.kind in ('boat','fountain') else 'traffic' if p.kind=='car' else 'leaves' if p.kind=='tree' else None
                gain,pan=spatial_gain(listener,p.x,p.y,9 if p.kind=='person' else 14)
                # Static geometry muffles sound behind buildings.
                if gain>.02 and any(world.city.solid(listener.x+(p.x-listener.x)*q/8,
                                                    listener.y+(p.y-listener.y)*q/8) for q in range(1,8)):
                    gain*=.25
                if cue: sources[f'{cue}:{index}']=(cue,gain*(.13 if cue=='leaves' else .28),pan)
                if p.kind=='person' and gain>.12:
                    nearby.append((p,gain,pan))
                    if p.activity=='walking' and self.clock>=self.cooldowns.get(index,0):
                        self.trigger('wetstep' if world.wet>.4 else 'step',gain*.25,pan)
                        self.cooldowns[index]=self.clock+self.rng.uniform(.48,.7)
        self.set_sources(sources)
        if not world.observing and math.hypot(world.velocity_x,world.velocity_y)>.35 and self.clock>=self.cooldowns.get('player',0):
            self.trigger('wetstep' if world.wet>.4 else 'step',.55)
            self.cooldowns['player']=self.clock+.45
        if self.last_scene is not None and world.scene_id!=self.last_scene:
            self.trigger('door',.3)
        self.last_scene=world.scene_id
        if self.clock>=self.next_detail:
            self.next_detail=self.clock+self.rng.uniform(4,10)
            musicians=[item for item in nearby if item[0].activity=='playing music']
            if musicians:
                _,gain,pan=musicians[0]; self.trigger('music',gain*.4,pan)
            elif world.weather==2:
                self.trigger('thunder',.3,self.rng.uniform(-.7,.7))
            elif 6<world.clock<18 and not interior and 39<listener.x<57 and 39<listener.y<57:
                self.trigger('bird',.25,self.rng.uniform(-.8,.8))

    def stop(self, cue=None):
        with self.lock:
            if cue is None: self.targets.clear(); self.voices.clear()
            else: self.targets.pop(cue,None)

    def close(self):
        if self.backend is not None:
            self.backend.close(); self.backend=None
        self.stop()


class ProcessAudio(Mixer):
    """Safe macOS stream using one long stereo file and one player process."""
    def __init__(self, volume=1., muted=False):
        super().__init__(volume, muted)
        self.targets={'rain':('rain',.25,0.),'wind':('wind',.05,0.),
                      'water':('water',.04,.15),'leaves':('leaves',.03,-.2)}
        self.player=shutil.which('afplay')
        self.path=os.path.join(tempfile.gettempdir(),'glyph-city-soundscape.wav')
        self.process=None
        self.sound_signature=None
        self.next_refresh=0.0
        self.write_soundscape()
        self.process=subprocess.Popen([self.player,'-v',str(max(.01,min(1.,volume))),self.path],
                                      stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

    def write_soundscape(self):
        frames=RATE*30
        self.cursor=0
        chunks=[]
        written=0
        while written<frames:
            chunk=self.render(min(4096,frames-written)); chunks.append(chunk); written+=len(chunk)
        data=np.concatenate(chunks)
        # Seamless loop: blend the last second into the first second.
        fade=min(RATE,len(data)//2)
        ramp=np.linspace(0,1,fade,dtype='float32')[:,None]
        data[-fade:]=data[-fade:]*(1-ramp)+data[:fade]*ramp
        pcm=np.clip(data*32767,-32767,32767).astype('<i2')
        with wave.open(self.path,'wb') as stream:
            stream.setnchannels(2); stream.setsampwidth(2); stream.setframerate(RATE)
            stream.writeframes(pcm.tobytes())

    def update(self, dt):
        if self.process is None or self.process.poll() is not None:
            self.write_soundscape()
            self.process=subprocess.Popen([self.player,'-v',str(max(.01,min(1.,self.volume))),self.path],
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

    def scene(self, world, listener, dt):
        super().scene(world,listener,dt)
        signature=(world.weather, listener.scene_id, int(world.rain*4),
                   int((listener.angle%(2*math.pi))/(math.pi/2)))
        if signature!=self.sound_signature and self.clock>=self.next_refresh:
            self.sound_signature=signature
            self.next_refresh=self.clock+8.0
            self.refresh()

    def refresh(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try: self.process.wait(timeout=.2)
            except subprocess.TimeoutExpired: self.process.kill()
        self.write_soundscape()
        self.process=subprocess.Popen([self.player,'-v',str(max(.01,min(1.,self.volume))),self.path],
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

    def stop(self, cue=None):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try: self.process.wait(timeout=.2)
            except subprocess.TimeoutExpired: self.process.kill()
        super().stop(cue)

    def close(self):
        if self.process and self.process.poll() is None: self.process.terminate()
        super().close()


def create_audio(*, volume=1., muted=False):
    if muted or os.environ.get('GLYPH_CITY_AUDIO','1')=='0':
        return SilentAudio(volume,muted)
    if np is None: return SilentAudio(volume,muted,'Install numpy to enable audio')
    mixer=None
    try:
        mixer=Mixer(volume,muted)
        if sys.platform=='darwin':
            mixer.close()
            return ProcessAudio(volume,muted)
        else:
            import sounddevice
            stream=sounddevice.OutputStream(samplerate=RATE,channels=2,dtype='float32',
                callback=lambda out,frames,timing,status: out.__setitem__(slice(None),mixer.render(frames)))
            stream.start(); mixer.backend=stream
        return mixer
    except (ImportError,OSError,RuntimeError) as exc:
        if mixer: mixer.close()
        return SilentAudio(volume,muted,str(exc))
