"""Hardcoded Odd/Even Mission Sol Split (`tune_odd` vs `test_even`).

Implements Block B2 (`M2`) of `PROMPT_ANTIGRAVITY_PASSE2B_V2_FUNNEL_21H20.md`:
- Tuning set (`tune_odd`): Perseverance waypoints with odd `sol` (`sol % 2 == 1`).
- Held-out test set (`test_even`): Perseverance waypoints with even `sol` (`sol % 2 == 0`).
"""

from __future__ import annotations

from collections.abc import Sequence

from marswalk.contracts.models import Waypoint


def assert_disjoint_sol_split(
    tune_waypoints: Sequence[Waypoint],
    test_waypoints: Sequence[Waypoint],
) -> None:
    """Raise ValueError if any waypoint ID or mission sol overlaps between tune and test."""
    tune_ids = {w.properties.waypoint_id for w in tune_waypoints}
    test_ids = {w.properties.waypoint_id for w in test_waypoints}
    overlap_ids = tune_ids & test_ids
    if overlap_ids:
        raise ValueError(f"Waypoint overlap detected between tune and test: {sorted(overlap_ids)}")

    tune_sols = {w.properties.sol for w in tune_waypoints}
    test_sols = {w.properties.sol for w in test_waypoints}
    overlap_sols = tune_sols & test_sols
    if overlap_sols:
        raise ValueError(f"Mission sol overlap detected between tune and test: {overlap_sols}")


def split_waypoints_odd_even(
    waypoints: Sequence[Waypoint],
) -> tuple[list[Waypoint], list[Waypoint]]:
    """deterministically partition waypoints into `(tune_odd_sols, test_even_sols)`."""
    tune_odd = [w for w in waypoints if w.properties.sol % 2 == 1]
    test_even = [w for w in waypoints if w.properties.sol % 2 == 0]
    assert_disjoint_sol_split(tune_odd, test_even)
    return (tune_odd, test_even)
