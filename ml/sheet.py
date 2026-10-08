"""Sheet music PDF -> MusicXML -> MIDI.   Run: python ml/sheet.py score.pdf"""
import subprocess, sys
from pathlib import Path

import pymupdf
from music21 import converter


def pdf_to_png(pdf):
    png = pdf.with_suffix(".png")
    pymupdf.open(pdf)[0].get_pixmap(dpi=300).save(png)  # page 1, 300 dpi keeps thin stems
    return png


def png_to_musicxml(png):
    subprocess.run(["homr", png], check=True)  # same as typing: homr score.png
    return png.with_suffix(".musicxml")        # homr saves it next to the png


def musicxml_to_midi(musicxml):
    mid = musicxml.with_suffix(".mid")
    converter.parse(musicxml).write("midi", fp=mid)
    return mid


if __name__ == "__main__":
    png = pdf_to_png(Path(sys.argv[1]))
    musicxml = png_to_musicxml(png)
    print(musicxml_to_midi(musicxml))
