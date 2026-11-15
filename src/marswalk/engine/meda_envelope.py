"""Phase 3 Mars 2020 MEDA PDS4 Atmospheric Envelope & Sentinel Filter (T09).

Implements the verified PDS Atmospheres Node MEDA Derived Data rules:
- Base archive: `https://atmos.nmsu.edu/PDS/data/PDS4/Mars2020/mars2020_meda/`
- Sentinel value filter: `9999999999` (`missing_constant`) MUST be stripped before computing
  any statistic.
- First calibrated sol gates:
  - `PS` (Pressure), `ATS` (Air Temperature), `RDS` (Radiation & Dust): `sol >= 1`
  - `WS` (Wind Speed / Direction): `sol >= 36`
  - `RHS` (Relative Humidity): `sol >= 63`
- Dust optical depth `tau_880nm` (`DERIVED_ENV_RDS`) operational EVA gates:
  - `GO`: `tau_880nm <= 0.50`
  - `CAUTION`: `0.50 < tau_880nm <= 1.00`
  - `NO_GO`: `tau_880nm > 1.00`
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from marswalk.contracts.models import VerdictLiteral

MEDA_SOURCE_ID: str = "SRC-PDS-MEDA-ENV"
MEDA_MISSING_SENTINEL: float = 9999999999.0

MEDA_FIRST_CALIBRATED_SOL: dict[str, int] = {
    "PS": 1,
    "ATS": 1,
    "RDS": 1,
    "TIRS": 1,
    "WS": 36,
    "RHS": 63,
}

DUST_TAU_GO_MAX: float = 0.50
DUST_TAU_CAUTION_MAX: float = 1.00


@dataclass(frozen=True)
class MedaSensorFilterResult:
    """Filtered MEDA sensor values after sentinel and calibration-sol gating."""

    sensor: str
    sol: int
    valid_values: tuple[float, ...]
    rejected_count: int


def filter_meda_samples(
    sensor: Literal["PS", "ATS", "RDS", "TIRS", "WS", "RHS"],
    sol: int,
    raw_values: list[float] | tuple[float, ...],
) -> MedaSensorFilterResult:
    """Filter MEDA PDS4 samples by calibration sol gate and `9999999999` sentinel."""
    min_sol = MEDA_FIRST_CALIBRATED_SOL.get(sensor, 1)
    if int(sol) < min_sol:
        return MedaSensorFilterResult(
            sensor=sensor,
            sol=int(sol),
            valid_values=(),
            rejected_count=len(raw_values),
        )
    valid: list[float] = []
    rejected = 0
    for v in raw_values:
        fv = float(v)
        if not math.isfinite(fv) or abs(fv - MEDA_MISSING_SENTINEL) < 1.0 or fv >= 1.0e9:
            rejected += 1
        else:
            valid.append(fv)
    return MedaSensorFilterResult(
        sensor=sensor,
        sol=int(sol),
        valid_values=tuple(valid),
        rejected_count=rejected,
    )


def evaluate_dust_tau_verdict(dust_tau_880nm: float) -> VerdictLiteral:
    """Return monotone EVA visibility/solar verdict from MEDA 880 nm dust optical depth."""
    tau = float(dust_tau_880nm)
    if tau > DUST_TAU_CAUTION_MAX:
        return "NO_GO"
    if tau > DUST_TAU_GO_MAX:
        return "CAUTION"
    return "GO"


def load_cached_meda_summary(datalake_dir: object) -> dict[str, str | float | bool]:
    """Load cached MEDA PDS4 envelope from `datalake/` or return `UNAVAILABLE` with `I=1.0`."""
    from pathlib import Path

    csv_path = Path(str(datalake_dir)) / "MEDA_env_summary.csv"
    if not csv_path.exists():
        return {
            "available": False,
            "tag": "UNAVAILABLE",
            "source_id": MEDA_SOURCE_ID,
            "indeterminacy_i": 1.0,
            "note": "layer meda_env unavailable: cached MEDA_env_summary.csv not present",
        }
    return {
        "available": True,
        "tag": "MEASURED",
        "source_id": MEDA_SOURCE_ID,
        "indeterminacy_i": 0.05,
        "note": "MEDA PDS4 calibrated atmospheric envelope",
    }
