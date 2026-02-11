# ElevenLabs Voice Profile — Channel Standard

## Voice

| Setting          | Value                    |
|------------------|--------------------------|
| Voice name       | Thomas Louis             |
| Source           | My Voices (custom)       |
| voice_id         | `IHw7aBJxrIo1SxkG9px5` (env: `ELEVENLABS_VOICE_ID`) |

## Generation Settings (Frozen)

| Parameter        | Value   | Notes                          |
|------------------|---------|--------------------------------|
| stability        | 0.50    | Balanced — not robotic, not chaotic |
| similarity_boost | 0.75    | Close to original voice        |
| style            | 0.00    | No style exaggeration          |
| model_id         | eleven_multilingual_v2 | Best quality for English |
| output_format    | mp3_44100_128 | Good quality, smaller files |

Do NOT change these settings between videos. Consistency > experimentation.

## Speaking Pace

- Target: ~155 words per minute (natural conversational)
- No rush, no drag
- Slight emphasis on product names and verdicts
- Calm authority — helpful expert, not hype man

## Tone Rules

- Sound helpful and slightly opinionated
- Never salesy or overhyped
- Never robotic or monotone
- Confident but not arrogant
- Natural pauses at commas and periods

## Forbidden Styles

- Overly enthusiastic / YouTuber energy
- Whisper ASMR
- Radio DJ voice
- Robotic / flat reading
- Sarcastic tone

## Fixed Lines (Generate Once, Reuse)

### Avatar Intro (3-5s)
Pre-generate and reuse across videos:
"Welcome back. Let's get into the rankings."

### Outro Disclosure
Pre-generate and reuse:
"As an Amazon Associate I earn from qualifying purchases."

These become consistent brand audio cues. Generate once, save to `audio/templates/`.
