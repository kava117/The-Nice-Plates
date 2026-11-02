"""Optical music recognition via the homr CLI, here or on homr_service/ when HOMR_URL is set."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

import requests

from easyParts import merge_musicxml


def _expected_output(image: Path) -> Path:
    """Return the MusicXML path homr writes for one image."""
    return image.with_suffix(".musicxml")


def _read_on_service(url: str, image: Path) -> None:
    """Send one page to homr_service/ and write its MusicXML where the CLI would."""
    token = os.environ.get("HOMR_TOKEN", "").strip()
    with image.open("rb") as f:
        # a page takes up to a minute on 2 vCPUs, plus up to a minute to wake a box scaled to zero
        reply = requests.post(f"{url}/read", files={"file": (image.name, f)},
                              headers={"Authorization": f"Bearer {token}"}, timeout=(10, 240))
    if not reply.ok:
        raise RuntimeError(f"homr service answered {reply.status_code}: {reply.text[-300:]}")
    _expected_output(image).write_bytes(reply.content)


def run_homr(images: Sequence[Path]) -> Path:
    """Run homr on one or more page images; return the MusicXML it wrote."""
    url = os.environ.get("HOMR_URL", "").strip().rstrip("/")
    if not url and shutil.which("homr") is None:
        raise RuntimeError("homr not found — pip install 'homr[cpu]', or set HOMR_URL")
    pages = []
    for image in images:  # homr's released CLI takes one image per call
        if url:
            _read_on_service(url, image)
        else:
            subprocess.run(["homr", str(image)], check=True)
        output = _expected_output(image)
        if not output.exists():
            raise FileNotFoundError(f"homr did not write {output}")
        pages.append(output)
    if len(pages) == 1:
        return pages[0]
    first = images[0]
    return merge_musicxml(pages, first.with_name(f"merged_{first.stem}.musicxml"))
