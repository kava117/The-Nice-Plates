"""Easier conversions: PDF -> PNG, MusicXML merging, and MusicXML -> MIDI."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pymupdf
from music21 import converter, stream


def pdf_to_pngs(pdf_path: Path, out_dir: Path, dpi: int = 300) -> list[Path]:
    """Rasterize every page of a PDF to out_dir; return the PNG paths in page order."""
    pngs = []
    with pymupdf.open(pdf_path) as doc:
        for i, page in enumerate(doc):
            png = out_dir / f"page_{i:03d}.png"
            page.get_pixmap(dpi=dpi).save(png)
            pngs.append(png)
    return pngs


def merge_musicxml(xml_paths: Sequence[Path], out_path: Path) -> Path:
    """Append each score's measures to the first, part by part; return out_path."""
    merged, *rest = (converter.parse(p) for p in xml_paths)
    for score in rest:
        for part, extra in zip(merged.parts, score.parts, strict=True):
            for measure in extra.getElementsByClass(stream.Measure):
                part.append(measure)
    merged.write("musicxml", fp=out_path)
    return out_path


def musicxml_to_midi(xml_path: Path, midi_path: Path) -> Path:
    """Convert a MusicXML file to MIDI with music21; return midi_path."""
    converter.parse(xml_path).write("midi", fp=midi_path)
    return midi_path
