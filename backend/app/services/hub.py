import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any


class TelemetryHub:
    def __init__(self) -> None:
        self._subs: list[asyncio.Queue] = []
        self.latest: list[dict[str, Any]] = []

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._subs.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        if queue in self._subs:
            self._subs.remove(queue)

    def publish(self, payload: dict[str, Any]) -> None:
        self.latest = (self.latest + [payload])[-40:]
        for queue in list(self._subs):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                    queue.put_nowait(payload)
                except asyncio.QueueEmpty:
                    pass

    async def stream(self) -> AsyncIterator[str]:
        queue = self.subscribe()
        try:
            for item in self.latest[-8:]:
                yield f"data: {json.dumps(item, default=str)}\n\n"
            while True:
                item = await queue.get()
                yield f"data: {json.dumps(item, default=str)}\n\n"
        finally:
            self.unsubscribe(queue)


hub = TelemetryHub()
