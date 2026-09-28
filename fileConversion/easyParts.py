# Easier conversions- PDF -> PNG and XML -> MIDI

import fitz
from music21 import converter

def pdf_to_pngs(pdf_path, dpi=300):
    with fitz.open(pdf_path) as doc:
        for i, page in enumerate(doc):
            page.get_pixmap(dpi=dpi).save(f"page_{i:03d}.png")

def musicxml_to_midi(xml_path, midi_path):
    converter.parse(xml_path).write("midi", fp=midi_path)