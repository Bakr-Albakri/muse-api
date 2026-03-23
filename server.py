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
    """Get direct audio URL for a video using innertube API"""
    if not video_id or len(video_id) > 20:
        return jsonify({"error": "invalid video id"}), 400

    import urllib.request
    import urllib.error

    try:
        # Use YouTube's innertube API directly - no cookies needed
        innertube_url = "https://www.youtube.com/youtubei/v1/player"
        payload = json.dumps({
            "videoId": video_id,
            "context": {
                "client": {
                    "clientName": "ANDROID",
                    "clientVersion": "19.09.37",
                    "androidSdkVersion": 30,
                    "hl": "en",
                    "gl": "US"
                }
            }
        }).encode()

        req = urllib.request.Request(
            innertube_url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "com.google.android.youtube/19.09.37 (Linux; U; Android 11) gzip"
            }
        )

        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())

        # Get video details
        video_details = data.get("videoDetails", {})
        streaming_data = data.get("streamingData", {})

        # Find audio formats from adaptiveFormats
        adaptive = streaming_data.get("adaptiveFormats", [])
        audio_formats = [f for f in adaptive if f.get("mimeType", "").startswith("audio/")]

        # Prefer m4a/mp4a
        m4a = [f for f in audio_formats if "mp4a" in f.get("mimeType", "")]
        best = m4a[-1] if m4a else (audio_formats[-1] if audio_formats else None)

        if not best:
            return jsonify({"error": "no audio found"}), 404

        audio_url = best.get("url", "")
        if not audio_url:
            # Handle signature cipher
            cipher = best.get("signatureCipher", "")
            if cipher:
                from urllib.parse import parse_qs
                params = parse_qs(cipher)
                audio_url = params.get("url", [""])[0]

        return jsonify({
            "url": audio_url,
            "ext": "m4a",
            "quality": best.get("audioQuality", ""),
            "filesize": int(best.get("contentLength", 0)),
            "title": video_details.get("title", ""),
            "author": video_details.get("author", ""),
            "duration": int(video_details.get("lengthSeconds", 0)),
            "thumbnail": video_details.get("thumbnail", {}).get("thumbnails", [{}])[-1].get("url", "")
        })

    except urllib.error.HTTPError as e:
        return jsonify({"error": f"YouTube API error: {e.code}"}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
