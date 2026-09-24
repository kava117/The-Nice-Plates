# ml

Turns a recording into text, then pulls tempo / key / time signature out of the text.

## 1. Install
```
pip install -r requirements.txt
```

## 2. Add your OpenAI key
```
cp .env.example .env
```
Open `.env`, replace `sk-your-key-here` with your key from https://platform.openai.com/api-keys.

`.env` is gitignored. Do not commit it.

## 3. Check it works (no key needed)
```
python ml/test_text.py
```
Should print `ok`.

## 4. Run on a recording
```
python ml/run.py clip.mp3
```
Should print:
```
{
  "text": "Minuet in G major at 80 bpm, three four.",
  "segments": [{"start": 0.0, "end": 3.2, "text": "Minuet in G major at 80 bpm, three four."}],
  "music": {"tempo": 80, "key": "G major", "time_signature": "3/4"}
}
```
Any mp3, m4a, wav or webm under 25 MB works.

## What each file does
- `transcribe.py` sends the audio to Whisper, gets text back.
- `text.py` reads the text, finds tempo / key / time signature.
- `run.py` runs both and prints the result.
- `test_text.py` checks `text.py` on three example sentences.

## To extend
- New music info: add one regex line in `text.py`.
- Use from the website: `from ml.transcribe import transcribe` and `from ml.text import process`.
