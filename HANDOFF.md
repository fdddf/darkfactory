# Handoff — darkfactory

Written 2026-10-18. Read this top to bottom before touching anything.

## What this is

A confidence layer around a black-box bug-fixing agent, built for the SAP
"dark factory" track. **The fixer is explicitly out of scope** — we never
open it. The deliverable is the set of interlocks that decide whether its
patch may merge unattended.

> The bug-fixing agent is the robot arm. Nobody cares how smart the arm is.
> They care about the interlocks.

Pipeline: `intake → precheck → blackbox → oracle + inspection → deploy → outcome`.
Default rule: **anything that is not a clear pass goes to a human.**

Two-key rule: a deterministic layer (pattern/diff rules) and a semantic layer
(Nemotron) must *both* clear a patch. Disagreement, or an error in either,
escalates.

## State: working, demo-ready

Last full run (`python3 -m darkfactory.cli run --all --runner phpunit --repo wp`),
all services live:

| bug | outcome | deterministic | semantic (Nemotron) |
|---|---|---|---|
| WP-A-1cc992c | **ALLOW** — shipped unattended | allow, 0 findings | allow, conf 0.95 |
| WP-66241 | **ESCALATE** at precheck | — | — |
| WP-64748 | **REJECT** at inspection | reject, 1 finding | reject, conf 0.95 |
| RT-EXPORT | **REJECT** at inspection | reject, 7 findings | reject, conf 1.0 |

The ALLOW case is the one that matters most: a gate that rejects everything
is worthless. Real Nemotron does not block the good patch.

Audit chain verifies (`python3 -m darkfactory.cli verify` → "chain intact").

## Credentials

All secrets live in **`.env`** at the project root. It is gitignored, and no
make target touches it. `load_env_file()` runs at the top of `cli.main()` and
in `Store.__init__`, so every entry point gets them.

Live and verified today: `NEBIUS_API_KEY` (Token Factory, 28 models),
`TAVILY_API_KEY`, `N8N_API_KEY` (n8n Cloud, HTTP 200, 0 workflows defined).
`DEVIN_API_KEY` is **not set** — it returned 403 on every endpoint and is an
account-side issue. Nothing in the demo path depends on Devin.

**If `.env` is missing, the pipeline silently degrades rather than failing.**
`--judge auto` falls back to `StubJudge`, whose signature is
`allow / confidence 0.5 / 0 findings / no error` on *every* bug. If you see
that, the model is not being called. Do not report those numbers as results.

## Running it

```bash
make console     # platform on http://localhost:8800
make real        # all four bugs, CLI, real PHPUnit
make reset       # clears audit + scan history; KEEPS repos and credentials
```

`make reset` used to be `rm -rf audit state` and it destroyed the user's
configured API keys. It is now `cli reset`, which is non-destructive and
prints what it kept. Do not "simplify" it back.

Requirements: PHP 8.4 (herd-lite), MariaDB running with a `wordpress_tests`
database, and a `wordpress-develop` checkout at `./wp`. Python is
**standard library only** — no pip dependencies, deliberately. Don't add any.

## Layout

```
darkfactory/
  schema.py              interface contract; the one shared thing
  audit.py               append-only JSONL, sha256 chain + HMAC
  policy.py + policy.json  49 rules / 25 CWE classes, policy as data
  precheck.py            4 gates; gate 4 = red for the RIGHT reason
  oracle.py              diff-based test selection + quarantine
  runners/phpunit.py     real wordpress-develop PHPUnit
  inspection/
    deterministic.py     pattern + flow rules, word-boundary matched
    semantic.py          Nemotron over stdlib urllib
    __init__.py          combine() = the two-key rule
  seed.py                makes bugs by reverting real WP fixes, source half only
  pipeline.py            Line, with an observer hook for SSE
  platform.py            Repository/Scan/Store, .env loading
  server.py              platform API + SSE
  cli.py                 run / verify / replay / serve / seed / quarantine / reset
web/                     React 19 + TS + Tailwind v4, 6 pages
fixtures/                4 bugs (bug_d is synthetic — say so on camera)
DEMO.md                  2-minute shot list
```

## Traps already paid for — do not re-introduce

- **`git revert <sha> -- src` does not work** ("bad revision 'src'").
  Use `git show --format= <sha> -- src | git apply -R`.
- **Quarantine must apply to the repro run too**, not just the regression run.
  A quarantined test can neither prove nor veto a fix.
- **wordpress-develop keeps sources under `src/`.** Diff paths read
  `src/wp-includes/...`. `normalize()` strips it; without that, every
  protected-path rule is silently bypassed. This is a security hole, not a
  cosmetic one.
- **PHPUnit runs ZERO tests and exits 0** for a directory target without
  `--test-suffix .php`. Hence `BASE_ARGS`.
- **PHPUnit 9 honours only the first positional target** — one subprocess per
  selector, then merge.
- **Precheck test paths are relative to the repo**, not to cwd. `precheck.run()`
  takes a `repo` argument for exactly this. Without it `php -l` lints a
  nonexistent file and every bug fails the syntax gate.
- **Never build Tailwind class names at runtime** (`'bg-x'.replace(...)`) —
  the compiler cannot see them. Use explicit maps.
- three.js was tried for the pipeline view and **cut** after repeated layout
  problems. The flat rail in `web/src/Pipeline.tsx` replaced it. Don't bring
  it back.

## Left to do

1. **Record the 2-minute video** — follow `DEMO.md`. This is the gating deliverable.
2. Push a public GitHub repo (the working tree is **not** a git repo yet).
3. Submit on the platform. **Submissions close 18:30 sharp**, auto-closed.

## Conventions

Secrets are never printed — mask them or report presence only. The project's
own diff inspector has a `secret_added` rule, so a credential committed to the
tree would be flagged by our own tool. Keep it that way.
