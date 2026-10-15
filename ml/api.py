"""The ml tools as a web API.   Run alone: python ml/api.py   (port 8002)"""
import sys, tempfile
from io import BytesIO
from pathlib import Path

from flask import Blueprint, Flask, abort, jsonify, redirect, request, send_file

HERE = Path(__file__).parent
sys.path[:0] = [str(HERE), str(HERE.parent), str(HERE.parent / "fileConversion")]  # lets app.py import this file too
from database import database

api = Blueprint("ml", __name__, url_prefix="/api")
# The pipeline (ml/requirements.txt) is imported inside the routes that need it, so the site runs without it.


def save_upload():
    upload = request.files["file"]
    path = Path(tempfile.mkdtemp()) / Path(upload.filename).name
    upload.save(path)
    return path


@api.post("/midi")  # sheet music in, MIDI out
def midi():
    from pdfToMidi import convert  # Robert's pipeline: PDF, image or MusicXML -> MIDI
    return send_file(convert(save_upload()))


@api.post("/transcribe")  # recording in, text + tempo / key / time signature out
def recording():
    import text, transcribe
    result = transcribe.transcribe(save_upload())
    return jsonify({**result, "music": text.process(result["text"])})


@api.get("/pieces")  # the library
def pieces():
    return jsonify(database.fetchPieces(database.demoUser()))


@api.post("/pieces")  # the library's upload form: sheet music in, saved to Pieces as MusicXML + MIDI
def add_piece():
    from easyParts import musicxml_to_midi
    from pdfToMidi import _to_musicxml
    src = save_upload()
    xml = _to_musicxml(src, Path(tempfile.mkdtemp()))
    mid = musicxml_to_midi(xml, src.with_suffix(".mid"))
    piece_id = database.addPiece(database.demoUser(), request.form.get("title") or src.stem,
                                 request.form.get("composer") or None, xml=xml.read_bytes(), midi=mid.read_bytes())
    return redirect(f"/practice.html?piece={piece_id}")


@api.get("/pieces/<int:piece_id>/musicxml")  # what the practice page renders
def piece_xml(piece_id):
    piece = database.fetchPiece(database.demoUser(), piece_id) or abort(404)
    return send_file(BytesIO(piece["xml"]), mimetype="application/xml")


if __name__ == "__main__":
    database.init_db()
    app = Flask(__name__)
    app.register_blueprint(api)
    app.run(port=8002)
