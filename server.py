from flask import Flask, request, jsonify
from flask_cors import CORS
import subprocess
import json
import os
import hashlib
import time

app = Flask(__name__)
CORS(app)

API_KEY = os.environ.get("MUSE_API_KEY", "muse_k9x7m2p4w8")

def check_key():
    key = request.headers.get("X-Api-Key") or request.args.get("key")
    if key != API_KEY:
        return False
    return True

@app.before_request
def auth():
    if request.path in ("/health", "/"):
        return
    if not check_key():
        return jsonify({"error": "unauthorized"}), 401

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

@app.route("/")
def index():
    try:
        with open("index.html", "r") as f:
            return f.read(), 200, {"Content-Type": "text/html; charset=utf-8"}
    except:
        return "Muse API", 200

@app.route("/search")
def search():
    q = request.args.get("q", "")
    if not q:
        return jsonify({"error": "missing query"}), 400

    try:
        result = subprocess.run(
            ["yt-dlp", "--dump-json", "--flat-playlist", "--no-download",
             f"ytsearch12:{q}"],
            capture_output=True, text=True, timeout=30
        )

        videos = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            try:
                data = json.loads(line)
                videos.append({
                    "videoId": data.get("id", ""),
                    "title": data.get("title", ""),
                    "author": data.get("channel", data.get("uploader", "")),
                    "lengthSeconds": data.get("duration", 0),
                    "thumbnail": data.get("thumbnail", ""),
                    "thumbnails": data.get("thumbnails", [])
                })
            except json.JSONDecodeError:
                continue

        return jsonify(videos)

    except subprocess.TimeoutExpired:
        return jsonify({"error": "search timeout"}), 504
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/audio/<video_id>")
def audio(video_id):
    """Get direct audio URL for a video"""
    if not video_id or len(video_id) > 20:
        return jsonify({"error": "invalid video id"}), 400

    try:
        result = subprocess.run(
            ["yt-dlp", "-f", "bestaudio[ext=m4a]/bestaudio",
             "--dump-json", "--no-download",
             f"https://www.youtube.com/watch?v={video_id}"],
            capture_output=True, text=True, timeout=30
        )

        if result.returncode != 0:
            return jsonify({"error": "failed to get audio info"}), 500

        data = json.loads(result.stdout)

        # Find best audio format
        formats = data.get("formats", [])
        audio_formats = [f for f in formats if f.get("acodec") != "none" and f.get("vcodec") in ("none", None)]

        # Prefer m4a, then any audio
        m4a = [f for f in audio_formats if f.get("ext") == "m4a"]
        best = m4a[-1] if m4a else (audio_formats[-1] if audio_formats else None)

        if not best:
            return jsonify({"error": "no audio found"}), 404

        return jsonify({
            "url": best.get("url", ""),
            "ext": best.get("ext", "m4a"),
            "quality": best.get("format_note", ""),
            "filesize": best.get("filesize", 0),
            "title": data.get("title", ""),
            "author": data.get("channel", data.get("uploader", "")),
            "duration": data.get("duration", 0),
            "thumbnail": data.get("thumbnail", "")
        })

    except subprocess.TimeoutExpired:
        return jsonify({"error": "timeout"}), 504
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
