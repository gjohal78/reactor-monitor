"""Live telemetry over WebSocket."""

import asyncio
import contextlib

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.realtime.hub import TelemetryHub

router = APIRouter(tags=["telemetry"])


@router.websocket("/ws/telemetry")
async def telemetry(websocket: WebSocket) -> None:
    """Stream every simulator sample (10 Hz) as JSON text frames. Server-to-client only.

    The latest sample is sent immediately on connect, so a client never waits for a tick.
    A second task reads from the socket purely to notice when the client disconnects;
    otherwise a client that goes away would only be noticed on the next failed send.
    """
    hub: TelemetryHub = websocket.app.state.hub
    await websocket.accept()
    queue = hub.subscribe()
    try:
        if hub.latest is not None:
            await websocket.send_text(hub.latest)

        async def send_loop() -> None:
            while True:
                await websocket.send_text(await queue.get())

        async def receive_loop() -> None:
            while True:
                await websocket.receive_text()  # raises WebSocketDisconnect on close

        tasks = {asyncio.create_task(send_loop()), asyncio.create_task(receive_loop())}
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        for task in done:
            with contextlib.suppress(WebSocketDisconnect):
                task.result()
    except WebSocketDisconnect:
        pass
    finally:
        hub.unsubscribe(queue)
