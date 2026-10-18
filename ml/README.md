# ml

![](../docs/system.svg)

Sheet music goes through Robert's `fileConversion/` pipeline. With `PHOTO_UPLOADS=off` and an `ANTHROPIC_API_KEY`, `claude_reads` in `api.py` writes the MusicXML from the image instead of homr. Recordings go through Whisper (`transcribe.py`) and `text.py` for tempo, key and time.

```bash
pip install -r ml/requirements.txt    # Python 3.11+
cp ml/.env.example ml/.env            # OpenAI key, only /transcribe needs it
python app.py                         # the site on :8001, API included
```

| route | in | out |
|---|---|---|
| `POST /api/pieces` | the library's upload form: sheet, `title`, `composer` | saved to Pieces, then the practice page |
| `GET /api/pieces` | | the library as JSON |
| `GET /api/pieces/ID/musicxml` | | the stored MusicXML, which the practice page renders |
| `POST /api/midi` | sheet | MIDI, nothing saved |
| `POST /api/transcribe` | recording | transcript + tempo / key / time, nothing saved |

Pieces belong to the signed-in Google user, or to `Sample User` when nobody is signed in.

Why homr, with test results: the `ml-evals` branch.
