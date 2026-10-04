"""A single input reader, safe terminal ownership, and exact-width ANSI output."""
from __future__ import annotations

import functools
import itertools
import os
import re
import select
import signal
import sys
import time
from dataclasses import dataclass


def truecolor_supported():
    if os.environ.get('TERM_PROGRAM') == 'Apple_Terminal': return False
    return (os.environ.get('COLORTERM','').lower() in ('truecolor','24bit')
            or any(n in os.environ.get('TERM','').lower() for n in ('kitty','direct','ghostty','wezterm'))
            or os.environ.get('TERM_PROGRAM','').lower() in ('vscode','iterm.app','wezterm','ghostty'))


@functools.lru_cache(maxsize=8192)
def color256(rgb):
    levels=(0,95,135,175,215,255)
    cube=tuple(min(range(6),key=lambda i:abs(levels[i]-v)) for v in rgb)
    cube_error=sum((levels[i]-v)**2 for i,v in zip(cube,rgb))
    grey=max(0,min(23,round((sum(rgb)/3-8)/10)))
    grey_error=sum((8+10*grey-v)**2 for v in rgb)
    return 232+grey if grey_error<cube_error else 16+36*cube[0]+6*cube[1]+cube[2]


def encode(buf, truecolor=True, x=1, y=1):
    parts=['\x1b[0m']; last_fg=last_bg=None
    for r,row in enumerate(buf):
        parts.append(f'\x1b[{y+r};{x}H')
        for (ch,fg,bg),run in itertools.groupby(row):
            count=sum(1 for _ in run)
            params=[]
            f=fg if truecolor else color256(fg)
            b=bg if truecolor else color256(bg)
            if ch!=' ' and f!=last_fg:
                params.append(f'38;2;{f[0]};{f[1]};{f[2]}' if truecolor else f'38;5;{f}')
                last_fg=f
            if b!=last_bg:
                params.append(f'48;2;{b[0]};{b[1]};{b[2]}' if truecolor else f'48;5;{b}')
                last_bg=b
            if params: parts.append('\x1b['+';'.join(params)+'m')
            parts.append((ch or ' ')*count)
    parts.append('\x1b[0m')
    return ''.join(parts)


def dirty_rows(previous, current):
    """Return row indices whose terminal cells changed.

    Rows with a different width are considered dirty in full.  The function
    is intentionally pure so it can be used by tests and by a future renderer
    without coupling it to terminal state.
    """
    old_rows=tuple(tuple(row) for row in previous)
    new_rows=tuple(tuple(row) for row in current)
    if len(old_rows)!=len(new_rows):
        return list(range(len(new_rows)))
    return [r for r,(old,new) in enumerate(zip(old_rows,new_rows)) if old!=new]


def dirty_spans(previous, current):
    """Return changed half-open spans as ``(row, start, end)``.

    A shape change cannot be safely patched in place, so callers should use
    ``FrameSnapshot.needs_full`` for that case.  For equal-shaped frames this
    returns the smallest contiguous runs of changed cells.
    """
    old_rows=tuple(tuple(row) for row in previous)
    new_rows=tuple(tuple(row) for row in current)
    if len(old_rows)!=len(new_rows) or any(len(a)!=len(b) for a,b in zip(old_rows,new_rows)):
        return [(r,0,len(row)) for r,row in enumerate(new_rows)]
    spans=[]
    for r,(old,new) in enumerate(zip(old_rows,new_rows)):
        start=None
        for c,(before,after) in enumerate(zip(old,new)):
            if before!=after and start is None:
                start=c
            elif before==after and start is not None:
                spans.append((r,start,c)); start=None
        if start is not None:
            spans.append((r,start,len(new)))
    return spans


def _encode_cells(cells, truecolor=True, x=1, y=1):
    """Encode independent cell runs with a fresh SGR state."""
    parts=['\x1b[0m',f'\x1b[{y};{x}H']
    last_fg=last_bg=None
    for (ch,fg,bg),run in itertools.groupby(cells):
        count=sum(1 for _ in run)
        params=[]
        f=fg if truecolor else color256(fg)
        b=bg if truecolor else color256(bg)
        if ch!=' ' and f!=last_fg:
            params.append(f'38;2;{f[0]};{f[1]};{f[2]}' if truecolor else f'38;5;{f}')
            last_fg=f
        if b!=last_bg:
            params.append(f'48;2;{b[0]};{b[1]};{b[2]}' if truecolor else f'48;5;{b}')
            last_bg=b
        if params: parts.append('\x1b['+';'.join(params)+'m')
        parts.append((ch or ' ')*count)
    parts.append('\x1b[0m')
    return ''.join(parts)


