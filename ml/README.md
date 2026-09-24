# ml

Audio file -> text (OpenAI Whisper) -> tempo / key / time signature.

## Setup
    pip install -r requirements.txt
    cp .env.example .env        # paste your OpenAI key into .env

Get a key at https://platform.openai.com/api-keys. Never commit `.env`.

## Run
    python ml/run.py clip.mp3

Prints:

    {
      "text": "Minuet in G major at 80 bpm, three four.",
      "segments": [{"start": 0.0, "end": 3.2, "text": "..."}],
      "music": {"tempo": 80, "key": "G major", "time_signature": "3/4"}
    }

Whisper accepts mp3, mp4, m4a, wav, webm (max 25 MB).

## Test without a key
    python ml/test_text.py

## Files
| file            | does                                              |
|-----------------|---------------------------------------------------|
| `transcribe.py` | audio -> text + timestamps. One Whisper call.     |
| `text.py`       | text -> tempo, key, time signature. Regex only.   |
| `run.py`        | glues the two, prints JSON.                       |

To add more music info, add a regex to `text.py`. To feed the UI, import `transcribe` and `process`.
