# skill-ci - Week 1 report (static lint MVP)

Date: 2026-11-14
Scope: static SKILL.md linting only. No dashboard, no trigger tests, no agent runs, no LLM calls, no network at runtime.

## 1. What was built

- `skill-lint <target>` CLI, source layout `src/skill_ci/`, entry points:
  - `PYTHONPATH=src python -m skill_ci <target>` (verified in tests),
  - console script `skill-lint = "skill_ci.cli:main"` declared in `pyproject.toml`
    (declared only; not pip-installed on this machine, see deviations).
- Output: Markdown (default) or JSON (`--format json`), both rendered from the
  same findings list; `--out FILE` writes to a file instead of stdout.
- Exit codes (fixed contract, enforced by tests):
  - `0` = scan completed, no error-severity findings,
  - `1` = scan completed, at least one error-severity finding,
  - `2` = usage/IO error (missing target, unreadable target, unwritable report).
- Zero runtime dependencies: standard library only, Python >= 3.11
  (tested on 3.12.10, Windows 11 / Git Bash).
- Every finding is a `Finding` dataclass with `rule_id`, `severity`
  (error/warning/info), `file` (repo-relative path), `line` (1-based; 0 =
  not line-specific, only used by STRUCT001/STRUCT002), `message`,
  optional `fix_hint`. No "feels wrong" findings: every rule is a
  deterministic check with a defined threshold.

## 2. Rule catalog (21 rules)

| rule_id | severity | meaning |
| --- | --- | --- |
| FM001 | error | frontmatter missing, unclosed, or contains lines outside the supported YAML subset |
| FM002 | error | frontmatter is missing the required `name` key |
| FM003 | error | `name` must be lowercase `[a-z0-9-]`, max 64 chars, no leading/trailing hyphen |
| FM004 | warning | `name` does not match the skill's parent directory name |
| FM005 | error | frontmatter is missing the required `description` key |
| FM006 | error | `description` must be a non-empty plain string |
| FM007 | info | unknown frontmatter key (supported: name, description, when_to_use, allowed-tools, license, metadata) |
| DQ001 | warning | description too short (< 20 chars) to trigger reliably |
| DQ002 | warning | description contains generic filler phrasing ("helps with", "various tasks", ...) |
| DQ003 | info | description lacks trigger guidance ("use when ...") |
| DQ004 | error | description exceeds the 1024-char spec limit |
| TK001 | warning | body exceeds 5000 estimated tokens |
| TK002 | error | body exceeds 15000 estimated tokens; move detail into reference files |
| DUP001 | error | skill name used by more than one SKILL.md |
| DUP002 | warning | descriptions near-identical across skills (SequenceMatcher >= 0.85) |
| DUP003 | warning | descriptions overlap heavily; triggering scope may conflict (token Jaccard >= 0.60) |
| SEC001 | warning | dangerous destructive shell command in body (rm -rf /, sudo rm, mkfs, dd if=/dev/, fork bomb, format c:, del /f, Remove-Item -Recurse -Force, ...) |
| SEC002 | warning | possible hardcoded credential/secret (AWS AKIA..., PEM private key, api_key/password/token assignments with quoted literals, ghp_ / xox- / sk- tokens) |
| SEC003 | warning | download-and-execute pattern (curl/wget pipe to shell, iex(iwr), Invoke-Expression, powershell -enc, eval $(curl)) |
| STRUCT001 | error | target directory contains no SKILL.md files |
| STRUCT002 | error | SKILL.md file could not be read |

Deliverable mapping: frontmatter checks (FM001-FM007), description quality
(DQ001-DQ004), token cost (TK001-TK002), description duplicate/conflict
(DUP001-DUP003), security hints (SEC001-SEC003).

## 3. Deterministic heuristics (documented rules, as required)

- Token estimate: `tokens = len(text) // 4` over the body (text after the
  closing `---`). Purely deterministic, English-biased; CJK text
  underestimates. Thresholds: TK001 > 5000, TK002 > 15000.
- Description similarity (DUP002): `difflib.SequenceMatcher(None, a.lower(),
  b.lower(), autojunk=False).ratio() >= 0.85` on all skill pairs.
- Description overlap (DUP003): token Jaccard over words `[a-z0-9]{3,}` of the
  lowercased descriptions, `>= 0.60`, only when DUP002 does not fire.
- Name validity (FM003): regex `^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$`, max 64.
- Frontmatter: a hand-written minimal YAML-subset parser (flat `key: value`
  scalars, quoted scalars, inline `[a, b]` lists, block lists, block scalars
  `>` / `|-` etc., indented continuation lines, full-line comments). Anything
  it does not understand becomes a parse note and a loud FM001 error - it
  never guesses and never silently misreads. No PyYAML.
- Generic-phrase list (DQ002) and trigger-hint list (DQ003) are fixed,
  versioned tuples in `src/skill_ci/rules.py`.

## 4. Scan target: anthropics/skills

Acquisition (see deviations for why this is not a `git clone`):

- `git clone --depth 1 https://github.com/anthropics/skills` failed twice
  (curl 28: could not connect to github.com:443 - github.com is unreachable
  from this machine; codeload.github.com is reachable).
- Fallback: downloaded the main-branch snapshot tarball from
  `https://codeload.github.com/anthropics/skills/tar.gz/refs/heads/main`
  (4.1 MB) and extracted it to `.scratch/anthropics-skills/` (gitignored).
- The checkout is treated as untrusted data exactly as specified: parsed as
  text only, never executed, never installed as a skill, no interpreter ever
  run from inside that directory (the only code that touched it runs from the
  skill-ci repo and reads files as text; verification used `python -I`).

Scan command:

