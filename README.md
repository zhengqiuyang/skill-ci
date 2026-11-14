# skill-ci

Static CI tooling for agent-skill (SKILL.md) repositories.
Zero runtime dependencies (Python standard library only, >= 3.11), no pip
install required to run, no network at runtime, no LLM calls.

> **Status: experimental alpha.** Static text checks only — this is not a
> runtime test of a skill. The repository is a work artifact, not a
> maintained product: no outreach, no support commitment. The 10-repo scan
> in `docs/w3-report.md` is a convenience sample, not a prevalence study;
> read its "honest positioning" and known-limitations sections first.

## What's inside

| tool | what it does |
| --- | --- |
| `skill-lint` | static linter for SKILL.md: frontmatter (FM00x), description quality (DQ00x), token budget (TK001/TK002), cross-skill duplicates (DUP00x), security hints (SEC00x), structure (STRUCT00x) — 22 rules |
| `skill-test` | trigger-prediction evaluation: given a labeled `prompts.jsonl` suite, predicts which skill each prompt would trigger (deterministic BM25 + fallback) and reports precision/recall/FP/FN with per-term evidence |

## Running without installing (bin launchers)

The launchers locate the repository root relative to their own location and
put `src/` on `PYTHONPATH` — no pip, no virtualenv, nothing written outside
the report you ask for.

```sh
# POSIX sh / Git Bash (works from any working directory)
bin/skill-lint <target-repo> [--format json|markdown] [--out FILE] [--all-instances]
bin/skill-test <skill-repo> --suite prompts.jsonl [--format json|markdown] [--out FILE] [--threshold X]
```

```bat
:: Windows cmd.exe
bin\skill-lint.cmd <target-repo> --format json
bin\skill-test.cmd <skill-repo> --suite prompts.jsonl
```

Equivalent without the launchers:

```sh
PYTHONPATH=src python -m skill_ci <target-repo>
PYTHONPATH=src python -m skill_ci test <skill-repo> --suite prompts.jsonl
```

After a normal `pip install .` the console scripts `skill-lint` /
`skill-test` are also available — but the repo is usable without any
installation.

## GitHub Action

`.github/workflows/skill-ci.yml` has three entry points:

- **`example-gate` (blocking)** — lints `examples/skills`; a real error
  fails the job. This is the gate to copy into your own repository.
- **`fixture-smoke` (non-blocking)** — lints the repo's own
  `tests/fixtures` tree, which intentionally contains malformed skills.
- **`workflow_call`** — reusable with a `target` input:

```yaml
- uses: <owner>/skill-ci/.github/workflows/skill-ci.yml@main
  with:
    target: .
```

Local validation is structural only; full schema/action validation
happens when GitHub first parses the workflow.

## skill-lint

```sh
bin/skill-lint ./some-skill-repo            # markdown, grouped by rule
bin/skill-lint ./some-skill-repo --format json
bin/skill-lint ./some-skill-repo --all-instances   # flat per-instance table (W1 shape)
```

- Default markdown groups findings **by rule**: severity, instance count,
  meaning, fix hint, affected `file:line` list. `--all-instances` restores
  the flat one-row-per-finding table.
- JSON output is always instance-level.
- Exit codes: `0` scan finished without error-severity findings; `1` scan
  finished with at least one error finding; `2` usage/IO error.
- Frontmatter parser (minimal YAML subset, stdlib only): flat `key: value`
  scalars, quoted values, inline/block lists, block scalars, comments, and —
  since W3.0 — **one level of nested mapping** under any `key:` (notably
  `metadata:`). Entry keys may contain `/` (e.g. `opencode/autoinvoke`);
  entry values support plain/quoted scalars, inline/block lists and block
  scalars (`>-`/`|-`). Entry values stay plain strings (quoted values are
  stripped; no type coercion); unknown `metadata:` subkeys are allowed and
  produce no findings; top-level unknown keys stay FM007 (info). Nesting
  deeper than one level under an entry is allowed but stored as a raw
  string — reported as **FM008 (info, "nested metadata stored raw")** since
  W3.1, never FM001; stray lines, duplicate keys and anything else
  unrecognized still fail loudly as FM001.
