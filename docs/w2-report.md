# skill-ci — Week 2 report

Date: 2026-11-14
Branch: `feat/w2` (from main @ `c97965f`)
Scope: four deliverables — bin launchers, CJK-weighted token estimation,
rule-grouped markdown output, `skill-test` trigger prediction — plus the
5-repo scan. No LLM, no real agent runs, no dashboard, no push, no publish.

Commits (semantic split):
- `2475072` feat(lint): bin launchers (sh + cmd) for skill-lint
- `047f1dc` feat(lint): script-weighted token estimator + CJK fixture
- `e805276` feat(lint): markdown grouped by rule + `--all-instances`
- `79fee27` chore(lint): bin/skill-test launchers
- `cba5aa2` feat(test): skill-test (prompts.jsonl + BM25 + metrics)
- docs commit: README.md + this report

## 1. bin launchers (`bin/skill-lint`, `bin/skill-lint.cmd`)

- `bin/skill-lint` (POSIX sh): derives the repo root from its own location
  (`cd $(dirname $0) && pwd -P`, two levels up), verifies `src/skill_ci`
  exists, then `exec python -m skill_ci "$@"`. Works from any cwd, survives
  paths with spaces, never invokes pip, never writes to C:.
- `bin/skill-lint.cmd` (cmd.exe): same semantics via `%~dp0` root
  derivation.
- Windows/Git Bash discovery worth recording: a ';'-joined PYTHONPATH value
  is interpreted by the MSYS runtime as an already-Windows path list, and a
  POSIX root inside such a list gets mis-converted (`/d/x` -> `D:\d\x`,
  observed). The sh launcher therefore hands over the src directory via
  `cygpath -m` (mixed form `D:/...`) on MINGW/MSYS/Cygwin and uses ':' +
  POSIX form elsewhere. Tests pin the behavior with real subprocess runs.
- `.gitattributes` pins launcher line endings (sh must stay LF — a CRLF
  checkout would break POSIX sh; cmd stays CRLF).
- Tests (`tests/test_launcher.py`, 7): foreign-cwd real run, space-in-path
  target, `--help` passthrough, orphan-script failure path (exit 2 +
  "cannot locate"), LF-only guard; cmd.exe real runs for the same shapes.

## 2. CJK-weighted token estimation

`src/skill_ci/tokens.py` — one shared estimator (one口径) used by TK001/TK002,
the inventory table and skill-test's token-cost section:

| tier | chars | weight (tokens/char) |
| --- | --- | --- |
| ASCII U+0000-U+007F | 0.25 | identical to W1 `len//4` for pure ASCII, so English verdicts do not move |
| CJK: unified ideographs (+ ext A/B..F, compatibility), CJK punctuation, kana, Hangul jamo+syllables, fullwidth | 1.0 | conservative central value of ~0.7-1.5 observed in public cl100k/o200k analyses |
| other non-ASCII (Cyrillic, Greek, Arabic, emoji, ...) | 0.5 | midpoint of ~0.3-0.6 for word-piece scripts |

Weights are exact powers of two, so the weighted sum is float-exact and
`int(sum)` keeps pure-ASCII equal to `len//4` character for character (the
TK001/TK002 boundary fixtures are unchanged: 5102/15102 estimated tokens).

**"误差 ≤20%" 的落地解释 (honest framing):** offline there is no real
tokenizer available, so the ≤20% acceptance is a *deterministic
self-consistency calibration against the documented reference weights*,
NOT a measured tokenizer accuracy:

1. test-side independent recomputation (regex classifier, not the
   implementation's loop) of 7 mixed-content samples (pure EN, pure ZH,
   7:3 and 3:7 mixes, CJK punctuation-heavy, Japanese-mixed, Cyrillic) —
   every sample within 20% of the reference (in fact exactly equal, since
   both sides use the same documented weights);
