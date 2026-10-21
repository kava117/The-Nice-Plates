"""The ml tools as a web API.   Run alone: python ml/api.py   (port 8002)"""
import logging, os, sys, tempfile
from io import BytesIO
from pathlib import Path

from flask import Blueprint, Flask, abort, jsonify, redirect, request, send_file
from flask_login import current_user

HERE = Path(__file__).parent
sys.path[:0] = [str(HERE), str(HERE.parent), str(HERE.parent / "fileConversion")]  # lets app.py import this file too
from database import database

api = Blueprint("ml", __name__, url_prefix="/api")


def user_id():
    return current_user.id if current_user.is_authenticated else database.demoUser()
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
    return jsonify(database.getPieces(user_id()))


def claude_reads(src):  # small servers can't fit homr; with an ANTHROPIC_API_KEY a vision model writes the MusicXML instead
    import base64, anthropic
    from music21 import converter
    if src.suffix.lower() == ".pdf":
        import fitz
        src = src.with_suffix(".png"); src.write_bytes(fitz.open(src.with_suffix(".pdf"))[0].get_pixmap(dpi=200).tobytes("png"))
    image = {"type": "base64", "media_type": "image/png" if src.suffix.lower() == ".png" else "image/jpeg",
             "data": base64.standard_b64encode(src.read_bytes()).decode()}
    key, workspace = (os.environ.get(k, "").strip() for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_WORKSPACE_ID"))  # pasted values often end in a newline
    with anthropic.Anthropic(api_key=key, default_headers={"anthropic-workspace-id": workspace} if workspace else {}).beta.messages.stream(
        model=os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5"), max_tokens=64000,
        betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        messages=[{"role": "user", "content": [{"type": "image", "source": image},
                  {"type": "text", "text": "Transcribe this sheet music as complete MusicXML (score-partwise, every note and rest, correct key and time signature). Reply with only the XML."}]}],
    ) as stream:
        text = stream.get_final_message().content[-1].text
    xml = src.with_suffix(".musicxml")
    xml.write_text(text[text.index("<"):text.rindex(">") + 1])
    converter.parse(xml)  # unreadable output raises, and the upload form says so
    return xml

@api.post("/pieces")  # the library's upload form: sheet music in, saved to Pieces as MusicXML + MIDI
def add_piece():
    from easyParts import musicxml_to_midi
    from pdfToMidi import _to_musicxml
    src = save_upload()
    photo = src.suffix.lower() in (".pdf", ".png", ".jpg", ".jpeg")
    if photo and os.environ.get("PHOTO_UPLOADS") == "off" and not os.environ.get("ANTHROPIC_API_KEY"):
        return redirect("/library?error=Reading photos and PDFs needs about 1 GB of memory, more than this free server has. Upload a MusicXML file here, or run the site on a laptop.")
    try:
        xml = claude_reads(src) if photo and os.environ.get("PHOTO_UPLOADS") == "off" else _to_musicxml(src, Path(tempfile.mkdtemp()))
        mid = musicxml_to_midi(xml, src.with_suffix(".mid"))
    except Exception:
        logging.exception(src.name)  # the page gets a plain message; the server log keeps the cause
        return redirect(f"/library?error=Could not read {src.name}. Upload a PDF, a photo of a score, or a MusicXML file.")
    piece_id = database.addPiece(user_id(), request.form.get("title") or src.stem,
                                 request.form.get("composer") or None, xml=xml.read_bytes(), midi=mid.read_bytes())
    return redirect(f"/practice?piece={piece_id}")


@api.get("/pieces/<int:piece_id>/musicxml")  # what the practice page renders
def piece_xml(piece_id):
    database.getPieceForUser(user_id(), piece_id) or abort(404)
    database.touchPiece(piece_id)  # the home page shows the three most recently opened
    return send_file(BytesIO(database.getXML(piece_id)["xml"]), mimetype="application/xml")


@api.post("/pieces/<int:piece_id>/recordings")  # the practice page's Record button
def add_recording(piece_id):
    database.getPieceForUser(user_id(), piece_id) or abort(404)
    return jsonify(id=database.addRecording(piece_id, request.files["file"].read()))


@api.get("/recordings/<int:recording_id>")
def play_recording(recording_id):
    row = database.getRecording(user_id(), recording_id) or abort(404)
    return send_file(BytesIO(row["audio"]), mimetype="audio/webm")


if __name__ == "__main__":
    database.init_db()
    app = Flask(__name__)
    app.register_blueprint(api)
    app.run(port=8002)
