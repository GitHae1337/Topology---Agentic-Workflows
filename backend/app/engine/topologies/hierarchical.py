"""Paper-style 4-stage HierarchicalExecutor (= hybrid topology).

Identical to CentralizedExecutor except:
  * Coordination prompt offers an optional `[PEER:Worker-i,Worker-j] <focus>`
    trailer that the manager may append to a single member's guidance.
  * If the manager triggers PEER for some pair, both workers run an extra
    lateral-exchange call BEFORE their R2 refine. The peer outputs flow into
    the refine prompt as the {peer_section} block.

Trial cost: 11 LLM calls baseline (same as centralized); +2 per PEER pair
the manager invokes (max 6 if all three pairs are triggered).
"""
from typing import Dict, List, AsyncGenerator, Tuple, Optional, Set
import asyncio
import json
import logging
import re

from .base import BaseTopologyExecutor
from ...models import TopologyConfig, AgentConfig, ExecutionMessage
from ...llm.base import LLMMessage
from ...thinking_style.prompts_active import (
    ORCHESTRATOR_PLANNING_USER,
    ORCHESTRATOR_COORDINATION_USER_HYBRID,
    ORCHESTRATOR_SYNTHESIS_USER,
    SUB_AGENT_START_USER,
    SUB_AGENT_COORDINATION_USER,
    SUB_AGENT_PEER_USER,
)

logger = logging.getLogger(__name__)


