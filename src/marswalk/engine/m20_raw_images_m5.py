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
- Used by `GET /v1/sites/{site_id}/waypoints/{sol}/cameras` and deterministic offline pack-build
  panorama verification; never invoked inside `/plan-route` or `/evaluate-route`.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import shutil
import ssl
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

M20_RAW_IMAGES_FEED_TEMPLATE: str = (
    "https://mars.nasa.gov/rss/api/"
    "?feed=raw_images&category=mars2020,ingenuity&feedtype=json&sol={sol}"
)
M20_RAW_IMAGES_ASSET_PREFIX: str = "https://mars.nasa.gov/mars2020-raw-images/"
VERIFIED_PANORAMAS_CACHE_NAME: str = "M20_verified_panoramas.json"
CANONICAL_PACK_PANORAMA_SOLS: tuple[int, ...] = (413, 609, 700, 753, 1578)
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


_LANDSCAPE_INSTRUMENT_RANK: dict[str, int] = {
    "NAVCAM_LEFT": 0,
    "NAVCAM_RIGHT": 1,
    "MCZ_LEFT": 2,
    "MCZ_RIGHT": 3,
    "FRONT_HAZCAM_LEFT_A": 4,
    "FRONT_HAZCAM_RIGHT_A": 5,
    "REAR_HAZCAM_LEFT": 6,
    "REAR_HAZCAM_RIGHT": 7,
}
_DIM_RE = re.compile(r"(\d+)\s*,\s*(\d+)")


def _parse_dimensions(dim_raw: Any) -> tuple[int, int]:
    """Parse `(width, height)` from `extended.dimension` string such as `'(1288,968)'`."""
    if not dim_raw:
        return (0, 0)
    m = _DIM_RE.search(str(dim_raw))
    if not m:
        return (0, 0)
    return (int(m.group(1)), int(m.group(2)))


def select_best_landscape_browse_entry(
    payload: dict[str, Any],
    *,
    target_site: int | None = None,
    target_drive: int | None = None,
    preferred_tier: Literal["medium", "large"] = "medium",
) -> dict[str, Any] | None:
    """Select a deterministic wide-FOV NASA Mars 2020 browse frame for `(sol, site, drive)`."""
    raw_items = payload.get("images")
    if not isinstance(raw_items, list):
        return None

    tier_order = (
        ("medium", "large", "full_res")
        if preferred_tier == "medium"
        else ("large", "medium", "full_res")
    )
    candidates: list[tuple[tuple[int, int, int, str], dict[str, Any]]] = []

    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        if str(raw.get("sample_type") or "").strip().lower() == "thumbnail":
            continue
        cam = raw.get("camera") if isinstance(raw.get("camera"), dict) else {}
        inst = str(cam.get("instrument") or "").strip()
        if inst not in _LANDSCAPE_INSTRUMENT_RANK:
            continue

        ext = raw.get("extended") if isinstance(raw.get("extended"), dict) else {}
        w_px, h_px = _parse_dimensions(ext.get("dimension"))
        if 0 < max(w_px, h_px) < 320:
            # Exclude tiny calibration subframes and postage stamps
            continue

        files = raw.get("image_files") if isinstance(raw.get("image_files"), dict) else {}
        chosen_url = ""
        for tier_key in tier_order:
            cand_u = str(files.get(tier_key) or "").strip()
            if cand_u.startswith(M20_RAW_IMAGES_ASSET_PREFIX):
                chosen_url = cand_u
                break
        if not chosen_url:
            continue

        site_val = _safe_int(raw.get("site"))
        drive_val = _safe_int(raw.get("drive"))
        if target_site is not None and target_drive is not None:
            if site_val == target_site and drive_val == target_drive:
                loc_rank = 0
            elif site_val == target_site:
                loc_rank = 1
            else:
                loc_rank = 2
        else:
            loc_rank = 0

        size_rank = 0 if (w_px >= 800 and h_px >= 550) else (1 if w_px >= 512 else 2)
        inst_rank = _LANDSCAPE_INSTRUMENT_RANK[inst]
        img_id = str(raw.get("imageid") or "")
        credit = str(raw.get("credit") or "NASA/JPL-Caltech").strip()

        sort_key = (loc_rank, inst_rank, size_rank, img_id)
        candidates.append(
            (
                sort_key,
                {
                    "image_id": img_id,
                    "sol": _safe_int(raw.get("sol")),
                    "site": site_val,
                    "drive": drive_val,
                    "instrument": inst,
                    "image_url": chosen_url,
                    "credit": credit,
                    "width_px": w_px,
                    "height_px": h_px,
                },
            )
        )

    if not candidates:
        return None
    candidates.sort(key=lambda pair: pair[0])
    return candidates[0][1]