- Known frontmatter keys = the SKILL.md spec keys (`name`, `description`,
  `when_to_use`, `allowed-tools`, `license`, `metadata`) plus the Claude
  Code frontmatter extension keys（2026-11 实测于公开 skill 仓库）:
  `effort`, `compatibility`, `context`, `argument-hint`, `user-invocable`,
  `disable-model-invocation` (`CLAUDE_CODE_EXTENSION_KEYS` in
  `src/skill_ci/rules.py`). Extension keys are accepted, not FM007; FM008
  reports any depth-2+ mapping the parser keeps as a raw string.
- Noise policy (configurable constants in `src/skill_ci/rules.py`, no
  repo-specific names):
  - **SEC002** — a credential-shaped string that is an obvious placeholder,
    documentation example or test value (`your-*`, `example*`/`xxx`
    substrings, `<...>` angle placeholders, `${...}` template references,
    `test-*`, AWS docs sample key, ...) is downgraded from warning to info
    (`SEC002_PLACEHOLDER_PREFIXES` / `SEC002_PLACEHOLDER_VALUES`);
  - **FM004** — a name/directory mismatch under a scaffold-style directory
    (`template(s)`, `example(s)`, `sample(s)`, `scaffold(s)`, `boilerplate`,
    `_template(s)`) is downgraded from warning to info
    (`FM004_TEMPLATE_DIR_MARKERS`).
- Token estimates are script-weighted (ASCII 0.25 tokens/char — identical to
  the old `len//4` for pure ASCII —, CJK ideographs/kana/Hangul/CJK
  punctuation/fullwidth 1.0, other non-ASCII 0.5); see
  `src/skill_ci/tokens.py` and `docs/w2-report.md` for the calibration
  status and its honest limits.

## skill-test

`skill-test` answers: *if skills were selected purely by their metadata
(name + description + when_to_use), how reliably would the right skill fire
for a prompt?* It uses a stdlib Okapi BM25 index (ASCII word tokens +
CJK character bigrams) with a documented score threshold and a
document-substring fallback. **No LLM, no agent runs, no network.**

### prompts.jsonl contract

One JSON object per line, exactly two keys:

```jsonl
{"prompt": "convert this csv export into an excel workbook", "expected": "csv-to-excel"}
{"prompt": "what is the capital of France", "expected": null}
{"prompt": "tell me a joke", "expected": "none"}
```

- `prompt`: required, non-empty string.
- `expected`: the skill `name` that SHOULD fire — or `null` / `"none"`
  (case-insensitive) for prompts that must fire NO skill.
- Unknown skill ids, malformed lines, or an empty suite are usage errors
  (exit 2) with 1-based line numbers.
- The contract is also documented in the `skill_ci.triggers` module
  docstring.

### Output

- trigger precision / recall, TP/FP/FN/TN (multi-class convention: a
  wrong-skill trigger counts as both FP and FN; an empty precision or
  recall denominator is defined as 1.0),
- FP list: prompt + wrongly fired skill + the exact terms that produced the
  score (BM25 idf x tf contributions) — every FP/FN is traceable to the
  words in the offending description,
- FN list: prompt + missed skill + why (best score below threshold or zero
  overlap),
- per-skill expected-vs-predicted hit distribution,
- token cost of each skill's trigger metadata (script-weighted) plus the
  whole-suite context load.

Exit codes: `0` = suite ran (skill-test measures, it does not gate);
`2` = usage/IO error.

## Development

```sh
PYTHONPATH=src python -m unittest discover -s tests   # 136 tests (W3.1)
python -m compileall src                              # must be clean
```

Layout: `src/skill_ci/` (cli, pipeline, rules, frontmatter, tokens, bm25,
triggers, render, test_cli), `tests/fixtures/` (synthetic skills incl. a
Chinese `cjk-skill`, plus a 5-skill trigger-test repo with a 20-prompt
labeled suite), `docs/` (weekly reports).

## Discipline

- No third-party runtime dependencies; stdlib only.
- No network at runtime. Third-party repos are fetched only as
  `codeload.github.com` snapshot tarballs into `.scratch/` (gitignored) and
  treated as untrusted data: parsed as text, never executed, never
  installed, no interpreter run from inside them.
- Nothing is written to the C: drive; run tests with `TMP`/`TEMP` pointed
  somewhere on `D:` if your shell maps `/tmp` to `C:`.

See `docs/w1-report.md` and `docs/w2-report.md` for scope, rule catalog,
calibration notes and known issues.
