# Firetell Audio Stream — Python Examples

> **Official sample code** for the Firetell `stream` call action.  
> Connect live call audio to your own WebSocket server for real-time transcription, compliance monitoring, or a fully custom AI voice bot.

📚 **Documentation**: [developers.firetell.com/docs/rest-api/workspace-api/call](https://developers.firetell.com/docs/rest-api/workspace-api/call/#8-custom-voice-bot-via-audio-stream)

---

## Overview

When you use the `stream` action in a Firetell call flow or outbound call, Firetell establishes a WebSocket connection to your server and streams raw **16-bit signed PCM audio** in real-time. With `bidirectional: true`, your server can also send audio back to be played to the caller.

```
[Caller] ◄──► [Firetell] ◄──► Your WebSocket Server
                                       │
                         One-way:  STT / Analytics / Recording
                         Full-duplex:  STT → LLM → TTS (AI Voice Bot)
```

---

## Examples

### Example 1 — One-Way Monitoring (`one_way_monitor.py`)

Receive the caller's live audio stream **without** affecting the call. Suitable for:

- Real-time speech-to-text (STT) transcription
- Keyword detection & compliance monitoring
- Call analytics and sentiment analysis
- Audio recording / archiving

### Example 2 — Full-Duplex AI Voice Bot (`full_duplex_bot.py`)

Receive audio **and** send audio back — build a fully custom AI voice bot using any STT, LLM, and TTS provider of your choice. Suitable for:

- Custom voice assistants with any AI model (GPT-4, Gemini, Claude, etc.)
- Virtual agents with proprietary business logic
- Real-time translation and interpretation services

---

## Prerequisites

- Python **3.10+**
- A Firetell workspace with API access — [firetell.com](https://firetell.com)
- A publicly accessible HTTPS/WSS endpoint (use [ngrok](https://ngrok.com) for local testing)

---

## Setup

```bash
git clone https://github.com/firetellcom/audio-stream-python-example.git
cd audio-stream-python-example
pip install -r requirements.txt
```

---

## Run the Examples

### One-Way Monitoring

```bash
PORT=3000 AUTH_TOKEN=your-secret-token python examples/one_way_monitor.py
```

### Full-Duplex AI Voice Bot

```bash
PORT=3001 AUTH_TOKEN=your-secret-token SAMPLE_RATE=8000 python examples/full_duplex_bot.py
```

| Environment Variable | Default         | Description                                                           |
| -------------------- | --------------- | --------------------------------------------------------------------- |
| `PORT`               | `3000` / `3001` | WebSocket server port                                                 |
| `AUTH_TOKEN`         | _(empty)_       | If set, validates `Authorization: Bearer <token>` header              |
| `SAMPLE_RATE`        | `8000`          | PCM sample rate — must match your `stream` action `sample_rate` param |

---

## Configure Your Firetell Call Flow

In your [JCA webhook response](https://developers.firetell.com/docs/rest-api/workspace-api/call-flows) or outbound [Make Call API](https://developers.firetell.com/docs/rest-api/workspace-api/call) request, include the `stream` action:

### One-Way Monitoring

```json
{
  "actions": [
    {
      "action": "stream",
      "params": {
        "ws_url": "wss://your-server.example.com/stream",
        "track": "both",
        "bidirectional": false,
        "headers": {
          "Authorization": "Bearer your-secret-token"
        }
      }
    }
  ]
}
```

### Full-Duplex AI Voice Bot

```json
{
  "actions": [
    {
      "action": "stream",
      "params": {
        "ws_url": "wss://your-server.example.com/bot",
        "track": "both",
        "sample_rate": 8000,
        "bidirectional": true,
        "headers": {
          "Authorization": "Bearer your-secret-token"
        }
      }
    }
  ]
}
```

---

## Audio Format

| Property                                        | Value                                  |
| ----------------------------------------------- | -------------------------------------- |
| Encoding                                        | 16-bit signed PCM, little-endian       |
| Sample rate                                     | `8000` Hz (default) or `16000` Hz      |
| Channels (incoming, `track=both`)               | Stereo — left = caller, right = callee |
| Channels (incoming, `track=inbound`/`outbound`) | Mono                                   |
| Channels (outgoing to Firetell)                 | Mono                                   |

---

## WebSocket Protocol

| Direction              | Frame type  | Content                                                     |
| ---------------------- | ----------- | ----------------------------------------------------------- |
| Firetell → Your server | Binary      | Raw PCM audio (caller's speech)                             |
| Your server → Firetell | Binary      | Raw PCM audio (bot speech — requires `bidirectional: true`) |
| Your server → Firetell | Text (JSON) | `{"type":"killAudio"}` — stop queued playback (barge-in)    |

---

## Query Parameters (Auto-Appended by Firetell)

Firetell automatically appends the following to your `ws_url` so you can identify the call without custom headers:

| Parameter            | Description                          |
| -------------------- | ------------------------------------ |
| `call_id`            | Unique Firetell call identifier      |
| `workspace_id`       | Your Firetell workspace ID           |
| `caller_number`      | Caller's phone number (E.164)        |
| `caller_name`        | Caller's display name (if available) |
| `destination_number` | The dialed number                    |
| `stream_type`        | Always `firetell_stream`             |

---

## Local Development with ngrok

If you don't have a public server, use [ngrok](https://ngrok.com) to expose your local server:

```bash
# Terminal 1 — start your server
python examples/full_duplex_bot.py

# Terminal 2 — expose it publicly
ngrok http 3001
```

Use the `wss://` ngrok URL in your `ws_url` param.

---

## Build Your AI Pipeline

Replace the placeholder logic in `full_duplex_bot.py` with your actual pipeline:

```python
async for message in websocket:
    if isinstance(message, str):
        continue
    caller_audio: bytes = message

    # 1. Voice Activity Detection (barge-in)
    if vad.is_speaking(caller_audio):
        await send_kill_audio()

    # 2. Stream to STT (e.g. Deepgram, Google, OpenAI Whisper)
    await stt_stream.send(caller_audio)

# When STT returns a final transcript:
async def on_transcript(text: str) -> None:
    # 3. LLM (e.g. OpenAI GPT-4, Google Gemini)
    reply = await llm.chat(text)

    # 4. TTS → PCM (must be mono, 16-bit, at SAMPLE_RATE Hz)
    audio_pcm = await tts.synthesize(reply, sample_rate=SAMPLE_RATE)
    await send_audio(audio_pcm)
```

---

## License

MIT — see [LICENSE](LICENSE)

## Contributing

Issues and PRs are welcome at [github.com/firetellcom/audio-stream-python-example](https://github.com/firetellcom/audio-stream-python-example).
