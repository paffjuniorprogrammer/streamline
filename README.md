# Streamline

A Flask-based authorized media player for direct MP4, WebM, and MKV URLs. MKV sources are transcoded to browser-compatible fragmented MP4 with FFmpeg.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python movie.py
```

Open `http://127.0.0.1:5000` and provide a direct media URL that you own or are authorized to stream.

FFmpeg must be installed and available on `PATH`. Set `FFMPEG_PATH` when it is installed elsewhere. `MAX_TRANSCODES` controls the maximum number of concurrent conversions and defaults to `3`.

## Production note

Do not expose Flask's development server directly to the public internet. Run the app behind a production WSGI server such as Waitress and a reverse proxy. Use only authorized media sources.