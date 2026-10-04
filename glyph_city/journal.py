"""Small, version-independent travel journal and the first fixed story."""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Iterable, Mapping

from .interactions import InteractionCandidate

STATUSES = ('unseen', 'seen', 'complete')


@dataclass
class JournalEntry:
    id: str
    kind: str
    title: str
    text: str = ''
    status: str = 'unseen'
    target: tuple[float, float] | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id or not self.kind or not self.title:
            raise ValueError('journal id, kind and title are required')
        if self.status not in STATUSES:
            raise ValueError(f'unknown journal status: {self.status!r}')
        if self.target is not None and not all(math.isfinite(v) for v in self.target):
            raise ValueError('journal target must contain finite coordinates')


class Journal:
    """An insertion-order independent collection of unique entries."""

    def __init__(self, entries: Iterable[JournalEntry] = ()):
        self._entries: dict[str, JournalEntry] = {}
        for entry in entries:
            self.add(entry)

    def add(self, entry: JournalEntry) -> JournalEntry:
        current = self._entries.get(entry.id)
        if current is None:
            self._entries[entry.id] = entry
            return entry
        # Re-discovering an entry may enrich its text/target, but never resets
        # progress or creates a duplicate row.
        if entry.text:
            current.text = entry.text
        if entry.target is not None:
            current.target = entry.target
        current.metadata.update(entry.metadata)
        if STATUSES.index(entry.status) > STATUSES.index(current.status):
            current.status = entry.status
        return current

    def record(self, id: str, *, kind: str, title: str, text: str = '',
               target: tuple[float, float] | None = None,
               status: str = 'seen', metadata: Mapping[str, str] | None = None) -> JournalEntry:
        return self.add(JournalEntry(id, kind, title, text, status, target,
                                     dict(metadata or {})))

    def mark_seen(self, id: str) -> JournalEntry:
        return self._set_status(id, 'seen')

    def mark_complete(self, id: str) -> JournalEntry:
        return self._set_status(id, 'complete')

    def _set_status(self, id: str, status: str) -> JournalEntry:
        if id not in self._entries:
            raise KeyError(id)
        entry = self._entries[id]
        if STATUSES.index(status) > STATUSES.index(entry.status):
            entry.status = status
        return entry

    def get(self, id: str) -> JournalEntry | None:
        return self._entries.get(id)

    def entries(self) -> tuple[JournalEntry, ...]:
        return tuple(self._entries[key] for key in sorted(self._entries))

    def destination(self, id: str) -> tuple[float, float] | None:
        entry = self._entries.get(id)
        return None if entry is None else entry.target

    def to_dict(self) -> list[dict]:
        return [{'id': e.id, 'kind': e.kind, 'title': e.title, 'text': e.text,
                 'status': e.status, 'target': list(e.target) if e.target else None,
                 'metadata': dict(sorted(e.metadata.items()))} for e in self.entries()]

    @classmethod
    def from_dict(cls, data: Iterable[Mapping]) -> 'Journal':
        entries = []
        for raw in data:
            target = raw.get('target')
            entries.append(JournalEntry(raw['id'], raw['kind'], raw['title'],
                                        raw.get('text', ''), raw.get('status', 'unseen'),
                                        tuple(target) if target is not None else None,
                                        dict(raw.get('metadata', {}))))
        return cls(entries)


@dataclass(frozen=True)
class StoryStep:
    id: str
    flag: str
    title: str
    text: str
    target: tuple[float, float]
    target_name: str
    window: tuple[float, float] | None
    fallback_target: tuple[float, float]
    fallback_name: str
    radius: float = 3.2


BOOK_STEPS = (
    StoryStep('book', 'book_found', 'The left-behind book',
              'A book waits on the bench. The first page has no name.',
              (45.0, 46.0), 'Willow Gardens', None, (45.0, 46.0), 'Willow Gardens'),
    StoryStep('seller', 'seller_hint', 'A bookseller remembers',
              'The bookseller points toward the canal after sunset.',
              (72.0, 48.0), 'Lantern Market', (16.0, 22.0), (60.0, 85.0), 'Moonwater Canal'),
    StoryStep('postcard', 'postcard_received', 'A card for the owner',
              'At the canal, a postcard carries the book home.',
              (60.0, 85.0), 'Moonwater Canal', None, (60.0, 85.0), 'Moonwater Canal'),
)


class BookStory:
    """The deliberately small three-stage story used by the first release."""

    steps = BOOK_STEPS

    @classmethod
    def current_step(cls, flags: Iterable[str]) -> StoryStep | None:
        known = set(flags)
        return next((step for step in cls.steps if step.flag not in known), None)

    @classmethod
    def destination(cls, step: StoryStep, hour: float) -> tuple[str, tuple[float, float]]:
        if step.window is None:
            return step.target_name, step.target
        start, end = step.window
        if start <= hour < end:
            return step.target_name, step.target
        return step.fallback_name, step.fallback_target

    @classmethod
    def candidates(cls, flags: Iterable[str], hour: float) -> tuple[InteractionCandidate, ...]:
        step = cls.current_step(flags)
        if step is None:
            return ()
        name, target = cls.destination(step, hour)
        return (InteractionCandidate('story_' + step.id, 'story:' + step.id,
                                     f'Read / talk: {name}', target[0], target[1],
                                     radius=step.radius, priority=100),)

    @classmethod
    def complete(cls, flags: set[str], step_id: str) -> str:
        step = next((step for step in cls.steps if step.id == step_id), None)
        if step is None:
            raise KeyError(step_id)
        if step.flag not in flags:
            flags.add(step.flag)
        return step.text

