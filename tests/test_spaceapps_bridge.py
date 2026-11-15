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
    """Verify the repo's ./shared directory and all 3 MCP configs match the 5 examples."""
    shared_dir = REPO_ROOT / "shared"
    assert (REPO_ROOT / ".mcp.json").exists()
    assert (REPO_ROOT / ".codex" / "config.toml").exists()
    assert (REPO_ROOT / ".antigravity" / "mcp.json").exists()
    assert (shared_dir / "00_PIVOT.md").exists()
    assert (shared_dir / "20_JOURNAL.md").exists()
    assert (shared_dir / "10_HANDOFFS" / "HO-001.json").exists()

    # Example 1: Whether called with for_agent="codex", "antigravity", "philippe", or "all",
    # HO-001 MUST be returned!
    for agent_query in ("codex", "antigravity", "philippe", "frontend", "all"):
        listing = bridge.handoff_list(for_agent=agent_query, status="OPEN", vault_dir=shared_dir)
        assert listing["count"] >= 1
        assert listing["handoffs"][0]["id"] == "HO-001"


def test_all_5_discord_examples_work_via_mcp_jsonrpc(tmp_path: Path) -> None:
    """Simulate the exact 5 Discord examples through MCP JSON-RPC calls."""
    vault = bridge.resolve_vault_dir(tmp_path / "vault")
    # Seed HO-001 into tmp vault like the repo
    (vault / "10_HANDOFFS" / "HO-001.json").write_text(
        (REPO_ROOT / "shared" / "10_HANDOFFS" / "HO-001.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    # Example 1: pivot_read() + handoff_list(for_agent="codex")
    r1_pivot = bridge.handle_mcp_request(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "pivot_read"}},
        vault_dir=vault,
    )
    assert r1_pivot is not None and not r1_pivot["result"]["isError"]

    r1_list = bridge.handle_mcp_request(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "handoff_list", "arguments": {"for_agent": "codex"}},
        },
        vault_dir=vault,
    )
    assert r1_list is not None and not r1_list["result"]["isError"]
    assert json.loads(r1_list["result"]["content"][0]["text"])["count"] == 1

    # Example 2: handoff_ack("HO-001") (even with minimal arguments)
    r2_ack = bridge.handle_mcp_request(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "handoff_ack", "arguments": {"id": "HO-001"}},
        },
        vault_dir=vault,
    )
    assert r2_ack is not None and not r2_ack["result"]["isError"]
    assert json.loads(r2_ack["result"]["content"][0]["text"])["status"] == "ACKED"

    # Example 3: handoff_create(to="antigravity", text="...") (even without sender/title)
    r3_create = bridge.handle_mcp_request(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "handoff_create",
                "arguments": {
                    "to": "antigravity",
                    "text": "Find 3 interactive Mars map examples with slope legend",
                },
            },
        },
        vault_dir=vault,
    )
    assert r3_create is not None and not r3_create["result"]["isError"]
    assert json.loads(r3_create["result"]["content"][0]["text"])["id"] == "HO-002"

    # Example 4: pivot_append(section="front", text="écran carte v1 intégré", author="codex")
    r4_pivot = bridge.handle_mcp_request(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "pivot_append",
                "arguments": {
                    "section": "front",
                    "text": "écran carte v1 intégré",
                    "author": "codex",
                },
            },
        },
        vault_dir=vault,
    )
    assert r4_pivot is not None and not r4_pivot["result"]["isError"]

    # Example 5: journal_append(author="philippe", text="...")
    r5_journal = bridge.handle_mcp_request(
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {
                "name": "journal_append",
                "arguments": {"author": "philippe", "text": "Connected 708 waypoints on feat/ui"},
            },
        },
        vault_dir=vault,
    )
    assert r5_journal is not None and not r5_journal["result"]["isError"]
