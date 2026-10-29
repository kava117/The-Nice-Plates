"""The ml tools as a web API.   Run alone: python ml/api.py   (port 8002)"""
import logging, os, sys, tempfile, threading
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

from flask import Blueprint, Flask, abort, jsonify, redirect, request, send_file
from flask_login import current_user

HERE = Path(__file__).parent
sys.path[:0] = [str(HERE), str(HERE.parent), str(HERE.parent / "fileConversion")]  # lets app.py import this file too
from database import database

api = Blueprint("ml", __name__, url_prefix="/api")


def user_id():
    return current_user.id if current_user.is_authenticated else database.demoUser()
# The pipeline (ml/requirements.txt) is imported inside the routes that need it, so the site runs without it.


CONVERT = threading.Semaphore(1)  # gunicorn runs 4 threads in one 512 MB process: a second upload waits rather than start a second homr
SCORES = {".musicxml", ".xml", ".mxl"}
PHOTOS = {".pdf", ".png", ".jpg", ".jpeg"}


def homr_ok():  # homr runs in this process, or on its own box at HOMR_URL (homr_service/)
    return bool(os.environ.get("HOMR_URL", "").strip()) or os.environ.get("PHOTO_UPLOADS") != "off"


def upload_problem(filename, claude_ok):
    """None if this upload can be read here, else a message for the user."""
    if not filename:
        return "Choose a file to upload."
    suffix = Path(filename).suffix.lower()
    if suffix not in SCORES | PHOTOS:
        return "Upload a PDF, PNG, JPG or MusicXML file."
    if suffix in PHOTOS and not homr_ok() and not claude_ok:  # homr would need ~1 GB on a 512 MB box
        return "Reading photos and PDFs needs about 1 GB of memory, more than this free server has. Upload a MusicXML file here, or run the site on a laptop."
    return None


def library_error(message):  # quote() so a '#' or '&' in a filename can't cut the message short
    return redirect("/library?error=" + quote(message))


@contextmanager
def saved_upload():  # the folder and everything converted into it is deleted when the block ends, even on an error
    upload = request.files["file"]
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / Path(upload.filename).name
        upload.save(path)
        yield path


@api.post("/midi")  # sheet music in, MIDI out
def midi():
    from pdfToMidi import convert  # Robert's pipeline: PDF, image or MusicXML -> MIDI
    problem = upload_problem(request.files["file"].filename, claude_ok=False)  # no Claude path here
    if problem:
        return jsonify(error=problem), 400
    with saved_upload() as src, CONVERT:
        mid = convert(src)
        return send_file(BytesIO(mid.read_bytes()), download_name=mid.name, mimetype="audio/midi")  # read now: the folder is gone before send_file streams


@api.post("/transcribe")  # recording in, text + tempo / key / time signature out
def recording():
    import text, transcribe
    with saved_upload() as src:
        result = transcribe.transcribe(src)
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
        model=os.environ.get("CLAUDE_MODEL", "claude-haiku-5-5"), max_tokens=64000,   # Haiku: $0.10 in / $0.50 out per million tokens, a twentieth of Sonnet
        messages=[{"role": "user", "content": [{"type": "image", "source": image},
                  {"type": "text", "text": "Transcribe this sheet music as complete MusicXML (score-partwise, every note and rest, correct key and time signature). Reply with only the XML."}]}],
    ) as stream:
        reply = stream.get_final_message()
    text = reply.content[-1].text
    used = getattr(reply, "usage", None)
    logging.warning("Claude read %s with %s: %s tokens in, %s out", src.name, getattr(reply, "model", "?"),
                    getattr(used, "input_tokens", "?"), getattr(used, "output_tokens", "?"))   # the Render log shows what each upload cost
    xml = src.with_suffix(".musicxml")
    xml.write_text(text[text.index("<"):text.rindex(">") + 1])
    converter.parse(xml)  # unreadable output raises, and the upload form says so
    return xml

def read_sheet(src, work, claude_ok):  # homr first wherever it can run; Claude when it can't, or when it fails
    from music21 import converter
    from pdfToMidi import _to_musicxml
    if src.suffix.lower() not in PHOTOS:
        return _to_musicxml(src, work)
    if homr_ok():
        try:
            xml = _to_musicxml(src, work)
            converter.parse(xml)  # unreadable output is a failure too, so Claude gets its turn
            logging.warning("homr read %s", src.name)
            return xml
        except Exception as e:
            if not claude_ok:
                raise
            logging.warning("homr could not read %s (%s); Claude will", src.name, e)
    return claude_reads(src)

@api.post("/pieces")  # the library's upload form: sheet music in, saved to Pieces as MusicXML + MIDI
def add_piece():
    from easyParts import musicxml_to_midi
    claude_ok = bool(os.environ.get("ANTHROPIC_API_KEY"))
    problem = upload_problem(request.files["file"].filename, claude_ok)
    if problem:
        return library_error(problem)
    with saved_upload() as src:
        try:
            with CONVERT:
                work = src.parent / "work"; work.mkdir()
                xml = read_sheet(src, work, claude_ok)
                mid = musicxml_to_midi(xml, src.with_suffix(".mid"))
        except Exception:
            logging.exception(src.name)  # the page gets a plain message; the server log keeps the cause
            return library_error(f"Could not read {src.name}. Upload a PDF, a photo of a score, or a MusicXML file.")
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
    audio = request.files["file"].read()
    if not audio:   # the microphone gave nothing (denied mid-take, or stopped at once)
        return jsonify(error="the recording is empty"), 400
    return jsonify(id=database.addRecording(piece_id, audio))


@api.get("/recordings/<int:recording_id>")
def play_recording(recording_id):
    row = database.getRecording(user_id(), recording_id) or abort(404)
    return send_file(BytesIO(row["audio"]), mimetype="audio/webm")


if __name__ == "__main__":
    database.init_db()
    app = Flask(__name__)
    app.register_blueprint(api)
    app.run(port=8002)
