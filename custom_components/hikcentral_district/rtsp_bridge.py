#!/usr/bin/env python3
"""HikCentral live-stream bridge for a standalone go2rtc instance.

Speaks the reverse-engineered Authenty RTSP protocol (see
hikcentral-bumblebee.streaming) and outputs raw Annex-B H.264 on
stdout — exactly what go2rtc's ``exec:`` source expects (its pipe flow
magic-probes the codec from the first stdout bytes; RTSP-over-stdout is
NOT a thing for go2rtc).

NOTE: HA 2026.6 bundles only a go2rtc *client* — ``go2rtc: streams:`` in
configuration.yaml is rejected there. Run go2rtc standalone, e.g. as a
container, and point the integration's stream_url_template at it:

    # standalone go2rtc.yaml (single-line exec!)
    streams:
      hik_cam_240:
        - exec: python3 /app/rtsp_bridge.py --host https://HCP --username USER --password PASS --camera 240 --insecure

    # integration options → stream URL template
    rtsp://127.0.0.1:18556/hik_cam_{id}

Modes:
  default      stream raw Annex-B H.264 to stdout (for go2rtc exec)
  --jpeg N     grab ~N seconds of video, print one JPEG to stdout, exit
  --h264 FILE  append raw Annex-B H.264 to FILE (debug)

The script reconnects (with fresh login + handshake) until stdout
closes or SIGTERM/SIGINT — go2rtc restarts the exec per consumer, so
"stream on demand" falls out for free.
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time

# Allow running from a checkout without installing the package
_HERE = os.path.dirname(os.path.abspath(__file__))
for _cand in (
    os.path.join(_HERE, "..", "..", "..", "src"),  # repo/…/src
    os.path.join(_HERE, "..", "..", ".."),  # site-packages style
):
    if os.path.isdir(os.path.join(_cand, "hikcentral_bumblebee")):
        sys.path.insert(0, os.path.abspath(_cand))
        break

from hikcentral_bumblebee import BumblebeeClient  # noqa: E402
from hikcentral_bumblebee.streaming import (  # noqa: E402
    AuthentyStreamClient,
    StreamError,
    snapshot_jpeg,
)

logging.basicConfig(
    level=logging.WARNING, format="%(levelname)s rtsp_bridge: %(message)s"
)
logging.getLogger().setLevel(logging.WARNING)
_LOG = logging.getLogger("rtsp_bridge")

#: On stream error, wait before reconnecting
_RECONNECT_DELAY = 2.0
#: Force a fresh login every N seconds (tokens are long-lived but not forever)
_RELOGIN_INTERVAL = 3600.0

_terminate = False


def _handle_signal(signum: int, frame: object) -> None:
    global _terminate
    _terminate = True


def _make_client(args: argparse.Namespace) -> BumblebeeClient:
    client = BumblebeeClient(
        args.host, args.username, args.password, verify=not args.insecure
    )
    client.login()
    return client


def stream_rtsp(args: argparse.Namespace) -> int:
    """Main mode: raw Annex-B H.264 to stdout, with auto-reconnect."""
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    out = sys.stdout.buffer
    client: BumblebeeClient | None = None
    logged_in_at = 0.0

    try:
        while not _terminate:
            if client is None or time.monotonic() - logged_in_at > _RELOGIN_INTERVAL:
                try:
                    client = _make_client(args)
                    logged_in_at = time.monotonic()
                except Exception as exc:  # noqa: BLE001
                    _LOG.warning("login failed: %s", exc)
                    time.sleep(_RECONNECT_DELAY)
                    continue

            try:
                info = client.get_stream_info(args.camera)
                with AuthentyStreamClient(info, timeout=10.0) as cli:
                    cli.play()
                    # go2rtc's magic probe requires the very first NAL to be
                    # an SPS (bitstream.Open rejects everything else), but the
                    # Authenty stream joins mid-GOP — skip forward to the next
                    # SPS before writing anything to stdout.
                    synced = False
                    for nal in cli.h264_chunks():
                        if _terminate:
                            break
                        if not synced:
                            if len(nal) < 5 or (nal[4] & 0x1F) != 7:  # SPS
                                continue
                            synced = True
                        out.write(nal)
                        out.flush()
            except BrokenPipeError:
                # consumer (go2rtc) went away — exit, it will respawn on demand
                return 0
            except (StreamError, OSError) as exc:
                _LOG.warning("stream ended: %s — reconnecting", exc)
                time.sleep(_RECONNECT_DELAY)
        return 0
    finally:
        try:
            out.flush()
        except (OSError, BrokenPipeError):
            pass


def mode_jpeg(args: argparse.Namespace) -> int:
    """One-shot: print a single JPEG frame to stdout."""
    client = _make_client(args)
    info = client.get_stream_info(args.camera)
    jpeg = snapshot_jpeg(info, seconds=args.seconds)
    if jpeg is None:
        print("no frame captured", file=sys.stderr)
        return 1
    sys.stdout.buffer.write(jpeg)
    return 0


def mode_h264_file(args: argparse.Namespace) -> int:
    """Debug: raw Annex-B H.264 to a file until interrupted."""
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    client = _make_client(args)
    info = client.get_stream_info(args.camera)
    written = 0
    while not _terminate:
        try:
            with (
                AuthentyStreamClient(info, timeout=10.0) as cli,
                open(args.h264, "ab") as sink,
            ):
                cli.play()
                for nal in cli.h264_chunks():
                    if _terminate:
                        break
                    sink.write(nal)
                    written += len(nal)
        except (StreamError, OSError) as exc:
            _LOG.warning("stream ended: %s — reconnecting", exc)
            time.sleep(_RECONNECT_DELAY)
    print(f"wrote {written} bytes to {args.h264}", file=sys.stderr)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--host", required=True, help="HikCentral base URL")
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--camera", required=True, help="camera element id")
    parser.add_argument("--insecure", action="store_true", help="skip TLS verification")
    parser.add_argument(
        "--jpeg",
        dest="seconds",
        type=float,
        default=None,
        metavar="SECONDS",
        help="one-shot: grab ~SECONDS of video, print one JPEG to stdout",
    )
    parser.add_argument(
        "--h264",
        dest="h264",
        default=None,
        metavar="FILE",
        help="debug: append raw Annex-B H.264 to FILE until interrupted",
    )
    args = parser.parse_args()

    if args.seconds is not None:
        return mode_jpeg(args)
    if args.h264 is not None:
        return mode_h264_file(args)
    return stream_rtsp(args)


if __name__ == "__main__":
    raise SystemExit(main())
