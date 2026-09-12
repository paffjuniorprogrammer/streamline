from html.parser import HTMLParser
import os
from pathlib import Path
import shutil
import subprocess
import threading
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urljoin, urlparse
from urllib.request import Request, urlopen

from flask import Flask, Response, render_template, request, stream_with_context, url_for

app = Flask(__name__)


def get_ffmpeg_path():
    configured_path = os.environ.get("FFMPEG_PATH")
    if configured_path and Path(configured_path).is_file():
        return configured_path

    installed_path = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    matches = installed_path.glob("Gyan.FFmpeg*/*/bin/ffmpeg.exe")
    return str(next(matches, "")) or shutil.which("ffmpeg") or "ffmpeg"


FFMPEG_PATH = get_ffmpeg_path()
MAX_TRANSCODES = max(1, int(os.environ.get("MAX_TRANSCODES", "3")))
transcode_slots = threading.BoundedSemaphore(MAX_TRANSCODES)


class MediaSourceParser(HTMLParser):
    """Find explicit HTML5 media sources without executing page scripts."""

    def __init__(self):
        super().__init__()
        self.sources = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag in {"video", "source"} and attributes.get("src"):
            self.sources.append(attributes["src"])

HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">

    <title>My Video Streamer</title>

    <style>
        * {
            box-sizing: border-box;
        }

        body {
            margin: 0;
            background: #111;
            color: white;
            font-family: Arial, sans-serif;
        }

        .container {
            width: 90%;
            max-width: 1000px;
            margin: 50px auto;
        }

        h1 {
            text-align: center;
            margin-bottom: 30px;
        }

        form {
            display: flex;
            gap: 10px;
            margin-bottom: 30px;
        }

        input {
            flex: 1;
            padding: 15px;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            outline: none;
        }

        button {
            padding: 15px 25px;
            border: none;
            border-radius: 8px;
            background: #008cff;
            color: white;
            font-size: 16px;
            cursor: pointer;
        }

        button:hover {
            background: #006dcc;
        }

        button:disabled {
            background: #555;
            cursor: wait;
        }

        video {
            width: 100%;
            max-height: 600px;
            background: black;
            border-radius: 10px;
        }

        .message {
            text-align: center;
            color: #aaa;
        }

        .url {
            margin-top: 15px;
            color: #aaa;
            word-break: break-all;
            font-size: 14px;
        }

        .controls {
            display: flex;
            gap: 10px;
            align-items: center;
            margin-top: 12px;
        }

        .controls input {
            max-width: 180px;
            padding: 10px;
        }

        .status {
            color: #aaa;
            min-height: 20px;
        }

        @media (max-width: 600px) {
            form {
                flex-direction: column;
            }

            button {
                width: 100%;
            }
        }
    </style>
</head>

<body>

<div class="container">

    <h1>🎬 My Video Streamer</h1>

    <form method="POST" id="url-form">

        <input
            type="url"
            name="video_url"
            placeholder="Paste direct video URL..."
            value="{{ video_url }}"
            required
        >

        <button type="submit" id="play-button">
            ▶ Play Video
        </button>

    </form>

    {% if error %}

        <p class="message">{{ error }}</p>

    {% elif video_url %}

        <video controls playsinline preload="metadata" data-stream-url="{{ stream_url }}">
            <source src="{{ stream_url }}">
            Your browser does not support video playback.
        </video>

        <div class="controls">
            <input id="jump-time" type="text" inputmode="numeric" placeholder="00:20:00" aria-label="Jump to time">
            <button type="button" id="jump-button">Jump</button>
            <button type="button" id="five-minute-button">+5 min</button>
        </div>
        <p class="status" id="video-status">Ready. Use the timeline or enter a time.</p>

        <script>
            const video = document.querySelector("video");
            const serverStream = video.dataset.streamUrl.startsWith("/stream?");
            let serverSeek = false;
            let ignoreSeekUntil = 0;

            function parseTime(value) {
                const parts = value.trim().split(":").map(Number);
                if (parts.some((part) => !Number.isFinite(part) || part < 0) || parts.length > 3) {
                    return NaN;
                }
                return parts.reduce((total, part) => total * 60 + part, 0);
            }

            function jumpTo(seconds) {
                if (!Number.isFinite(seconds) || seconds < 0) {
                    document.querySelector("#video-status").textContent = "Enter a valid time such as 00:20:00.";
                    return;
                }
                if (!serverStream) {
                    video.currentTime = seconds;
                    video.play().catch(() => {});
                    return;
                }

                serverSeek = true;
                ignoreSeekUntil = Date.now() + 1500;
                video.dataset.targetTime = seconds;
                document.querySelector("#video-status").textContent = "Seeking...";
                video.src = `${video.dataset.streamUrl}&start=${encodeURIComponent(seconds)}`;
                video.load();
                video.play().catch(() => {});
            }

            video.addEventListener("seeking", () => {
                if (!serverStream || serverSeek || Date.now() < ignoreSeekUntil || video.currentTime < 1) {
                    return;
                }
                jumpTo(video.currentTime);
            });

            video.addEventListener("loadedmetadata", () => {
                if (serverSeek) {
                    video.currentTime = Number(video.dataset.targetTime);
                    delete video.dataset.targetTime;
                    setTimeout(() => { serverSeek = false; }, 250);
                }
            });

            document.querySelector("#jump-button").addEventListener("click", () => {
                jumpTo(parseTime(document.querySelector("#jump-time").value));
            });
            document.querySelector("#five-minute-button").addEventListener("click", () => {
                jumpTo(video.currentTime + 300);
            });
            video.addEventListener("canplay", () => { document.querySelector("#video-status").textContent = "Ready to play."; });
            video.addEventListener("waiting", () => { document.querySelector("#video-status").textContent = "Buffering..."; });
        </script>

        <div class="url">
            Video URL: {{ video_url }}
        </div>

    {% else %}

        <p class="message">
            Paste a direct video URL above to start streaming.
        </p>

    {% endif %}

    <script>
        const form = document.querySelector("#url-form");
        if (form) {
            form.addEventListener("submit", () => {
                const button = document.querySelector("#play-button");
                button.disabled = true;
                button.textContent = "Loading...";
            });
        }
    </script>

