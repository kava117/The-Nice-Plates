"""Convert a PDF, image, or MusicXML file into a MIDI file."""

from __future__ import annotations

import argparse
import shutil
import tempfile
from pathlib import Path

from easyParts import musicxml_to_midi, pdf_to_pngs
from homr_omr import run_homr

PDF = {".pdf"}
IMAGES = {".png", ".jpg", ".jpeg"}
MUSICXML = {".musicxml", ".xml", ".mxl"}


def _to_musicxml(src: Path, work: Path) -> Path:
    """Enter the pipeline at the stage matching src's type; return a MusicXML path."""
    suffix = src.suffix.lower()
    if suffix in MUSICXML:
        return src
    if suffix in PDF:
        images = pdf_to_pngs(src, work)
        if not images:
            raise ValueError(f"no pages in {src}")
    else:
        images = [Path(shutil.copy(src, work))]
    return run_homr(images)


# TODO: Audiveris backend
def convert(src: Path, dst: Path | None = None, keep: bool = False) -> Path:
    """Convert a PDF, image, or MusicXML file to MIDI; return the .mid path."""
    if not src.exists():
        raise FileNotFoundError(f"input not found: {src}")
    accepted = sorted(PDF | IMAGES | MUSICXML)
    if src.suffix.lower() not in accepted:
        raise ValueError(f"unsupported file {src.name}; expected one of {accepted}")
    dst = dst or src.with_suffix(".mid")
    if keep:
        work = dst.parent / f"{dst.stem}_work"
        work.mkdir(parents=True, exist_ok=True)
        return musicxml_to_midi(_to_musicxml(src, work), dst)
    with tempfile.TemporaryDirectory() as tmp:
        return musicxml_to_midi(_to_musicxml(src, Path(tmp)), dst)


def main() -> None:
    """Parse CLI args and call convert()."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument("--keep-intermediates", action="store_true")
    args = parser.parse_args()
    print(convert(args.input, args.output, args.keep_intermediates))


if __name__ == "__main__":
    main()
