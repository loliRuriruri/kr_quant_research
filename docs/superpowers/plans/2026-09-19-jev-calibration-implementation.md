# JEV Calibration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build J2 calibration tooling that turns blind human labels and JEV probabilities into auditable, provider/model/evaluator-scoped threshold evidence without enabling production routing or mutating Quant.

**Architecture:** Keep calibration logic in a pure, deterministic Python module (`jev_calibration.py`). Treat existing season JEV shadow JSON under `data/research_snapshots/season_jev_shadow/` as read-only inputs. Store runtime labels/reports under `data/research/jev_calibration/` (gitignored). Ship tracked `config/jev_thresholds.json` with all-null heads. Separate calibration-only selection from locked holdout evaluation. CLI scripts orchestrate only; no UI in the first slice.

**Tech Stack:** Python 3.11+, pytest, stdlib `json` / `hashlib` / `argparse` / `pathlib`, existing `kr_quant.atomic_io.write_json_atomic`. No new dependencies (no pandas/sklearn for calibration).

**Spec:** `docs/superpowers/specs/2026-09-19-jev-calibration-design.md` (commit `92be125ca8a9738814eb7a7cfff55d9486d07565`)

## Execution Notes

DO NOT run all tasks continuously.

After each implementation Task:

1. commit on the implementation branch
2. push the branch (no force)
3. report evidence (commands, PASS/FAIL, SHAs)
4. **STOP for GPT/user review**

Only start the next Task after explicit approval.

Work in an isolated worktree. Do not use a dirty primary checkout. Do not `git add .` / `git add -A`. Stage exact paths only. Run `git diff --cached --check` (exit 0) before every commit.

## Global Constraints

- Keep `config/season_jev.json` `enabled=false`, `provider=typesafe_direct`, `model=jev-latest`.
- No Quant score/rank/snapshot/trade mutation.
- No automatic provider fallback.
- No automatic threshold deployment into production routing.
- Seeded thresholds start as `null` → `UNCALIBRATED` / `SHADOW_ONLY`.
- Missing threshold file / bucket / head → `SHADOW_ONLY` / `UNCALIBRATED` (never invent `0.5`).
- `0.5` remains display/normalize-only (`normalizeAnswers`); never a production default.
- Calibration identity: `provider + requested_model + evaluator_version`.
- OpenRouter alias `~typesafe/jev-latest` is not a production calibration bucket.
- `unknown` human labels are excluded from confusion metrics (not coerced to `false`).
- Division by zero in rates → JSON `null` / Python `None` (never invented `0.0`).
- Holdout metrics hidden until selection lock; evaluate exactly one locked threshold per head.
- Global JEV call caps remain authoritative; calibration tooling tests must not open a live-call bypass.
- Do not start J3 / J4 / public dashboard redesign / UI implementation in this plan.
- Modify `season_jev_shadow.py` only for the approved Task 5 safe-`state` persistence. Leave `season_jev_budget.py` unchanged.

## Review Focus

1. **Ticker / state leakage across splits** (Task 2): same ticker (or same `state_hash`) must never land in both calibration and holdout under `ticker-grouped-v1`.
2. **Same-version conflicting revisions** (Task 2): identical `annotation_version` with different canonical content must raise `REVISION_CONFLICT`, never silent overwrite via `labeled_at`.
3. **Holdout peeking before lock** (Task 4): calibration reports and open-state APIs must not expose holdout metrics; holdout evaluation requires `SELECTION_LOCKED`.
4. **Wrong bucket threshold application** (Task 1): provider / `requested_model` / `evaluator_version` mismatches must not return another bucket's threshold or any numeric fallback.
5. **Quant-forbidden fields in calibration state** (Task 2 `assert_calibration_state_clean` + Task 5 persisted/exported `state` regressions): recursive rejection of `quantReference`, `quant_reference`, `pre_entry_rank`, `grade`, `seasonality_score`, `score_breakdown`.

---

## File Map

### Planned create

| Path | Responsibility |
|---|---|
| `config/jev_thresholds.json` | Tracked all-null threshold buckets (Direct + OpenRouter pinned) |
| `src/kr_quant/research/jev_calibration.py` | Pure calibration core: lookup, identity, split, hash, metrics, sweep, reports, selection lock, holdout eval |
| `scripts/jev_calibration_export.py` | Thin argparse CLI orchestration (export / ingest / report / lock / holdout) |
| `tests/unit/test_jev_calibration.py` | All J2 unit/integration tests for the module + CLI helpers |

### Planned modify

| Path | Responsibility |
|---|---|
| `.gitignore` | Add `data/research/jev_calibration/` (Task 5) |
| `src/kr_quant/research/season_jev_shadow.py` | Task 5 minimal change: persist exact safe evaluated `state` on GENERATED / REUSED records for reproducible calibration export; keep `quant_reference` as separate side metadata; no Quant rank/score mutation |
| `tests/unit/test_season_jev_shadow.py` | Task 5 regressions for persisted `state`, Quant isolation, unchanged Quant bundle/snapshot behavior |

### Expected unchanged (first slice)

| Path | Note |
|---|---|
| `src/kr_quant/research/season_jev_budget.py` | Unchanged |
| `config/season_jev.json` | Remains `enabled=false` Direct defaults |
| `scripts/jev/*.mjs` / runners | Unchanged |
| UI / dashboard files | Out of scope |

### Runtime paths (not tracked)

```text
{settings.data_dir}/research/jev_calibration/
  labels/
  exports/
  reports/
  selections/
```

Shadow read-only source (existing):

```text
{settings.data_dir}/research_snapshots/season_jev_shadow/{generation_id}__{provider}.json
```

### Fixed public interfaces (lock these names across Tasks)

Module: `kr_quant.research.jev_calibration`

