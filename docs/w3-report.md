# W3 Report — whitelist, FM008, CI workflow, 10-repo scan, top-20 verification

**Status: DRAFT for lead review.** Branch `feat/w3`, base HEAD `4689833`,
W3.1 commits `04dc7c5` (feat parser), `43e99af` (test parser), `86e8950`
(docs), `ecff9ea` (feat ci). 136 tests green (`PYTHONPATH=src python -m
unittest discover -s tests`), `python -m compileall src` clean. Scan date:
2026-11-14. Nothing was pushed and no issue/PR was filed.

## 1. What changed in W3.1

### 1.1 Frontmatter whitelist extension (FM007)

`KNOWN_FRONTMATTER_KEYS` now also accepts six Claude Code frontmatter
extension keys（2026-11 实测于公开 skill 仓库：Jeffallan/claude-skills、
jwilger/agent-skills）:

`effort`, `compatibility`, `context`, `argument-hint`, `user-invocable`,
`disable-model-invocation`

Kept in a separate documented frozenset `CLAUDE_CODE_EXTENSION_KEYS`
(`src/skill_ci/rules.py`) so the source of the list stays reviewable and
the next iteration is a one-line change.

### 1.2 Depth-2 nested metadata: FM008 (info), never FM001

`metadata.foo.bar` (two or more levels under a frontmatter key) has parsed
without FM001 since W3.0 (stored as a raw string). W3.1 makes that
capability limit **visible**: each raw-captured entry is recorded on
`SkillDoc.raw_nested` and reported as **FM008 (info) "nested metadata
stored raw"**. FM008 never gates the exit code. Motivation: the linter's
stance is to say what it cannot tell — silently storing content unparsed
was the one remaining quiet path.

### 1.3 Regression evidence (untrusted repos, text-parse only)

Snapshots: `.scratch/w3-runs/lint-w31-*.json`, `parse-w31-*.json`
(compare against W3.0 `lint-after-*` / `parse-after-*`).

| repo | files | parse state vs W3.0 | FM001 | FM007 before → after | other findings |
| --- | ---: | --- | ---: | --- | --- |
| anthropics/skills | 20 | byte-identical | 0 → 0 | 0 → 0 | identical (zero regression) |
| Jeffallan/claude-skills | 67 | byte-identical | 0 → 0 | 0 → 0 | identical |
| jwilger/agent-skills | 21 | byte-identical | 0 → 0 | **32 → 0** | FM002/DQ003 unchanged |
| Teaonly/skill.mk | 19 | (W3.0 already clean) | 0 | 2 → 0 | clean |

The whitelist cleared **34 FM007 findings in total** (jwilger 32 +
Teaonly 2); nothing else moved on any of the four repos — no finding was
added, removed or re-severitied except the intended FM007 removals.

## 2. CI workflow (`.github/workflows/skill-ci.yml`, committed, not pushed)

- Triggers on `push` / `pull_request`; matrix `os: [ubuntu-latest,
  windows-latest]`, `fail-fast: false`.
- Runs `PYTHONPATH=src python -m skill_ci .` over the repository's own
  SKILL.md files (the `tests/fixtures/**` tree; local dry run: 41 skills,
  exit 1). No pip, no install.
- **Non-blocking by design** (`continue-on-error: true`, rationale
  documented in the file header): the in-repo SKILL.md files are
  intentionally malformed fixtures, so an error exit is the expected
  steady state; gating PRs on it would fail every push. A W4 gate should
  point the linter at real skills, not the fixture tree.
- **Validation honesty**: the workflow YAML was checked locally with a
  hand-rolled structural subset checker only (no PyYAML on the dev
  machine; tabs, key/list-line shape, indentation, quote and `${{ }}`
  balance, top-level keys). 完整验证在首次 push 后进行 — full schema and
  action-version validation happens the first time GitHub parses it.

## 3. Ten-repo scan

Five repos carried over (tarballs reused from `.scratch/`), five new
(codeload `main`-branch tarballs fetched 2026-11-14 into `.scratch/w3-new/`,
each extracted into its own directory, parsed as text only, `python -I`,
never executed/installed). Candidates were tried in the agreed order;
the first five all yielded SKILL.md files, so the sixth
(`Beirutii/claude-context-governor`) was **not needed and not fetched**.

