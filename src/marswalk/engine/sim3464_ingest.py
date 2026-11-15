"""Phase 3 USGS SIM 3464 Geologic Unit & Contact Uncertainty Ingest (T04).

Supports the 5 USGS SIM 3464 units crossing the 2x2 km Western Delta Front window:
- `NHjf2`: Jezero fan 2 deposit (upper fan topset / alluvial layers)
- `Aeb`: Aeolian bedforms (large ripples / TARs; slip hazard penalty)
- `cr`: Crater rim and wall material
- `Nue`: Undivided etched unit
- `Njf`: Jezero floor volcanic / crater floor unit

Per Sun & Stack (2020, USGS SIM 3464), geologic contact lines carry a `100-200 m`
positional uncertainty (`contact_buffer_m = 150.0`), increasing local indeterminacy `I`
near unit boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass

SIM3464_SOURCE_ID: str = "SRC-USGS-SIM3464"
SIM3464_FEATURESERVER_URL: str = (
    "https://services.arcgis.com/v01gqwM5QqNysAAi/arcgis/rest/services/"
    "Jezero_Crater_Geologic_Map_SIM3464/FeatureServer/2/query"
)
SIM3464_CONTACT_BUFFER_M: float = 150.0

WINDOW_SIM3464_UNITS: dict[str, str] = {
    "NHjf2": "Jezero fan 2 deposit (upper delta layered topset, USGS SIM 3464)",
    "NHjf1": "Jezero fan 1 deposit (lower delta foreset/scarp bench, USGS SIM 3464)",
    "Nle": "Lower etched delta margin contact unit (USGS SIM 3464)",
    "Aeb": "Aeolian bedforms (sand ripples / TARs, USGS SIM 3464)",
    "cr": "Crater rim / wall breccia and megablock unit (USGS SIM 3464)",
    "Nue": "Undivided etched unit (USGS SIM 3464)",
    "Njf": "Jezero crater floor mafic unit (USGS SIM 3464)",
}


@dataclass(frozen=True)
class Sim3464CellContext:
    """Resolved USGS SIM 3464 geologic unit and contact-zone uncertainty for a cell."""

    unit_code: str
    unit_label: str
    near_contact_zone: bool
    contact_indeterminacy_boost: float
    sand_speed_factor: float


def classify_sim3464_unit_context(
    raw_unit_string: str,
    distance_to_contact_m: float | None = None,
) -> Sim3464CellContext:
    """Extract SIM 3464 unit code, sand speed factor, and 150 m contact-zone uncertainty."""
    code = raw_unit_string.split()[0].strip("[]()") if raw_unit_string else "NHjf2"
    if code not in WINDOW_SIM3464_UNITS:
        code = "NHjf2"
    label = WINDOW_SIM3464_UNITS[code]
    near_contact = (
        distance_to_contact_m is not None
        and float(distance_to_contact_m) <= SIM3464_CONTACT_BUFFER_M
    )
    i_boost = 0.08 if near_contact else 0.0
    sand_factor = 0.85 if code == "Aeb" else 1.0
    return Sim3464CellContext(
        unit_code=code,
        unit_label=label,
        near_contact_zone=near_contact,
        contact_indeterminacy_boost=i_boost,
        sand_speed_factor=sand_factor,
    )