```python
BOOLEAN_HEADS: tuple[str, ...]  # exactly the 7 boolean heads; reviewClass excluded
FN_SENSITIVE_HEADS: frozenset[str]
STATUS_UNCALIBRATED = "UNCALIBRATED"
STATUS_SHADOW_ONLY = "SHADOW_ONLY"
SPLIT_CALIBRATION = "calibration"
SPLIT_HOLDOUT = "holdout"
STATE_CALIBRATION_OPEN = "CALIBRATION_OPEN"
STATE_SELECTION_LOCKED = "SELECTION_LOCKED"
STATE_HOLDOUT_REVEALED = "HOLDOUT_REVEALED"
REVIEW_ACCEPT = "ACCEPT"
REVIEW_REJECT = "REJECT"
REVIEW_COLLECT_MORE = "COLLECT_MORE_LABELS"
SPLIT_METHOD_VERSION = "ticker-grouped-v1"
HASH_METHOD_VERSION = "canonical-jsonl-v1"
SWEEP_METHOD_VERSION = "observed-boundaries-v1"

class CalibrationError(ValueError): ...
class RevisionConflict(CalibrationError): ...  # message includes REVISION_CONFLICT

def load_thresholds(path: Path) -> dict: ...
def lookup_threshold(
    config: dict,
    *,
    provider: str,
    requested_model: str,
    evaluator_version: str,
    head: str,
) -> dict:
    """Return {"status": STATUS_SHADOW_ONLY|STATUS_UNCALIBRATED|..., "threshold": float|None}.
    Missing bucket/head or null threshold => threshold None + SHADOW_ONLY/UNCALIBRATED.
    Never returns 0.5 as a fallback.
    """

def threshold_status_from_path(
    path: Path,
    *,
    provider: str,
    requested_model: str,
    evaluator_version: str,
    head: str,
) -> dict:
    """Missing file maps to SHADOW_ONLY/UNCALIBRATED with threshold None (no raise required)."""

def make_sample_id(provider: str, requested_model: str, evaluator_version: str, state_hash: str) -> str: ...
def assign_split(*, ticker: str | None, state_hash: str) -> str: ...
def assert_calibration_state_clean(state: object) -> None: ...
def validate_sample(sample: dict) -> None: ...
def select_active_rows(rows: list[dict]) -> list[dict]: ...
def dataset_hash_v1(rows: list[dict]) -> str: ...
def ensure_split_consistency(rows: list[dict]) -> None: ...

def confusion_counts(*, y_true: list[bool], y_pred: list[bool]) -> dict: ...
def rates_from_counts(counts: dict) -> dict: ...
def predict_positive(probability: float, threshold: float) -> bool: ...
def evaluate_head_at_threshold(samples: list[dict], *, head: str, threshold: float) -> dict: ...
def sweep_head_thresholds(samples: list[dict], *, head: str) -> list[dict]: ...

def build_calibration_report(*, dataset_id: str, dataset_hash: str, bucket: dict, samples: list[dict]) -> dict: ...
def calibration_metrics_hash(report: dict) -> str: ...
def support_status(samples: list[dict], *, head: str, split: str) -> dict:
    """Return valid/positive/negative/unknown counts and eligibility flags for one head+split.
    Keys: valid_count, positive_count, negative_count, unknown_count,
    analysis_eligible (>=50 valid), production_review_eligible (>=100 valid),
    insufficient_class_support (valid>=50 and (positive<10 or negative<10)).
    unknown never counts toward valid/positive/negative.
    """

def lock_selection(manifest: dict) -> dict:
    """Validate selection_basis==calibration_only, head in BOOLEAN_HEADS,
    selected_threshold in [0,1], holdout_revealed is False.
    Set state=SELECTION_LOCKED, holdout_revealed=False, selected_at.
    Compute selection_manifest_hash over canonical fields EXCLUDING selection_manifest_hash itself.
    """

def selection_manifest_hash(manifest: dict) -> str:
    """SHA-256 lowercase hex over canonical JSON of manifest with selection_manifest_hash field omitted.
    Recursive sorted keys, compact separators, ensure_ascii=False, UTF-8.
    """

def evaluate_holdout_locked(*, samples: list[dict], selection: dict) -> dict:
    """Derive head and selected_threshold ONLY from selection (locked authority).
    Reject if selection.state is not SELECTION_LOCKED (or equivalent pre-reveal locked state).
    No alternate-threshold / winner fields.
    """

def attach_review_status(holdout_report: dict, status: str) -> dict: ...
def mark_holdout_non_pristine(selection: dict) -> dict: ...

def calibration_root(settings) -> Path: ...
def export_candidates_from_shadow(
    shadow_payload: dict,
    *,
    provider: str,
    requested_model: str,
    evaluator_version: str,
) -> list[dict]:
    """Read persisted shadow results using candidate_id + state_hash + state + answers.
    Missing state => raise CalibrationError matching SHADOW_STATE_MISSING.
    Never reconstruct historical state from current snapshots.
    """

def build_blind_label_template(rows: list[dict]) -> list[dict]:
    """Human-facing blind rows: include state/evidence + human_labels placeholders + blind=True.
    Must omit jev_answers, probability, threshold, prediction, display decision, reviewClass answers.
    """

def ingest_blind_labels(*, template_rows: list[dict], internal_rows: list[dict]) -> list[dict]:
    """Join committed human labels to internal export by sample_id.
    Authoritative jev_answers come only from internal_rows; label file cannot overwrite them.
    """
```

Artifact separation (hard):

- **Internal calibration export** — may include `state`, `jev_answers`, provider/model metadata (not for blind human viewing before label commit).
- **Blind label template** — state/evidence + human label fields only; no JEV probabilities.
- **Label ingest** — joins blind template results to internal export by `sample_id`.

CLI: `scripts/jev_calibration_export.py` (argparse, matches `scripts/evaluate_season_ai.py` style)

```text
python scripts/jev_calibration_export.py export-candidates --shadow PATH --out PATH
python scripts/jev_calibration_export.py blind-template --dataset PATH --out PATH
python scripts/jev_calibration_export.py ingest-labels --labels PATH --dataset PATH --out PATH
python scripts/jev_calibration_export.py calibration-report --dataset PATH --out PATH
python scripts/jev_calibration_export.py lock-selection --manifest PATH --out PATH
python scripts/jev_calibration_export.py holdout-eval --dataset PATH --selection PATH --out PATH
```