| # | repo | skills | E | W | I | exit | rule breakdown |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | anthropics/skills | 20 | 2 | 2 | 10 | 1 | DQ002×1 DQ003×9 DQ004×1 FM004×1 TK001×1 TK002×1 |
| 2 | Jeffallan/claude-skills | 67 | 0 | 0 | 2 | 0 | SEC002×2 (placeholders, info) |
| 3 | jwilger/agent-skills | 21 | 1 | 0 | 8 | 1 | DQ003×8 FM002×1 |
| 4 | starslingdev/skills | 5 | 0 | 3 | 1 | 0 | DQ003×1 TK001×3 |
| 5 | Teaonly/skill.mk | 19 | 0 | 0 | 0 | 0 | — |
| 6 | microsoft/cat-agent-skills | 293 | 8 | 15 | 107 | 1 | DQ002×1 DQ003×98 DUP001×4 DUP003×1 FM001×4 FM004×1 FM007×8 TK001×13 |
| 7 | obra/superpowers | 15 | 0 | 0 | 1 | 0 | DQ003×1 |
| 8 | UiPath/coder_eval | 6 | 6 | 0 | 3 | 1 | DQ003×2 FM002×6 FM007×1 |
| 9 | gtrabanco/agentic-workflow | 34 | 5 | 2 | 87 | 1 | DQ003×31 DUP001×1 FM001×2 FM005×2 FM007×56 TK001×2 |
| 10 | hussi9/skill-router | 2 | 1 | 1 | 0 | 1 | DUP001×1 FM004×1 |
| | **total** | **482** | **23** | **23** | **219** | | |

Exit-code changes vs the W2 baseline for the five carried-over repos:
**none** (anthropics 1→1, Jeffallan 0→0, jwilger 1→1, starslingdev 0→0,
Teaonly 0→0); the W3.1 change removed findings without flipping any gate.

Observations:

- **FM008 fired zero times in 482 real skills** — depth-2 metadata nesting
  did not occur in this sample. The rule exists to keep the parser's
  honest "stored raw" path visible, not because it is noisy.
- **Residual FM007 keys** (i.e. whitelist candidates for a future
  iteration, *lead decision*): `version` ×32 and `author` ×25 (both all
  from gtrabanco/agentic-workflow), `cowork` ×7 (cat-agent),
  `disallowed-tools` ×1 (coder_eval). `disallowed-tools` is the strongest
  candidate: it mirrors `allowed-tools` and appears to be a genuine host
  key; `version`/`author` are usually inside `metadata:` in the
  anthropics spec, so top-level uses may be drift worth reporting after
  all.
- cat-agent-skills is a submission-style monorepo (293 skills): its
  findings are dominated by intentionally-repeated per-submission skill
  names and DQ003 info noise, which is exactly the "review pointer, not
  verdict" tier.
- The two DQ004/TK002 errors in anthropics/skills are real spec-limit
  violations in `skills/claude-api` (see §5 and outreach draft 2).

## 4. Top-20 findings: manual verification

Method: all 265 findings from the 10 repos sorted by severity
(error → warning → info), then rule id, file, line; top 20 taken. The
top 20 are the first 20 of the 23 errors (the remaining errors are
TK002 claude-api and FM005 ×2 gtrabanco, outside the cut). Each finding
was checked against the source SKILL.md.

Verdict classes: **TP** = finding matches the file and is a real issue
worth fixing; **TP-context** = matches the file but the content is
intentional (test fixture / stub); **TP-contract** = matches the
linter's documented contract but the file is valid YAML that our minimal
subset rejects (parser limitation — from the author's perspective a
false positive; counted honestly here).

