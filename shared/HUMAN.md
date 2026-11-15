# shared/ — how we talk to each other through the code

> *We work on two machines, in two heads, with several agents. This folder is where the work changes hands without getting lost.*
> — Jean-Sébastien

## Be clear about what "shared" means

- **On one machine**, your agents (Codex, Antigravity) can read and write this folder at the same time: what one writes, the other reads right away.
- **Between my machine and yours**, nothing is shared until someone runs `git pull` or `git push`. There is no live link between our computers. Git is the bridge.

So the reflex is simple: **pull before you read, push after you write.**

## The four things in here

| Path | What it is | When you use it |
|---|---|---|
| `00_PIVOT.md` | The status board: where contract, engine and frontend stand | Read it when you start a session |
| `10_HANDOFFS/` | Tickets passed from one person or agent to another | When you need something from me, or when you deliver something |
| `20_JOURNAL.md` | A dated log of what was done | At the end of a work block, in one or two lines |
| `30_STITCH/` | Drop zone for Stitch screens, wireframes and specs | When you want me or an agent to see a design |

## The commands (no setup needed beyond Python)

```bash
python tools/spaceapps_bridge.py pivot-read
python tools/spaceapps_bridge.py handoff-list --for-agent teammate
python tools/spaceapps_bridge.py handoff-create --from teammate --to jean --title "Need cell size in meters" --body "..."
python tools/spaceapps_bridge.py handoff-ack --id HO-001 --by teammate --note "Loaded in UI"
python tools/spaceapps_bridge.py journal-append --author teammate --text "Map renders the 708 stops"
```

Then `git add shared/ && git commit -m "..." && git push`.

Your agents can also call the same six tools through the MCP server declared in `.mcp.json` (`python tools/spaceapps_bridge.py serve-mcp`).

## Three rules

1. Never write a key, a password, a token or an email address in here. This repository will become public.
2. Use the names `jean`, `teammate`, `codex`, `antigravity` as authors, never Discord handles.
3. Acknowledging a handoff means "I received it", not "it is done". Write the result in the journal when it is done.
