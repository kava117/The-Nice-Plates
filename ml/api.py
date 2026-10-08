"""The ml tools as a web API.   Run alone: python ml/api.py   (port 8002)"""
import sys, tempfile
from pathlib import Path

from flask import Blueprint, Flask, jsonify, request, send_file

sys.path.insert(0, str(Path(__file__).parent))  # lets app.py import this file too
import sheet, text, transcribe

api = Blueprint("ml", __name__, url_prefix="/api")


def save_upload():
    upload = request.files["file"]
    path = Path(tempfile.mkdtemp()) / Path(upload.filename).name
    upload.save(path)
    return path


@api.post("/sheet")  # sheet music PDF in, MIDI out (?as=musicxml for the notes)
def sheet_music():
    musicxml = sheet.png_to_musicxml(sheet.pdf_to_png(save_upload()))
    return send_file(musicxml if request.args.get("as") == "musicxml" else sheet.musicxml_to_midi(musicxml))


@api.post("/transcribe")  # recording in, text + tempo / key / time signature out
def recording():
    result = transcribe.transcribe(save_upload())
    return jsonify({**result, "music": text.process(result["text"])})


if __name__ == "__main__":
    app = Flask(__name__)
    app.register_blueprint(api)
    app.run(port=8002)