| # | rule | repo | location | verdict | evidence (one line) |
| ---: | --- | --- | --- | --- | --- |
| 1 | DQ004 | anthropics/skills | skills/claude-api/SKILL.md:3 | TP | folded description measures 1068 chars > 1024 spec limit (block scalar `|-`, lines 3–8) |
| 2 | DUP001 | gtrabanco/agentic-workflow | .../test/fixtures/projection-golden/skills-source/golden-skill/SKILL.md:2 | TP-context | both files literally say `name: golden-skill`; skills-source is the build input, expected/ is the golden copy — intentional fixture |
| 3 | DUP001 | microsoft/cat-agent-skills | submissions/reg-submission-authoring/source-ingest/SKILL.md:2 | TP | `name: source-ingest` duplicated with submissions/product-content-catalog-enrichment/source-ingest |
| 4 | DUP001 | microsoft/cat-agent-skills | submissions/returns-refund-case/policy-retrieve/SKILL.md:2 | TP | `name: policy-retrieve` duplicated with submissions/denials-appeals-response/policy-retrieve |
| 5 | DUP001 | microsoft/cat-agent-skills | submissions/store-associate-assist/policy-retrieve/SKILL.md:2 | TP | third `name: policy-retrieve` copy (same collision group) |
| 6 | DUP001 | microsoft/cat-agent-skills | submissions/work-order-assist/knowledge-retrieve/SKILL.md:2 | TP | `name: knowledge-retrieve` duplicated with submissions/customer-service-order-support/knowledge-retrieve |
| 7 | DUP001 | hussi9/skill-router | SKILL.md:2 | TP | repo-root SKILL.md and codex-skill/skill-router/SKILL.md both say `name: skill-router` |
| 8 | FM001 | gtrabanco/agentic-workflow | scripts/fixtures/unit-route/skills/phase-lint/SKILL.md:1 | TP-context | whole file is `# phase-lint skill stub` — no frontmatter; fixture stub, not a real skill |
| 9 | FM001 | gtrabanco/agentic-workflow | skills/product-audit/SKILL.md:7 | TP-contract | `metadata:` subkey `opencode/autoinvoke: false` is valid YAML; subset key regex rejects `/` in nested keys |
| 10 | FM001 | microsoft/cat-agent-skills | submissions/ai-first-process-redesign/SKILL.md:20 | TP-contract | folded scalar `changelog: >-` under a nested metadata entry (lines 19–23) — valid YAML, unsupported in nested entries |
| 11 | FM001 | microsoft/cat-agent-skills | submissions/ai-first-process-redesign/SKILL.md:21 | TP-contract | same block-scalar continuation line |
| 12 | FM001 | microsoft/cat-agent-skills | submissions/ai-first-process-redesign/SKILL.md:22 | TP-contract | same block-scalar continuation line |
| 13 | FM001 | microsoft/cat-agent-skills | submissions/ai-first-process-redesign/SKILL.md:23 | TP-contract | same block-scalar continuation line |
| 14 | FM002 | jwilger/agent-skills | .claude/skills/bump/SKILL.md:1 | TP | frontmatter (lines 1–10) has description/user-invocable/argument-hint/allowed-tools but no `name` |
| 15 | FM002 | UiPath/coder_eval | plugins/coder-eval/skills/analyze/SKILL.md:1 | TP | description + allowed-tools present, `name` absent |
| 16 | FM002 | UiPath/coder_eval | plugins/coder-eval/skills/check-skill/SKILL.md:1 | TP | same |
| 17 | FM002 | UiPath/coder_eval | plugins/coder-eval/skills/ci/SKILL.md:1 | TP | same |
| 18 | FM002 | UiPath/coder_eval | plugins/coder-eval/skills/init/SKILL.md:1 | TP | same |
| 19 | FM002 | UiPath/coder_eval | plugins/coder-eval/skills/lint-tasks/SKILL.md:1 | TP | same |
| 20 | FM002 | UiPath/coder_eval | plugins/coder-eval/skills/task/SKILL.md:1 | TP | same |

**Tally: 20/20 findings match the file content (0 strict false
positives). 13 actionable TP, 2 TP-context (intentional fixture content),
5 TP-contract (valid YAML rejected by the documented subset — a parser
limitation, not an author error).** The 5 TP-contract findings (product-audit
`a/b` subkeys; ai-first block scalar in a nested entry) are the two
concrete W4 parser-subset fixes this week's scan surfaced; both would be
FM001 today and both are the kind of finding that erodes author trust if
left unexplained, which is why the verdict column names them.

Most typical three cases:

1. **#14 (jwilger bump, FM002)** — a real, one-line fix: the skill works
   in place but cannot be registered by anything that requires `name`
   (outreach draft 1).
2. **#1 (anthropics claude-api, DQ004)** — the spec-limit violation is
   real and measurable (1068 > 1024), in the most authoritative skill
   collection available (outreach draft 2).
3. **#9 (gtrabanco product-audit, FM001)** — the honest failure mode:
   our rule fired exactly as documented, and the file is nevertheless
   valid YAML. Reported as TP-contract and queued as a parser fix, not
   defended as author error.

## 5. Methods, heuristics, and what the numbers do not mean

