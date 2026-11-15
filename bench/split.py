"""CLI shim forwarding `bench/split.py` to `marswalk.bench.split`."""

from __future__ import annotations

from marswalk.bench.split import assert_disjoint_sol_split, split_waypoints_odd_even

__all__ = ["assert_disjoint_sol_split", "split_waypoints_odd_even"]
