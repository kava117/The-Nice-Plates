# Gunicorn reads this file by itself, so it holds even when Render's start command is a bare
# "gunicorn app:app" (the dashboard doesn't read render.yaml). Flags on the command line win.
workers = 1      # a second would double homr's memory on the 512 MB box
threads = 4      # one slow page no longer holds up every other click
timeout = 300    # a photo read by Claude can take a minute
