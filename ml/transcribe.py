"""Audio file -> text, via OpenAI Whisper. Needs OPENAI_API_KEY in .env"""
from dotenv import load_dotenv
from openai import OpenAI


def transcribe(path):
    """Return {"text": full transcript, "segments": [{"start", "end", "text"}, ...]}"""
    load_dotenv()
    with open(path, "rb") as f:
        r = OpenAI().audio.transcriptions.create(
            model="whisper-1", file=f,
            response_format="verbose_json", timestamp_granularities=["segment"])
    return {"text": r.text.strip(),
            "segments": [{"start": s.start, "end": s.end, "text": s.text.strip()} for s in r.segments]}
