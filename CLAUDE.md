# Topology — Prompt-Structure × MAS-Topology Alignment Study

User-side prompt 의 작성 구조 (sas / independent / centralized / hybrid) 가 MAS topology 와의 fit 을 통해 task 성능에 영향을 주는지 정량 검증. TravelPlanner 벤치마크, paper-style 4-stage orchestrator-sub-agent flow.

## Setup

- Python 3.11, OpenAI `responses.create` API, default model `gpt-5.4-mini`.
- **4 prompt styles × 4 topologies = 16 cells per task** (decentralized 제외).
- **Alignment hypothesis**: diagonal cells (style == topology) > off-diagonal in pass@1.
- Style query 출처: `backend/data/thinking_styles/prompts_v5.json` (180 task × 4 style; SAS 는 원본 TravelPlanner query fallback).
- Task source: `backend/data/travelplanner_validation.jsonl` (180 task, level easy/medium/hard 각 60).

## 4-stage flow (centralized + hybrid)

Per trial 11 LLM calls (centralized; hybrid +2 per PEER pair triggered).

| Round | Orchestrator (Leader/Manager) | Sub-agent × 3 (Member/Worker) |
|---|---|---|
| **R1 Planning** | JSON `{subtasks: [{agent_id, objective, focus}]}` (1 call) | each work + summarize_findings (parallel, 3 calls) |
| **R2 Coordination** | per-Member guidance (parallel, 3 calls) | each refine + updated findings (parallel, 3 calls) |
| **R3 Synthesis** | final plan — the ONLY place with output schema (1 call) | — |

- **Sub-agent 는 findings 만 반환** (plan 안 만듦). Output schema 는 synthesis 1 곳뿐.
- **Sub-agent system prompt 에 user's styled query 안 보임** (orchestrator 만 봄) — styled query 는 orchestrator 의 planning/coordination guidance 를 통해서만 sub-agent 행동에 mediate.
- **Hybrid PEER**: Manager 의 R2 coordination 출력에 `[PEER:Worker-i,Worker-j] <focus>` marker 있으면 그 두 Worker 가 lateral exchange 1회 (2 calls 추가). Manager 결정.

## Independent / SAS topology

새 paper-style flow 가 아닌 단순 구조:
- **Independent**: 3 Worker 가 parallel 로 user query 받아서 각자 full plan → Aggregator (LLM synthesis).
- **SAS**: Solo agent 1번 호출로 plan 직접 출력.

## Key files

| | |
|---|---|
| `backend/app/thinking_style/prompts_paper_style.py` | 8 prompt template 상수 (orchestrator base/planning/coord/synthesis + sub-agent base/start/coord/peer + hybrid coord variant) |
| `backend/app/thinking_style/topologies.py` | 5 topology preset 함수 (agent persona / role / edges) |
| `backend/app/thinking_style/loader.py` | prompts.json / prompts_v5.json loader |
| `backend/app/engine/topologies/base.py` | `BaseTopologyExecutor` + `call_agent` (LLM call → `_llm_call_log` capture) + `extract_reference` |
| `backend/app/engine/topologies/centralized.py` | 4-stage flow 구현 (orchestrator vs sub-agent task_instance 분리) |
| `backend/app/engine/topologies/hierarchical.py` | centralized 동일 + PEER (marker parse + lateral exchange) |
| `backend/app/engine/topologies/independent.py` | Worker parallel + LLM Aggregator |
| `backend/app/engine/topologies/sas.py`, `mesh.py` | SAS, Decentralized (mesh 는 main analysis 미사용) |
| `backend/app/llm/providers/openai_provider.py` | model routing (gpt-5.4-mini 는 temperature path) |
| `backend/app/benchmarks/travelplanner/{dataset,prompts,parser,evaluator,runner}.py` | TravelPlanner data load + prompt build + plan parse + scoring |
| `backend/scripts/run_thinking_style_matrix.py` | Matrix runner |
| `backend/scripts/build_comparison_html.py` | Interactive trace viewer builder (`backend/data/thinking_styles/trace_dump/comparison.html`) |
| `backend/scripts/analyze_pilot_v8.py` | 4-test analysis (Wilcoxon / Permutation / Per-row max binomial / 2-way ANOVA SS) + heatmap + summary.md |
| `backend/scripts/dump_trace_md.py` | per-trial markdown dump |

## Run an experiment

```bash
# Per-level 30 task pilot (90 task × 16 cell = 1440 trial, ~6h sequential)
python -m backend.scripts.run_thinking_style_matrix \
  --per-level-limit 30 --filter-level easy,medium,hard --seed 42 \
  --model gpt-5.4-mini --temperature 0.0 \
  --prompts backend/data/thinking_styles/prompts_v5.json \
  --styles sas,independent,centralized,hybrid \
  --topologies sas,independent,centralized,hybrid \
  --output backend/data/thinking_styles/pilot_<name>.jsonl \
  --save-trace
```

`--resume <file>` 로 중단된 run append + 이미 처리한 (task, style, topo) skip 가능.

## Trace inspection

`open backend/data/thinking_styles/trace_dump/comparison.html` → 좌측에 jsonl drop → row 클릭하면 우측에 trace 전체 (`User's query` / `System prompt` / `Round prompt` / `Output` / `Evaluation result`). Reference data 는 `[reference info omitted]` placeholder 로 strip.

## Server

| | |
|---|---|
| Host | `147.47.123.184` |
| SSH port | `2211` |
| User | `joseph423` |
| Path | `/home/joseph423/Topology/` |

수정한 backend 파일만 sync:
```bash
rsync -avzR -e 'ssh -p 2211' \
  backend/app/thinking_style/prompts_paper_style.py \
  backend/app/thinking_style/topologies.py \
  backend/app/engine/topologies/base.py \
  backend/app/engine/topologies/centralized.py \
  backend/app/engine/topologies/hierarchical.py \
  backend/scripts/run_thinking_style_matrix.py \
  backend/scripts/build_comparison_html.py \
  joseph423@147.47.123.184:/home/joseph423/Topology/
```

결과 회수: `scp -P 2211 joseph423@147.47.123.184:/home/joseph423/Topology/backend/data/thinking_styles/<file>.jsonl backend/data/thinking_styles/`

## Code conventions

- **try-catch 금지** — print/log 로 흐름 추적. 에러는 raise 되도록 두기.
- **Plan-first** — 코드 수정 전 (1) 어떤 파일을 왜 건드리는지 high-level → (2) 각 step 시작 전 file/line + before/after detail. 사용자 확인 후 진행.
- **Surgical edits** — scope 벗어난 변경 금지. 같은 기능 이름이 이미 있으면 새 이름.
- **Korean response (존댓말)** — 사용자가 반말로 써도 응답은 존댓말.
- **No code blocks by default** — 사용자 응답에서 before/after code 보여줄 때만.
- **No analogies** — 도메인 용어로 직접 설명.
