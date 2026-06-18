# Black Volt render worker (Stage 2 hybrid render bridge) — deploy image.
#
# Runs render_worker.py (stdlib HTTP + ffmpeg). In this image there is no
# BitTrader pipeline, so produce_single is unavailable → the worker emits a
# branded ffmpeg sample clip. To produce real AI video, run the worker from the
# BitTrader repo on a host that has its pipeline + keys and point
# SOCIAL_RENDER_URL at it instead (see docs/setup-social-media.md).
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY render_worker.py .

EXPOSE 8090
CMD ["python3", "render_worker.py"]
