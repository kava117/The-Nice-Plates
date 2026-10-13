"""The ml tools as a web API.   Run alone: python ml/api.py   (port 8002)"""
import sys, tempfile
from pathlib import Path

from flask import Blueprint, Flask, jsonify, request, send_file

HERE = Path(__file__).parent
sys.path[:0] = [str(HERE), str(HERE.parent / "fileConversion")]  # lets app.py import this file too
import text, transcribe
from pdfToMidi import convert  # Robert's pipeline: PDF, image or MusicXML -> MIDI

api = Blueprint("ml", __name__, url_prefix="/api")


def save_upload():
    upload = request.files["file"]
    path = Path(tempfile.mkdtemp()) / Path(upload.filename).name
    upload.save(path)
    return path


@api.post("/midi")  # sheet music in, MIDI out
def midi():
    return send_file(convert(save_upload()))


@api.post("/transcribe")  # recording in, text + tempo / key / time signature out
def recording():
    result = transcribe.transcribe(save_upload())
    return jsonify({**result, "music": text.process(result["text"])})


if __name__ == "__main__":
    app = Flask(__name__)
    app.register_blueprint(api)
    app.run(port=8002)
