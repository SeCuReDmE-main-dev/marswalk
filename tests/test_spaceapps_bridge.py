"""Tests for the MarsWalk Shared Memory Bridge (`tools/spaceapps_bridge.py` & `shared/`)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BRIDGE_PATH = REPO_ROOT / "tools" / "spaceapps_bridge.py"

spec = importlib.util.spec_from_file_location("spaceapps_bridge", BRIDGE_PATH)
assert spec is not None and spec.loader is not None
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


def test_committed_shared_vault_has_initial_handoff_ho001() -> None:
    """Verify the repo's ./shared directory contains 00_PIVOT.md, 20_JOURNAL.md, and HO-001."""
    shared_dir = REPO_ROOT / "shared"
    assert (REPO_ROOT / ".mcp.json").exists()
    assert (shared_dir / "00_PIVOT.md").exists()
    assert (shared_dir / "20_JOURNAL.md").exists()
    assert (shared_dir / "10_HANDOFFS" / "HO-001.json").exists()

    listing = bridge.handoff_list(
        for_agent="frontend-philippe", status="OPEN", vault_dir=shared_dir
    )
    assert listing["count"] >= 1
    assert listing["handoffs"][0]["id"] == "HO-001"


def test_all_6_spaceapps_bridge_tools_and_mcp_jsonrpc(tmp_path: Path) -> None:
    """Verify all 6 spaceapps-bridge tools and MCP JSON-RPC dispatch."""
    vault = bridge.resolve_vault_dir(tmp_path / "vault")

    # 1. pivot_append + pivot_read
    bridge.pivot_append("FRONTEND", "Initialized Leaflet EPSG:4326 map", "philippe", vault)
    p_data = bridge.pivot_read(vault)
    assert "Initialized Leaflet EPSG:4326 map" in p_data["content"]

    # 2. handoff_create + handoff_list + handoff_ack
    ho = bridge.handoff_create(
        sender="codex",
        to="antigravity",
        title="Inspect scale-gap cells on Western Delta",
        body="Highlight cells where 1m slope >= 20 deg and 64m slope < 15 deg.",
        vault_dir=vault,
    )
    assert ho["id"] == "HO-001"
    assert ho["status"] == "OPEN"

    listed = bridge.handoff_list(for_agent="antigravity", status="OPEN", vault_dir=vault)
    assert listed["count"] == 1

    acked = bridge.handoff_ack("HO-001", by_agent="antigravity", note="Done in UI", vault_dir=vault)
    assert acked["status"] == "ACKED"
    assert acked["acked_by"] == "antigravity"

    # 3. journal_append
    j_res = bridge.journal_append("philippe", "Connected waypoints.geojson (708 stops)", vault)
    assert j_res["status"] == "ok"

    # 4. MCP JSON-RPC tools/list & tools/call
    resp_list = bridge.handle_mcp_request(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, vault_dir=vault
    )
    assert resp_list is not None
    tool_names = {t["name"] for t in resp_list["result"]["tools"]}
    assert tool_names == {
        "pivot_read",
        "pivot_append",
        "handoff_create",
        "handoff_list",
        "handoff_ack",
        "journal_append",
    }

    resp_call = bridge.handle_mcp_request(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "handoff_list", "arguments": {"for_agent": "antigravity"}},
        },
        vault_dir=vault,
    )
    assert resp_call is not None
    assert resp_call["result"]["isError"] is False
    parsed = json.loads(resp_call["result"]["content"][0]["text"])
    assert parsed["count"] == 1
