"""
Firetell Audio Stream — Example 2: Full-Duplex Custom AI Voice Bot
==================================================================

This server implements a full-duplex audio bridge between Firetell and your
custom AI voice bot pipeline. The server:

  1. Receives raw PCM audio from the caller (via Firetell)
  2. Passes it to your STT / LLM / TTS pipeline
  3. Sends synthesized PCM audio back to Firetell, which plays it to the caller

Audio format (both directions):
  - Encoding: 16-bit signed PCM, little-endian
  - Sample rate: 8000 Hz (default) or 16000 Hz — must match your stream action config
  - Incoming (Firetell → Your server): stereo if track=both, mono otherwise
  - Outgoing (Your server → Firetell): mono at the configured sample_rate

Control frames (Your server → Firetell):
  - Send JSON text frame {"type": "killAudio"} to immediately stop queued
    playback on Firetell's side (use for barge-in / interruption detection)

Firetell automatically appends the following query params to your ws_url:
  ?workspace_id=...&call_id=...&caller_number=...&caller_name=...
  &destination_number=...&stream_type=firetell_stream

Requirements:
  pip install websockets

Usage:
  PORT=3001 AUTH_TOKEN=your-secret-token SAMPLE_RATE=8000 python examples/full_duplex_bot.py

Then configure your Firetell call flow or outbound call with:
  {
    "action": "stream",
    "params": {
      "ws_url": "wss://your-server.example.com/bot",
      "track": "both",
      "sample_rate": 8000,
      "bidirectional": true,
      "headers": { "Authorization": "Bearer your-secret-token" }
    }
  }

IMPORTANT: bidirectional: true requires answer_call: true (the default).
Audio injection only works after the call channel is in the ACTIVE (answered) state.
"""

import asyncio
import json
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
logger = logging.getLogger("bot")

PORT = int(os.environ.get("PORT", 3001))
AUTH_TOKEN = os.environ.get("AUTH_TOKEN", "")
SAMPLE_RATE = int(os.environ.get("SAMPLE_RATE", 8000))  # Must match stream action config


def generate_sine_tone(frequency_hz: float, duration_sec: float, sample_rate: int) -> bytes:
    """
    Generate a pure sine tone as raw 16-bit signed PCM (mono, little-endian).
    In production, replace this with your actual TTS output.

    Play back with: ffplay -f s16le -ar 8000 -ac 1 tone.pcm
    """
    num_samples = int(sample_rate * duration_sec)
    amplitude = 8000  # ~25% of 16-bit max (32767) — comfortable volume
    samples = [
        int(amplitude * math.sin(2 * math.pi * frequency_hz * i / sample_rate))
        for i in range(num_samples)
    ]
    return struct.pack(f"<{num_samples}h", *samples)


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

    logger.info(
        "New bidirectional call connected: call_id=%s workspace=%s caller=%s(%s) dest=%s",
        call_id, workspace_id, caller_number, caller_name, destination_number,
    )

    # ── 2. Optional: verify Authorization header ──────────────────────────────
    if AUTH_TOKEN:
        auth_header = websocket.request.headers.get("Authorization", "")
        if auth_header != f"Bearer {AUTH_TOKEN}":
            logger.warning("Unauthorized connection from call %s — closing", call_id)
            await websocket.close(1008, "Unauthorized")
            return

    # ── 3. Session state ──────────────────────────────────────────────────────
    chunks_received = 0
    started_at = time.monotonic()

    # ── 4. Helpers ────────────────────────────────────────────────────────────

    async def send_audio(pcm_bytes: bytes) -> None:
        """
        Send a bytes buffer of raw 16-bit signed PCM mono audio to Firetell.
        Firetell will play this audio to the caller in real-time.

        :param pcm_bytes: Raw PCM audio — 16-bit, little-endian, mono, at SAMPLE_RATE Hz
        """
        if websocket.state.name != "OPEN":
            return
        try:
            await websocket.send(pcm_bytes)
        except Exception as exc:
            logger.error("Error sending audio to call %s: %s", call_id, exc)

    async def send_kill_audio() -> None:
        """
        Instruct Firetell to immediately stop any audio currently being played
        to the caller. Call this when the caller starts speaking (barge-in).
        """
        if websocket.state.name != "OPEN":
            return
        try:
            await websocket.send(json.dumps({"type": "killAudio"}))
            logger.info("Sent killAudio (barge-in) for call %s", call_id)
        except Exception as exc:
            logger.error("Error sending killAudio to call %s: %s", call_id, exc)

    # ── 5. Greeting: play welcome audio when connection is established ─────────
    # In a real implementation, generate this via your TTS provider.
    # Here we generate a 1-second sine wave tone as a placeholder.
    greeting = generate_sine_tone(440, 1.0, SAMPLE_RATE)
    await asyncio.sleep(0.2)  # Small delay to ensure channel is ready
    await send_audio(greeting)
    logger.info("Sent greeting audio for call %s", call_id)

    # ── 6. Handle incoming audio frames (caller's speech) ────────────────────
    try:
        async for message in websocket:
            if isinstance(message, str):
                # Firetell does not send text frames in bidirectional mode
                continue

            caller_audio: bytes = message
            chunks_received += 1

            # ── Your AI pipeline here ───────────────────────────────────────
            #
            # Step 1: Voice Activity Detection (VAD)
            #   Detect if the caller is speaking to trigger barge-in
            #   Example:
            #     if vad.is_speaking(caller_audio):
            #         await send_kill_audio()
            #
            # Step 2: Speech-to-Text (STT)
            #   Stream caller_audio to your STT provider
            #   Example:
            #     await stt_stream.send(caller_audio)
            #
            # Step 3: LLM Processing (on final transcript)
            #   Example:
            #     response_text = await llm.chat(transcript)
            #
            # Step 4: Text-to-Speech (TTS)
            #   Convert LLM response to PCM audio (must be mono, 16-bit, SAMPLE_RATE Hz)
            #   Example:
            #     response_audio = await tts.synthesize(
            #         response_text, sample_rate=SAMPLE_RATE
            #     )
            #     await send_audio(response_audio)
            #
            # ────────────────────────────────────────────────────────────────

            # Demo: echo a short beep every 100 chunks (~2 seconds)
            if chunks_received % 100 == 0:
                logger.info(
                    "call=%s chunks=%d bytes=%d",
                    call_id, chunks_received, len(caller_audio),
                )
                beep = generate_sine_tone(880, 0.1, SAMPLE_RATE)  # 100ms beep
                await send_audio(beep)

    except websockets.exceptions.ConnectionClosed:
        pass  # normal close

    # ── 7. Log final stats ────────────────────────────────────────────────────
    duration = time.monotonic() - started_at
    logger.info(
        "Call ended: call=%s duration=%.1fs chunks=%d",
        call_id, duration, chunks_received,
    )
    # Clean up your STT/LLM/TTS pipeline resources here


async def main() -> None:
    logger.info("WebSocket server listening on ws://0.0.0.0:%d", PORT)
    async with websockets.serve(handle_connection, "0.0.0.0", PORT):
        await asyncio.get_event_loop().create_future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
