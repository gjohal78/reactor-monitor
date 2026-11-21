"""Live telemetry and alarm changes over WebSocket.

Frames are JSON objects ``{"type": ..., "data": ...}``:

- ``alarm_snapshot``: sent once on connect, listing every currently open alarm
- ``telemetry``: every simulator sample (10 Hz)
- ``alarm``: an alarm changed state (``data.previous_state`` -> ``data.state``)
"""

import asyncio
import contextlib

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.alarms.service import AlarmService
from app.auth.dependencies import websocket_user
from app.realtime.hub import TelemetryHub

router = APIRouter(tags=["telemetry"])


@router.websocket("/ws/telemetry")
async def telemetry(websocket: WebSocket, token: str | None = None) -> None:
    """Stream telemetry and alarm changes as JSON text frames. Server-to-client only.

    On connect the client gets the open alarms and the latest sample straight away. The
    subscription starts before that snapshot is taken (with no await in between), so no
    alarm change can fall in the gap between the snapshot and the live stream.

    Requires a valid access token (any role) as ``?token=...``, because browsers can't send
    an Authorization header on a WebSocket. Without one the handshake is refused (HTTP 403).
    The token is checked once, at connect time.
    A second task reads from the socket purely to notice when the client disconnects;
    otherwise a client that goes away would only be noticed on the next failed send.
    """
    if await asyncio.to_thread(websocket_user, websocket, token) is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    hub: TelemetryHub = websocket.app.state.hub
    alarms: AlarmService = websocket.app.state.alarms
    await websocket.accept()
    queue = hub.subscribe()
    snapshot, latest = alarms.snapshot_message(), hub.latest
    try:
        await websocket.send_text(snapshot)
        if latest is not None:
            await websocket.send_text(latest)

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
