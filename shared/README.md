# Shared Team & Multi-Agent Memory Vault (`shared/`)

This folder is the **two-level shared memory bridge** for the MarsWalk team:

1. **Same-Machine Bridge (Codex ↔ Antigravity IDE):**
   Both **Codex** and **Google Antigravity IDE** read and write to this `./shared` directory via `.mcp.json` (`spaceapps-bridge` MCP server or `python tools/spaceapps_bridge.py` CLI). What Codex writes, Antigravity reads immediately, and vice versa.
2. **Cross-Teammate Bridge (`@EbaAaZ` ↔ `@Maptop` via Git):**
   Because `./shared` lives inside the Git repository alongside `public_packs/jezero/v1/`, a simple `git pull` / `git push` synchronizes our handoffs, pivot state, and journal entries across both machines without needing an external database.

---

## Vault Structure

- `00_PIVOT.md` — Live shared status board (`[CONTRACT]`, `[ENGINE]`, `[FRONTEND]`).
- `10_HANDOFFS/` — Structured handoff tickets between `engine`, `frontend`, `codex`, and `antigravity`.
- `20_JOURNAL.md` — Timestamped progress and evidence log for the Space Apps judges.
- `30_STITCH/` — Drop zone for UI wireframes, Stitch exports, or component specs.

---

## 6 Tools (Available via MCP `spaceapps-bridge` or CLI `python tools/spaceapps_bridge.py`)

| Tool | MCP Call | CLI Equivalent |
| :--- | :--- | :--- |
| `pivot_read` | `pivot_read()` | `python tools/spaceapps_bridge.py pivot-read` |
| `pivot_append` | `pivot_append(section, text, author)` | `python tools/spaceapps_bridge.py pivot-append --section frontend --author philippe --text "..."` |
| `handoff_create` | `handoff_create(sender, to, title, body)` | `python tools/spaceapps_bridge.py handoff-create --from codex --to antigravity --title "..." --body "..."` |
| `handoff_list` | `handoff_list(for_agent="all", status="OPEN")` | `python tools/spaceapps_bridge.py handoff-list --for-agent all` |
| `handoff_ack` | `handoff_ack(handoff_id, by_agent, note)` | `python tools/spaceapps_bridge.py handoff-ack --id HO-001 --by philippe --note "Loaded in UI"` |
| `journal_append` | `journal_append(author, text)` | `python tools/spaceapps_bridge.py journal-append --author philippe --text "..."` |
