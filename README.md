# r4-claude-olympics-velara-tracker

Round 4 ("Six Versions of Ready") submission scaffold. VELARA is a
fictional medicine; this repo analyzes a fictional data pack
(`VELARA_tracker.xlsx` + `dashboard_status.csv`) and emits a single JSON
report describing findings and a per-country risk ranking.

**Status: scaffold only.** No finding or slippage rules are implemented
yet — see "What's implemented vs. stubbed" below. Rule logic will be
filled in once the data has been audited and domain leads have answered
the open questions in [NOTES/lead_refs.md](NOTES/lead_refs.md).

## Contract

The evaluation agent runs:

```
python3 solve.py <pack_dir>
```

where `<pack_dir>` is an absolute path to a folder containing
`VELARA_tracker.xlsx` and `dashboard_status.csv`. `solve.py` must print
**exactly one JSON object** to stdout and nothing else:

```json
{
  "findings": [
    {"what": "CODE", "where": "Country1;Country2", "proof": "<=200 chars"}
  ],
  "risk_ranking": [
    {
      "country": "...",
      "rank": 1,
      "slippage_days": 0,
      "impact_score": 0,
      "driver": "NONE",
      "evidence": "..."
    }
  ]
}
```

- `where` uses semicolons, never commas, and is never empty.
- `risk_ranking` contains all 30 countries exactly once, ranked 1 (worst)
  to 30. Clean countries get `slippage_days` 0, `impact_score` 0,
  `driver` `"NONE"`.
- Runtime limit: 300 seconds. Dependency install limit: 900 seconds.
- All diagnostics go to stderr.

## Running it

```bash
pip install -r requirements.txt
python3 solve.py /absolute/path/to/pack_dir
```

Currently this will run end-to-end and produce a **valid but empty**
report: no findings, and every country in the pack listed as clean in
`risk_ranking` (since no rules are implemented yet). It will never crash
with empty or malformed stdout — see "Safety nets" below.

## Repo layout

```
velara_config.json       runtime/entrypoint descriptor for the eval harness
requirements.txt         pinned deps: pandas==2.2.3, openpyxl==3.1.5
solve.py                 thin entry point (CLI arg parsing, error fallback, final print)
velara/
  __init__.py
  paths.py                resolve bundled resources + pack files relative to this package, not CWD
  reference/countries.json  static ISO 3166-1 name/alpha-2/alpha-3 reference list
  loading.py               read tracker workbook + dashboard CSV, light generic cleaning only
  countries.py             derive the actual 30-country list from the pack's own data
  changes.py               month-over-month diff detection (STUB - NotImplementedError)
  rules.py                 finding-producing rule checks + registry (STUB - empty registry)
  slippage.py              per-country slippage_days/impact_score calc (STUB - NotImplementedError)
  ranking.py               combine findings + slippage into risk_ranking, build final payload
  validation.py            structural checks against the output contract (not domain checks)
tools/
  validate_output.py       standalone contract checker for a JSON file/stdin
  audit_pack.py            read-only plain-text audit report for a pack folder
  smoke_test.sh            times solve.py, checks stdout parses, runs the validator
NOTES/
  lead_refs.md             log of questions sent to domain leads and their answers
```

## What's implemented vs. stubbed

| Module | Status |
|---|---|
| `paths.py` | Implemented. Resolves bundled files from the script's own directory. |
| `loading.py` | Implemented. Generic load + column-name normalization only. |
| `countries.py` | Implemented. Pulls country values from any column literally named "country" in the pack, canonicalizable against the static ISO reference list. |
| `changes.py` | Stub. Raises `NotImplementedError`. Row key and comparison columns unconfirmed. |
| `rules.py` | Stub. Empty `RULES` registry; `run_all_rules` returns `[]`. |
| `slippage.py` | Stub. Raises `NotImplementedError`. Slippage definition unconfirmed. |
| `ranking.py` | Partially implemented. `build_clean_ranking` works today; it does not yet incorporate real slippage once that module is filled in. |
| `validation.py` | Implemented. Structural contract checks only (shape, uniqueness, formula consistency) — not a domain correctness check. |

## solve.py safety nets

- The whole run is wrapped in try/except. On any internal error, it
  still prints one valid JSON object: every known country listed as
  unranked-clean, with the exception message recorded in each row's
  `evidence` field. The traceback goes to stderr, never stdout.
- Before printing the real (non-error) result, `validation.py` checks:
  30 unique countries, ranks 1..30 unique and complete, no empty
  `where`, no commas in `where`, `proof` <= 200 chars, and
  `impact_score == slippage_days * forecast_volume` wherever a
  per-country forecast volume is supplied. Violations are reported to
  stderr; the best-effort JSON is still printed (the agent must never
  see empty stdout).
- Country names/codes are read from the pack and from
  `velara/reference/countries.json`, never hardcoded to this
  specific dataset's countries.

## Local tooling

These are developer-only tools; they are not run by the evaluation
agent and are not part of the `solve.py` contract.

### `tools/audit_pack.py`

Read-only exploration of a pack folder. Prints sheet names, row counts,
column names, blank counts, duplicate rows, text columns that look
date-like (plus mixed-format detection within a column), low-cardinality
category values per column, and a month-to-month diff summary matched
on a row key (first of `country`, `country_code`, `code`, `market`,
`region` found in both sheets). Never modifies the pack.

```bash
python3 tools/audit_pack.py /absolute/path/to/pack_dir
```

### `tools/validate_output.py`

Checks a `solve.py`-shaped JSON payload against the output contract.
Reports pass/fail per rule.

```bash
python3 tools/validate_output.py path/to/output.json
# or
python3 solve.py /absolute/path/to/pack_dir | python3 tools/validate_output.py -
```

### `tools/smoke_test.sh`

Runs `solve.py` against a pack folder, times it against the 300s limit,
confirms stdout parses as a single JSON object, and runs
`validate_output.py` against it.

```bash
tools/smoke_test.sh /absolute/path/to/pack_dir
```

## Testing

There is no automated test suite yet (no rule logic exists to test).
Once rules and slippage logic are implemented against confirmed domain
answers, add unit tests under a `tests/` folder and wire them into
`tools/smoke_test.sh` or a separate CI step.

## Notes on country handling

The 30 countries graded on come from the data pack itself, not from any
list hardcoded in this repo. `velara/countries.py` reads whatever values
appear in a column named "country" across every tracker sheet and the
dashboard CSV. `velara/reference/countries.json` is a generic, static
ISO 3166-1 reference (name / alpha-2 / alpha-3) used only to help
canonicalize spelling/casing differences — it is not itself the source
of the 30-country list and is not specific to this dataset.
