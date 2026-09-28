"""homr vs oemer on pages where we know the right notes.   Run: python ml/homr_vs_oemer/compare.py

Each folder has page.png, the right answer (truth.musicxml, which verovio drew as page.png),
and what each reader wrote after reading page.png.
oemer 0.1.5, the version pip gives a Mac, only ran after three fixes: CPU instead of CoreML,
numpy.int = int, and opencv-python<5.
"""
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt
from music21 import converter

HERE = Path(__file__).parent
PAGES = {"melody": "melody", "chorale": "Bach chorale", "piano": "Joplin rag"}
COLORS = {"homr": "#2f8a5b", "oemer": "#8a7fd0"}
SECONDS = {"homr": [6, 6, 3], "oemer": [268, 261, 276]}  # one page at a time, M3 MacBook


def notes(musicxml):
    """Every note head as (pitch, length). A chord gives one per head."""
    score = converter.parse(musicxml)
    return Counter((p.midi, float(n.quarterLength)) for n in score.flatten().notes for p in n.pitches)


def percent_right(page, reader):
    """Missing notes and extra notes both pull this down."""
    truth = notes(HERE / page / "truth.musicxml")
    got = notes(HERE / page / f"{reader}.musicxml")
    matched = sum((truth & got).values())
    average = (sum(truth.values()) + sum(got.values())) / 2
    return round(100 * matched / average)


plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False, "font.size": 9})
fig, (notes_ax, time_ax) = plt.subplots(1, 2, figsize=(8, 2.6))
for i, reader in enumerate(COLORS):
    x = [n + (i - 0.5) * 0.4 for n in range(len(PAGES))]  # homr just left of each label, oemer just right
    percents = [percent_right(page, reader) for page in PAGES]
    print(reader, dict(zip(PAGES, percents)))
    for ax, values in ((notes_ax, percents), (time_ax, SECONDS[reader])):
        bars = ax.bar(x, values, 0.36, color=COLORS[reader], label=reader)
        ax.bar_label(bars, padding=2)
for ax in (notes_ax, time_ax):
    ax.set_xticks(range(len(PAGES)), PAGES.values())
notes_ax.set(ylabel="notes right (%)", ylim=(0, 110))
time_ax.set(ylabel="seconds per page")
notes_ax.legend(frameon=False, ncols=2, loc="upper left", bbox_to_anchor=(0, 1.18))
fig.savefig(HERE / "results.png", dpi=200, bbox_inches="tight")
