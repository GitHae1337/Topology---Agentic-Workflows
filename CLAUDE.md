# Topology — No-Code MAS Authoring Tool (Study Project)

HCI 2-phase study에서 쓰는 no-code Multi-Agent System (MAS) authoring tool 프로토타입.

## Study Design

| Phase | What | N |
|---|---|---|
| **Phase 1** | AI-only HumanEval baseline (5 토폴로지 fixed preset, 164 problems) | 5 presets |
| **Phase 2** | Novice 참가자가 직접 workflow를 빌드 → 같은 HumanEval에 평가 | 10명 × 4–6 trial = 40–60 trials |

- **Trial 단위**: 1 trial = (participant, task, topology) 조합 1개. 한 참가자가 보통 2–3개 task에서 4–6개 topology를 시도.
- **5 valid topologies**: chain, centralized, cycle, hierarchical, mesh
- **Topology 강제**: 시스템이 강제하지 않음 — 연구자가 구두로 "이번엔 centralized로 agent 4개" 지정. 실제 빌드한 결과는 auto-classifier가 라벨링.

## Stack

- **Frontend**: React 18 + TypeScript + Vite (port 3000), Zustand state, snapshot-based undo/redo
- **Backend**: FastAPI + Python 3.11 (port 8000), SQLite + aiosqlite, SSE streaming
- **LLM**: OpenAI `responses.create` API, gpt-4.1 / gpt-5

## Implemented Modules (E group — AI-Human Gap Analysis Pipeline)

### E1 — Phase 1 model selection
- `backend/app/humaneval/presets.py` — 5 preset 함수에 `model: str` 파라미터 추가
- `backend/app/humaneval/runner.py` — `run_all_presets(..., model=)` 추가
- `backend/scripts/run_humaneval.py` — `--model` CLI 인자

### E2 — Researcher panel (trial 시작)
- `frontend/src/components/ResearcherPanel/ResearcherPanel.tsx` (NEW) — TopBar 우측, Clear 버튼 왼쪽에 inline. participantId + taskId 입력 → "Start Trial" → 캔버스 리셋 + 새 sessionId
- `frontend/src/store/sessionStore.ts` — `startTrial(pid, tid)` action
- `frontend/src/store/canvasStore.ts` — `resetForNewTrial()` action (`clearCanvas`와 별개로 추가됨)
- `backend/app/api/edit_log.py` — `SessionStartRequest`에 `taskId` 추가
- `frontend/src/api/editLog.ts` — payload에 taskId 포함

### E3 — Workflow ↔ session linking
- `backend/app/api/workflows.py` — `init_db()`에 `session_id` 컬럼 idempotent migration (PRAGMA table_info 검사)
- `backend/app/models/workflow.py` — WorkflowDefinition/Create/Update에 `session_id: Optional[str]`
- `frontend/src/api/workflow.ts` — `convertToApiFormat(..., sessionId)` 추가
- `frontend/src/components/ChatPanel/ChatPanel.tsx` — workflow save 시 `useSessionStore.getState().sessionId` 가져와 같이 보냄

### E4 — Topology auto-classifier
- `backend/app/humaneval/topology_classifier.py` (NEW) — `classify_workflow(data) → (label, agent_count)`. Multi-template일 땐 가장 많은 agent 가진 template을 dominant로 선택. Unknown type은 "none"으로 fallback.

### E5 — Phase 2 evaluator
- `backend/app/humaneval/workflow_adapter.py` (NEW) — workflows.db row → `(TopologyConfig, list[AgentConfig], label, agent_count)`. label="none" 또는 dominant agent <2면 None.
- `backend/scripts/run_phase2.py` (NEW) — workflows.db에서 `session_id IS NOT NULL` row만 → 어댑터 → `run_preset_on_dataset` → `phase2_results.json`. CLI 인자: `--db`, `--output`, `--max-problems`, `--override-model` (fairness용으로 모든 agent.model 통일).

### E6 — Master table + analysis
- `backend/scripts/extract_metrics.py` (NEW) — `Log/<datetime>/session_*.json` + 동일 폴더 jsonl → `behavior_metrics.csv` (1 row/session). 컬럼: participant_id, task_id, total_edits, undo_count, redo_count, first_click_latency, session_duration, distinct_action_types, max_undo_stack_depth.
- `backend/scripts/build_master_table.py` (NEW) — Phase 1 results + Phase 2 results + behavior metrics → `master_table.csv`. source 컬럼으로 phase1/phase2 구분. session_id로 metric join.
- `backend/scripts/analyze_gap.py` (NEW) — 3-level 통계:
  - Aggregate: phase1 vs phase2 → Mann-Whitney U
  - Topology: 5 토폴로지별 Mann-Whitney U
  - Participant: (참가자, 토폴로지) paired diff → Wilcoxon signed-rank
  - Behavior correlations: pass@1 vs {duration, edits, undo, agent_count} → Spearman ρ
  - Outputs: `analysis_summary.md` + `plots/{pass_at_1_per_topology, behavior_correlations, per_participant_strip}.png`