2. English regression vs the W1 `len//4` baseline within 20% (exactly 0%);
3. pure-Chinese within 20% of one token per char (exact by construction);
4. the W1 bug is pinned by a test: for a Chinese body the new estimate is
   >= 3x the old `len//4` value (real correction factor ~4x);
5. **real tokenizer validation is deferred to W3 (requires network access).**
   Nothing in the docs or tests claims tokenizer-grade accuracy.

Supporting changes: Chinese trigger-hint equivalents added to DQ003
(`当用户 / 当需要 / 适用于 / 何时使用`) so a Chinese description that says
when to use the skill is not flagged; new fixture
`tests/fixtures/cjk-skill` (Chinese description with trigger guidance +
Chinese body) lints clean through all 21 rules. Side effect visible in the
anthropics scan: `claude-api` body_tokens moved 25990 -> 25995 — the ~20
non-ASCII characters (curly quotes/em-dashes) in that body now count 0.5
each instead of 0.25.

Hangul is deliberately weighted like ideographs (1.0) rather than being
dumped into "other": its real per-char cost is close to CJK ideographs, and
0.5 would have repeated the W1 under-estimation bug for Korean.

## 3. Markdown grouped by rule (+ `--all-instances`)

- Default markdown: `## Findings by rule`, one sorted section per rule_id —
  severity + instance count, catalog meaning, fix hint(s), affected
  `file:line` list with the per-instance message. Readability first.
- `--all-instances` (CLI flag) restores the W1 flat one-row-per-instance
  table.
- JSON output unchanged (instance-level, W1 contract).
- `tests/test_render.py` (10 tests) pins: grouped headings + counts,
  meaning/fix-hint/location presence, ascending rule order, instance
  completeness (each location exactly once), plural/singular counts,
  no-findings wording in both shapes, and the JSON contract with/without
  the flag.

## 4. skill-test (trigger prediction, no LLM)

Entry: `python -m skill_ci test <repo> --suite prompts.jsonl` (same
`main()` dispatch as `python -m skill_ci`), plus `bin/skill-test` /
`bin/skill-test.cmd` launchers. Flags: `--format markdown|json`,
`--out FILE`, `--threshold X` (default = documented constant).

- **prompts.jsonl contract** (README + `skill_ci.triggers` docstring):
  one object per line, exactly `{"prompt": str, "expected": skill_id |
  null | "none"}`. Malformed lines, missing keys, empty suites, and
  unknown expected ids are usage errors (exit 2) with 1-based line
  numbers.
- **Predictor**: stdlib Okapi BM25 (`skill_ci/bm25.py`, k1=1.5, b=0.75,
  Lucene-style always-positive idf) over each skill's
  name + description + when_to_use; tokenization = ASCII word tokens +
  CJK character bigrams (standard dependency-free CJK indexing).
  `BM25_TRIGGER_THRESHOLD = 1.0` (constant, documented). Fallback rule
  when scoring stays below threshold: normalized prompt contained in a
  skill's normalized metadata (unique candidate predicts; ties resolve by
  BM25). Deterministic, offline.
- **Metrics**: precision/recall, TP/FP/FN/TN. Multi-class convention
  (documented + tested): a wrong-skill trigger counts as FP *and* FN; an
  empty precision/recall denominator is defined as 1.0 (nothing wrong
  happened). Exit code 0 = suite ran (skill-test measures, it does not
  gate).
- **Traceability**: every prediction carries its top scores and the
  per-term BM25 contributions (`idf x tf-weight`), so each FP/FN names the
  exact words in the offending description that produced it.
- **Token cost section**: per-skill name/description/when_to_use token
  estimate (script-weighted) + whole-suite context load.

### Synthetic fixture results (5 skills, 20 labeled prompts)

Engineered a priori; values asserted exactly in tests:

- TP 12, FP 1, FN 1, TN 6 — precision = recall = 12/13 = 0.9231
- The FP is `export the database table to a csv file` -> `csv-to-excel`,
  evidence `'csv' (2.38)` — a rare term (df=1) whose meaning differs
  between the prompt's intent (DB export) and the skill (CSV->Excel). The
  report names the term; that is the designed "explainable FP".
