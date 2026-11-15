# frontend/ — your house

> *I built the engine so that you never have to fight it. Everything below the map is mine to keep honest. Everything you see on the screen is yours to make beautiful.*
> — Jean-Sébastien

This folder is **yours**. Framework, map library, colors, typography, motion, the product name, the `.spaceapps.earth` domain: you choose. Nothing in `src/`, `tests/` or the engine will ever require you to change your choices.

---

## 1. What this app is, in one breath

An astronaut on Mars cannot trust an orbital slope map blindly: a map that looks flat from orbit at 64 m can hide a dangerous slope at a few meters. In 1971, Apollo 14 astronauts walked toward Cone Crater and never found its rim, because the real terrain did not match what they expected.

**Perseverance has already driven here.** At 708 stops it measured how tilted it was on the real ground. My engine compares the orbital map, at several scales, against that ground truth. Your interface shows, cell by cell, **which scale you can believe**, and whether a walk is **GO, CAUTION or NO_GO**.

Our sentence: ***The map that knows at which scale it lies.***

---

## 2. What you open, in this order

| # | File | Why you open it | Do you edit it? |
|---|---|---|---|
| 1 | `frontend/HUMAN.md` (this file) | The map of your work | Yes, add your own notes |
| 2 | [`frontend/README.md`](README.md) | Loading the pack in 10 lines of JavaScript + the Mars Trek tile grid warning | Yes |
| 3 | [`../public_packs/HUMAN.md`](../public_packs/HUMAN.md) | What each data file contains, field by field, and what is real or simulated **right now** | No, read only |
| 4 | [`../schemas/HUMAN.md`](../schemas/HUMAN.md) | How to generate your TypeScript types from the contract | No, read only |
| 5 | [`../shared/HUMAN.md`](../shared/HUMAN.md) | How we pass work to each other (handoffs, journal) | Yes, through the CLI |
| 6 | [`../src/marswalk/HUMAN.md`](../src/marswalk/HUMAN.md) | Only if you want the live API instead of static files | No |

You never need Python to build or deploy the UI. The data is already computed, signed and committed as static files.

---

## 3. The four rules that keep us honest on screen

1. **Never hard-code a number from the data.** Cell size, number of cells and baselines can change when my engine ships a new pack. Read them from `hazard_grid.json` (`cell_size_m`, `rows`, `cols`, `baselines_m`).
2. **Always show the provenance tag.** Every value is wrapped as `{ value, unit, tag, source_id, note }`. Show `tag` (`MEASURED`, `DERIVED` or `SIMULATED`) next to the value, even small. A judge must be able to tell real rover data from a simulation at a glance.
3. **Read `grid_status` before you trust the hazard grid.** `"PLACEHOLDER"` means synthetic values to build the UI against. Display a visible *"preview data"* badge. `"ENGINE"` means my real engine computed it from the HiRISE terrain model.
4. **Vocabulary on screen.** Say **Confidence** and **GO / CAUTION / NO_GO**. Never show "T/I/F", "neutrosophic" or "plithogenic" in the interface. Those words live in the engine and in the docs, not in front of the astronaut.

---

## 4. How confidence becomes something a human understands

Each hazard cell carries `confidence: { t, i, f }`, three numbers between 0 and 1:

| Field | What it means for the astronaut | Suggested label |
|---|---|---|
| `t` | How much the evidence agrees that the ground is walkable | **Agreement** |
| `i` | How much the scales disagree, or data is missing | **Scale uncertainty** |
| `f` | How strongly the evidence points to a danger | **Hazard risk** |

`verdict` is already decided for you. Never recompute it in the browser: show it, and show `reason` (a human sentence) when the user clicks a cell.

---

## 5. The three moments I dream the judges will see

1. **The zoom that reveals.** The user switches from the 64 m view to a finer scale, and a cell that looked green turns orange. That is the scale gap: `slope_deg_by_baseline["64"]` versus the finer baselines.
2. **The rover as witness.** Clicking a Perseverance stop shows the tilt the rover **measured** on the ground (`rover_tilt_deg`, tag `MEASURED`) beside what the orbital map predicted, plus the real panorama (`panorama_url`).
3. **The walk.** The astronaut route (`route.geojson`, tag `SIMULATED` for now), with the 2 km walk-back limit and the 20° suit limit from `eva_constraints.json`.

These are dreams, not orders. If you find a better story, follow it.

---

## 6. When you need something from me

Do not wait and do not guess the format: write a handoff (see `../shared/HUMAN.md`). If a field is missing, unclear or wrong, that is **my** bug, not yours.