class HierarchicalExecutor(BaseTopologyExecutor):
    """Paper-style hybrid topology executor with optional manager-triggered PEER."""

    async def execute(
        self,
        topology: TopologyConfig,
        agents: Dict[str, AgentConfig],
        input_message: str,
        conversation_history: List[Dict[str, str]] = None,
    ) -> AsyncGenerator[ExecutionMessage, None]:
        logger.info(f"Starting hierarchical (paper-style hybrid) with {len(agents)} agents")

        manager = None
        workers: List[AgentConfig] = []
        for agent_id in topology.agents:
            a = agents.get(agent_id)
            if not a:
                continue
            if a.topology_role == "Manager":
                manager = a
            elif a.topology_role == "Worker":
                workers.append(a)

        if manager is None or not workers:
            yield self.create_message("system", "user", "Error: missing manager or workers")
            return

        # Orchestrator (Manager) sees reference + styled query. Sub-agents
        # (Workers) see only the reference data — the styled query is hidden
        # from them so it can only influence behaviour via the manager's
        # planning + coordination outputs.
        reference_block, styled_query = self._split_input(input_message)
        orch_ref_and_query = self._build_orch_ref_and_query(reference_block, styled_query)
        sub_ref_only = reference_block
        manager = manager.model_copy(update={
            "instructions": manager.instructions.format(task_instance=orch_ref_and_query)
        })
        workers = [
            w.model_copy(update={"instructions": w.instructions.format(task_instance=sub_ref_only)})
            for w in workers
        ]

        # ============== R1: Manager planning ==============
        planning_user = ORCHESTRATOR_PLANNING_USER.format(num_agents=len(workers))
        planning_response = await self.call_agent(
            manager, [LLMMessage(role="user", content=planning_user)]
        )
        yield self.create_message(
            manager.name, "all", planning_response,
            {"round": 1, "type": "planning"},
        )

        subtasks = self._parse_planning_json(planning_response, workers)
        for w in workers:
            if w.id not in subtasks:
                subtasks[w.id] = {
                    "objective": styled_query or "Build a complete trip plan candidate.",
                    "focus": "(fallback: planning JSON missing for this worker)",
                }

        # ============== R1: Workers work in parallel ==============
        r1_findings = await self._workers_work_r1(workers, subtasks)
        for wid, output in r1_findings.items():
            agent = next(w for w in workers if w.id == wid)
            yield self.create_message(
                agent.name, manager.name, output,
                {"round": 1, "type": "findings"},
            )

        # ============== R2: Manager coordination per Worker (parallel) ==============
        # Each returns (guidance_text, peer_pair_or_None, peer_focus_or_None).
        coord_results = await self._manager_coordinate_per_worker(
            manager, workers, subtasks, r1_findings
        )
        # Yield the coordination broadcasts.
        for wid, (guidance, _peer_pair, _peer_focus) in coord_results.items():
            target = next(w for w in workers if w.id == wid)
            yield self.create_message(
                manager.name, target.name, guidance,
                {"round": 2, "type": "coordination", "target": target.name},
            )

        # ============== R2 (optional): PEER pairs ==============
        # Collect distinct unordered pairs the manager triggered.
        peer_pairs: Set[Tuple[str, str]] = set()
        peer_focuses: Dict[Tuple[str, str], str] = {}
        for wid, (_g, pair, focus) in coord_results.items():
            if pair is None:
                continue
            key = tuple(sorted(pair))
            peer_pairs.add(key)
            if focus and key not in peer_focuses:
                peer_focuses[key] = focus

        # peer_findings[worker_id] = list of (peer_name, peer_output_text) from this worker's PEER exchanges
        peer_findings: Dict[str, List[Tuple[str, str]]] = {w.id: [] for w in workers}
        if peer_pairs:
            peer_results = await self._run_peer_exchanges(
                workers, peer_pairs, peer_focuses, r1_findings
            )
            for (wid_a, wid_b), (out_a, out_b) in peer_results.items():
                agent_a = next(w for w in workers if w.id == wid_a)
                agent_b = next(w for w in workers if w.id == wid_b)
                peer_findings[wid_a].append((agent_b.name, out_a))
                peer_findings[wid_b].append((agent_a.name, out_b))
                yield self.create_message(
                    agent_a.name, agent_b.name, out_a,
                    {"round": 2, "type": "peer_exchange", "peer": agent_b.name},
                )
                yield self.create_message(
                    agent_b.name, agent_a.name, out_b,
                    {"round": 2, "type": "peer_exchange", "peer": agent_a.name},
                )

        # ============== R2: Workers refine in parallel (with optional peer_section) ==============
        r2_guidance_only = {wid: g for wid, (g, _p, _f) in coord_results.items()}
        r2_findings = await self._workers_refine_r2(
            workers, r2_guidance_only, r1_findings, peer_findings
        )
        for wid, output in r2_findings.items():
            agent = next(w for w in workers if w.id == wid)
            yield self.create_message(
                agent.name, manager.name, output,
                {"round": 2, "type": "findings"},
            )

        # ============== R3: Manager synthesis ==============
        all_findings_str = self._format_all_findings(
            workers, r1_findings, r2_findings, peer_findings
        )
        synth_user = ORCHESTRATOR_SYNTHESIS_USER.format(all_findings=all_findings_str)
        final_plan = await self.call_agent(
            manager, [LLMMessage(role="user", content=synth_user)]
        )
        yield self.create_message(
            manager.name, "output", final_plan,
            {"round": 3, "type": "final_synthesis"},
        )
        logger.info("Hierarchical (paper-style hybrid) execution complete")

    # ---------- helpers ----------

    def _split_input(self, input_message: str) -> Tuple[str, str]:
        marker = "\n\nQuery: "
        idx = input_message.find(marker)
        if idx == -1:
            return input_message, ""
        return input_message[:idx], input_message[idx + len(marker):]

    def _build_orch_ref_and_query(self, reference_block: str, styled_query: str) -> str:
        """Orchestrator-only task_instance: reference + styled query (the only
        agent allowed to see the user's styled request)."""
        if reference_block and styled_query:
            return f"{reference_block}\n\nUser's styled request:\n{styled_query}"
        if styled_query:
            return f"User's styled request:\n{styled_query}"
        return reference_block

    def _parse_planning_json(
        self, response: str, workers: List[AgentConfig]
    ) -> Dict[str, Dict[str, str]]:
        match = re.search(r"\{[\s\S]*\}", response)
        if not match:
            logger.warning("Planning JSON not found in Manager response")
            return {}
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            m2 = re.search(r'"subtasks"\s*:\s*(\[[\s\S]*?\])', response)
            if not m2:
                return {}
            try:
                data = {"subtasks": json.loads(m2.group(1))}
            except json.JSONDecodeError:
                return {}

        subtasks_list = data.get("subtasks") if isinstance(data, dict) else None
        if not isinstance(subtasks_list, list):
            return {}

        result: Dict[str, Dict[str, str]] = {}
        for i, sub in enumerate(subtasks_list):
            if i >= len(workers):
                break
            if not isinstance(sub, dict):
                continue
            result[workers[i].id] = {
                "objective": str(sub.get("objective", "")),
                "focus": str(sub.get("focus", "")),
            }
        return result

    def _parse_peer_marker(
        self, guidance: str, workers: List[AgentConfig]
    ) -> Tuple[Optional[Tuple[str, str]], Optional[str]]:
        """Look for a single '[PEER:Worker-i,Worker-j] <focus>' line in the
        manager's coordination output. Returns (worker_id_pair, focus_text) or
        (None, None) if absent / unparseable / not a pair of distinct workers."""
        pat = re.compile(r"\[PEER:\s*([^\]]+)\]\s*(.+?)(?:\n|$)", re.IGNORECASE)
        m = pat.search(guidance)
        if not m:
            return None, None
        names = [n.strip() for n in m.group(1).split(",")]
        focus = m.group(2).strip()
        if len(names) < 2:
            return None, None
        by_name = {w.name.lower(): w.id for w in workers}
        wid_a = by_name.get(names[0].lower())
        wid_b = by_name.get(names[1].lower())
        if not wid_a or not wid_b or wid_a == wid_b:
            return None, None
        return (wid_a, wid_b), focus

    async def _workers_work_r1(
        self,
        workers: List[AgentConfig],
        subtasks: Dict[str, Dict[str, str]],
    ) -> Dict[str, str]:
        async def work_one(w: AgentConfig) -> Tuple[str, str]:
            sub = subtasks.get(w.id, {"objective": "", "focus": ""})
            user_msg = SUB_AGENT_START_USER.format(
                orchestrator_objective=sub["objective"],
                orchestrator_focus=sub["focus"],
            )
            output = await self.call_agent(w, [LLMMessage(role="user", content=user_msg)])
            return w.id, output

        results = await asyncio.gather(*[work_one(w) for w in workers])
        return dict(results)

    async def _manager_coordinate_per_worker(
        self,
        manager: AgentConfig,
        workers: List[AgentConfig],
        subtasks: Dict[str, Dict[str, str]],
        r1_findings: Dict[str, str],
    ) -> Dict[str, Tuple[str, Optional[Tuple[str, str]], Optional[str]]]:
        """Returns {worker_id: (guidance_text, optional_peer_pair, optional_peer_focus)}."""
        async def coord_for(target: AgentConfig) -> Tuple[str, Tuple[str, Optional[Tuple[str, str]], Optional[str]]]:
            sub = subtasks.get(target.id, {"objective": "", "focus": ""})
            team_context_parts = []
            for other in workers:
                if other.id == target.id:
                    continue
                team_context_parts.append(
                    f"[{other.name}]: {r1_findings.get(other.id, '(no findings)')}"
                )
            team_context = "\n\n".join(team_context_parts) if team_context_parts else "(none)"
            user_msg = ORCHESTRATOR_COORDINATION_USER_HYBRID.format(
                round_num=2,
                agent_id=target.name,
                agent_objective=sub["objective"],
                agent_strategy=sub["focus"],
                agent_findings_summary=r1_findings.get(target.id, "(no findings yet)"),
                team_context=team_context,
            )
            guidance = await self.call_agent(manager, [LLMMessage(role="user", content=user_msg)])
            peer_pair, peer_focus = self._parse_peer_marker(guidance, workers)
            return target.id, (guidance, peer_pair, peer_focus)

        results = await asyncio.gather(*[coord_for(w) for w in workers])
        return dict(results)

    async def _run_peer_exchanges(
        self,
        workers: List[AgentConfig],
        peer_pairs: Set[Tuple[str, str]],
        peer_focuses: Dict[Tuple[str, str], str],
        r1_findings: Dict[str, str],
    ) -> Dict[Tuple[str, str], Tuple[str, str]]:
        """Run each peer pair as 2 parallel calls (one per worker)."""
        by_id = {w.id: w for w in workers}

        async def one_exchange(pair: Tuple[str, str]) -> Tuple[Tuple[str, str], Tuple[str, str]]:
            wid_a, wid_b = pair
            agent_a = by_id[wid_a]
            agent_b = by_id[wid_b]
            focus = peer_focuses.get(pair, "")

            async def one_side(self_agent: AgentConfig, peer_agent: AgentConfig) -> str:
                user_msg = SUB_AGENT_PEER_USER.format(
                    peer_agent_id=peer_agent.name,
                    peer_focus=focus,
                    own_findings=r1_findings.get(self_agent.id, "(no findings)"),
                    peer_findings=r1_findings.get(peer_agent.id, "(no findings)"),
                )
                return await self.call_agent(self_agent, [LLMMessage(role="user", content=user_msg)])

            out_a, out_b = await asyncio.gather(
                one_side(agent_a, agent_b),
                one_side(agent_b, agent_a),
            )
            return pair, (out_a, out_b)

        results = await asyncio.gather(*[one_exchange(p) for p in peer_pairs])
        return dict(results)

    async def _workers_refine_r2(
        self,
        workers: List[AgentConfig],
        r2_guidance: Dict[str, str],
        r1_findings: Dict[str, str],
        peer_findings: Dict[str, List[Tuple[str, str]]],
    ) -> Dict[str, str]:
        async def refine_one(w: AgentConfig) -> Tuple[str, str]:
            peer_list = peer_findings.get(w.id, [])
            if peer_list:
                peer_section = "\nPeer exchange outcomes:\n" + "\n\n".join(
                    f"[Exchange with {peer_name}]:\n{peer_out}"
                    for peer_name, peer_out in peer_list
                ) + "\n"
            else:
                peer_section = ""
            user_msg = SUB_AGENT_COORDINATION_USER.format(
                round_num=2,
                orchestrator_guidance=r2_guidance.get(w.id, "(no guidance)"),
                previous_findings=r1_findings.get(w.id, "(no previous findings)"),
                peer_section=peer_section,
            )
            output = await self.call_agent(w, [LLMMessage(role="user", content=user_msg)])
            return w.id, output

        results = await asyncio.gather(*[refine_one(w) for w in workers])
        return dict(results)

    def _format_all_findings(
        self,
        workers: List[AgentConfig],
        r1_findings: Dict[str, str],
        r2_findings: Dict[str, str],
        peer_findings: Dict[str, List[Tuple[str, str]]],
    ) -> str:
        parts = []
        for w in workers:
            parts.append(f"=== {w.name} ===")
            parts.append(f"[Round 1 findings]\n{r1_findings.get(w.id, '(none)')}")
            for peer_name, peer_out in peer_findings.get(w.id, []):
                parts.append(f"[Peer exchange with {peer_name}]\n{peer_out}")
            parts.append(f"[Round 2 findings]\n{r2_findings.get(w.id, '(none)')}")
        return "\n\n".join(parts)