- The FN is a paraphrased billing prompt with zero token overlap with
  `pdf-invoice` metadata (no stemming in the tokenizer, deliberate):
  "predicted none; no term overlap at all".
- Chinese path: both `cn-invoice` prompts (CJK bigrams) trigger correctly;
  its description costs 49 tokens vs ~32 under the old `len//4`.
- Whole-suite trigger-metadata load: 186 tokens for 5 skills.
- Edge tests: empty suite, all-null suite (precision=recall=1.0
  convention), unknown id, malformed line, missing suite/repo, `--out`.

### Real repos

None of the 5 scanned repos ships a labeled trigger suite, so per plan:
skill-test metrics come from the synthetic fixture. As a clearly-labeled
bonus, a *self-trigger sanity check* (prompt = 80-char truncation of each
skill's own description, expected = that skill) was run on all 5 repos:
**recall 1.000 on all 128 prompts** (67/67 jeffallan, 20/20 anthropics,
20/20 jwilger, 19/19 teaonly, 5/5 starslingdev). This is a retrieval
sanity bound — the prompt literally contains the index terms — not
realistic trigger quality.

## 5. Five-repo scan

Acquisition: `codeload.github.com/<owner>/<repo>/tar.gz/refs/heads/main`
(all 5 were on `main`; no master fallback needed, no fallback repo
needed). anthropics/skills reuses the W1 tarball already in `.scratch/`;
the other 4 were downloaded this week (~31 MB total). Untrusted-data
discipline unchanged: extracted into per-repo directories under
`.scratch/` (gitignored), parsed as text only, never executed or
installed, no interpreter run from inside (aggregation scripts run from
the skill-ci repo with `python -I`, paths passed as arguments).

| repo | skills | E/W/I | exit | rule hits |
| --- | ---: | --- | --- | --- |
| anthropics/skills | 20 | 2/3/9 | 1 | DQ003 x9, DQ002, DQ004, FM004, TK001, TK002 |
| Jeffallan/claude-skills | 67 | 602/2/0 | 1 | FM001 x602, SEC002 x2 |
| jwilger/agent-skills | 21 | 132/0/40 | 1 | FM001 x131, DQ003 x8, FM007 x32, FM002 |
| starslingdev/skills | 5 | 0/3/1 | 0 | TK001 x3, DQ003 |
| Teaonly/SKILL.mk | 19 | 0/0/2 | 0 | FM007 x2 |

Most interesting findings per repo:

1. **Jeffallan/claude-skills — 602 FM001, one systematic cause.** Every one
   of the 67 files uses a *flat nested mapping* under `metadata:` (author,
   version, domain, triggers, related-skills, ...). The W1 parser
   deliberately rejects nested mappings (fail-loud, documented), so each
   indented line becomes one FM001. The files are otherwise high quality:
   all descriptions carry trigger guidance, bodies 771-1893 tokens (well
   within budget), zero security issues except two SEC002 hits that are
   placeholder test passwords in Django/NestJS code examples
   (`django-expert/SKILL.md:117`, `nestjs-expert/SKILL.md:171`). W3
   candidate: support one-level nested mappings and/or per-file note
   deduplication — 602 findings for one root cause is noise.
2. **jwilger/agent-skills — the same nested-`metadata` pattern** (131
   FM001) plus 32 FM007 unknown-key hits (`effort` x19, `compatibility` x7,
   `context` x4, `argument-hint`, `user-invocable`). Useful schema signal:
   real repos extend the frontmatter schema in ways the W1 whitelist does
   not know.
3. **starslingdev/skills — token budgets**: 3 of 5 skills exceed the 5k
   recommended budget (ci-speedup 9524, sling 8268, ci-secure 7710) with
   zero errors otherwise. Cleanest exits of the "heavy" repos.
4. **Teaonly/SKILL.mk — cleanest repo**: 19 skills, 0 errors, 0 warnings,
   only 2 FM007 (`disable-model-invocation`, which is actually a real
   Claude Code frontmatter key our whitelist should probably accept).
5. **anthropics/skills — unchanged outliers**: `claude-api` DQ004 (1068-char
   description) + TK002 (25995 estimated tokens, +5 vs W1 purely from
   non-ASCII weighting); `skill-creator` TK001 (8179); the template FM004
   (by design). 9/20 descriptions still lack trigger guidance (DQ003).

## 6. Deviations from plan

1. **CJK "误差 ≤20%" is a self-consistency calibration** (documented above
   and in `tokens.py`): offline there is no tokenizer; the tests verify
   agreement with the documented reference weights and the English
   baseline, explicitly not real tokenizer accuracy. Real validation
   deferred to W3 (needs network). Not presented as measured precision.
2. **Hangul weighted 1.0 (CJK tier), not "other"**: the orchestrator note
   listed Korean as an example "other" member; the documented real-world
   cost (~1 token/char) places it with ideographs. Decision + rationale in
   `tokens.py`.
3. **skill-test CLI**: provided both forms (subcommand + `bin/skill-test`
   launchers); the plan offered either.
4. **skill-test on real repos**: no repo ships a suite (noted per plan);
   added the labeled-bonus self-trigger sanity check (recall 1.000 x5).
5. anthropics tarball reused from W1 instead of re-downloading (same
   snapshot channel, same untrusted-data handling).
6. Test/temp hygiene: W2 runs export `TEMP/TMP/TMPDIR=D:\tmp\w2` —
   Python's default temp resolution would otherwise place test scratch
   dirs on C: (Git Bash maps /tmp to C:\Users\Admin\AppData\Local\Temp).
   README documents this for future runs. All W2-era writes (repo, .scratch,
   temp) are on D:.
7. One extra `chore(lint)` commit for the skill-test launchers (they were
   written alongside the lint launchers but reference the test
   subcommand, so they land one commit before it).

## 7. Verification checklist

- bin launcher bare runs: `bin/skill-lint <target>` and
  `bin/skill-test <repo> --suite ...` succeed from a foreign cwd via sh and
  cmd (pinned by tests).
- CJK: all calibration tests green (<= 20% band, exact by construction);
  Chinese fixture lints clean.
- skill-test metrics explainable: FP names `'csv'`, FN names zero overlap.
- Tests: **97 green** (`PYTHONPATH=src python -m unittest discover -s tests`)
  — 36 W1 + 61 W2 (launcher 7, tokens 17, render 10, skill-test 27).
- `python -m compileall src` clean.
- No C-drive writes by W2 operations (repo/temp/scratch all on D:; TEMP
  redirected per deviation 6); no runtime network use; the only network
  traffic was the 4 permitted codeload tarball downloads.

## 8. Known issues / limitations

- Nested `metadata:` mappings flood FM001 on two of five real repos
  (602 + 131 findings). Fail-loud is by design, but per-file note
  aggregation or one-level nested-mapping support is the obvious W3 item.
- Frontmatter whitelist lacks keys real repos use
  (`disable-model-invocation`, `effort`, `compatibility`, ...): schema
  policy decision needed (accept / per-ecosystem profile).
- SEC002 flags placeholder passwords in example code — right severity
  (warning), but context awareness (code fences, "example"/"placeholder")
  would reduce noise.
- CJK matching uses character bigrams: single-character CJK queries do not
  match bigram-indexed descriptions; no word segmentation (zero-dep
  constraint).
- BM25 has no stemming ('convert' vs 'converts' do not match) — deliberate;
  visible in the designed FN.
- Other-tier 0.5 tokens/char underestimates emoji (~1-3 tokens each);
  documented, no corpus in scope uses them in bulk.
- skill-test measures metadata-only routing; real agent trigger behavior
  needs an LLM and stays out of scope by charter.
