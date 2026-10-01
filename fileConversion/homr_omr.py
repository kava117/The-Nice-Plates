"""Optical music recognition via the homr CLI."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

from easyParts import merge_musicxml


def _expected_output(image: Path) -> Path:
    """Return the MusicXML path homr writes for one image."""
    return image.with_suffix(".musicxml")


def run_homr(images: Sequence[Path]) -> Path:
    """Run homr on one or more page images; return the MusicXML it wrote."""
    if shutil.which("homr") is None:
        raise RuntimeError("homr not found — pip install 'homr[cpu]'")
    pages = []
    for image in images:  # homr's released CLI takes one image per call
        subprocess.run(["homr", str(image)], check=True)
        output = _expected_output(image)
        if not output.exists():
            raise FileNotFoundError(f"homr did not write {output}")
        pages.append(output)
    if len(pages) == 1:
        return pages[0]
    first = images[0]
    return merge_musicxml(pages, first.with_name(f"merged_{first.stem}.musicxml"))
