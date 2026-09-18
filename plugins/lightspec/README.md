# lightspec

Skills for the lightspec spec pipeline: turn a feature request into one reviewable spec file,
approve it on substance, and file it as a hew epic. Usable from any coding agent that loads
skills (Claude Code, opencode, codex).

## Overview

The process this serves is **ADR → spec → approve → implement**:

- **draft-spec** — turns a feature request into `specs/NNN-slug/spec.md`: description, prior
  decisions, prioritised user stories, tasks, and a done-when checklist. A script
  (`lightspec.py`) owns the format so every spec comes out identical; the skill supplies the
  judgment. Specs leave here at `Draft`.
- **approve-spec** — reviews a Draft spec the way someone who has to live with it would, and
  either moves it to `Accepted` or sends it back with blocking objections. Six questions, one
  per section; a finding that would not hold up the work is not a finding.
- **spec-to-epic** — files an Accepted spec as a hew epic: one epic issue carrying the spec's
  framing, one child issue per user story, done-when items derived per story so `work-issue`
  can drive them test-first.

## Prerequisites

- `python3` (stdlib only — the scripts need no virtualenv) and `uv` for the documented
  `uv run --no-project` invocations
- `spec-to-epic` additionally needs [`hew`](https://github.com/lumberbarons/hew) on PATH,
  authenticated via `gh auth login`
- Run from a checkout of the target repository

## Skills

| Skill | Description | Model-Invocable |
|-------|-------------|-----------------|
| `draft-spec` | Draft a feature spec into `specs/NNN-slug/spec.md` | Yes |
| `approve-spec` | Review a Draft spec on substance; accept or send back | Yes |
| `spec-to-epic` | File an Accepted spec as a hew epic with child issues | Yes |

Skill names are agent-neutral. Agents that resolve skills by name (opencode, codex) call them
directly; Claude Code prefixes the plugin name (`/lightspec:draft-spec`).

## Usage

```
draft-spec "Price Drop Watchlist"          # produce specs/NNN-slug/spec.md at Draft
approve-spec 009                           # substance review; moves to Accepted or sends back
spec-to-epic 009                           # file it in hew as an epic with children

draft-spec --dry-run                       # skeleton only
spec-to-epic specs/001-x/spec.md           # by path instead of number
```

## The pipeline

```
ADR (decisions plugin) ─→ draft-spec ─→ approve-spec ─→ spec-to-epic ─→ hew epic
                                                     (human gate)     └→ work-issue per child
```

Each skill hands off at a file or tracker boundary and stops: draft-spec never approves, never
files; approve-spec never edits the spec it reviewed; spec-to-epic never starts the work. The
chain is safe to stop at any link, and each link is invocable on its own.

## The format

`lightspec.py` generates the skeleton and checks the result, so the format is enforced rather
than described. Closed vocabularies the checker holds shut:

- **Status** — `Draft | Accepted | Implemented | Superseded`. Nothing else passes; only
  `Superseded` may carry text after the word, and only a link.
- **Priorities** — P1 is what makes the feature worth shipping at all; P2/P3 what makes it good.
- **Done When** — observable claims a stranger could falsify without reading the diff.

Citation links in Prior Decisions are resolved against the repository by `check`, so a
plausible-looking path to an ADR that does not exist is caught rather than believed.

## Maintenance

The format is defined twice — skeleton generator and checker — and the tests pin them together:

```bash
python3 -m unittest discover plugins/lightspec/skills/draft-spec/scripts
python3 -m unittest discover plugins/lightspec/skills/spec-to-epic/scripts
```

A fresh skeleton must fail the check for its `<FILL: ...>` markers and nothing else;
`reference/example-spec.md` must pass.
