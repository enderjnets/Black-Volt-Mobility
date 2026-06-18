#!/usr/bin/env python3
"""Black Volt render worker — the Stage 2 hybrid render bridge.

Black Volt Mobility offloads heavy video rendering to BitTrader. This is the thin,
dependency-free worker that wires the two together:

    Black Volt  ──POST /render (HMAC-signed)──►  this worker
                                                   produce_single()  (or sample)
    Black Volt  ◄──POST callback (HMAC-signed)──  finished mp4 (base64)

Both directions are authenticated with one shared secret (`BV_RENDER_SIGNING_KEY`,
HMAC-SHA256 over the raw body, header `x-bv-render-signature`). The worker renders
asynchronously and posts the finished mp4 back inline as base64 — Black Volt writes
it under its public /media mount (no file hosting needed here, no SSRF surface).

Uses only the Python standard library + ffmpeg (already a BitTrader dependency).
Real rendering goes through `agents.producer.produce_single`; if that's
unavailable or `BV_RENDER_SAMPLE=1`, it emits a short branded ffmpeg sample clip so
the whole signed round-trip is testable without the paid MiniMax video APIs.

Run:
    BV_RENDER_SIGNING_KEY=<shared-secret> [BV_RENDER_SAMPLE=1] python3 render_worker.py
    # listens on 0.0.0.0:8090 (override with BV_RENDER_PORT)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import subprocess
import tempfile
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bv.render_worker")

SIGNING_KEY = os.environ.get("BV_RENDER_SIGNING_KEY", "")
PORT = int(os.environ.get("BV_RENDER_PORT", "8090"))
SAMPLE_ONLY = os.environ.get("BV_RENDER_SAMPLE", "") in ("1", "true", "yes")
MAX_BODY = 4 * 1024 * 1024  # inbound render request bodies are tiny (script JSON)


def _sign(body: bytes) -> str:
    return base64.b64encode(
        hmac.new(SIGNING_KEY.encode("utf-8"), body, hashlib.sha256).digest()
    ).decode("ascii")


def _verify(body: bytes, signature: str) -> bool:
    if not SIGNING_KEY:
        return False
    return hmac.compare_digest(_sign(body), signature or "")


_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial.ttf",
)


def _font_path() -> str | None:
    for p in _FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


def _ffmpeg_sample(title: str = "") -> bytes:
    """A short, valid, on-brand vertical mp4 — a stand-in render so the signed
    pipeline works without the paid video APIs. Draws the brand over void-black
    when a font is available; falls back to a plain color clip otherwise."""
    base = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=0x0A0A0F:s=1080x1920:d=3",
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-shortest", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-c:a", "aac",
        "-movflags", "+faststart",
    ]
    font = _font_path()
    vf = []
    if font:
        vf.append(
            f"drawtext=fontfile={font}:text='BLACK VOLT':fontcolor=0x00E5FF:"
            "fontsize=120:x=(w-text_w)/2:y=(h/2)-170"
        )
        vf.append(
            f"drawtext=fontfile={font}:text='Silent Power. Premium Arrival.':"
            "fontcolor=0xC7CBD4:fontsize=40:x=(w-text_w)/2:y=(h/2)+30"
        )
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "sample.mp4")
        cmd = base + (["-vf", ",".join(vf)] if vf else []) + [out]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError:
            # drawtext can fail on some ffmpeg builds — fall back to plain color.
            subprocess.run(base + [out], check=True, capture_output=True)
        return Path(out).read_bytes()


def _render_bytes(script: dict) -> bytes:
    """Produce the mp4 bytes for a job. Real pipeline when available, else sample."""
    if not SAMPLE_ONLY:
        try:
            from agents.producer import produce_single

            with tempfile.TemporaryDirectory() as d:
                result = produce_single(script, Path(d))
                if isinstance(result, dict) and result.get("status") == "ok":
                    out = result.get("output_file")
                    if out and os.path.exists(out):
                        return Path(out).read_bytes()
                log.warning("produce_single did not yield a file (%s) — using sample", result)
        except Exception as e:  # missing deps / API keys / render error → sample
            log.warning("produce_single unavailable (%s) — using sample", e)
    return _ffmpeg_sample()


def _process(job: dict) -> None:
    job_id = job.get("job_id")
    callback_url = job.get("callback_url")
    try:
        mp4 = _render_bytes(job.get("script") or {})
        payload = {
            "job_id": job_id,
            "tenant_id": job.get("tenant_id"),
            "post_id": job.get("post_id"),
            "media_b64": base64.b64encode(mp4).decode("ascii"),
            "media_ext": "mp4",
        }
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            callback_url, data=body,
            headers={"Content-Type": "application/json", "x-bv-render-signature": _sign(body)},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            log.info("job %s callback %s (%d bytes mp4)", job_id, resp.status, len(mp4))
    except Exception as e:
        log.error("job %s failed: %s", job_id, e)


class Handler(BaseHTTPRequestHandler):
    def _json(self, code: int, obj: dict) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(obj).encode("utf-8"))

    def log_message(self, *args):  # quiet default access log
        pass

    def do_GET(self):
        if self.path == "/health":
            return self._json(200, {"ok": True, "sample_only": SAMPLE_ONLY})
        self._json(404, {"error": "not_found"})

    def do_POST(self):
        if self.path != "/render":
            return self._json(404, {"error": "not_found"})
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY:
            return self._json(400, {"error": "bad_length"})
        body = self.rfile.read(length)
        if not _verify(body, self.headers.get("x-bv-render-signature", "")):
            return self._json(403, {"error": "invalid_signature"})
        try:
            job = json.loads(body)
        except Exception:
            return self._json(400, {"error": "invalid_json"})
        if not (job.get("callback_url") and job.get("post_id") and job.get("tenant_id")):
            return self._json(400, {"error": "missing_fields"})
        threading.Thread(target=_process, args=(job,), daemon=True).start()
        self._json(202, {"accepted": job.get("job_id")})


def main() -> None:
    if not SIGNING_KEY:
        raise SystemExit("BV_RENDER_SIGNING_KEY is required")
    log.info("Black Volt render worker on :%d (sample_only=%s)", PORT, SAMPLE_ONLY)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