```
PYTHONPATH=src python -m skill_ci .scratch/anthropics-skills --format markdown --out .scratch/w1-run.md
```

### Results

- Skills scanned: 20 (19 under `skills/`, plus `template/SKILL.md`)
- Findings: 2 error / 3 warning / 9 info - exit code 1
- Parser: 20/20 files parsed with zero parse notes - the minimal YAML subset
  covers the official repo's frontmatter (including `description: |-` block
  scalars) without a single FM001 false positive.
- Clean rule families: no FM001/002/003/005/006 (frontmatter structure is
  valid everywhere), no DUP001/002/003 (no duplicate names, no overlapping
  descriptions), no SEC001/002/003 (no destructive-command / secret /
  pipe-to-shell patterns).

### Findings (all 14)

| rule_id | severity | location | message |
| --- | --- | --- | --- |
| DQ004 | error | skills/claude-api/SKILL.md:3 | description is 1068 chars (> 1024 spec limit) |
| TK002 | error | skills/claude-api/SKILL.md:9 | body is ~25990 estimated tokens (> 15000 hard limit) |
| TK001 | warning | skills/skill-creator/SKILL.md:5 | body is ~8156 estimated tokens (> 5000 budget) |
| FM004 | warning | template/SKILL.md:2 | 'name' 'template-skill' does not match parent directory 'template' |
| DQ002 | warning | skills/frontend-design/SKILL.md:3 | generic filler phrase: "helps with" |
| DQ003 | info | skills/brand-guidelines/SKILL.md:3 | lacks trigger guidance |
| DQ003 | info | skills/claude-api/SKILL.md:3 | lacks trigger guidance |
| DQ003 | info | skills/frontend-design/SKILL.md:3 | lacks trigger guidance |
| DQ003 | info | skills/internal-comms/SKILL.md:3 | lacks trigger guidance |
| DQ003 | info | skills/pptx/SKILL.md:3 | lacks trigger guidance |
| DQ003 | info | skills/theme-factory/SKILL.md:3 | lacks trigger guidance |
| DQ003 | info | skills/web-artifacts-builder/SKILL.md:3 | lacks trigger guidance |
| DQ003 | info | skills/webapp-testing/SKILL.md:3 | lacks trigger guidance |
| DQ003 | info | template/SKILL.md:3 | lacks trigger guidance |

### Observations

1. `skills/claude-api/SKILL.md` is the outlier on both cost axes: 1068-char
   description (independently verified as ~1107 chars when the block scalar is
   naively joined; the linter folds continuation lines with single spaces -
   both measurements are above the 1024 limit) and a ~26k-token monolithic
   body. This is exactly the "split into progressive-loading reference files"
   case the thresholds were designed for.
2. `skills/skill-creator/SKILL.md` (8.2k tokens) is the meta-skill for writing
   skills - above the recommended budget but far from the hard limit.
3. `template/SKILL.md` name mismatch is by design (it is a scaffold), so FM004
   there is a known acceptable finding, not a bug.
4. 9 of 20 official descriptions do not contain a "use when ..." clause. That
   is why DQ003 is info severity: it flags a documentation-recommendation gap,
   not a spec violation.
5. Token sizes of the remaining skills cluster between ~0.3k and ~5k estimated
   tokens, i.e. within the recommended budget.

Raw machine-readable output of this run is kept (gitignored) at
`.scratch/w1-run.json` / `.scratch/w1-run.md`.

## 5. Test coverage

- 36 tests, all green (`PYTHONPATH=src python -m unittest discover -s tests`),
  plus `python -m compileall src` clean before every commit.
- Synthetic fixtures only (`tests/fixtures/`), one per rule: good skill
  (zero findings), no frontmatter, missing name/description, invalid name,
  tiny/generic/empty/oversized description, unknown keys, name/dir mismatch,
  duplicate name pair, near-identical description pair, overlapping
  (conflicting) description pair, dangerous-command + secret +
  download-and-execute body, and programmatically generated oversized bodies
  for TK001/TK002 boundaries (5102 and 15102 estimated tokens).
- Frontmatter parser unit tests: flat keys, block/inline lists, quoted values,
  comments, block scalars, unclosed frontmatter, unrecognized lines,
  duplicate keys, empty values.
- CLI tests: exit codes 0/1/2, markdown and JSON output shapes,
  `python -m skill_ci` subprocess verification.
- No real user data committed anywhere in the repo.

## 6. Deviations from plan

1. `git clone` was replaced by a codeload.github.com snapshot tarball:
   github.com:443 is unreachable from this machine (two `git clone` attempts
   failed in ~21s with connection errors, well inside the 2-minute abort
   rule). Content is identical to the repo main branch; security handling is
   unchanged (untrusted data, text-only parsing).
2. The `skill-lint` console script is declared in `pyproject.toml` but not
   installed (`pip install -e .` would write into the C-drive Python
   environment, violating the disk rule). `python -m skill_ci` is the verified
   entry point (covered by tests); `skill-lint` becomes available after a
   normal install.
3. Week 1 scope respected: no dashboard, no trigger tests, no agent runs, no
   LLM calls, no web UI, no publish, no push.

## 7. Known issues / limitations

- Token heuristic is English-biased; CJK-heavy skills need a different
  estimator (planned: per-script char weights).
- Cross-skill duplicate checks are O(n^2) on description pairs - fine at
  current scale (20 skills), worth indexing if a repo exceeds hundreds.
- FM004 assumes skill directory name == frontmatter name; repos using
  non-standard layouts will see warnings (by design, it caught the
  `template/` case).
- DQ002/DQ003 are list-based heuristics; they document intent, not truth -
  hence warning/info severities only.
- The YAML subset does not support nested mappings or anchors; such
  frontmatter fails loudly with FM001 (fail-loud over fail-silent).