Pytest invocation (Windows repo venv, matches prior JEV plans):

```text
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest ...
```

---


## Task 1: Threshold Config + Bucket Lookup + SHADOW_ONLY

**Interfaces:**

Consumes:

- Spec §4 threshold schema / null semantics
- Seeded buckets: Direct `typesafe_direct` / `jev-latest` / `season-jev-shadow-v1` and OpenRouter `openrouter` / `typesafe/jev-1.13` / `season-jev-shadow-v1`

Produces:

- `config/jev_thresholds.json`
- `load_thresholds`, `lookup_threshold`, `threshold_status_from_path`, status constants, `BOOLEAN_HEADS`
- unit tests proving no `0.5` fallback and full isolation (Review Focus #4)

Files:

- Create: `config/jev_thresholds.json`
- Create: `src/kr_quant/research/jev_calibration.py` (Task 1 surface; later Tasks extend same file)
- Create: `tests/unit/test_jev_calibration.py`

### Steps

- [ ] **Step 1: Write failing tests**

```python
import json
from pathlib import Path
import pytest
from kr_quant.research import jev_calibration as cal

def _seed(tmp_path: Path) -> Path:
    path = tmp_path / "jev_thresholds.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "buckets": [
            {
                "provider": "typesafe_direct",
                "requested_model": "jev-latest",
                "evaluator_version": "season-jev-shadow-v1",
                "thresholds": {h: None for h in [
                    "materialNow", "needsCurrentYearCheck", "needsNews", "needsDart",
                    "historicalConflict", "invalidationCheckNeeded", "needsDeepAI",
                ]},
            },
            {
                "provider": "openrouter",
                "requested_model": "typesafe/jev-1.13",
                "evaluator_version": "season-jev-shadow-v1",
                "thresholds": {h: None for h in [
                    "materialNow", "needsCurrentYearCheck", "needsNews", "needsDart",
                    "historicalConflict", "invalidationCheckNeeded", "needsDeepAI",
                ]},
            },
        ],
    }), encoding="utf-8")
    return path

def test_boolean_heads_match_spec():
    assert cal.BOOLEAN_HEADS == (
        "materialNow", "needsCurrentYearCheck", "needsNews", "needsDart",
        "historicalConflict", "invalidationCheckNeeded", "needsDeepAI",
    )
    assert "reviewClass" not in cal.BOOLEAN_HEADS

def test_null_threshold_is_shadow_only(tmp_path):
    cfg = cal.load_thresholds(_seed(tmp_path))
    got = cal.lookup_threshold(
        cfg, provider="typesafe_direct", requested_model="jev-latest",
        evaluator_version="season-jev-shadow-v1", head="needsDart",
    )
    assert got["threshold"] is None
    assert got["status"] in {cal.STATUS_SHADOW_ONLY, cal.STATUS_UNCALIBRATED}
    assert got["threshold"] != 0.5

def test_threshold_status_from_missing_path(tmp_path):
    got = cal.threshold_status_from_path(
        tmp_path / "nope.json",
        provider="typesafe_direct", requested_model="jev-latest",
        evaluator_version="season-jev-shadow-v1", head="needsNews",
    )
    assert got["threshold"] is None
    assert got["status"] in {cal.STATUS_SHADOW_ONLY, cal.STATUS_UNCALIBRATED}

def test_missing_bucket_head_and_mismatches(tmp_path):
    cfg = cal.load_thresholds(_seed(tmp_path))
    cases = [
        dict(provider="openrouter", requested_model="jev-latest",
             evaluator_version="season-jev-shadow-v1", head="needsDart"),
        dict(provider="typesafe_direct", requested_model="typesafe/jev-1.13",
             evaluator_version="season-jev-shadow-v1", head="needsDart"),
        dict(provider="typesafe_direct", requested_model="jev-latest",
             evaluator_version="other-eval", head="needsDart"),
        dict(provider="typesafe_direct", requested_model="jev-latest",
             evaluator_version="season-jev-shadow-v1", head="reviewClass"),
    ]
    for kwargs in cases:
        got = cal.lookup_threshold(cfg, **kwargs)
        assert got["threshold"] is None
        assert got["status"] in {cal.STATUS_SHADOW_ONLY, cal.STATUS_UNCALIBRATED}
```

Seeded tracked file content (exact buckets; all seven heads `null`):

```json
{
  "schema_version": 1,
  "buckets": [
    {
      "provider": "typesafe_direct",
      "requested_model": "jev-latest",
      "evaluator_version": "season-jev-shadow-v1",
      "thresholds": {
        "materialNow": null,
        "needsCurrentYearCheck": null,
        "needsNews": null,
        "needsDart": null,
        "historicalConflict": null,
        "invalidationCheckNeeded": null,
        "needsDeepAI": null
      }
    },
    {
      "provider": "openrouter",
      "requested_model": "typesafe/jev-1.13",
      "evaluator_version": "season-jev-shadow-v1",
      "thresholds": {
        "materialNow": null,
        "needsCurrentYearCheck": null,
        "needsNews": null,
        "needsDart": null,
        "historicalConflict": null,
        "invalidationCheckNeeded": null,
        "needsDeepAI": null
      }
    }
  ]
}
```

- [ ] **Step 2: Run RED**

```text
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_jev_calibration.py -q --tb=line -k "boolean_heads or null_threshold or missing or mismatches"
```

Expected: FAIL (module/config missing).

- [ ] **Step 3: Minimal implementation** — seed JSON + lookup helpers only; no metrics/CLI.

- [ ] **Step 4: GREEN** — same `-k` command PASS.

- [ ] **Step 5: Commit**

```text
git add config/jev_thresholds.json src/kr_quant/research/jev_calibration.py tests/unit/test_jev_calibration.py
git diff --cached --check
git commit -m "feat(jev): add calibration threshold contract"
```

STOP for review.

---

## Task 2: Sample Identity, Revisions, Split, Canonical Hash, Quant Guards

**Interfaces:**

Consumes: Task 1 constants; Spec §§7–11, 17

Produces: `make_sample_id`, `assign_split`, `select_active_rows`, `dataset_hash_v1`, `assert_calibration_state_clean`, `validate_sample`, `ensure_split_consistency`

### Steps

- [ ] **Step 1: Failing tests (Review Focus #1, #2, #5)**

```python
import hashlib
import pytest
from kr_quant.research import jev_calibration as cal

def test_sample_id_formula():
    sid = cal.make_sample_id("typesafe_direct", "jev-latest", "season-jev-shadow-v1", "abc")
    raw = b"typesafe_direct\njev-latest\nseason-jev-shadow-v1\nabc"
    assert sid == hashlib.sha256(raw).hexdigest()

def test_ticker_grouped_same_ticker_different_generation_and_state():
    a = cal.assign_split(ticker="005930", state_hash="h1")
    b = cal.assign_split(ticker="005930", state_hash="h2")
    assert a == b
    assert a in {cal.SPLIT_CALIBRATION, cal.SPLIT_HOLDOUT}

def test_missing_ticker_uses_state_hash_deterministic():
    a = cal.assign_split(ticker="", state_hash="deadbeef")
    b = cal.assign_split(ticker=None, state_hash="deadbeef")
    assert a == b
    assert cal.assign_split(ticker=None, state_hash="deadbeef") == a

def test_split_consistency_conflicts_fail_closed():
    rows = [
        {"sample_id": "s1", "ticker": "005930", "state_hash": "h1", "split": cal.SPLIT_CALIBRATION,
         "annotation_version": 1},
        {"sample_id": "s2", "ticker": "005930", "state_hash": "h2", "split": cal.SPLIT_HOLDOUT,
         "annotation_version": 1},
    ]
    with pytest.raises(cal.CalibrationError, match="SPLIT_TICKER_CONFLICT"):
        cal.ensure_split_consistency(rows)

def test_revision_conflict_same_version_different_content():
    rows = [
        {"sample_id": "s", "annotation_version": 2, "labeled_at": "2026-01-01T00:00:00Z",
         "human_labels": {"needsDart": True}},
        {"sample_id": "s", "annotation_version": 2, "labeled_at": "2026-01-02T00:00:00Z",
         "human_labels": {"needsDart": False}},
    ]
    with pytest.raises(cal.RevisionConflict, match="REVISION_CONFLICT"):
        cal.select_active_rows(rows)

def test_revision_duplicate_same_content_dedupes():
    row = {"sample_id": "s", "annotation_version": 1, "labeled_at": "2026-01-01T00:00:00Z",
           "human_labels": {"needsDart": True}}
    active = cal.select_active_rows([row, dict(row)])
    assert len(active) == 1

def test_dataset_hash_row_order_invariant():
    rows = [
        {"sample_id": "b", "annotation_version": 1, "x": 1},
        {"sample_id": "a", "annotation_version": 1, "x": 2},
    ]
    assert cal.dataset_hash_v1(rows) == cal.dataset_hash_v1(list(reversed(rows)))
    assert len(cal.dataset_hash_v1(rows)) == 64

def test_annotation_version_rejects_string():
    with pytest.raises(cal.CalibrationError):
        cal.select_active_rows([{"sample_id": "s", "annotation_version": "v1", "human_labels": {}}])

@pytest.mark.parametrize("bad", [
    {"quantReference": {}},
    {"quant_reference": {}},
    {"pre_entry_rank": 1},
    {"nested": {"grade": "A"}},
    {"score_breakdown": {}},
    {"seasonality_score": 1.0},
])
def test_forbidden_quant_fields_rejected(bad):
    with pytest.raises(ValueError):
        cal.assert_calibration_state_clean(bad)
```

- [ ] **Step 2: RED**

```text
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_jev_calibration.py -q --tb=line -k "sample_id or ticker_grouped or revision or dataset_hash or forbidden_quant or annotation_version or split_consistency"
```

- [ ] **Step 3: Implement** split/hash/revision/guards only (`ticker-grouped-v1`, `canonical-jsonl-v1`).

- [ ] **Step 4: GREEN** — same `-k` PASS.

- [ ] **Step 5: Commit**

```text
git add src/kr_quant/research/jev_calibration.py tests/unit/test_jev_calibration.py
git diff --cached --check
git commit -m "feat(jev): add deterministic calibration dataset"
```

STOP for review.

---

## Task 3: Metrics + observed-boundaries-v1 Sweep

**Interfaces:**

Consumes: Task 2 samples with `split`, `human_labels`, `jev_answers`

Produces: `confusion_counts`, `rates_from_counts`, `predict_positive`, `evaluate_head_at_threshold`, `sweep_head_thresholds`, `FN_SENSITIVE_HEADS`

### Fixture (exact)

Five rows for head `needsNews`:

| id | split | human | probability |
|----|-------|-------|-------------|
| c1 | calibration | true | 0.80 |
| c2 | calibration | true | 0.40 |
| c3 | calibration | false | 0.70 |
| c4 | calibration | unknown | 0.90 |
| h1 | holdout | true | 0.10 |

At threshold `0.50` on calibration-valid `{true,false}` rows only:

- TP=1 (c1), FP=1 (c3), TN=0, FN=1 (c2); c4 excluded as unknown
- precision = 0.5, recall = 0.5, **FPR = 1.0** (FP/(FP+TN)=1/1), FNR = 0.5, unknown_count = 1

`observed-boundaries-v1` candidates use **only calibration + valid human labels** probabilities:

```text
sorted({0.0, 1.0, 0.80, 0.40, 0.70})
```

- unknown row probability `0.90` is **not** a boundary candidate
- holdout probability `0.10` is **not** a boundary candidate

Separate zero-denominator fixture (no human negatives among included rows): FP=0, TN=0 ⇒ `FPR is None`.

### Steps

- [ ] **Step 1: Failing tests**

```python
from kr_quant.research import jev_calibration as cal

def _samples():
    def row(sid, split, lab, p):
        return {
            "sample_id": sid,
            "split": split,
            "human_labels": {"needsNews": lab},
            "jev_answers": {"needsNews": {"probability": p}},
        }
    return [
        row("c1", cal.SPLIT_CALIBRATION, True, 0.80),
        row("c2", cal.SPLIT_CALIBRATION, True, 0.40),
        row("c3", cal.SPLIT_CALIBRATION, False, 0.70),
        row("c4", cal.SPLIT_CALIBRATION, "unknown", 0.90),
        row("h1", cal.SPLIT_HOLDOUT, True, 0.10),
    ]

def test_confusion_and_rates_with_fpr_one():
    m = cal.evaluate_head_at_threshold(_samples(), head="needsNews", threshold=0.5)
    assert (m["TP"], m["FP"], m["TN"], m["FN"]) == (1, 1, 0, 1)
    assert m["precision"] == 0.5 and m["recall"] == 0.5
    assert m["FPR"] == 1.0
    assert m["FNR"] == 0.5
    assert m["unknown_count"] == 1

def test_fpr_none_when_no_human_negatives():
    rows = [
        {"sample_id": "a", "split": cal.SPLIT_CALIBRATION,
         "human_labels": {"needsNews": True}, "jev_answers": {"needsNews": {"probability": 0.9}}},
        {"sample_id": "b", "split": cal.SPLIT_CALIBRATION,
         "human_labels": {"needsNews": True}, "jev_answers": {"needsNews": {"probability": 0.1}}},
    ]
    m = cal.evaluate_head_at_threshold(rows, head="needsNews", threshold=0.5)
    assert m["FP"] == 0 and m["TN"] == 0
    assert m["FPR"] is None

def test_invalid_probability_excluded_and_counted():
    rows = _samples() + [{
        "sample_id": "c5", "split": cal.SPLIT_CALIBRATION,
        "human_labels": {"needsNews": True},
        "jev_answers": {"needsNews": {"probability": 1.5}},
    }]
    m = cal.evaluate_head_at_threshold(rows, head="needsNews", threshold=0.5)
    assert m["invalid_probability_count"] == 1

def test_sweep_uses_observed_boundaries_and_calibration_only():
    table = cal.sweep_head_thresholds(_samples(), head="needsNews")
    thresholds = [row["threshold"] for row in table]
    assert thresholds == sorted({0.0, 1.0, 0.80, 0.40, 0.70})
    assert 0.90 not in thresholds  # unknown label must not create a boundary
    assert 0.10 not in thresholds  # holdout must not create a boundary
    assert all("holdout_metrics" not in row for row in table)
    assert cal.predict_positive(0.5, 0.5) is True
    assert cal.predict_positive(0.49, 0.5) is False

def test_fn_sensitive_heads_listed_no_auto_winner_api():
    assert cal.FN_SENSITIVE_HEADS == frozenset({
        "needsDart", "historicalConflict", "invalidationCheckNeeded",
    })
    assert not hasattr(cal, "auto_select_production_threshold")
```

- [ ] **Step 2: RED**

```text
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_jev_calibration.py -q --tb=line -k "confusion or fpr_none or invalid_probability or sweep_uses or fn_sensitive"
```

- [ ] **Step 3: Implement** metrics/sweep only. Prediction rule: `probability >= threshold`. No production threshold writer.

- [ ] **Step 4: GREEN** — same `-k` PASS.

- [ ] **Step 5: Commit**

```text
git add src/kr_quant/research/jev_calibration.py tests/unit/test_jev_calibration.py
git diff --cached --check
git commit -m "feat(jev): add calibration threshold sweep"
```

STOP for review.

---

## Task 4: Calibration Report + Selection Lock + Holdout Evaluation

**Interfaces:**

Consumes: Task 3 metrics; Spec §§15–16

Produces: `build_calibration_report`, `support_status`, `lock_selection`, `selection_manifest_hash`, `evaluate_holdout_locked`, `attach_review_status`, `mark_holdout_non_pristine`, state constants

### Steps

- [ ] **Step 1: Failing tests (Review Focus #3 + support gates)**

```python
import pytest
from kr_quant.research import jev_calibration as cal

def _manifest(**over):
    base = {
        "dataset_id": "d1",
        "dataset_hash": "a" * 64,
        "bucket": {"provider": "typesafe_direct", "requested_model": "jev-latest",
                   "evaluator_version": "season-jev-shadow-v1"},
        "head": "needsDart",
        "selected_threshold": 0.73,
        "selection_basis": "calibration_only",
        "calibration_metrics_hash": "b" * 64,
        "holdout_revealed": False,
    }
    base.update(over)
    return base

def test_calibration_report_omits_holdout_metrics():
    samples = [
        {"sample_id": "c1", "split": cal.SPLIT_CALIBRATION, "ticker": "005930",
         "human_labels": {"needsDart": True},
         "jev_answers": {"needsDart": {"probability": 0.8}}, "annotation_version": 1},
        {"sample_id": "h1", "split": cal.SPLIT_HOLDOUT, "ticker": "000660",
         "human_labels": {"needsDart": False},
         "jev_answers": {"needsDart": {"probability": 0.2}}, "annotation_version": 1},
    ]
    report = cal.build_calibration_report(
        dataset_id="d1", dataset_hash="a" * 64,
        bucket={"provider": "typesafe_direct", "requested_model": "jev-latest",
                "evaluator_version": "season-jev-shadow-v1"},
        samples=samples,
    )
    assert report.get("state") == cal.STATE_CALIBRATION_OPEN
    assert "holdout_metrics" not in report
    assert "needsDart" in report.get("heads", {})

def test_holdout_before_lock_unavailable():
    with pytest.raises(cal.CalibrationError, match="CALIBRATION_OPEN|SELECTION_LOCKED|holdout"):
        cal.evaluate_holdout_locked(
            samples=[],
            selection={"state": cal.STATE_CALIBRATION_OPEN, "head": "needsDart",
                       "selected_threshold": 0.7, "holdout_revealed": False},
        )

def test_lock_selection_rejects_bad_invariants():
    with pytest.raises(cal.CalibrationError):
        cal.lock_selection(_manifest(selection_basis="holdout"))
    with pytest.raises(cal.CalibrationError):
        cal.lock_selection(_manifest(head="reviewClass"))
    with pytest.raises(cal.CalibrationError):
        cal.lock_selection(_manifest(selected_threshold=1.5))
    with pytest.raises(cal.CalibrationError):
        cal.lock_selection(_manifest(holdout_revealed=True))

def test_lock_selection_hash_excludes_own_field():
    locked = cal.lock_selection(_manifest())
    assert locked["state"] == cal.STATE_SELECTION_LOCKED
    assert locked["selection_basis"] == "calibration_only"
    assert locked["holdout_revealed"] is False
    recomputed = cal.selection_manifest_hash(locked)
    assert locked["selection_manifest_hash"] == recomputed
    # Mutating only the hash field must not change recomputation (hash excludes itself).
    mutated = dict(locked)
    mutated["selection_manifest_hash"] = "0" * 64
    assert cal.selection_manifest_hash(mutated) == recomputed

def test_holdout_eval_derives_threshold_only_from_selection():
    samples = [
        {"sample_id": "h1", "split": cal.SPLIT_HOLDOUT,
         "human_labels": {"needsDart": True}, "jev_answers": {"needsDart": {"probability": 0.9}}},
        {"sample_id": "h2", "split": cal.SPLIT_HOLDOUT,
         "human_labels": {"needsDart": False}, "jev_answers": {"needsDart": {"probability": 0.1}}},
    ]
    selection = cal.lock_selection(_manifest(selected_threshold=0.73))
    report = cal.evaluate_holdout_locked(samples=samples, selection=selection)
    assert report["selected_threshold"] == 0.73
    assert report["head"] == "needsDart"
    assert "alternative_threshold" not in report
    assert "best_threshold" not in report
    assert "winner" not in report
    assert report.get("state") == cal.STATE_HOLDOUT_REVEALED
    reviewed = cal.attach_review_status(report, cal.REVIEW_REJECT)
    assert reviewed["review_status"] == cal.REVIEW_REJECT

def test_threshold_change_after_reveal_marks_non_pristine():
    selection = {"holdout_revealed": True, "selected_threshold": 0.5, "pristine_holdout": True}
    out = cal.mark_holdout_non_pristine(selection)
    assert out["pristine_holdout"] is False

def _label_rows(n_true, n_false, n_unknown=0, split=None):
    split = split or cal.SPLIT_CALIBRATION
    rows = []
    for i in range(n_true):
        rows.append({"sample_id": f"t{i}", "split": split,
                     "human_labels": {"needsDart": True},
                     "jev_answers": {"needsDart": {"probability": 0.8}}})
    for i in range(n_false):
        rows.append({"sample_id": f"f{i}", "split": split,
                     "human_labels": {"needsDart": False},
                     "jev_answers": {"needsDart": {"probability": 0.2}}})
    for i in range(n_unknown):
        rows.append({"sample_id": f"u{i}", "split": split,
                     "human_labels": {"needsDart": "unknown"},
                     "jev_answers": {"needsDart": {"probability": 0.5}}})
    return rows

def test_support_status_gates_50_100_and_unknown_excluded():
    s49 = cal.support_status(_label_rows(25, 24, 10), head="needsDart", split=cal.SPLIT_CALIBRATION)
    assert s49["valid_count"] == 49
    assert s49["unknown_count"] == 10
    assert s49["analysis_eligible"] is False
    assert s49["production_review_eligible"] is False

    s50 = cal.support_status(_label_rows(25, 25, 5), head="needsDart", split=cal.SPLIT_CALIBRATION)
    assert s50["valid_count"] == 50
    assert s50["analysis_eligible"] is True
    assert s50["production_review_eligible"] is False

    s100 = cal.support_status(_label_rows(50, 50, 3), head="needsDart", split=cal.SPLIT_CALIBRATION)
    assert s100["valid_count"] == 100
    assert s100["production_review_eligible"] is True

def test_support_status_insufficient_class_support():
    # valid=50 but positives only 5
    rows = _label_rows(5, 45)
    st = cal.support_status(rows, head="needsDart", split=cal.SPLIT_CALIBRATION)
    assert st["valid_count"] == 50
    assert st["insufficient_class_support"] is True
```

Notes:

- `attach_review_status` records human `ACCEPT` / `REJECT` / `COLLECT_MORE_LABELS` only; it must not invent status from metric numbers.
- `support_status` / report flags never auto-enable JEV or auto-write production thresholds.
- `evaluate_holdout_locked` takes `selection` only; head/threshold come from the lock.

- [ ] **Step 2: RED**

```text
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_jev_calibration.py -q --tb=line -k "calibration_report or holdout_before or lock_selection or holdout_eval or non_pristine or support_status"
```

- [ ] **Step 3: Implement** report/lock/holdout only.

- [ ] **Step 4: GREEN** — same `-k` PASS.

- [ ] **Step 5: Commit**

```text
git add src/kr_quant/research/jev_calibration.py tests/unit/test_jev_calibration.py
git diff --cached --check
git commit -m "feat(jev): lock calibration holdout evaluation"
```

STOP for review.

---

## Task 5: Shadow State Persistence + Export / Blind Template / CLI

**Interfaces:**

Consumes: existing shadow JSON (`candidate_id`, `state_hash`, `answers`, `quant_reference`, …); Task 2–4 functions; `write_json_atomic`

Produces:

- Minimal `season_jev_shadow.py` change: persist exact safe evaluated `state` on GENERATED / REUSED records
- `calibration_root`, `export_candidates_from_shadow`, `build_blind_label_template`, `ingest_blind_labels`
- CLI `scripts/jev_calibration_export.py` with subcommands listed in Fixed interfaces
- `.gitignore` entry `data/research/jev_calibration/`

### Shadow persistence contract (actual repo today)

Persisted results today use `candidate_id` (not a top-level `id`) and do **not** currently store `state`. Task 5 adds `state` beside GENERATED/REUSED records:

- `state` = exact object that passed `assert_state_clean` for that evaluation
- `quant_reference` remains **separate** side metadata (never merged into `state`)
- Old artifacts without `state` are **not** reconstructed from current season/calendar snapshots

Export behavior for missing state:

```text
raise CalibrationError("SHADOW_STATE_MISSING")
```

(No historical backfill in J2 first slice.)

### Steps

- [ ] **Step 1: Failing tests (Review Focus #5 + blind contract)**

```python
from pathlib import Path
from types import SimpleNamespace
import pytest
from kr_quant.research import jev_calibration as cal

def test_calibration_root_under_data_research(tmp_path):
    settings = SimpleNamespace(data_dir=tmp_path / "data")
    assert cal.calibration_root(settings) == tmp_path / "data" / "research" / "jev_calibration"

def test_export_candidates_requires_persisted_state_and_candidate_id():
    shadow_payload = {
        "generation_id": "g1",
        "results": [{
            "candidate_id": "sig-1",
            "candidate_type": "season_pattern",
            "ticker": "005930",
            "state_hash": "h1",
            "state": {"identity": {"ticker": "005930"}},
            "answers": {
                "needsDart": {"probability": 0.6},
                "materialNow": {"probability": 0.5},
                "needsCurrentYearCheck": {"probability": 0.1},
                "needsNews": {"probability": 0.2},
                "historicalConflict": {"probability": 0.1},
                "invalidationCheckNeeded": {"probability": 0.1},
                "needsDeepAI": {"probability": 0.1},
                "reviewClass": {"choice": "monitor"},
            },
            "quant_reference": {"grade": "A"},
        }],
    }
    rows = cal.export_candidates_from_shadow(
        shadow_payload,
        provider="typesafe_direct",
        requested_model="jev-latest",
        evaluator_version="season-jev-shadow-v1",
    )
    assert rows[0]["candidate_id"] == "sig-1"
    assert rows[0]["sample_id"] == cal.make_sample_id(
        "typesafe_direct", "jev-latest", "season-jev-shadow-v1", "h1",
    )
    assert rows[0]["split"] in {cal.SPLIT_CALIBRATION, cal.SPLIT_HOLDOUT}
    assert "quant_reference" not in rows[0]["state"]
    cal.assert_calibration_state_clean(rows[0]["state"])
    assert "jev_answers" in rows[0]  # internal export may keep answers

def test_export_missing_state_fail_closed():
    payload = {"results": [{
        "candidate_id": "sig-1", "ticker": "005930", "state_hash": "h1",
        "answers": {},
    }]}
    with pytest.raises(cal.CalibrationError, match="SHADOW_STATE_MISSING"):
        cal.export_candidates_from_shadow(
            payload, provider="typesafe_direct", requested_model="jev-latest",
            evaluator_version="season-jev-shadow-v1",
        )

def test_export_rejects_quant_inside_state():
    with pytest.raises(ValueError):
        cal.export_candidates_from_shadow(
            {"results": [{"candidate_id": "x", "ticker": "1", "state_hash": "h",
                          "state": {"grade": "A"}, "answers": {}}]},
            provider="typesafe_direct", requested_model="jev-latest",
            evaluator_version="season-jev-shadow-v1",
        )

def test_blind_template_hides_probabilities_and_predictions():
    internal = [{
        "sample_id": "s1", "candidate_id": "sig-1", "candidate_type": "season_pattern",
        "ticker": "005930", "generation_id": "g1", "selection_date": "2026-09-01",
        "state": {"identity": {"ticker": "005930"}},
        "jev_answers": {"needsDart": {"probability": 0.9, "decision": True}},
        "annotation_version": 1,
    }]
    template = cal.build_blind_label_template(internal)
    row = template[0]
    assert row["blind"] is True
    assert "jev_answers" not in row
    assert "threshold" not in row
    assert "prediction" not in row
    assert "decision" not in row
    for head in cal.BOOLEAN_HEADS:
        assert head in row["human_labels"]
    # placeholders only — None or "unknown" (no probabilities / decisions)
    assert set(row["human_labels"].values()) <= {None, "unknown"}

def test_ingest_joins_by_sample_id_and_preserves_jev_answers():
    internal = [{
        "sample_id": "s1", "state": {"identity": {"ticker": "005930"}},
        "jev_answers": {"needsDart": {"probability": 0.9}},
        "human_labels": {},
    }]
    labeled = [{
        "sample_id": "s1", "blind": True, "annotation_version": 1,
        "human_labels": {h: False for h in cal.BOOLEAN_HEADS},
        # malicious attempt to overwrite answers:
        "jev_answers": {"needsDart": {"probability": 0.01}},
    }]
    out = cal.ingest_blind_labels(template_rows=labeled, internal_rows=internal)
    assert out[0]["jev_answers"]["needsDart"]["probability"] == 0.9
    assert out[0]["human_labels"]["needsDart"] is False

def test_ingest_rejects_unknown_sample_id_and_bad_annotation_version():
    internal = [{"sample_id": "s1", "jev_answers": {}, "state": {}}]
    with pytest.raises(cal.CalibrationError):
        cal.ingest_blind_labels(
            template_rows=[{"sample_id": "nope", "annotation_version": 1,
                            "human_labels": {h: "unknown" for h in cal.BOOLEAN_HEADS}}],
            internal_rows=internal,
        )
    with pytest.raises(cal.CalibrationError):
        cal.ingest_blind_labels(
            template_rows=[{"sample_id": "s1", "annotation_version": "v1",
                            "human_labels": {h: "unknown" for h in cal.BOOLEAN_HEADS}}],
            internal_rows=internal,
        )

def test_cli_help_lists_required_subcommands():
    import scripts.jev_calibration_export as cli
    parser = cli.build_parser()
    help_text = parser.format_help()
    for name in (
        "export-candidates", "blind-template", "ingest-labels",
        "calibration-report", "lock-selection", "holdout-eval",
    ):
        assert name in help_text
```

Also extend `tests/unit/test_season_jev_shadow.py` (RED first) with:

```python
def test_generated_record_persists_clean_state(tmp_path, monkeypatch, env_key):
    # After evaluate_generation, persisted GENERATED result contains `state`
    # that passes shadow.assert_state_clean, and quant_reference remains a sibling key.

def test_reused_record_persists_clean_state(tmp_path, monkeypatch, env_key):
    # REUSED path likewise persists `state` beside answers; no Quant fields inside state.
```

(Implement these against the existing shadow test harness patterns in that file.)

- [ ] **Step 2: RED**

```text
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_jev_calibration.py -q --tb=line -k "calibration_root or export_ or blind_ or ingest_ or cli_help"
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_season_jev_shadow.py -q --tb=line -k "persists_clean_state"
```

- [ ] **Step 3: Implement**

1. Minimal `season_jev_shadow.py` persistence of safe `state` for GENERATED/REUSED
2. Calibration export / blind-template / ingest core
3. Thin CLI (`build_parser` + subcommands)
4. `.gitignore` → `data/research/jev_calibration/`
5. Use `write_json_atomic` for outputs; **no live JEV API calls**; no historical state reconstruction

- [ ] **Step 4: GREEN** + verify ignore:

```text
git check-ignore -v data/research/jev_calibration/labels/example.jsonl
```

- [ ] **Step 5: Commit**

```text
git add src/kr_quant/research/jev_calibration.py src/kr_quant/research/season_jev_shadow.py tests/unit/test_jev_calibration.py tests/unit/test_season_jev_shadow.py scripts/jev_calibration_export.py .gitignore
git diff --cached --check
git commit -m "feat(jev): add calibration export workflow"
```

STOP for review.

---

## Task 6: Integration / Regression / Invariance

**Interfaces:**

Consumes: Tasks 1–5 artifacts

Produces: evidence that J2 tooling is green without live API calls and without mutating JEV enablement/Quant

### Steps

- [ ] **Step 1: Targeted calibration suite**

```text
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_jev_calibration.py -q --tb=line
```

Expected: PASS

- [ ] **Step 2: Adjacent JEV regression (unchanged modules)**

```text
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_season_jev_shadow.py tests/unit/test_season_jev_budget.py -q --tb=line
```

Expected: PASS

- [ ] **Step 3: Full pytest**

```text
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest -q --tb=short
```

Expected: PASS. If pre-existing failures exist unrelated to J2, document them with evidence and do not expand J2 scope to fix unrelated issues.

- [ ] **Step 4: Static invariance checks**

```text
git diff --check
git show HEAD:config/season_jev.json
git show HEAD:config/jev_thresholds.json
git grep -n "data/research/jev_calibration/" .gitignore
```

Assert:

- `season_jev.json`: `enabled=false`, `provider=typesafe_direct`, `model=jev-latest`
- `jev_thresholds.json`: both seeded buckets; seven heads all `null`
- `.gitignore` contains `data/research/jev_calibration/`
- `season_jev_budget.py` unchanged vs plan base
- `season_jev_shadow.py` diff is limited to safe `state` persistence for GENERATED/REUSED (no Quant mutation, no enablement changes)
- no J3 implementation files added
- `tests/unit/test_jev_calibration.py` contains no live network / Node runner invocation helpers

- [ ] **Step 5: Commit only if a test-only fix was required**

```text
git add tests/unit/test_jev_calibration.py
git diff --cached --check
git commit -m "test(jev): validate calibration integration"
```

If Steps 1–4 already PASS with no diff, do **not** create an empty commit; report evidence and STOP.

STOP for review.

---

## Spec Coverage Matrix

| Spec area | Task |
|---|---|
| Approach A / architecture | Header + Tasks 3–4 |
| Bucket identity / isolation | Task 1 |
| Threshold schema / null / SHADOW_ONLY | Task 1 |
| 7 heads / reviewClass excluded | Task 1 |
| Label schema / unknown handling | Tasks 2–3 |
| Blind labeling protocol | Task 5 (`build_blind_label_template` / ingest tests; no UI) |
| Sample identity / revisions | Task 2 |
| Storage + gitignore policy | Task 5 |
| ticker-grouped-v1 / leakage guards | Task 2 |
| Support gates 50/100 + class support | Task 4 (`support_status` tests) |
| Metrics / null-safe rates | Task 3 |
| observed-boundaries-v1 | Task 3 |
| Selection lock / holdout hidden / one candidate | Task 4 |
| Pristine holdout invalidation | Task 4 |
| Separated calibration vs holdout reports | Task 4 |
| canonical-jsonl-v1 | Task 2 |
| Quant isolation | Task 2 + Task 5 |
| Budget authoritative / no live test calls | Tasks 5–6 |
| Error handling | Tasks 1–4 |
| Testing strategy | All tasks + Task 6 |
| J3 handoff / non-goals | Global Constraints + Task 6 |
| UI concept | Out of implementation scope |

## Forbidden Implementation Behaviors

- Setting `enabled=true`
- Automatic threshold adoption / deployment
- Holdout peeking / publishing holdout metrics for a full shortlist before lock
- Quant mutation
- Provider winner selection
- OpenRouter alias production calibration bucket
- Automatic provider fallback
- J3 / J4 implementation
- Public dashboard redesign / calibration UI build
- New ML dependencies (pandas/sklearn/etc. for calibration)
- Live JEV API calls inside calibration unit tests

## Plan Self-Review Checklist

- Spec §§1–28 mapped in coverage matrix
- No placeholder tokens (deferred-work markers) in task steps
- Function names consistent across Tasks (`lookup_threshold`, `dataset_hash_v1`, `lock_selection`, `evaluate_holdout_locked`, …)
- Review Focus (exactly 5) each tied to named tests
- No UI / J3 / auto-deploy scope creep
- Per-task STOP/review protocol stated in Execution Notes and each Task
- Exact pytest commands use repo venv path
- Exact commit messages listed per Task
- `season_jev_shadow.py` changes limited to approved safe-`state` persistence in Task 5
