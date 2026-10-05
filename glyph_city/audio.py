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
import time
from pathlib import Path

try:
    import numpy as np
except ImportError:
    np = None

RATE = 24000
ASSET_DIR = Path(__file__).resolve().parents[1] / 'assets' / 'audio'


def load_sample(path):
    with wave.open(str(path), 'rb') as stream:
        if stream.getframerate()!=RATE or stream.getsampwidth()!=2:
            raise ValueError('Audio bank must use 24 kHz PCM16')
        channels=stream.getnchannels()
        data=np.frombuffer(stream.readframes(stream.getnframes()),dtype='<i2')
    return (data.astype('float32')/32768).reshape(-1,channels)

# Short Foley is prepared once when the mixer starts.  Triggering a footstep
# used to run a convolution and allocate a fresh waveform on the audio path,
# which could add latency exactly when the camera or NPCs were busiest.
SFX_DURATIONS = {
    'step': .22, 'wetstep': .30, 'door': .60, 'bird': .65,
    'bell': 2.4, 'music': 1.9, 'thunder': 5.0, 'car_pass': 1.4,
    'rain_hit': .42, 'drip': .55,
}


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
    def __init__(self, volume=1., muted=False, *, generate=False):
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
        self.banks={}
        for name,seconds,low,high in (
                ('rain',29,180,5500),('wind',31,35,650),('water',37,90,1700),
                ('traffic',23,45,380),('leaves',19,600,3500)):
            path=ASSET_DIR/(name+'.wav')
            self.banks[name]=(load_sample(path) if path.exists() and not generate
                              else self.texture(seconds,low,high))
        self.samples={}
        for cue in SFX_DURATIONS:
            variants=[]
            for variant in range(3):
                path=ASSET_DIR/f'{cue}-{variant+1}.wav'
                variants.append(load_sample(path)[:,0] if path.exists() and not generate
                                else self._synth(cue,variant))
            self.samples[cue]=tuple(variants)
        self.sample_index={cue: 0 for cue in SFX_DURATIONS}

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
            # Each positioned source has its own phase; several cars/trees
            # no longer amplify identical noise in perfect synchrony.
            phase=sum((i+1)*ord(ch) for i,ch in enumerate(name))*7919
            modulation=.87+.13*np.sin(indices/RATE*.31+len(name))
            output+=bank[(indices+phase)%len(bank)]*envelope*modulation[:,None]
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

    def _synth(self, cue, variant=0):
        """Create one natural-sounding Foley variant during mixer setup."""
        n=int(RATE*SFX_DURATIONS[cue]); t=np.arange(n)/RATE
        noise=self.rng.normal(size=n)
        if cue in ('step','wetstep','door','thunder','car_pass','rain_hit','drip'):
            width={'step':25,'wetstep':9,'door':55,'thunder':190,
                   'car_pass':75,'rain_hit':5,'drip':7}[cue]
            filtered=np.convolve(noise,np.ones(width)/math.sqrt(width),'same')
            decay={'step':25,'wetstep':17,'door':8,'thunder':.9,
                   'car_pass':2.2,'rain_hit':10,'drip':8}[cue]
            data=filtered*np.exp(-t*decay)*({'thunder':.18,'car_pass':.12,
                                              'rain_hit':.065}.get(cue,.10))
            if cue in ('step','wetstep'):
                # A quiet tonal body makes wet footsteps read as material,
                # while the noise keeps each variant from sounding synthetic.
                body=np.sin(2*math.pi*(85+variant*9)*t)*np.exp(-t*18)*.035
                data += body
            elif cue=='car_pass':
                sweep=np.sin(2*math.pi*(75+variant*18)*t)*np.exp(-t*1.8)*.06
                data += sweep
            elif cue=='drip':
                click=np.sin(2*math.pi*760*t)*np.exp(-t*22)*.12
                data += click
        elif cue=='bird':
            frequency=1700+variant*260+self.rng.uniform(-70,70)
            chirp=np.sin(2*math.pi*(frequency*t+350*t*t))
            second=np.sin(2*math.pi*(frequency*1.17*t+240*t*t))
            data=(chirp+second*.45)*np.sin(math.pi*t/t[-1])**4*.045
        else:
            frequency=[196.,220.,261.63,293.66,329.63][variant%5]
            data=sum(np.sin(2*math.pi*frequency*ratio*t)*level*np.exp(-t*decay)
                     for ratio,level,decay in ((1,.09,2),(2.01,.025,3),(3.98,.01,6)))
        data*=np.minimum(1,t/.008)
        data[-min(n,240):]*=np.linspace(1,0,min(n,240))
        return data.astype('float32')

    def trigger(self, cue, gain=.3, pan=0):
        # No speech-like beeps: conversations are text, while Foley stays
        # environmental.  Samples were generated in __init__, so this path
        # only schedules an already prepared buffer.
        variants=self.samples.get(cue)
        if not variants or gain<=.005: return False
        variant=self.sample_index[cue]
        self.sample_index[cue]=(variant+1)%len(variants)
        data=variants[variant]
        with self.lock:
            if len(self.voices)>=16: return False
            self.voices.append((data,0,gain,pan))
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
                if p.kind=='car' and gain>.16 and self.clock>=self.cooldowns.get('car:'+str(index),0):
                    self.trigger('car_pass',gain*.32,pan)
                    self.cooldowns['car:'+str(index)]=self.clock+self.rng.uniform(2.8,5.2)
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
            elif world.rain>.45:
                self.trigger('rain_hit',.22,self.rng.uniform(-.8,.8))
            elif interior and world.rain>.1:
                self.trigger('drip',.16,self.rng.uniform(-.5,.5))
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
    """macOS fallback with short, overlapped stereo chunks on a worker thread.

    The game only changes source targets. Mixing, WAV encoding and launching
    afplay happen off the game thread. The shared overlap contains identical
    PCM with complementary fades, so weather and camera changes do not stop
    an active rain bed or discard Foley.
    """
    def __init__(self, volume=1., muted=False):
        super().__init__(volume,muted)
        self.player=shutil.which('afplay')
        if not self.player: raise OSError('afplay is unavailable')
        self.targets={'rain':('rain',.25,0.),'wind':('wind',.05,0.),
                      'water':('water',.04,.15),'leaves':('leaves',.03,-.2)}
        self.directory=tempfile.TemporaryDirectory(prefix='glyph-city-audio-')
        self.processes=[]
        self.done=threading.Event()
        self.worker=threading.Thread(target=self._stream,name='glyph-city-audio',daemon=True)
        self.worker.start()

    def _stream(self):
        stride=3.0; overlap=.3
        shared=None; sequence=0
        try:
            deadline=time.monotonic()
            while not self.done.is_set():
                # Render the new part once. The tail is reused in the next
                # file to keep phase and gain continuous across player starts.
                if shared is None:
                    data=self.render(round(RATE*(stride+overlap)))
                else:
                    data=np.concatenate((shared,self.render(round(RATE*stride))))
                shared=data[-round(RATE*overlap):].copy()
                fade=round(RATE*overlap)
                ramp=np.linspace(0,1,fade,dtype='float32')[:,None]
                data[:fade]*=ramp; data[-fade:]*=1-ramp
                path=Path(self.directory.name)/f'chunk-{sequence%4}.wav'
                with wave.open(str(path),'wb') as stream:
                    stream.setnchannels(2); stream.setsampwidth(2); stream.setframerate(RATE)
                    stream.writeframes(np.clip(data*32767,-32767,32767).astype('<i2').tobytes())
                delay=deadline-time.monotonic()
                if delay>0 and self.done.wait(delay): break
                if self.done.is_set(): break
                process=subprocess.Popen([self.player,str(path)],
                                         stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                self.processes=[p for p in self.processes if p.poll() is None]
                self.processes.append(process)
                sequence+=1
                deadline+=stride
                # An overloaded machine may miss a deadline; recover from
                # current time instead of launching several chunks at once.
                deadline=max(deadline,time.monotonic()+.05)
        except (OSError,ValueError,RuntimeError) as exc:
            self.reason=str(exc); self.status='audio-error'

    def update(self, dt):
        pass

    def close(self):
        self.done.set()
        if threading.current_thread() is not self.worker:
            self.worker.join(timeout=2)
        for process in self.processes:
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=.2)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait()
        self.processes.clear()
        if not self.worker.is_alive(): self.directory.cleanup()
        super().close()


def create_audio(*, volume=1., muted=False):
    if muted or os.environ.get('GLYPH_CITY_AUDIO','1')=='0':
        return SilentAudio(volume,muted)
    if np is None: return SilentAudio(volume,muted,'Install numpy to enable audio')
    mixer=None
    try:
        # Prefer a continuous native callback on every platform, including
        # macOS. The process fallback remains usable without sounddevice.
        import sounddevice
        mixer=Mixer(volume,muted)
        stream=sounddevice.OutputStream(samplerate=RATE,channels=2,dtype='float32',
            callback=lambda out,frames,timing,status: out.__setitem__(slice(None),mixer.render(frames)))
        mixer.backend=stream
        stream.start()
        return mixer
    except (ImportError,OSError,RuntimeError,ValueError) as exc:
        if mixer: mixer.close()
        if sys.platform=='darwin' and shutil.which('afplay'):
            try: return ProcessAudio(volume,muted)
            except (OSError,RuntimeError,ValueError) as fallback:
                return SilentAudio(volume,muted,str(fallback))
        return SilentAudio(volume,muted,str(exc))
