"""
Firetell Audio Stream — Example 1: One-Way Monitoring
======================================================

This server receives a live audio stream from Firetell during an active call.
Use this pattern for:
  - Real-time speech-to-text (STT) / transcription
  - Keyword detection & compliance monitoring
  - Call analytics and sentiment analysis
  - Audio recording / archiving

Audio format: raw 16-bit signed PCM, little-endian
  - Sample rate: 8000 Hz or 16000 Hz (as configured in the stream action)
  - Channels: 2 (stereo) if track=both, 1 (mono) if track=inbound/outbound
              Stereo: left channel = caller, right channel = callee

Firetell automatically appends the following query parameters to your ws_url:
  ?workspace_id=...&call_id=...&caller_number=...&caller_name=...
  &destination_number=...&stream_type=firetell_stream

Requirements:
  pip install websockets

Usage:
  PORT=3000 AUTH_TOKEN=your-secret-token python examples/one_way_monitor.py

Then configure your Firetell call flow or outbound call with:
  {
    "action": "stream",
    "params": {
      "ws_url": "wss://your-server.example.com/stream",
      "track": "both",
      "bidirectional": false,
      "headers": { "Authorization": "Bearer your-secret-token" }
    }
  }
"""

import asyncio
import logging
import math
import os
import struct
import time
from urllib.parse import parse_qs, urlparse

import websockets
from websockets.server import ServerConnection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("monitor")

PORT = int(os.environ.get("PORT", 3000))
AUTH_TOKEN = os.environ.get("AUTH_TOKEN", "")  # Optional


async def handle_connection(websocket: ServerConnection) -> None:
    # ── 1. Parse call context from query params ───────────────────────────────
    parsed = urlparse(websocket.request.path)
    params = parse_qs(parsed.query)

    def qp(key: str) -> str:
        return params.get(key, [""])[0]

    call_id            = qp("call_id") or "unknown"
    workspace_id       = qp("workspace_id")
    caller_number      = qp("caller_number")
    caller_name        = qp("caller_name")
    destination_number = qp("destination_number")
    stream_type        = qp("stream_type")

    logger.info(
        "New call stream connected: call_id=%s workspace=%s caller=%s(%s) dest=%s type=%s",
        call_id, workspace_id, caller_number, caller_name, destination_number, stream_type,
    )

    # ── 2. Optional: verify Authorization header ──────────────────────────────
    if AUTH_TOKEN:
        auth_header = websocket.request.headers.get("Authorization", "")
        if auth_header != f"Bearer {AUTH_TOKEN}":
            logger.warning("Unauthorized connection from call %s — closing", call_id)
            await websocket.close(1008, "Unauthorized")
            return

    # ── 3. Track stats ────────────────────────────────────────────────────────
    chunks_received = 0
    bytes_received = 0
    started_at = time.monotonic()

    # ── 4. Optional: open a file to save raw PCM audio ───────────────────────
    # Uncomment to write raw PCM to disk. Play back with:
    #   ffplay -f s16le -ar 8000 -ac 2 recordings/<call_id>.pcm
    #
    # import pathlib
    # recordings_dir = pathlib.Path("recordings")
    # recordings_dir.mkdir(exist_ok=True)
    # pcm_file = open(recordings_dir / f"{call_id}.pcm", "wb")

    # ── 5. Handle incoming audio frames ──────────────────────────────────────
    try:
        async for message in websocket:
            if isinstance(message, str):
                # Firetell does not send text frames in one-way mode
                logger.debug("Unexpected text frame from call %s: %s", call_id, message)
                continue

            chunk: bytes = message
            chunks_received += 1
            bytes_received += len(chunk)

            # Log every 50 chunks (~1 second at 20ms/chunk)
            if chunks_received % 50 == 0:
                elapsed = time.monotonic() - started_at
                logger.info(
                    "call=%s elapsed=%.1fs chunks=%d bytes=%d",
                    call_id, elapsed, chunks_received, bytes_received,
                )

            # ── Your processing logic here ──────────────────────────────────
            # Examples:
            #   pcm_file.write(chunk)                      # save to disk
            #   await stt_client.send_audio(chunk)         # stream to STT API
            #   compliance_engine.analyze(chunk, call_id)  # compliance check
            # ───────────────────────────────────────────────────────────────

    except websockets.exceptions.ConnectionClosed as exc:
        pass  # normal close — handled below

    # ── 6. Log final stats ────────────────────────────────────────────────────
    duration = time.monotonic() - started_at
    logger.info(
        "Call stream ended: call=%s duration=%.1fs chunks=%d bytes=%d",
        call_id, duration, chunks_received, bytes_received,
    )
    # pcm_file.close()


async def main() -> None:
    logger.info("WebSocket server listening on ws://0.0.0.0:%d", PORT)
    async with websockets.serve(handle_connection, "0.0.0.0", PORT):
        await asyncio.get_event_loop().create_future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
