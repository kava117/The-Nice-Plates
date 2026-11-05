# Gunicorn reads this file by itself, so it holds even when Render's start command is a bare
# "gunicorn app:app" (the dashboard doesn't read render.yaml). Flags on the command line win.
workers = 1      # a second would double homr's memory on the 512 MB box
threads = 16     # a photo Claude is reading holds a thread for a minute; the rest keep the site answering
timeout = 300    # a photo read by Claude can take a minute
