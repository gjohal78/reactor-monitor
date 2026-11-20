"""Fan-out of WebSocket messages to connected clients.

Each client gets its own small bounded buffer, and publishing never waits, so a slow or
stalled client can never slow down the 10 Hz simulator loop. When a client's buffer is
full, the oldest *telemetry* sample is dropped: for live values only the newest one
matters. Alarm messages are marked critical and are never dropped, since missing an alarm
change is not acceptable (and they are rare, so they cannot grow the buffer much).
"""

import asyncio
from collections import deque

DEFAULT_QUEUE_SIZE = 20  # 2 s of telemetry backlog at 10 Hz


class Subscription:
    def __init__(self, maxsize: int) -> None:
        self._maxsize = maxsize
        self._items: deque[tuple[bool, str]] = deque()  # (critical, message)
        self._ready = asyncio.Event()

    def __len__(self) -> int:
        return len(self._items)

    def put(self, message: str, *, critical: bool) -> None:
        if len(self._items) >= self._maxsize:
            self._drop_oldest_non_critical()
        self._items.append((critical, message))
        self._ready.set()

    def get_nowait(self) -> str:
        _, message = self._items.popleft()
        if not self._items:
            self._ready.clear()
        return message

    async def get(self) -> str:
        while not self._items:
            await self._ready.wait()
        return self.get_nowait()

    def _drop_oldest_non_critical(self) -> None:
        for index, (critical, _) in enumerate(self._items):
            if not critical:
                del self._items[index]
                return
        # Buffer is all alarm messages: keep them all rather than drop one.


class TelemetryHub:
    def __init__(self, queue_size: int = DEFAULT_QUEUE_SIZE) -> None:
        self._queue_size = queue_size
        self._subscribers: set[Subscription] = set()
        self.latest: str | None = None  # newest telemetry message, sent on connect

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def subscribe(self) -> Subscription:
        subscription = Subscription(self._queue_size)
        self._subscribers.add(subscription)
        return subscription

    def unsubscribe(self, subscription: Subscription) -> None:
        self._subscribers.discard(subscription)

    def publish(self, message: str, *, critical: bool = False) -> None:
        """Queue ``message`` for every subscriber. Must be called from the event loop."""
        if not critical:
            self.latest = message
        for subscription in self._subscribers:
            subscription.put(message, critical=critical)
