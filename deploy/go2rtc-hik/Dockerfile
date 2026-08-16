# go2rtc + HikCentral Authenty bridge (RTSP server for hikcentral_district)
#
# HA 2026.6 bundles only a go2rtc *client* — its YAML no longer accepts
# streams/rtsp keys, so custom exec sources must run in a standalone go2rtc.
# This image carries:
#   - go2rtc 1.9.14 (binary copied from the official image, digest-pinned)
#   - python3 + hikcentral_bumblebee (pinned commit) for the exec source
# rtsp_bridge.py is bind-mounted at runtime from the HA config dir
# (HACS-installed hikcentral_district >= 0.5.0), so the bridge stays in sync
# with the deployed integration version.
#
# Requires stack .env: HIK_URL, HIK_USER, HIK_PASS (see .env.example).

FROM ghcr.io/alexxit/go2rtc@sha256:675c318b23c06fd862a61d262240c9a63436b4050d177ffc68a32710d9e05bae AS go2rtc

# python:3.13-slim, digest-pinned per SECURITY.md
FROM python:3.13-slim@sha256:ffb752e139c0a19692a43af8d8523b274222dd68eebad5d583b45c2201c6e30a

# No git in slim — install from the commit tarball (same pin, no VCS needed)
RUN pip install --no-cache-dir \
    "hikcentral_bumblebee@https://github.com/megastruktur/hikcentral-bumblebee/archive/7bb1b352a6f8e5aac419cad75ab80b02002a2882.tar.gz"

# ffmpeg: snapshot_jpeg() (bridge --jpeg mode) decodes H.264 via ffmpeg
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY --from=go2rtc /usr/local/bin/go2rtc /usr/local/bin/go2rtc

EXPOSE 18555
CMD ["go2rtc", "-config", "/etc/go2rtc/go2rtc.yaml"]