- `backend/requirements.txt` — scipy, pandas, matplotlib 추가

## 실험 진행 순서 (operational)

### 단계 0 — 실험 시작 전 (1회)
```bash
# Phase 1 baseline 미리 (몇 시간 걸림 — 전날 밤)
python -m backend.scripts.run_humaneval --presets chain centralized cycle hierarchical mesh --model gpt-4.1
```
연구자는 (participant × task × topology) 매트릭스 스프레드시트로 별도 준비.

### 단계 1 — 참가자 한 명당 실험
```bash
# Terminal 1
cd backend && uvicorn app.main:app --reload
# Terminal 2
cd frontend && npm run dev
```
한 trial 사이클:
1. TopBar **Researcher** → participantId + taskId → **Start Trial**
2. 연구자 구두 지정: "이번엔 centralized, agent 4개"
3. 참가자 캔버스에서 빌드
4. **Save** 클릭 (DB에 sessionId와 함께 저장)
5. 다음 trial → 다시 Researcher → Start Trial (캔버스 자동 리셋)

흔한 실수: (1) Save 안 누르면 DB에 안 들어감, (2) Researcher 패널 task_id 갱신 빼먹지 말 것.

### 단계 2 — 모든 참가자 끝난 후 (1회, 자동)
```bash
python -m backend.scripts.run_phase2 --override-model gpt-4.1
python -m backend.scripts.extract_metrics
python -m backend.scripts.build_master_table
python -m backend.scripts.analyze_gap
```
최종: `backend/data/analysis/analysis_summary.md` + `plots/*.png`.

## Code Conventions (사용자 강제 규칙)

- **try-catch 금지** — print/log로 흐름 추적. 에러는 raise되도록 두기.
- **Plan-first 필수** — 코드 수정 전 (1) 어떤 파일을 왜 건드리는지 high-level → (2) 각 step 시작 전 file/line + before/after detail.
- **Surgical edits** — scope 벗어난 변경 금지. 같은 기능 이름이 이미 있으면 새 이름 (e.g. `clearCanvas` 존재해서 `resetForNewTrial` 추가).
- **Korean response** — 사용자 응답은 한국어.
- **Migration은 idempotent** — `PRAGMA table_info`로 컬럼 존재 확인 후 ALTER.

## Data layout

```
backend/
  workflows.db                       # SQLite — workflows + session_id
  data/
    phase2_results.json              # E5 output
    behavior_metrics.csv             # E6-1 output
    master_table.csv                 # E6-2 output
    analysis/
      analysis_summary.md            # E6-3 output
      plots/*.png
Log/
  <YYYY-MM-DD-HH-MM>/                # FastAPI 부팅마다 생성
    session_<sid>.json               # session_start (1개)
    edit_log_<sid>.jsonl             # 구조 편집 append-only
    events_<sid>.jsonl               # first_click / undo / redo / session_end
  phase1_humaneval/<datetime>/
    results_<preset>.json            # Phase 1 per-preset 집계
```

## Known caveats

- Phase 1 agent_count는 build_master_table에서 `3` 하드코딩 (모든 baseline preset이 3-agent).
- Researcher panel은 topology를 강제하지 않음 — 참가자가 빌드한 결과를 auto-classifier가 라벨링하는 방식. 연구자가 구두로 지정해야 함.
- workflows.db에 E3 migration 적용되려면 한 번은 FastAPI 서버를 띄워야 `session_id` 컬럼이 생김 (또는 `python -c "import asyncio; from app.api.workflows import init_db; asyncio.run(init_db())"`).
- Phase 2 evaluator는 default로 참가자가 저장한 agent.model을 그대로 씀. fair comparison 원하면 `--override-model gpt-4.1`.

## Pending / future work

(현재 Group E까지 완료. 다음 자연스러운 step 후보)
- Researcher 패널에서 topology + agent_count도 강제 선택하게 만들기 (현재는 구두 지정)
- task_id를 자유 입력 대신 dropdown으로
- master_table에 phase1 per-problem agent_count를 trials 중 첫 record에서 자동 산출 (현재 하드코딩)
- 코드 실행 외 다른 task domain 추가 (현재 HumanEval만)