def encode_delta(previous, current, truecolor=True, x=1, y=1):
    """Encode only changed spans between equal-shaped terminal frames.

    Every span has an absolute cursor position and its own SGR reset.  This
    makes spans safe even when a terminal receives a dropped or coalesced
    frame.  ``None`` or a shape mismatch returns the existing full-frame
    encoding as the correctness fallback.
    """
    old_rows=tuple(tuple(row) for row in previous) if previous is not None else None
    new_rows=tuple(tuple(row) for row in current)
    if old_rows is None or len(old_rows)!=len(new_rows) or any(len(a)!=len(b) for a,b in zip(old_rows,new_rows)):
        return encode(new_rows,truecolor,x,y)
    parts=[]
    for r,start,end in dirty_spans(old_rows,new_rows):
        parts.append(_encode_cells(new_rows[r][start:end],truecolor,x+start,y+r))
    return ''.join(parts)


@dataclass
class FrameSnapshot:
    """Experimental frame cache for opt-in delta output.

    ``encode`` keeps the previous frame only after producing output.  Calling
    ``invalidate`` forces the next call to use the full-frame oracle, which is
    required after resize, palette changes, or any external screen mutation.
    """
    previous: tuple | None = None
    force_full: bool = True
    config: tuple | None = None

    def invalidate(self):
        self.force_full=True

    @property
    def needs_full(self):
        return self.force_full or self.previous is None

    def encode(self, buf, truecolor=True, x=1, y=1):
        current=tuple(tuple(row) for row in buf)
        config=(bool(truecolor),x,y)
        shape_changed=(self.previous is not None and
                       (len(self.previous)!=len(current) or
                        any(len(a)!=len(b) for a,b in zip(self.previous,current))))
        config_changed=self.config is not None and self.config!=config
        full=self.force_full or self.previous is None or shape_changed or config_changed
        output=encode(current,truecolor,x,y) if full else encode_delta(self.previous,current,truecolor,x,y)
        self.previous=current
        self.config=config
        self.force_full=False
        return output


@dataclass
class Event:
    key: str = ''
    shift: bool = False
    release: bool = False
    repeat: bool = False
    enhanced: bool = False
    mouse: tuple | None = None


@dataclass
class HeldKey:
    """A logical key held by the game loop.

    ``until`` is only used by the character-only legacy fallback.  Enhanced
    terminal events have an explicit release and therefore use ``None``.
    """
    until: float | None
    shift: bool = False


