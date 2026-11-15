"""MarsWalk Shared Memory Bridge (`tools/spaceapps_bridge.py`).

Provides the 6 shared-vault tools (`pivot_read`, `pivot_append`, `handoff_create`,
`handoff_list`, `handoff_ack`, `journal_append`) plus bidirectional sync between
`<repo>/shared/` and `~/spaceapps-vault` (if present on the developer's machine).

Works simultaneously as:
1. A zero-dependency stdio MCP server (`python tools/spaceapps_bridge.py serve-mcp`)
   wired in `.mcp.json`, `.codex/config.toml`, and `.antigravity/mcp.json`;
2. A fast CLI (`python tools/spaceapps_bridge.py <command>`).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _repo_shared_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "shared"


def _home_local_vault() -> Path:
    return Path.home() / "spaceapps-vault"


def _ensure_vault_layout(base: Path) -> None:
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


def sync_with_home_vault(repo_vault: Path) -> dict[str, Any]:
    """Bidirectionally sync files between `repo/shared` and `~/spaceapps-vault` if present."""
    home_vault = _home_local_vault()
    if not home_vault.exists() or home_vault.resolve() == repo_vault.resolve():
        return {"synced": False, "home_vault": str(home_vault)}

    _ensure_vault_layout(repo_vault)
    _ensure_vault_layout(home_vault)
    copied: list[str] = []

    # 1. Sync handoffs in both directions (newest mtime wins)
    for src_dir, dst_dir in (
        (repo_vault / "10_HANDOFFS", home_vault / "10_HANDOFFS"),
        (home_vault / "10_HANDOFFS", repo_vault / "10_HANDOFFS"),
    ):
        for f in sorted(src_dir.glob("*.json")):
            target = dst_dir / f.name
            if not target.exists() or f.stat().st_mtime > target.stat().st_mtime + 0.5:
                shutil.copy2(f, target)
                copied.append(f"10_HANDOFFS/{f.name}")

    # 2. Sync 30_STITCH assets in both directions
    for src_dir, dst_dir in (
        (repo_vault / "30_STITCH", home_vault / "30_STITCH"),
        (home_vault / "30_STITCH", repo_vault / "30_STITCH"),
    ):
        for f in sorted(src_dir.glob("*")):
            if f.is_file() and f.name != ".gitkeep":
                target = dst_dir / f.name
                if not target.exists() or f.stat().st_mtime > target.stat().st_mtime + 0.5:
                    shutil.copy2(f, target)
                    copied.append(f"30_STITCH/{f.name}")

    # 3. Mirror 00_PIVOT.md and 20_JOURNAL.md from repo_vault to home_vault if home_vault is older
    for doc_name in ("00_PIVOT.md", "20_JOURNAL.md"):
        r_doc = repo_vault / doc_name
        h_doc = home_vault / doc_name
        if r_doc.exists() and (
            not h_doc.exists() or r_doc.stat().st_mtime >= h_doc.stat().st_mtime
        ):
            shutil.copy2(r_doc, h_doc)

    return {"synced": True, "home_vault": str(home_vault), "copied": copied}


def resolve_vault_dir(vault_override: str | Path | None = None) -> Path:
    """Resolve the shared vault directory (defaults to `<repo>/shared`)."""
    if vault_override is not None:
        base = Path(vault_override).expanduser().resolve()
        _ensure_vault_layout(base)
        return base

    env_vault = os.environ.get("SPACEAPPS_VAULT")
    if env_vault:
        base = Path(env_vault).expanduser().resolve()
    else:
        base = _repo_shared_dir()
    _ensure_vault_layout(base)
    if base.resolve() == _repo_shared_dir().resolve():
        sync_with_home_vault(base)
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
    section: str = "FRONTEND",
    text: str = "",
    author: str = "agent",
    vault_dir: Path | None = None,
) -> dict[str, Any]:
    """Append a timestamped status line to `00_PIVOT.md`."""
    vault = resolve_vault_dir(vault_dir)
    pivot_path = vault / "00_PIVOT.md"
    current = pivot_path.read_text(encoding="utf-8")
    norm_section = section.strip().upper()
    if norm_section in ("FRONT", "UI"):
        norm_section = "FRONTEND"
    header = f"## [{norm_section}]"
    entry = f"- `[{_utc_now()}] ({author.strip()})`: {text.strip()}\n"

    if header in current:
        parts = current.split(header, 1)
        updated = f"{parts[0]}{header}\n{entry}{parts[1].lstrip(chr(10))}"
    else:
        updated = f"{current.rstrip()}\n\n{header}\n{entry}"

    pivot_path.write_text(updated, encoding="utf-8")
    if vault.resolve() == _repo_shared_dir().resolve():
        sync_with_home_vault(vault)
    return {"status": "ok", "section": norm_section, "entry": entry.strip()}


def handoff_create(
    sender: str = "codex",
    to: str = "antigravity",
    title: str = "Handoff",
    body: str = "",
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

    effective_title = title.strip() or (body.strip()[:60] if body else "Handoff")
    effective_body = body.strip() or effective_title

    payload: dict[str, Any] = {
        "id": ho_id,
        "created_at": _utc_now(),
        "sender": sender.strip(),
        "to": to.strip(),
        "status": "OPEN",
        "acked_by": None,
        "acked_at": None,
        "ack_note": None,
        "title": effective_title,
        "body": effective_body,
    }
    out_path = handoffs_dir / f"{ho_id}.json"
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if vault.resolve() == _repo_shared_dir().resolve():
        sync_with_home_vault(vault)
    return payload


def handoff_list(
    for_agent: str = "all",
    status: str = "ALL",
    vault_dir: Path | None = None,
) -> dict[str, Any]:
    """List handoffs in `10_HANDOFFS/` filtered by recipient (with alias support) and status."""
    vault = resolve_vault_dir(vault_dir)
    handoffs_dir = vault / "10_HANDOFFS"
    items: list[dict[str, Any]] = []
    q_agent = for_agent.strip().lower()
    frontend_aliases = {"codex", "antigravity", "philippe", "maptop", "front", "frontend", "ui"}

    for p in sorted(handoffs_dir.glob("HO-*.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        target_to = str(data.get("to", "")).lower()
        if q_agent not in ("all", "", "*"):
            matched = q_agent in target_to or (
                q_agent in frontend_aliases
                and any(alias in target_to for alias in frontend_aliases)
            )
            if not matched:
                continue
        if status.upper() not in ("ALL", "", "*") and (
            str(data.get("status", "")).upper() != status.upper()
        ):
            continue
        items.append(data)
    return {"count": len(items), "handoffs": items}


def handoff_ack(
    handoff_id: str = "HO-001",
    by_agent: str = "philippe",
    note: str = "Acknowledged",
    vault_dir: Path | None = None,
) -> dict[str, Any]:
    """Acknowledge an open handoff ticket in `10_HANDOFFS/`."""
    vault = resolve_vault_dir(vault_dir)
    norm_id = handoff_id.strip().upper()
    if not norm_id.startswith("HO-"):
        norm_id = f"HO-{int(norm_id):03d}" if norm_id.isdigit() else norm_id
    target = vault / "10_HANDOFFS" / f"{norm_id}.json"
    if not target.exists():
        raise FileNotFoundError(f"Handoff '{handoff_id}' not found in {target.parent}")
    data = json.loads(target.read_text(encoding="utf-8"))
    data["status"] = "ACKED"
    data["acked_by"] = by_agent.strip()
    data["acked_at"] = _utc_now()
    data["ack_note"] = note.strip()
    target.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if vault.resolve() == _repo_shared_dir().resolve():
        sync_with_home_vault(vault)
    return data


def journal_append(
    author: str = "philippe",
    text: str = "",
    vault_dir: Path | None = None,
) -> dict[str, Any]:
    """Append a timestamped entry to `20_JOURNAL.md`."""
    vault = resolve_vault_dir(vault_dir)
    journal_path = vault / "20_JOURNAL.md"
    line = f"- `[{_utc_now()}] ({author.strip()})`: {text.strip()}\n"
    with journal_path.open("a", encoding="utf-8") as fh:
        fh.write(line)
    if vault.resolve() == _repo_shared_dir().resolve():
        sync_with_home_vault(vault)
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
                    "default": "FRONTEND",
                    "description": "Section (CONTRACT, ENGINE, FRONTEND / front)",
                },
                "text": {"type": "string", "description": "Status message to append"},
                "author": {"type": "string", "default": "codex", "description": "Author or agent"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "handoff_create",
        "description": "Create a structured handoff ticket in shared/10_HANDOFFS/.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sender": {"type": "string", "default": "codex"},
                "to": {"type": "string", "default": "antigravity"},
                "title": {"type": "string", "default": "Handoff"},
                "body": {"type": "string", "description": "Full handoff instructions or summary"},
                "text": {"type": "string", "description": "Alias for body"},
            },
            "required": ["to"],
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
        "description": "Acknowledge a handoff ticket by ID (defaults to HO-001).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "handoff_id": {"type": "string", "default": "HO-001"},
                "id": {"type": "string", "description": "Alias for handoff_id"},
                "by_agent": {"type": "string", "default": "philippe"},
                "note": {"type": "string", "default": "Acknowledged"},
            },
        },
    },
    {
        "name": "journal_append",
        "description": "Append a progress entry to shared/20_JOURNAL.md.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "author": {"type": "string", "default": "philippe"},
                "text": {"type": "string", "description": "Journal entry text"},
            },
            "required": ["text"],
        },
    },
]


def handle_mcp_request(req: dict[str, Any], vault_dir: Path | None = None) -> dict[str, Any] | None:
    """Process a single JSON-RPC 2.0 MCP message with resilient parameter aliases."""
    method = req.get("method")
    msg_id = req.get("id")
    params = req.get("params") or {}

    if method and method.startswith("notifications/"):
        return None

    if method == "initialize":
        req_proto = params.get("protocolVersion") or "2024-11-05"
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": req_proto,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "spaceapps-bridge", "version": "1.0.0"},
            },
        }

    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}

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
                    section=args.get("section") or "FRONTEND",
                    text=args.get("text") or args.get("content") or args.get("message") or "",
                    author=args.get("author") or args.get("sender") or "codex",
                    vault_dir=vault_dir,
                )
            elif name == "handoff_create":
                body_val = (
                    args.get("body")
                    or args.get("text")
                    or args.get("content")
                    or args.get("message")
                    or args.get("title")
                    or ""
                )
                title_val = args.get("title") or body_val[:60] or "Handoff"
                res = handoff_create(
                    sender=args.get("sender") or args.get("from") or args.get("author") or "codex",
                    to=args.get("to") or args.get("for_agent") or "antigravity",
                    title=title_val,
                    body=body_val,
                    vault_dir=vault_dir,
                )
            elif name == "handoff_list":
                res = handoff_list(
                    for_agent=args.get("for_agent") or args.get("to") or "all",
                    status=args.get("status") or "ALL",
                    vault_dir=vault_dir,
                )
            elif name == "handoff_ack":
                res = handoff_ack(
                    handoff_id=args.get("handoff_id") or args.get("id") or "HO-001",
                    by_agent=args.get("by_agent")
                    or args.get("by")
                    or args.get("author")
                    or "philippe",
                    note=args.get("note") or args.get("text") or "Acknowledged",
                    vault_dir=vault_dir,
                )
            elif name == "journal_append":
                res = journal_append(
                    author=args.get("author") or args.get("by") or "philippe",
                    text=args.get("text") or args.get("content") or args.get("message") or "",
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
    """Run the JSON-RPC 2.0 MCP server supporting both Content-Length and newline framing."""
    stdin_buf = sys.stdin.buffer
    stdout_buf = sys.stdout.buffer

    while True:
        first_line = stdin_buf.readline()
        if not first_line:
            break
        stripped = first_line.strip()
        if not stripped:
            continue

        if stripped.lower().startswith(b"content-length:"):
            length = int(stripped.split(b":", 1)[1].strip())
            while True:
                hdr_line = stdin_buf.readline()
                if not hdr_line or hdr_line.strip() == b"":
                    break
            body_bytes = stdin_buf.read(length)
            req = json.loads(body_bytes.decode("utf-8"))
            resp = handle_mcp_request(req, vault_dir=vault_dir)
            if resp is not None:
                out_bytes = json.dumps(resp).encode("utf-8")
                header = f"Content-Length: {len(out_bytes)}\r\n\r\n".encode("ascii")
                stdout_buf.write(header + out_bytes)
                stdout_buf.flush()
        else:
            req = json.loads(stripped.decode("utf-8"))
            resp = handle_mcp_request(req, vault_dir=vault_dir)
            if resp is not None:
                stdout_buf.write((json.dumps(resp) + "\n").encode("utf-8"))
                stdout_buf.flush()
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
    sub.add_parser("sync", help="Bidirectionally sync ./shared with ~/spaceapps-vault if present")
    sub.add_parser("pivot-read", help="Read shared/00_PIVOT.md")

    p_app = sub.add_parser("pivot-append", help="Append line to shared/00_PIVOT.md")
    p_app.add_argument("--section", default="FRONTEND")
    p_app.add_argument("--author", default="agent")
    p_app.add_argument("--text", required=True)

    p_hc = sub.add_parser("handoff-create", help="Create handoff ticket in shared/10_HANDOFFS/")
    p_hc.add_argument("--from", dest="sender", default="codex")
    p_hc.add_argument("--to", required=True)
    p_hc.add_argument("--title", default="Handoff")
    p_hc.add_argument("--body", required=True)

    p_hl = sub.add_parser("handoff-list", help="List handoffs in shared/10_HANDOFFS/")
    p_hl.add_argument("--for-agent", default="all")
    p_hl.add_argument("--status", default="ALL")

    p_ha = sub.add_parser("handoff-ack", help="Acknowledge a handoff ticket")
    p_ha.add_argument("--id", dest="handoff_id", default="HO-001")
    p_ha.add_argument("--by", dest="by_agent", default="philippe")
    p_ha.add_argument("--note", default="Acknowledged")

    p_ja = sub.add_parser("journal-append", help="Append entry to shared/20_JOURNAL.md")
    p_ja.add_argument("--author", default="philippe")
    p_ja.add_argument("--text", required=True)

    args = parser.parse_args(argv)
    vault = resolve_vault_dir(args.vault)

    if args.command == "serve-mcp":
        return serve_mcp_stdio(vault)
    if args.command == "sync":
        print(json.dumps(sync_with_home_vault(vault), indent=2))
        return 0
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
