# bookworm, not the default slim: the apt package names below are different on trixie.
FROM python:3.11-slim-bookworm

# rapidocr, which homr reads titles with, pulls in the full opencv-python, and that needs these.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libsm6 libxext6 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
# --init downloads homr's models into the image, so a cold start doesn't fetch them from GitHub.
RUN pip install --no-cache-dir -r requirements.txt && homr --init
COPY server.py .

EXPOSE 8000
CMD ["gunicorn", "server:app", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "2", "--timeout", "300", "--access-logfile", "-"]