- **Untrusted-data discipline**: third-party content only ever enters as
  codeload tarballs into gitignored `.scratch/` directories; every scan
  is text parsing with `python -I` / `PYTHONPATH=src python -m skill_ci`
  run from the trusted repo root; nothing extracted is executed,
  installed, or run as code; no interpreter is launched from inside an
  extracted tree.
- **CJK 自洽口径 (self-consistent token accounting)**: one shared
  script-weighted estimate (`src/skill_ci/tokens.py`) — ASCII 0.25
  tokens/char (identical to `len//4` for pure ASCII), CJK ~1.0, other
  non-ASCII 0.5 — used by TK001/TK002 and by skill-test's context-load
  numbers, so every figure in this report is comparable within the
  toolset. It is *not* a tokenizer: numbers are budgeting estimates, and
  cross-tool consistency (自洽) is the guarantee, not absolute accuracy
  (calibration status and limits: docs/w2-report.md).
- **DQ003 (no "use when" phrasing) is info on purpose**: absence of the
  literal hint is observable; whether the skill actually triggers
  correctly is not, from static text. Treat the 150 DQ003 hits as review
  pointers, not verdicts.
- **Verification method**: severity→rule sort (§4), then each of the 20
  findings was checked by opening the exact file and line and comparing
  against the message; every claim in the verdict column is one
  sentence that can be re-checked against the named file.

### Honest positioning

This linter is **insufficient when it can't tell, and it says so when it
can't tell**. It checks structure and spec limits it can verify from text
(keys present, name/directory agreement, description length, token
budgets, placeholder-shaped secrets) and deliberately refuses to judge
what text cannot show: it cannot tell whether a description triggers
well (DQ003 is info), whether a raw-stored nested mapping is meaningful
(FM008, info), or whether a rejected construct is author error or parser
limitation (parse notes name the exact unsupported construct instead of
guessing). 23 errors across 482 skills — 13 of them confirmed actionable
in the top-20 cut — is the honest resolution of this toolset this week,
not a quality verdict on the scanned repos, several of which are
internally consistent in ways a flat-name linter cannot model
(cat-agent's per-submission packaging being the clearest example).

## 6. Known limitations (this week)

- The YAML subset still rejects two valid-YAML constructs found in the
  wild: `/` inside nested-map keys (product-audit) and block scalars
  under nested-map entries (ai-first-process-redesign). Both are
  documented subset limits, reported loudly (FM001 with the exact line),
  never guessed at. W4 candidates.
- FM007 remains intentionally strict; residual keys (`version`, `author`,
  `cowork`, `disallowed-tools`) need a lead decision (§3).
- The 10-repo sample is convenience-sampled (candidates fixed in the
  plan); counts are not prevalence estimates for the ecosystem.
- CI workflow unvalidated beyond the structural subset check (§2).
- FM008 has no real-world instance in this sample; its fixture coverage
  is synthetic only.

## 7. Outreach drafts (written, NOT sent)

`outreach/jwilger-agent-skills-bump-missing-name.md` (FM002, one-line
fix), `outreach/anthropics-skills-claude-api-description-and-body.md`
(DQ004 1068>1024 + TK002 ~26k-token body), `outreach/starslingdev-skills-ci-speedup-body-budget.md`
(TK001 9524-token body, pattern shared by 3 of 5 skills in that repo).
Each carries file/line/rule evidence and a concrete proposed frontmatter/
structure fix, friendly tone. Sending requires lead approval; per W3
rules nothing was posted.

## 8. Deviations from plan

- None material. `Beirutii/claude-context-governor` was never fetched
  because the first five candidates all succeeded (plan allowed stopping
  at 10 repos). The `unknown-nested` fixture was edited (key `context` →
  `x-custom-scope`) because `context` joined the whitelist and the test
  would otherwise have been vacuous — the test itself was neither
  deleted nor skipped. One new stray: `.scratch/w3-tools/check_workflow.py`
  (workflow self-checker, untracked by design since `.scratch/` is
  gitignored).

## 9. Decisions needed from lead

1. Residual whitelist keys — add `disallowed-tools` (and possibly
   `version`/`author` at top level) or keep FM007 reporting them?
2. Approve/adjust the 3 outreach drafts before any sending (W4).
3. W4 parser fixes for the two TP-contract constructs (nested-entry
   block scalars, `/` in nested keys) — take both, or document-only?
4. CI gate policy for W4: keep fixture-tree linting non-blocking and add
   a real-skills gate, or leave as is?