</div>

</body>
</html>
"""


@app.route("/", methods=["GET", "POST"])
def home():

    video_url = ""
    stream_url = ""
    error = ""
    movie_title = "Streamline Player"
    media_format = "READY"

    if request.method == "POST":
        video_url = request.form.get("video_url", "").strip()
        movie_title = get_movie_title(video_url)
        parsed_url = urlparse(video_url)
        page_suffixes = (".html", ".htm")
        path = parsed_url.path.lower()

        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            error = "Enter a complete HTTP or HTTPS video URL."
            video_url = ""
        elif path.endswith(page_suffixes):
            video_url, error = find_media_source(video_url)
            if not error:
                resolved_path = urlparse(video_url).path.lower()
                if resolved_path.endswith(".mkv"):
                    stream_url = url_for("stream_video", source=video_url)
                    media_format = "MKV · TRANSCODED"
                elif resolved_path.endswith((".mp4", ".webm", ".ogg", ".ogv")):
                    stream_url = video_url
                    media_format = Path(resolved_path).suffix[1:].upper()
                else:
                    error = "The page resolved to an unsupported video format."
        elif path.endswith(".mkv"):
            stream_url = url_for("stream_video", source=video_url)
            media_format = "MKV · TRANSCODED"
        elif path.endswith((".mp4", ".webm", ".ogg", ".ogv")):
            stream_url = video_url
            media_format = Path(path).suffix[1:].upper()
        else:
            error = "Use a direct MKV, MP4, WebM, OGG, or OGV video URL."
            video_url = ""

    return render_template(
        "index.html",
        video_url=video_url,
        stream_url=stream_url,
        error=error,
        movie_title=movie_title,
        media_format=media_format,
    )


def get_movie_title(video_url):
    filename = Path(unquote(urlparse(video_url).path)).name
    if not filename:
        return "Streamline Player"
    title = Path(filename).stem
    title = title.replace("_", " ").replace(".", " ").replace("-", " ")
    return " ".join(title.split()).title()


@app.route("/stream")
def stream_video():
    source = request.args.get("source", "").strip()
    start = request.args.get("start", "0")
    parsed_source = urlparse(source)

    if parsed_source.scheme not in {"http", "https"} or not parsed_source.netloc:
        return "Invalid video URL.", 400

    try:
        start_seconds = max(0.0, float(start))
    except ValueError:
        return "Invalid start time.", 400

    if not transcode_slots.acquire(blocking=False):
        return "The server is busy converting other videos. Please try again shortly.", 503

    command = [
        FFMPEG_PATH, "-hide_banner", "-loglevel", "error",
        "-ss", str(start_seconds), "-i", source,
        "-map", "0:v:0", "-map", "0:a:0", "-c:v", "libx264",
        "-preset", "veryfast", "-tune", "zerolatency", "-c:a", "aac",
        "-profile:a", "aac_low", "-ar", "48000", "-ac", "2", "-b:a", "192k",
        "-af", "aresample=async=1:first_pts=0", "-f", "mp4",
        "-movflags", "frag_keyframe+empty_moov+default_base_moof",
        "-flush_packets", "1", "pipe:1",
    ]

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except FileNotFoundError:
        transcode_slots.release()
        return "FFmpeg is not installed or is not available on PATH.", 500

    @stream_with_context
    def generate():
        try:
            while True:
                chunk = process.stdout.read(64 * 1024)
                if not chunk:
                    break
                yield chunk
        finally:
            if process.poll() is None:
                process.kill()
            process.stdout.close()
            process.stderr.close()
            process.wait()
            transcode_slots.release()

    return Response(generate(), mimetype="video/mp4")


def find_media_source(page_url):
    request = Request(
        page_url,
        headers={"User-Agent": "AuthorizedVideoStreamer/1.0"},
    )

    try:
        with urlopen(request, timeout=15) as response:
            content_type = response.headers.get_content_type()
            if content_type != "text/html":
                return "", "The supplied URL did not return an HTML page."
            page_html = response.read(2_000_000).decode("utf-8", errors="replace")
    except (HTTPError, URLError, TimeoutError) as exc:
        return "", f"Could not fetch the authorized page: {exc}"

    parser = MediaSourceParser()
    parser.feed(page_html)

    for source in parser.sources:
        media_url = urljoin(page_url, source)
        extension = urlparse(media_url).path.lower()
        if extension.endswith((".mp4", ".webm", ".ogg", ".ogv")):
            return media_url, ""

    if parser.sources:
        return "", "The page exposes media, but the format is not browser-compatible. Convert it to MP4/WebM."

    return "", "No explicit HTML5 video source was found on that page."


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True,
        threaded=True,
    )