class InputState:
    """Turn terminal events into one consistent snapshot for the simulation.

    The old game kept key expiry and menu/focus cleanup inside ``play``.  That
    made it easy for one key to disappear while another key was still held.
    This small state machine keeps those rules in one place and makes the
    enhanced press/release path deterministic.  Plain character terminals do
    not provide a physical key-up event; their short timeout is kept only as
    a documented compatibility fallback.
    """
    MOVEMENT = frozenset('wasd')
    TURN = frozenset('qe')
    LEGACY_TTL = .32

    def __init__(self):
        self.held: dict[str,HeldKey] = {}
        self.shifts: set[str] = set()
        self.mode = 'legacy'
        self.legacy_chord = False

    def clear(self):
        self.held.clear()
        self.shifts.clear()
        self.legacy_chord = False

    def clear_movement(self):
        """Emergency brake for character-only terminals without key-up events."""
        self.held.clear()
        self.shifts.clear()

    def _refresh_legacy_walk(self, now: float):
        """Refresh only WASD in a legacy chord; turning keeps its own lease."""
        if not self.legacy_chord:
            return
        self.held = {name: HeldKey(now + self.LEGACY_TTL, value.shift)
                     if name in self.MOVEMENT else value
                     for name, value in self.held.items()
                     if value.until is None or value.until > now}

    def apply(self, event: Event, now: float):
        """Apply one event and return a focus-loss flag when appropriate."""
        if event.enhanced:
            self.mode = 'enhanced'
        key = event.key
        if key == 'focus-out':
            self.clear()
            return True
        if key in ('shift-left','shift-right'):
            if event.release:
                self.shifts.discard(key)
                if not self.shifts:
                    self.held = {name: HeldKey(value.until, False)
                                 for name, value in self.held.items()}
            else:
                self.shifts.add(key)
            self._refresh_legacy_walk(now)
            return False
        if key in self.MOVEMENT:
            if event.release:
                self.held.pop(key, None)
            elif event.enhanced:
                self.held[key] = HeldKey(None, event.shift)
            else:
                other_active = any(other != key and
                                   (value.until is None or value.until > now)
                                   for other, value in self.held.items())
                self.held[key] = HeldKey(now + self.LEGACY_TTL, event.shift)
                if other_active:
                    self.legacy_chord = True
                if self.legacy_chord:
                    # A plain terminal has no release event. Refresh the
                    # active chord on every movement event so a second key's
                    # repeat cannot make the first key disappear. If input
                    # stops entirely, the whole chord expires safely.
                    if not event.shift:
                        self.held = {name: HeldKey(value.until, False)
                                     for name, value in self.held.items()}
                    self._refresh_legacy_walk(now)
            return False
        if key in self.TURN:
            # Turning is an independent control. In legacy terminals a turn
            # repeat may disappear when a walk key is pressed, so it must not
            # refresh or latch the walking chord.
            if event.release:
                self.held.pop(key, None)
            elif event.enhanced:
                self.held[key] = HeldKey(None, event.shift)
            else:
                self.held[key] = HeldKey(now + self.LEGACY_TTL, event.shift)
                self._refresh_legacy_walk(now)
            return False
        return False

    def snapshot(self, now: float):
        """Return the shape expected by ``World.update`` and prune fallback keys."""
        self.held = {key: value for key, value in self.held.items()
                     if value.until is None or value.until > now}
        return ({key: (float('inf') if value.until is None else value.until,
                       value.shift) for key, value in self.held.items()},
                set(self.shifts))


class Input:
    def __init__(self):
        self.pending=''
        self.escape_at=0.0

    def feed(self, data=b'', now=None):
        now=time.monotonic() if now is None else now
        self.pending+=data.decode('ascii','ignore')
        events=[]
        while self.pending:
            s=self.pending
            if s[0]!='\x1b':
                self.pending=s[1:]
                ch=s[0]
                key={'\x03':'exit','\t':'tab','\n':'enter','\r':'enter',' ':'photo','\x7f':'backspace'}.get(ch,ch.lower())
                events.append(Event(key,shift=ch.isupper()))
                continue
            if s=='\x1b':
                if not self.escape_at: self.escape_at=now
                if now-self.escape_at>.06:
                    self.pending=''; self.escape_at=0; events.append(Event('exit'))
                break
            self.escape_at=0
            if s[1] not in '[O':
                self.pending=s[2:]
                continue
            if len(s)==2: break
            if s[1]=='O':
                self.pending=s[3:]
                key={'A':'w','B':'s','C':'e','D':'q','H':'home'}.get(s[2])
                if key: events.append(Event(key))
                continue
            match=re.match(r'\x1b\[([0-?]*)([ -/]*)([@-~])',s)
            if not match:
                if len(s)>128: self.pending=s[1:]
                else: break
                continue
            self.pending=s[match.end():]
            body,_,final=match.groups()
            try:
                if body.startswith('<') and final in 'Mm':
                    button,mx,my=map(int,body[1:].split(';'))
                    if button&32: events.append(Event(mouse=(mx,my)))
                elif final=='u':
                    seg=body.split(';'); code=int(seg[0].split(':')[0])
                    mods=seg[1].split(':') if len(seg)>1 else ['1']
                    mask=int(mods[0] or '1')-1
                    event=int(mods[1]) if len(mods)>1 and mods[1] else 1
                    key={27:'exit',9:'tab',32:'photo',57417:'q',57418:'e',57419:'w',57420:'s',
                         57423:'home',57441:'shift-left',57447:'shift-right'}.get(code)
                    if key is None and 32<=code<=126: key=chr(code).lower()
                    if code==99 and mask&4: key='exit'
                    if key: events.append(Event(key,bool(mask&1),event==3,event==2,True))
                elif final in 'ABCDH':
                    key={'A':'w','B':'s','C':'e','D':'q','H':'home'}[final]
                    modifiers=body.split(';')[-1].split(':') if ';' in body else ['1']
                    mods=int(modifiers[0] or '1')-1
                    kind=int(modifiers[1]) if len(modifiers)>1 else 1
                    events.append(Event(key,bool(mods&1),kind==3,kind==2,':' in body))
                elif final=='~' and body in ('1','7'):
                    events.append(Event('home'))
                elif final=='O' and not body:
                    events.append(Event('focus-out'))
            except (ValueError,OverflowError):
                continue
        return events


