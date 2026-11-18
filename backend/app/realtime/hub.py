"""Fan-out of telemetry messages to WebSocket clients.

Each client gets its own small bounded queue. The simulator publishes without awaiting,
so a slow or stalled client can never slow down the 10 Hz loop: when a client's queue is
full, its oldest message is dropped. For live telemetry the newest sample is what matters.
"""

import asyncio

DEFAULT_QUEUE_SIZE = 20  # 2 s of backlog at 10 Hz


class TelemetryHub:
    def __init__(self, queue_size: int = DEFAULT_QUEUE_SIZE) -> None:
        self._queue_size = queue_size
        self._subscribers: set[asyncio.Queue[str]] = set()
        self.latest: str | None = None

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def subscribe(self) -> asyncio.Queue[str]:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=self._queue_size)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[str]) -> None:
        self._subscribers.discard(queue)

    def publish(self, message: str) -> None:
        """Queue ``message`` for every subscriber. Must be called from the event loop."""
        self.latest = message
        for queue in self._subscribers:
            if queue.full():
                queue.get_nowait()  # drop the oldest sample for this slow client
            queue.put_nowait(message)
