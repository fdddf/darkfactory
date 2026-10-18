# Dark Factory

A confidence layer that lets a repository fix its own trivial bugs and ship
them with nobody approving the change by hand.

Pointing a coding agent at a bug and getting a plausible fix is close to
solved. What stops it being autonomous is that nobody will merge and deploy
that fix without reading it first, so a human stays in the loop and the
autonomy quietly disappears. That is a trust problem, not a capability one.

**So the agent is not the deliverable. The interlocks around it are.**
The fixer is a black box behind a three-argument interface. Swap in Devin, an
open model on Nebius Token Factory, or a shell script — none of the confidence
is meant to come from it.

Target repository: WordPress core.

## Try it

No keys, no PHP, no WordPress checkout needed. The line runs end to end
against recorded fixtures:

```bash
make demo
```

Three bugs go in. One ships unattended, two do not:

| Bug | Outcome | Stopped by |
|---|---|---|
| `WP-A-1cc992c` CSS variable names generated inconsistently (Trac #65927) | **ships** | — |
| `WP-66241` HTML API character reference decoding (Trac #66241) | **escalate** | pre-check: no test reproduces it in 3 attempts |
| `WP-64748` privacy policy page title escaping (Trac #64748) | **reject** | diff inspection: the fix deletes the escaping |

All three are real WordPress regressions, seeded by reverting the commits
that fixed them (see **Bug provenance** below). A fourth fixture,
`RT-EXPORT`, is **synthetic and labelled as such**: one deliberately bad
patch that trips seven rules across six CWE classes at once, so the rule set
can be shown working in a single pass. A real black box would rarely produce
all of those together.

`WP-64748` is the one that matters. WordPress changed `esc_html( $page_title )`
to `wp_kses( $page_title, <allowlist> )` so that permitted markup in a page
title renders instead of showing as entities. Revert that and the bug is
"my `<strong>` shows up as `&lt;strong&gt;`". The cheapest fix is to drop the
escaping altogether — and it works. The test goes green, the markup renders,
and the patch ships stored XSS.

The oracle says yes. Diff inspection says no.

```bash
python3 -m darkfactory.cli replay WP-C-59831
```

```
14:42:47  allow     precheck    bug reproduced by a generated test
14:42:47  produced  blackbox    fixture:c_insecure.diff returned a diff
14:42:47  allow     oracle      repro went red to green and regression held
14:42:47  reject    inspection  deterministic layer rejected the change
14:42:47  reject    outcome     handed to a human at inspection
```

### The audit trail is checkable

Every entry commits to the hash of the one before it and is signed.

```bash
make verify   # chain intact
make tamper   # edit one byte, then verify again
```

```
chain broken
  ✗ entry #14 (inspection, bug WP-C-59831): contents were edited after the fact
```

## The line

```
bug report
  → ① pre-check      can we generate a test that reproduces this?      no → human
  → ② black box      fix(bug, failing_test, repo) -> diff              (not ours)
  → ③a oracle        repro red→green, regression holds, tests untouched
  → ③b inspection    is the change itself safe to ship?
  → ④ gated deploy   flag + 10% canary + SLO auto-rollback
  → ⑤ audit          hash-chained, signed, replayable
```

One rule runs through all of it: **anything that is not a clear pass goes to
a person.** The line never guesses.

### ① Pre-check — four gates

"Trivial" has one operational meaning: a test can be generated that
reproduces the bug. Four gates, all must pass, three attempts, then a human.

1. `php -l` passes
2. PHPUnit loads and runs it
3. It is red
4. **It is red for the right reason** — an assertion failure, not a fatal error

Gate 4 is the one worth defending. A test that dies on a missing class has
not reproduced anything.

### ③a Oracle

Red → green on the reproducing test, and the covering regression tests hold.
Plus one rule that is not in the brief: **the diff may not touch `tests/**`**.
The oracle is only evidence if the fixer cannot edit it.

Results come from PHPUnit's JUnit XML, not from scraping stdout, so every
case is known by name — which is what quarantine and the audit trail need.

**Selection.** We do not run twenty thousand tests. We run the ones covering
the changed code, and the audit records how that set was chosen; scoping the
suite is a decision the line justifies, not a shortcut around one. A pcov
coverage map (`coverage-map.json`) is used when present, otherwise the path
heuristic WordPress's mirrored test layout makes possible. Candidates that do
not resolve on disk are dropped and reported rather than handed to PHPUnit.

**No evidence is not good evidence.** An empty selection, a suite that fails
to start, or a timeout escalates. It never reads as green.

**Quarantine.** A test that passes and fails on the same tree cannot serve as
an oracle, so known flaky tests are named in `policy.json` and their results
are recorded as suppressed rather than silently dropped. This cuts both ways:
a quarantined test is excluded from the reproducing run too, so it can neither
prove nor veto a fix.

```bash
make quarantine SEL=tests/phpunit/tests/formatting   # run x3, report disagreement
```

Add `--write` to record what it finds in the policy.

#### Running it for real

```bash
make real        # the line, with PHPUnit against wp/
make selftest    # proves the runner works without WordPress or MySQL
```

Verified against wordpress-develop with PHPUnit 9.6.38: 1753 real tests in
14s for the formatting change, 1179 in 68s for the admin one, 86s for all
three bugs end to end. Setup is in [SERVICES.md](SERVICES.md) §11 — it needs
MariaDB but not Docker.

Two PHPUnit behaviours would otherwise have given us a silent green, and both
are handled in the runner: a directory target runs **zero tests and exits 0**
unless `--test-suffix .php` is passed, because WordPress names its test files
`humanTimeDiff.php` rather than `humanTimeDiffTest.php`; and PHPUnit 9 honours
only the first positional target, so the runner invokes it once per selector
and merges.

The runner picks a backend: `vendor/bin/phpunit` locally, `npm run test:php`
when Docker is there, or `$DF_PHPUNIT_CMD` to run the suite somewhere else
entirely — a Nebius Sandbox, for instance. Nothing else in the pipeline
changes when the backend does.

### Briefing the human

Every path that is not a clear pass ends with a person, and that person
arrives holding a rule name and a line number. So when the line stops on a
security finding, it researches what it stopped on — the vulnerability
class, WordPress's own history with it, the published advisories — and files
that with the rejection, sources and all.

Tavily does the retrieval. It runs only on reject and escalate, so a clean
run makes no network calls.

```bash
python3 -m darkfactory.cli run --all --enrich tavily
```

The brief lands in the audit trail as its own entry, which means the record
says not just that we refused a patch but what we knew when we did.

### ③b Diff inspection — two keys

Security by reading the output rather than caging the runtime. Two
independent layers, both must clear a change, and a disagreement escalates
rather than being resolved in favour of either one.

**Deterministic** (`darkfactory/inspection/deterministic.py`) — reproducible
from the patch and `policy.json` alone, no model involved. Every finding
carries the CWE it falls under, so it can be looked up against published
advisories rather than read only as our own rule name. 25 weakness classes:

| | |
|---|---|
| removed guards | CWE-862 authorization, CWE-352 CSRF, CWE-89 prepared statements, CWE-79 escaping, CWE-601 open redirect, CWE-22 path validation, CWE-208 timing |
| added sinks | CWE-95 code injection, CWE-78 command injection, CWE-502 deserialization, CWE-611 XXE, CWE-918 SSRF, CWE-434 file upload, CWE-621 variable overwrite, CWE-327 weak crypto, CWE-338 weak randomness, CWE-200/209 disclosure |
| flow patterns | CWE-89 interpolated SQL, CWE-22 path traversal, CWE-98 file inclusion, CWE-79 unescaped echo |
| the line's own rules | CWE-798 hardcoded credentials, CWE-345 test tampering, CWE-1357 dependency change, protected paths, blast radius |

Function-shaped patterns match on a word boundary, so `rand(` does not fire
on `mt_rand(` and `system(` does not fire on `filesystem(`. Folds in the
WordPress `phpcs` security sniffs when phpcs is installed.

**Semantic** (`semantic.py`) — NVIDIA Nemotron on Nebius Token Factory,
temperature 0, strict JSON schema, for what pattern matching cannot see.
If it errors or times out, that is an escalation, not an allow.

## The platform

```bash
make platform       # builds the frontend, serves everything on :8800
```

React + TypeScript + Tailwind on a standard-library Python API. Six screens:

| | |
|---|---|
| **Overview** | what shipped, what was refused, what went to a person |
| **Repositories** | attach a checkout by clone URL or local path; auto scan watches HEAD and starts a scan when it moves |
| **Live scan** | the line driven by the server's event stream, gate by gate |
| **Findings** | every rule that fired, its evidence, advisory lookup, the proposed patch and how it was really fixed |
| **Reports** | per-scan decision trail, severity breakdown, the audit chain |
| **Integrations** | Token Factory, Nemotron, Sandboxes, Tavily, n8n and Devin — credentials go live for the next scan |

For development, `make dev` runs Vite with hot reload and proxies `/api` to
`make api` in another shell. The same line runs headless with `make real`,
which is the fallback if anything is wrong with a browser on the day.

### Deploying on a Nebius VM

```bash
sudo bash deploy/bootstrap.sh
```

Installs PHP, MariaDB, Node and nginx; builds the frontend; clones
wordpress-develop and wires its test config; seeds bugs from real history;
and runs the platform under systemd behind nginx on port 80. The nginx
config disables buffering on `/api/events` — without that the live view
arrives in one lump when the scan ends.

## Layout

```
darkfactory/
  schema.py              interface contracts — the only shared surface
  policy.py  policy.json what a fix is allowed to look like
  precheck.py            the four gates
  blackbox/              swappable fixers: fixture, devin, tokenfactory
  oracle.py              test selection, execution, anti-tamper
  inspection/            diffparse, deterministic, semantic, two-key rule
  deploy.py              flag, canary, SLO, rollback
  audit.py               hash chain, signatures, verification
  pipeline.py            the line
  seed.py                make bugs by reverting real WordPress fixes
  enrich/                Tavily research for escalations
  runners/               PHPUnit execution and JUnit parsing
  platform.py            repositories, scans, integrations; state in one file
  server.py              platform API, event stream, serves the React build
  cli.py                 serve / run / seed / replay / verify / quarantine
web/                     React + TypeScript + Tailwind
  src/Pipeline.tsx       the line, drawn flat
  src/pages/             overview, repositories, scan, findings, report, integrations
deploy/                  bootstrap.sh, systemd unit, nginx config
fixtures/                three bugs and their recorded diffs
```

Every stage is a seam. `--fixer`, `--judge` and the runner/deployer objects
swap implementations without the pipeline changing.

```bash
python3 -m darkfactory.cli run --all --fixer devin --judge nemotron
```

## Bug provenance

Seeded by reverting real WordPress fix commits, so each bug carries its
original Trac ticket and the project's own fix as ground truth.

```bash
make seed    # or: python3 -m darkfactory.cli seed --repo wp --count 3
```

The seeder searches history for commits that changed both source and tests,
then **reverts only the source half**. The test that shipped with the fix
stays in the tree and goes red the moment the source regresses — a
reproduction nobody can accuse us of tuning. It verifies that too: a
candidate whose carried test stays green after the revert is rejected,
because the test does not cover the regression.

That rejection is where `WP-66241` came from. It is a real fix whose test
genuinely does not cover the behaviour, which is exactly the bug the line
must refuse to touch.

## Services

| Service | Where it is used |
|---|---|
| **Nebius Token Factory** | all inference; OpenAI-compatible, strict `json_schema` verdicts |
| **NVIDIA Nemotron** | the semantic half of diff inspection — the most judgement-heavy step |
| **Nebius Sandboxes** | VM isolation for the black box; branching to test candidate patches in parallel |
| **Tavily** | researches every escalation so the human arrives briefed, with sources |
| **Devin** | a black-box implementation; parallel sessions, one per qualified bug |
| **n8n** | pipeline orchestration, with an explicit error branch to a human at every gate |

What to sign up for, with endpoints and env vars: [SETUP.md](SETUP.md).
Service details and MCP configuration: [SERVICES.md](SERVICES.md).
Build plan and scope: [PLAN.md](PLAN.md).

Nothing in that list is needed to run the demo. With no keys at all the line
runs end to end, raises findings, writes reports and verifies its chain; the
keys turn the model, research and sandbox layers from stubs into the real
thing.

## What is deliberately missing

A runtime sandbox around the black box. Inspecting the diff catches a wrong
or out-of-bounds fix, but not an agent that reaches the network or reads a
secret while it executes. Nebius Sandboxes gives us the containment
primitive — scoped file access, no secret access, an outbound allowlist — and
wiring the fixer into it is the next step.
