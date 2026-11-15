"""MarsWalk Shared Memory Bridge (`tools/spaceapps_bridge.py`).

Provides the 6 shared-vault tools (`pivot_read`, `pivot_append`, `handoff_create`,
`handoff_list`, `handoff_ack`, `journal_append`) both as:
1. A zero-dependency stdio MCP server (`python tools/spaceapps_bridge.py serve-mcp`)
   configured in `.mcp.json` for Codex and Google Antigravity IDE;
2. A fast CLI (`python tools/spaceapps_bridge.py <command>`) synchronized across
   teammates via Git inside `<repo>/shared/`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_vault_dir(vault_override: str | Path | None = None) -> Path:
    """Resolve the shared vault directory (defaults to `<repo>/shared`)."""
    if vault_override is not None:
        base = Path(vault_override).expanduser().resolve()
    else:
        env_vault = os.environ.get("SPACEAPPS_VAULT")
        if env_vault:
            base = Path(env_vault).expanduser().resolve()
        else:
            base = Path(__file__).resolve().parents[1] / "shared"
    (base / "10_HANDOFFS").mkdir(parents=True, exist_ok=True)
    (base / "30_STITCH").mkdir(parents=True, exist_ok=True)
    pivot = base / "00_PIVOT.md"
    if not pivot.exists():
        pivot.write_text(
            "# MarsWalk Shared Pivot (`shared/00_PIVOT.md`)\n\n"
            "## [CONTRACT]\n\n## [ENGINE]\n\n## [FRONTEND]\n",
            encoding="utf-8",
        )
    journal = base / "20_JOURNAL.md"
    if not journal.exists():
        journal.write_text(
            "# MarsWalk Shared Evidence & Progress Journal (`shared/20_JOURNAL.md`)\n\n",
            encoding="utf-8",
        )
    return base


def pivot_read(vault_dir: Path | None = None) -> dict[str, Any]:
    """Read the full contents of `00_PIVOT.md`."""
    vault = resolve_vault_dir(vault_dir)
    pivot_path = vault / "00_PIVOT.md"
    return {
        "vault": str(vault),
        "content": pivot_path.read_text(encoding="utf-8"),
    }


def pivot_append(
    section: str,
    text: str,
    author: str = "agent",
    vault_dir: Path | None = None,
) -> dict[str, Any]:
    """Append a timestamped status line to `00_PIVOT.md`."""
    vault = resolve_vault_dir(vault_dir)
    pivot_path = vault / "00_PIVOT.md"
    current = pivot_path.read_text(encoding="utf-8")
    header = f"## [{section.strip().upper()}]"
    entry = f"- `[{_utc_now()}] ({author})`: {text.strip()}\n"

    if header in current:
        parts = current.split(header, 1)
        updated = f"{parts[0]}{header}\n{entry}{parts[1].lstrip(chr(10))}"
    else:
        updated = f"{current.rstrip()}\n\n{header}\n{entry}"

    pivot_path.write_text(updated, encoding="utf-8")
    return {"status": "ok", "section": section.upper(), "entry": entry.strip()}


def handoff_create(
    sender: str,
    to: str,
    title: str,
    body: str,
    vault_dir: Path | None = None,
) -> dict[str, Any]:
    """Create a new handoff JSON ticket inside `10_HANDOFFS/`."""
    vault = resolve_vault_dir(vault_dir)
    handoffs_dir = vault / "10_HANDOFFS"
    existing = sorted(handoffs_dir.glob("HO-*.json"))
    next_num = len(existing) + 1
    ho_id = f"HO-{next_num:03d}"
    while (handoffs_dir / f"{ho_id}.json").exists():
        next_num += 1
        ho_id = f"HO-{next_num:03d}"

    payload: dict[str, Any] = {
        "id": ho_id,
        "created_at": _utc_now(),
        "sender": sender.strip(),
        "to": to.strip(),
        "status": "OPEN",
        "acked_by": None,
        "acked_at": None,
        "ack_note": None,
        "title": title.strip(),
        "body": body.strip(),
    }
    out_path = handoffs_dir / f"{ho_id}.json"
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def handoff_list(
    for_agent: str = "all",
    status: str = "ALL",
    vault_dir: Path | None = None,
) -> dict[str, Any]:
    """List handoffs in `10_HANDOFFS/` filtered by recipient and status."""
    vault = resolve_vault_dir(vault_dir)
    handoffs_dir = vault / "10_HANDOFFS"
    items: list[dict[str, Any]] = []
    for p in sorted(handoffs_dir.glob("HO-*.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        if for_agent.lower() != "all" and for_agent.lower() not in str(data.get("to", "")).lower():
            continue
        if status.upper() != "ALL" and str(data.get("status", "")).upper() != status.upper():
            continue
        items.append(data)
    return {"count": len(items), "handoffs": items}


def handoff_ack(
    handoff_id: str,
    by_agent: str,
    note: str = "Acknowledged",
    vault_dir: Path | None = None,
) -> dict[str, Any]:
    """Acknowledge an open handoff ticket in `10_HANDOFFS/`."""
    vault = resolve_vault_dir(vault_dir)
    target = vault / "10_HANDOFFS" / f"{handoff_id.strip().upper()}.json"
    if not target.exists():
        raise FileNotFoundError(f"Handoff '{handoff_id}' not found in {target.parent}")
    data = json.loads(target.read_text(encoding="utf-8"))
    data["status"] = "ACKED"
    data["acked_by"] = by_agent.strip()
    data["acked_at"] = _utc_now()
    data["ack_note"] = note.strip()
    target.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return data


def journal_append(
    author: str,
    text: str,
    vault_dir: Path | None = None,
) -> dict[str, Any]:
    """Append a timestamped entry to `20_JOURNAL.md`."""
    vault = resolve_vault_dir(vault_dir)
    journal_path = vault / "20_JOURNAL.md"
    line = f"- `[{_utc_now()}] ({author.strip()})`: {text.strip()}\n"
    with journal_path.open("a", encoding="utf-8") as fh:
        fh.write(line)
    return {"status": "ok", "entry": line.strip()}


MCP_TOOLS_SCHEMA: list[dict[str, Any]] = [
    {
        "name": "pivot_read",
        "description": "Read the shared MarsWalk pivot board (shared/00_PIVOT.md).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "pivot_append",
        "description": "Append a status update to a section of shared/00_PIVOT.md.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "section": {
                    "type": "string",
                    "description": "Section (CONTRACT, ENGINE, FRONTEND)",
                },
                "text": {"type": "string", "description": "Status message to append"},
                "author": {"type": "string", "description": "Author or agent name"},
            },
            "required": ["section", "text"],
        },
    },
    {
        "name": "handoff_create",
        "description": "Create a structured handoff ticket in shared/10_HANDOFFS/.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sender": {"type": "string"},
                "to": {"type": "string"},
                "title": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["sender", "to", "title", "body"],
        },
    },
    {
        "name": "handoff_list",
        "description": "List handoff tickets in shared/10_HANDOFFS/.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "for_agent": {"type": "string", "default": "all"},
                "status": {"type": "string", "default": "ALL"},
            },
        },
    },
    {
        "name": "handoff_ack",
        "description": "Acknowledge a handoff ticket by ID (e.g. HO-001).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "handoff_id": {"type": "string"},
                "by_agent": {"type": "string"},
                "note": {"type": "string", "default": "Acknowledged"},
            },
            "required": ["handoff_id", "by_agent"],
        },
    },
    {
        "name": "journal_append",
        "description": "Append a progress entry to shared/20_JOURNAL.md.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "author": {"type": "string"},
                "text": {"type": "string"},
            },
            "required": ["author", "text"],
        },
    },
]


def handle_mcp_request(req: dict[str, Any], vault_dir: Path | None = None) -> dict[str, Any] | None:
    """Process a single JSON-RPC 2.0 MCP message."""
    method = req.get("method")
    msg_id = req.get("id")
    params = req.get("params") or {}

    if method == "notifications/initialized":
        return None

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "spaceapps-bridge", "version": "1.0.0"},
            },
        }

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"tools": MCP_TOOLS_SCHEMA},
        }

    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        try:
            if name == "pivot_read":
                res = pivot_read(vault_dir)
            elif name == "pivot_append":
                res = pivot_append(
                    section=args["section"],
                    text=args["text"],
                    author=args.get("author", "agent"),
                    vault_dir=vault_dir,
                )
            elif name == "handoff_create":
                res = handoff_create(
                    sender=args["sender"],
                    to=args["to"],
                    title=args["title"],
                    body=args["body"],
                    vault_dir=vault_dir,
                )
            elif name == "handoff_list":
                res = handoff_list(
                    for_agent=args.get("for_agent", "all"),
                    status=args.get("status", "ALL"),
                    vault_dir=vault_dir,
                )
            elif name == "handoff_ack":
                res = handoff_ack(
                    handoff_id=args["handoff_id"],
                    by_agent=args["by_agent"],
                    note=args.get("note", "Acknowledged"),
                    vault_dir=vault_dir,
                )
            elif name == "journal_append":
                res = journal_append(
                    author=args["author"],
                    text=args["text"],
                    vault_dir=vault_dir,
                )
            else:
                raise ValueError(f"Unknown tool: {name}")

            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(res, indent=2)}],
                    "isError": False,
                },
            }
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": f"Error: {exc}"}],
                    "isError": True,
                },
            }

    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def serve_mcp_stdio(vault_dir: Path | None = None) -> int:
    """Run the JSON-RPC 2.0 MCP server over stdin/stdout."""
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        req = json.loads(line)
        resp = handle_mcp_request(req, vault_dir=vault_dir)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the SpaceApps Bridge CLI or stdio MCP server."""
    parser = argparse.ArgumentParser(
        prog="spaceapps-bridge",
        description="MarsWalk Shared Memory Bridge (MCP Server + CLI over ./shared)",
    )
    parser.add_argument("--vault", default=None, help="Optional override path for shared vault")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("serve-mcp", help="Run stdio JSON-RPC MCP server")
    sub.add_parser("pivot-read", help="Read shared/00_PIVOT.md")

    p_app = sub.add_parser("pivot-append", help="Append line to shared/00_PIVOT.md")
    p_app.add_argument("--section", required=True)
    p_app.add_argument("--author", default="agent")
    p_app.add_argument("--text", required=True)

    p_hc = sub.add_parser("handoff-create", help="Create handoff ticket in shared/10_HANDOFFS/")
    p_hc.add_argument("--from", dest="sender", required=True)
    p_hc.add_argument("--to", required=True)
    p_hc.add_argument("--title", required=True)
    p_hc.add_argument("--body", required=True)

    p_hl = sub.add_parser("handoff-list", help="List handoffs in shared/10_HANDOFFS/")
    p_hl.add_argument("--for-agent", default="all")
    p_hl.add_argument("--status", default="ALL")

    p_ha = sub.add_parser("handoff-ack", help="Acknowledge a handoff ticket")
    p_ha.add_argument("--id", dest="handoff_id", required=True)
    p_ha.add_argument("--by", dest="by_agent", required=True)
    p_ha.add_argument("--note", default="Acknowledged")

    p_ja = sub.add_parser("journal-append", help="Append entry to shared/20_JOURNAL.md")
    p_ja.add_argument("--author", required=True)
    p_ja.add_argument("--text", required=True)

    args = parser.parse_args(argv)
    vault = resolve_vault_dir(args.vault)

    if args.command == "serve-mcp":
        return serve_mcp_stdio(vault)
    if args.command == "pivot-read":
        print(json.dumps(pivot_read(vault), indent=2))
        return 0
    if args.command == "pivot-append":
        print(json.dumps(pivot_append(args.section, args.text, args.author, vault), indent=2))
        return 0
    if args.command == "handoff-create":
        print(
            json.dumps(handoff_create(args.sender, args.to, args.title, args.body, vault), indent=2)
        )
        return 0
    if args.command == "handoff-list":
        print(json.dumps(handoff_list(args.for_agent, args.status, vault), indent=2))
        return 0
    if args.command == "handoff-ack":
        print(json.dumps(handoff_ack(args.handoff_id, args.by_agent, args.note, vault), indent=2))
        return 0
    if args.command == "journal-append":
        print(json.dumps(journal_append(args.author, args.text, vault), indent=2))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
