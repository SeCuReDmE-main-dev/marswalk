"""Phase 4 Mars 2020 Perseverance `raw_images` RSS JSON Camera Connector (`M5`).

Enforces CTO rules (`F3`, `H4`, Arbitration #2):
- Zero reference to the retired legacy Mars Photos REST service (`HTTP 404`).
- Queries the official NASA/JPL Mars 2020 RSS JSON feed with server-side `&sol=` filtering:
  `https://mars.nasa.gov/rss/api/?feed=raw_images&category=mars2020,ingenuity&feedtype=json&sol=<SOL>`
- Parses native JSON fields directly (`sol`, `site`, `drive`, `extended.mastAz`,
  `extended.mastEl`, `attitude`, and `camera.camera_model_component_list` CAHV/CAHVOR),
  without fragile filename substring slicing or Hazcam `0/180 deg` azimuth guessing.
- Implements deterministic client-side instrument filtering, circular azimuth ranking, and
  pagination (`page`, `page_size`) because the upstream API ignores `num` when `sol` is set.
- Dedicated to `GET /v1/sites/{site_id}/waypoints/{sol}/cameras` only; never invoked inside
  `/plan-route` or `/evaluate-route`.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

M20_RAW_IMAGES_FEED_TEMPLATE: str = (
    "https://mars.nasa.gov/rss/api/"
    "?feed=raw_images&category=mars2020,ingenuity&feedtype=json&sol={sol}"
)
MAX_RAW_IMAGES_PAYLOAD_BYTES: int = 8 * 1024 * 1024  # 8 MiB response ceiling

NAVIGATION_AND_MAST_CAMERAS: frozenset[str] = frozenset(
    {
        "NAVCAM_LEFT",
        "NAVCAM_RIGHT",
        "MCZ_LEFT",
        "MCZ_RIGHT",
        "FRONT_HAZCAM_LEFT_A",
        "FRONT_HAZCAM_RIGHT_A",
        "REAR_HAZCAM_LEFT",
        "REAR_HAZCAM_RIGHT",
    }
)


@dataclass(frozen=True)
class ParsedM20RawImage:
    """Normalized camera telemetry parsed natively from the Mars 2020 `raw_images` JSON."""

    image_id: str
    sol: int
    site: int | None
    drive: int | None
    instrument: str
    image_url: str
    mast_azimuth_deg: float | None
    mast_elevation_deg: float | None
    attitude_quaternion: str | None
    camera_model_type: str | None
    azimuth_delta_deg: float | None


@dataclass(frozen=True)
class PaginatedCameraResult:
    """Client-paginated Mars 2020 rover camera response for a mission sol."""

    sol: int
    source_status: Literal["cached", "live", "offline_unavailable"]
    cache_sha256: str | None
    total_matching: int
    page: int
    page_size: int
    items: tuple[ParsedM20RawImage, ...]


def circular_angle_diff_deg(az_a_deg: float, az_b_deg: float) -> float:
    """Compute shortest circular angular separation in `[0, 180]` degrees."""
    diff = (float(az_a_deg) - float(az_b_deg) + 180.0) % 360.0 - 180.0
    return abs(diff)


def _safe_float(val: Any) -> float | None:
    if val is None or val == "" or str(val).upper() == "UNK":
        return None
    try:
        out = float(val)
    except (TypeError, ValueError):
        return None
    return out if (-3600.0 <= out <= 3600.0) else None


def _safe_int(val: Any) -> int | None:
    if val is None or val == "" or str(val).upper() == "UNK":
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def parse_m20_raw_images_payload(
    payload: dict[str, Any],
    *,
    target_azimuth_deg: float | None = None,
    max_azimuth_delta_deg: float = 90.0,
    instruments: frozenset[str] | None = NAVIGATION_AND_MAST_CAMERAS,
    page: int = 1,
    page_size: int = 12,
    source_status: Literal["cached", "live", "offline_unavailable"] = "cached",
    cache_sha256: str | None = None,
    fallback_sol: int = 0,
) -> PaginatedCameraResult:
    """Parse native Mars 2020 `raw_images` JSON items and paginate on the client (`H4`)."""
    raw_items = payload.get("images")
    if not isinstance(raw_items, list):
        raw_items = []

    parsed: list[ParsedM20RawImage] = []
    resolved_sol = int(fallback_sol)

    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        cam = raw.get("camera") if isinstance(raw.get("camera"), dict) else {}
        ext = raw.get("extended") if isinstance(raw.get("extended"), dict) else {}
        files = raw.get("image_files") if isinstance(raw.get("image_files"), dict) else {}

        inst = str(cam.get("instrument") or "").strip()
        if instruments is not None and inst not in instruments:
            continue

        img_url = str(files.get("medium") or files.get("full_res") or files.get("small") or "")
        if not img_url:
            continue

        sol_val = _safe_int(raw.get("sol"))
        if sol_val is not None:
            resolved_sol = sol_val
        site_val = _safe_int(raw.get("site"))
        drive_val = _safe_int(raw.get("drive"))
        mast_az = _safe_float(ext.get("mastAz"))
        mast_el = _safe_float(ext.get("mastEl"))
        att_raw = raw.get("attitude")
        attitude = str(att_raw).strip() if att_raw not in (None, "") else None

        cm_list = cam.get("camera_model_component_list")
        cm_type = str(cam.get("model_type") or "").strip() or None
        if cm_type is None and isinstance(cm_list, (dict, list)) and cm_list:
            cm_type = "CAHV"

        az_delta: float | None = None
        if target_azimuth_deg is not None:
            if mast_az is None:
                # Never invent a 0/180 deg fallback when mastAz is absent (`H4`)
                continue
            az_delta = round(circular_angle_diff_deg(mast_az, target_azimuth_deg), 2)
            if az_delta > float(max_azimuth_delta_deg):
                continue

        parsed.append(
            ParsedM20RawImage(
                image_id=str(raw.get("imageid") or ""),
                sol=sol_val if sol_val is not None else resolved_sol,
                site=site_val,
                drive=drive_val,
                instrument=inst,
                image_url=img_url,
                mast_azimuth_deg=round(mast_az, 2) if mast_az is not None else None,
                mast_elevation_deg=round(mast_el, 2) if mast_el is not None else None,
                attitude_quaternion=attitude,
                camera_model_type=cm_type,
                azimuth_delta_deg=az_delta,
            )
        )

    parsed.sort(
        key=lambda item: (
            item.azimuth_delta_deg if item.azimuth_delta_deg is not None else 999.0,
            item.site if item.site is not None else 999999,
            item.drive if item.drive is not None else 999999,
            item.image_id,
        )
    )

    p_num = max(1, int(page))
    p_sz = max(1, min(100, int(page_size)))
    start = (p_num - 1) * p_sz
    end = start + p_sz
    return PaginatedCameraResult(
        sol=resolved_sol,
        source_status=source_status,
        cache_sha256=cache_sha256,
        total_matching=len(parsed),
        page=p_num,
        page_size=p_sz,
        items=tuple(parsed[start:end]),
    )


def fetch_or_load_m20_sol_cameras(
    datalake_dir: Path,
    sol: int,
    *,
    target_azimuth_deg: float | None = None,
    max_azimuth_delta_deg: float = 90.0,
    page: int = 1,
    page_size: int = 12,
    allow_network: bool = True,
    timeout_s: float = 4.0,
) -> PaginatedCameraResult:
    """Load cached `raw_images` JSON for `sol` or fetch with graceful offline fallback."""
    sol_int = max(0, int(sol))
    cache_dir = datalake_dir / "m20_raw_images"
    cache_file = cache_dir / f"sol_{sol_int:04d}.json"

    if cache_file.exists():
        try:
            raw_bytes = cache_file.read_bytes()
            if len(raw_bytes) <= MAX_RAW_IMAGES_PAYLOAD_BYTES:
                digest = hashlib.sha256(raw_bytes).hexdigest()
                payload = json.loads(raw_bytes.decode("utf-8"))
                if isinstance(payload, dict):
                    return parse_m20_raw_images_payload(
                        payload,
                        target_azimuth_deg=target_azimuth_deg,
                        max_azimuth_delta_deg=max_azimuth_delta_deg,
                        page=page,
                        page_size=page_size,
                        source_status="cached",
                        cache_sha256=digest,
                        fallback_sol=sol_int,
                    )
        except (OSError, ValueError, UnicodeDecodeError):
            pass

    if allow_network:
        url = M20_RAW_IMAGES_FEED_TEMPLATE.format(sol=sol_int)
        if url.startswith("https://mars.nasa.gov/"):
            req = urllib.request.Request(url, headers={"User-Agent": "MarsWalk-SpaceApps2026/1.1"})
            tmp_file = cache_dir / f".sol_{sol_int:04d}.{os.getpid()}.tmp"
            try:
                with urllib.request.urlopen(req, timeout=float(timeout_s)) as resp:  # noqa: S310
                    raw_bytes = resp.read(MAX_RAW_IMAGES_PAYLOAD_BYTES + 1)
                if len(raw_bytes) <= MAX_RAW_IMAGES_PAYLOAD_BYTES:
                    payload = json.loads(raw_bytes.decode("utf-8"))
                    if isinstance(payload, dict):
                        cache_dir.mkdir(parents=True, exist_ok=True)
                        tmp_file.write_bytes(raw_bytes)
                        os.replace(tmp_file, cache_file)
                        digest = hashlib.sha256(raw_bytes).hexdigest()
                        return parse_m20_raw_images_payload(
                            payload,
                            target_azimuth_deg=target_azimuth_deg,
                            max_azimuth_delta_deg=max_azimuth_delta_deg,
                            page=page,
                            page_size=page_size,
                            source_status="live",
                            cache_sha256=digest,
                            fallback_sol=sol_int,
                        )
            except Exception:
                try:
                    if tmp_file.exists():
                        tmp_file.unlink()
                except OSError:
                    pass

    return PaginatedCameraResult(
        sol=sol_int,
        source_status="offline_unavailable",
        cache_sha256=None,
        total_matching=0,
        page=max(1, int(page)),
        page_size=max(1, min(100, int(page_size))),
        items=(),
    )