def _inject_ssl_truststore() -> None:
    """Inject OS certificate store when `truststore` is available."""
    try:
        import truststore

        truststore.inject_into_ssl()
    except ImportError:
        pass


def ensure_verified_waypoint_panoramas(
    datalake_dir: Path,
    raw_waypoints: dict[str, Any],
    *,
    allow_network: bool = True,
) -> tuple[Path | None, dict[str, dict[str, Any]]]:
    """Resolve and cache verified `HTTP 200` `mars2020-raw-images` URLs for all waypoints."""
    datalake_dir.mkdir(parents=True, exist_ok=True)
    waypoint_keys: list[tuple[int, int, int]] = []
    distinct_sols: set[int] = set()
    for feat in raw_waypoints.get("features", []):
        props = feat.get("properties", {})
        sol = int(props.get("sol") or 0)
        site = int(props.get("site") or 0)
        drive = int(props.get("drive") or 0)
        waypoint_keys.append((sol, site, drive))
        distinct_sols.add(sol)

    cache_path = datalake_dir / VERIFIED_PANORAMAS_CACHE_NAME
    if not cache_path.exists():
        canonical_cache = (
            Path(__file__).resolve().parents[3] / "datalake" / VERIFIED_PANORAMAS_CACHE_NAME
        )
        if canonical_cache.exists() and canonical_cache.resolve() != cache_path.resolve():
            shutil.copyfile(canonical_cache, cache_path)

    existing_entries: dict[str, dict[str, Any]] = {}
    checked_sols: set[int] = set()
    if cache_path.exists() and cache_path.stat().st_size > 2:
        try:
            doc = json.loads(cache_path.read_text(encoding="utf-8"))
            raw_entries = doc.get("entries")
            if isinstance(raw_entries, dict):
                existing_entries = dict(raw_entries)
                for k_str in existing_entries:
                    if k_str.isdigit():
                        checked_sols.add(int(k_str))
            raw_checked = doc.get("checked_sols")
            if isinstance(raw_checked, list):
                checked_sols.update(int(x) for x in raw_checked)
            if distinct_sols.issubset(checked_sols) or not allow_network:
                return (cache_path, existing_entries)
        except (OSError, ValueError):
            pass

    if not allow_network:
        return (None, {})

    _inject_ssl_truststore()
    pending_sols = sorted(distinct_sols - checked_sols)
    sol_to_triples: dict[int, list[tuple[int, int, int]]] = {}
    for sol, site, drive in sorted(set(waypoint_keys)):
        sol_to_triples.setdefault(sol, []).append((sol, site, drive))

    def _fetch_chunk(sol_chunk: list[int]) -> tuple[dict[str, dict[str, Any]], set[int]]:
        chunk_entries: dict[str, dict[str, Any]] = {}
        chunk_checked: set[int] = set()
        ctx = ssl.create_default_context()
        conn: http.client.HTTPSConnection | None = None
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; MarsWalk-SpaceApps2026/1.1)",
            "Accept": "application/json",
            "Connection": "keep-alive",
        }
        try:
            for s_val in sol_chunk:
                p_dict: dict[str, Any] | None = None
                path_q = (
                    "/rss/api/?feed=raw_images&category=mars2020,ingenuity"
                    f"&feedtype=json&sol={s_val}"
                )
                for attempt in range(4):
                    try:
                        if conn is None:
                            conn = http.client.HTTPSConnection(
                                "mars.nasa.gov", timeout=15.0, context=ctx
                            )
                        conn.request("GET", path_q, headers=headers)
                        resp = conn.getresponse()
                        status = resp.status
                        body = resp.read(MAX_RAW_IMAGES_PAYLOAD_BYTES + 1)
                        if status == 200 and len(body) <= MAX_RAW_IMAGES_PAYLOAD_BYTES:
                            parsed = json.loads(body.decode("utf-8"))
                            if isinstance(parsed, dict):
                                p_dict = parsed
                                chunk_checked.add(s_val)
                                break
                        if status in (403, 429, 503):
                            conn.close()
                            conn = None
                            time.sleep(3.0 * (attempt + 1))
                            continue
                    except Exception:
                        if conn is not None:
                            try:
                                conn.close()
                            except Exception:
                                pass
                            conn = None
                        time.sleep(1.0 * (attempt + 1))
                if p_dict is not None:
                    for _, site_v, drive_v in sol_to_triples.get(s_val, []):
                        best = select_best_landscape_browse_entry(
                            p_dict,
                            target_site=site_v,
                            target_drive=drive_v,
                            preferred_tier="medium",
                        )
                        if best is not None:
                            chunk_entries[f"{s_val}:{site_v}:{drive_v}"] = best
                            sol_key = str(s_val)
                            if sol_key not in chunk_entries:
                                chunk_entries[sol_key] = best
                time.sleep(0.12)
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
        return (chunk_entries, chunk_checked)

    entries_out = dict(existing_entries)
    if pending_sols:
        mid = (len(pending_sols) + 1) // 2
        chunks = [c for c in (pending_sols[:mid], pending_sols[mid:]) if c]
        with ThreadPoolExecutor(max_workers=len(chunks)) as pool:
            for c_entries, c_checked in pool.map(_fetch_chunk, chunks):
                entries_out.update(c_entries)
                checked_sols.update(c_checked)

    doc_out = {
        "schema": "marswalk.m20_verified_panoramas.v1",
        "source_id": "SRC-M20-RAW-IMAGES",
        "checked_sols": sorted(checked_sols),
        "entries": dict(sorted(entries_out.items())),
    }
    tmp_path = datalake_dir / f".{VERIFIED_PANORAMAS_CACHE_NAME}.{os.getpid()}.tmp"
    tmp_path.write_bytes((json.dumps(doc_out, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    os.replace(tmp_path, cache_path)
    return (cache_path, doc_out["entries"])


def materialize_canonical_pack_panoramas(
    datalake_dir: Path,
    pack_dir: Path,
    verified_entries: dict[str, dict[str, Any]],
    canonical_stops: list[tuple[int, int, int]],
    *,
    allow_network: bool = True,
) -> list[Path]:
    """Copy or download unmodified NASA `medium` (`800 px`) JPEGs into `pack_dir/panoramas/`."""
    datalake_pan_dir = datalake_dir / "panoramas"
    datalake_pan_dir.mkdir(parents=True, exist_ok=True)
    canonical_pan_dir = Path(__file__).resolve().parents[3] / "datalake" / "panoramas"
    pack_pan_dir = pack_dir / "panoramas"
    pack_pan_dir.mkdir(parents=True, exist_ok=True)

    if allow_network:
        _inject_ssl_truststore()

    written: list[Path] = []
    for sol, site, drive in sorted(canonical_stops, key=lambda t: t[0]):
        entry = verified_entries.get(f"{sol}:{site}:{drive}") or verified_entries.get(str(sol))
        if not entry:
            continue
        img_url = str(entry.get("image_url") or "")
        if not img_url.startswith(M20_RAW_IMAGES_ASSET_PREFIX):
            continue

        rel_name = f"sol_{sol:04d}_ncam.jpg"
        cached_jpg = datalake_pan_dir / rel_name
        if not cached_jpg.exists():
            canon_jpg = canonical_pan_dir / rel_name
            if canon_jpg.exists() and canon_jpg.resolve() != cached_jpg.resolve():
                shutil.copyfile(canon_jpg, cached_jpg)
        if (not cached_jpg.exists() or cached_jpg.stat().st_size < 2048) and allow_network:
            req = urllib.request.Request(
                img_url, headers={"User-Agent": "MarsWalk-SpaceApps2026/1.1"}
            )
            with urllib.request.urlopen(req, timeout=12.0) as resp:  # noqa: S310
                jpg_bytes = resp.read(MAX_RAW_IMAGES_PAYLOAD_BYTES + 1)
            if len(jpg_bytes) > MAX_RAW_IMAGES_PAYLOAD_BYTES or not jpg_bytes.startswith(
                b"\xff\xd8"
            ):
                raise RuntimeError(f"Invalid JPEG bytes fetched for Sol {sol} ({img_url})")
            tmp_jpg = datalake_pan_dir / f".{rel_name}.{os.getpid()}.tmp"
            tmp_jpg.write_bytes(jpg_bytes)
            os.replace(tmp_jpg, cached_jpg)

        if cached_jpg.exists() and cached_jpg.stat().st_size >= 2048:
            dst_jpg = pack_pan_dir / rel_name
            shutil.copyfile(cached_jpg, dst_jpg)
            written.append(dst_jpg)

    return written