class Terminal:
    def __init__(self, truecolor=None):
        self.truecolor=truecolor_supported() if truecolor is None else truecolor
        self.input=Input()
        self.old=None
        self.signals={}
        self.frame_snapshot=FrameSnapshot()

    def __enter__(self):
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise RuntimeError('Open an interactive terminal to play, or use --shot for a preview.')
        if os.name!='posix':
            raise RuntimeError('Interactive play needs a POSIX terminal (macOS, Linux, or WSL).')
        import termios, tty
        self.fd=sys.stdin.fileno()
        self.old=termios.tcgetattr(self.fd)
        try:
            tty.setraw(self.fd)
            for sig in (signal.SIGTERM,signal.SIGHUP):
                self.signals[sig]=signal.signal(sig,self._interrupt)
            sys.stdout.write('\x1b[22;0t\x1b]2;Glyph City - Afterlight\x07'
                             '\x1b[?1049h\x1b[?25l\x1b[?7l\x1b[>11u\x1b[?1004h\x1b[2J')
            sys.stdout.flush()
        except BaseException:
            self.__exit__(None,None,None)
            raise
        return self

    @staticmethod
    def _interrupt(*args):
        raise KeyboardInterrupt

    def __exit__(self,*args):
        import termios
        try:
            sys.stdout.write('\x1b[?2026l\x1b[?1003l\x1b[?1006l\x1b[?1004l\x1b[<u'
                             '\x1b[0m\x1b[?7h\x1b[?25h\x1b[?1049l\x1b[23;0t')
            sys.stdout.flush()
        finally:
            if self.old is not None: termios.tcsetattr(self.fd,termios.TCSADRAIN,self.old)
            for sig,handler in self.signals.items(): signal.signal(sig,handler)

    def size(self):
        try: return os.get_terminal_size(sys.stdout.fileno())
        except OSError: return 80,24

    def aspect(self):
        import fcntl, struct, termios
        try:
            rows,cols,xp,yp=struct.unpack('HHHH',fcntl.ioctl(sys.stdout.fileno(),termios.TIOCGWINSZ,b'\0'*8))
            value=(xp/cols)/(yp/rows)
            if .25<=value<=1: return value
        except (OSError,ZeroDivisionError): pass
        return .5

    def events(self):
        data=b''
        while select.select([self.fd],[],[],0)[0]:
            chunk=os.read(self.fd,4096)
            if not chunk: return [Event('exit')]
            data+=chunk
        return self.input.feed(data)

    def mouse(self, enabled):
        sys.stdout.write('\x1b[?1006h\x1b[?1003h' if enabled else '\x1b[?1003l\x1b[?1006l')
        sys.stdout.flush()

    def clear(self):
        self.frame_snapshot.invalidate()
        sys.stdout.write('\x1b[0m\x1b[2J')

    def draw(self,buf,x,y,delta=False):
        payload=self.frame_snapshot.encode(buf,self.truecolor,x,y) if delta else encode(buf,self.truecolor,x,y)
        if not delta:
            # Keep the optional delta cache synchronized with full redraws.
            self.frame_snapshot.previous=tuple(tuple(row) for row in buf)
            self.frame_snapshot.config=(bool(self.truecolor),x,y)
            self.frame_snapshot.force_full=False
        sys.stdout.write('\x1b[?2026h'+payload+'\x1b[?2026l')
        sys.stdout.flush()
