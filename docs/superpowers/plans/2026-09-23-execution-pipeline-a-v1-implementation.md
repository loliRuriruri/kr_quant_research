# Pipeline A v1 — Implementation Plan

**Status:** Plan Lock (A0 companion)  
**Date:** 2026-09-23 (Asia/Seoul)  
**Design:** `docs/superpowers/specs/2026-09-23-execution-pipeline-self-healing-design.md`  
**Base:** `origin/main` @ `aaeb557a92ceaaad36af0712942fd80e6b21afa3`  
**Design branch:** `pipeline-a-v1-design`  
**Impl branch (later):** `pipeline-a-v1-impl` (or continue linearly after A0 merge policy)

This plan implements the locked design. Hard constraints **H1–H20** in the design doc are binding; do not weaken them in code.

## Global git / safety rules

- Author: `loliRuriruri <a4judas@naver.com>`
- No `git add .` / `git add -A`; stage exact paths only
- No amend, force push, main push (until explicit merge approval)
- No reset/rebase/stash of preserved local `main` @ `5ca60a8` chore
- No JEV/J3/config diffs; verify with `git diff origin/main -- config/season_jev.json config/jev_thresholds.json` empty of intentional changes
- Each task: commit → push feature branch → STOP → return TASK packet
- `$PY = C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe`
- Final A5: `& $PY -m pytest -q --tb=short` must exit 0 / 0 failed

## A0 — Design Lock (THIS TASK)

**Deliverables only:**

1. `docs/superpowers/specs/2026-09-23-execution-pipeline-self-healing-design.md` (includes H1–H20)
2. `docs/superpowers/plans/2026-09-23-execution-pipeline-a-v1-implementation.md` (this file)

**Commit subject (exact):**

```text
docs(pipeline): lock self-healing execution design v1
```

**Push:** `pipeline-a-v1-design` only.  
**Forbidden:** any production/UI/test/config code changes.  
**After A0:** STOP. Do not start A1.

## A1 — Health + Planner foundation

**Goals:**

- Add `src/kr_quant/web/pipeline_health.py` (read-only, H19/H20)
- Add `src/kr_quant/web/pipeline_plan.py` (health → plan; no execution)
- Wire read-only API stubs if needed for tests (`GET /api/pipeline/health`, `GET /api/pipeline/plan`) **without** changing smart-sync behavior yet
- Unit tests for health/planner matrix items 1–19 (design §21.1–21.2)

**Commit (exact):** `feat(pipeline): add artifact health and repair planning`  
**STOP after A1.**

## A2 — Smart Sync self-healing

**Goals:**

- Extend `job_smart_sync(..., trigger=..., mode=normal|recover)`; invalid mode fail-closed (H7)
- Artifact > ledger (H2); DART essential before Quant (H4/H5); bounded essential repair (H12)
- Post-action verify + dependent stop (H8/H9)
- Preserve scheduler `mode=normal` path; single RUNNER (H10)
- Tests matrix 20–28

**Commit (exact):** `fix(pipeline): make smart sync artifact-aware and self-healing`  
**STOP after A2.**

## A3 — Three-layer UI

**Goals:**

- Reorganize `view-run` into Layers A/B/C per design
- Demote Full Update to advanced; one daily primary CTA; repair CTA in Layer B
- Plan preview from health/plan APIs; busy disable + reason (H11); long-job warning
- Sidebar unchanged (H1); tests 29–36

**Commit (exact):** `feat(web): reorganize execution pipeline controls`  
**STOP after A3.**

## A4 — Season Last-Known-Good UX

**Goals:**

- Preserve source-change / updating guards (H13)
- Serve valid LKG with `stale_while_revalidate` metadata (H14)
- UI stale banner; switch to current when ready; no false current / no JEV trigger from LKG
- Tests 37–43

**Commit (exact):** `feat(season): serve last-known-good snapshot during refresh`  
**STOP after A4.**

## A5 — Final certification

**Goals:**

- Test-only reinforcements if gaps remain; no feature add
- Full suite green; safety checks 44–50
- Optional commit (exact): `test(pipeline): certify self-healing execution invariants`
- Empty commit forbidden if nothing to add

**STOP after A5.** No main merge until GPT verification.

## Allowed / forbidden files

See design §15. If production scope must expand beyond the allow-list: STOP and report.

## Required test matrix (from design lock)

### Health (1–10)

1. healthy artifact set → READY  
2. facts missing → REPAIR_REQUIRED  
3. facts corrupt → REPAIR_REQUIRED  
4. ledger DART success + facts missing → REPAIR_REQUIRED  
5. coverage 99.9 + facts missing → REPAIR_REQUIRED  
6. facts valid + coverage below target → PARTIAL, not MISSING  
7. prices stale → NEEDS_DAILY_UPDATE / WAITING_SOURCE as appropriate  
8. quant output missing → REPAIR_REQUIRED  
9. quant as_of older than prices → stale  
10. health scan does not mutate files/ledger  

### Planner (11–19)

11. all healthy → no destructive actions  
12. only KRX stale → REFRESH_KRX  
13. facts missing → REPAIR_DART_ESSENTIAL before REBUILD_QUANT  
14. quant stale only → REBUILD_QUANT only  
15. recover never schedules `krx-history`  
16. recover never schedules continuous DART  
17. recover never schedules Full Update  
18. normal may schedule one DART maintenance batch  
19. KIS failure does not force Quant rebuild  

### Smart Sync (20–28)

20. `trigger` independent of `mode`  
21. invalid mode fails closed  
22. DART ledger success cannot bypass missing essential artifact  
23. DART essential verify failure blocks Quant  
24. Quant success but output verify failure blocks publish  
25. KRX success but stored date stale → not verified success  
26. cancellation retains completed steps  
27. scheduler normal path unchanged  
28. RUNNER remains single-flight  

### UI (29–36)

29. one primary daily CTA  
30. repair CTA only primary inside repair layer  
31. Full Update not daily primary  
32. advanced long jobs collapsed by default  
33. busy RUNNER disables smart/recover CTA  
34. busy reason shows current job kind  
35. plan preview reflects health plan  
36. sidebar markup/navigation unchanged  

### Season (37–43)

37. current ready → current returned  
38. current unavailable + valid LKG + updating → LKG + stale metadata  
39. LKG `is_current=false`  
40. no LKG → existing pending/503  
41. corrupt LKG not served  
42. LKG does not trigger new JEV shadow evaluation  
43. current complete → LKG superseded  

### Safety (44–50)

44. JEV enabled remains false  
45. threshold config unchanged  
46. no J3 code change  
47. no factor/ranking algorithm change  
48. public publish safety not weakened  
49. no queue/multi-runner  
50. full suite exit 0 / 0 failed  

## Task return packet template

Use `=== [KR QUANT] PIPELINE A TASK <N> PACKET ===` (IDENTITY / SCOPE / CONTRACT / TESTS / STATIC / COMMIT / PUSH / AUTHOR VERDICT / STOP).

## A5 final packet

Use `=== [KR QUANT] PIPELINE A V1 FINAL CERTIFICATION PACKET ===` before any main merge request.
