# 2-minute demo — shot list

**Before you hit record**

```bash
make reset && make console     # clean history, platform on :8800
```

Open six tabs in this order so every cut is one click away:
`/` · `/repositories` · `/scan` · `/findings` · `/reports` · `/integrations`

Zoom the browser to 110%. Hide the bookmarks bar. Terminal on a second window,
font ≥ 16pt — you cut to it twice.

---

## 0:00 – 0:12 · The problem
**Screen** `/` dashboard, idle.

> "Autonomous bug-fixing agents are nearly here. The blocker isn't that they
> can't write patches — it's that nobody will let one merge unattended.
> This is the layer that makes that safe."

## 0:12 – 0:25 · The thesis
**Screen** `/` — point the cursor at the six pipeline nodes as you name them.

> "The fixer is a black box. We never look inside it. We gate it:
> reproduce the bug, let the box patch it, then check the patch two
> independent ways — tests for behaviour, diff inspection for security.
> Both must clear. Anything else goes to a human."

## 0:25 – 0:50 · The patch that ships
**Screen** `/scan` → **Scan now** on `wordpress-develop`. Let the nodes light up.

> "Real WordPress. This bug is a reverted upstream commit, Trac 65927 — the
> fix removed, its test kept, so the suite is genuinely red. Precheck proves
> the test fails for the right reason. PHPUnit runs the selected tests.
> Deterministic inspection finds nothing. Nemotron agrees."

**Beat on** `ALLOW — shipped unattended`.

> "That's the one case that must work. A gate that rejects everything is useless."

## 0:50 – 1:15 · The patch that must not ship
**Screen** stay on `/scan`, run `WP-64748`. Then cut to `/findings`.

> "Same pipeline, different bug. The fixer's patch is green — every test
> passes. And it swapped `wp_kses` for `esc_html` on a page title."

**Point at the CWE-79 badge.**

> "Tests can't see that. The diff inspector can: a removed output-escaping
> guard on a protected path. Rejected, with the line and the rule."

## 1:15 – 1:35 · Red team
**Screen** run `RT-EXPORT`, then `/findings`.

> "This one is adversarial — a patch written to look like a bug fix and
> quietly widen an export. Seven findings. Tavily pulls live CVE context
> for the escalation so the human reviewer opens with sources, not a diff."

## 1:35 – 1:52 · The receipt
**Screen** terminal.

```bash
darkfactory verify
```
> "Every decision is hash-chained and signed."

Edit one line of `audit/trail.jsonl` in the editor, save, re-run:

```bash
darkfactory verify
```
> "It names the entry that moved. You can't quietly rewrite why something shipped."

## 1:52 – 2:00 · Close
**Screen** `/integrations` — the connected services.

> "Nebius Token Factory, Nemotron, Tavily, n8n. The fixer is the robot arm.
> This is the interlock."

**Devin shows disconnected** — its key 403s, account-side. Nothing in the demo
path uses it, so don't linger on that tile. If asked: "the fixer is pluggable;
we run it as a fixture here, which is the point — we never trust it anyway."

---

## Lines to avoid
- Don't call the fixer ours — it's a black box on purpose, and that's the point.
- Don't say "AI finds bugs". The deterministic layer finds them; the model is the second key.
- `bug_d_redteam` is synthetic. Say so, as above. The other three are real reverted commits.

## If something goes red on camera
`WP-66241` escalates at precheck by design — it can't be reproduced in 3 attempts.
If it comes up, that's a feature: *"it refuses to let the box touch a bug it can't prove exists."*
