# MAIN # 
# use the other files to convert an input PDF file into a MIDI file 
from easyParts import pdf_to_pngs, musicxml_to_midi

pdf_to_pngs("score.pdf")
musicxml_to_midi("score.musicxml", "score.mid")
# 3 methods: oemer, homr, Audiveris

# oemer - Good for grand staff and two part 

# homr

# Audiveris


