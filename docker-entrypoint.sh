#!/bin/sh
# Keep the media extractors current without rebuilding the image: sites change
# often and a pinned extractor silently breaks. Best-effort — failure falls
# back to the bundled versions. Disable with YTDLP_AUTO_UPDATE=false.
set -e

if [ "${YTDLP_AUTO_UPDATE:-true}" = "true" ]; then
    echo "Updating yt-dlp and gallery-dl to the latest releases..."
    pip install --no-cache-dir --upgrade yt-dlp gallery-dl \
        || echo "Extractor update failed; continuing with the bundled versions."
fi

exec python main.py
