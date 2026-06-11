"""In-process event bus + WebSocket hub. See plan/20-attachments.md §6.

Attachments call ``events.publish("todo.updated", payload)``; the hub fans the
event out to every connected WebSocket client. This is how a change on the laptop
shows up live on the phone without polling.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Event:
    topic: str
    payload: Any = None

    def as_message(self) -> dict[str, Any]:
        return {"type": "event", "topic": self.topic, "payload": self.payload}


@dataclass
class EventBus:
    """Fan-out bus. Each subscriber gets its own asyncio.Queue."""

    _subscribers: set[asyncio.Queue[Event]] = field(default_factory=set)

    def subscribe(self) -> asyncio.Queue[Event]:
        q: asyncio.Queue[Event] = asyncio.Queue(maxsize=256)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[Event]) -> None:
        self._subscribers.discard(q)

    def publish(self, topic: str, payload: Any = None) -> None:
        """Publish an event. Non-blocking; drops to slow/full subscribers."""
        event = Event(topic=topic, payload=payload)
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # A wedged client shouldn't back-pressure publishers. Drop.
                pass

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)
