"""Paper-style 4-stage CentralizedExecutor.

Per trial: 11 LLM calls total.
  R1: Leader planning (JSON subtasks)              → 1 call
  R1: Member-1/2/3 work + summarize (parallel)     → 3 calls
  R2: Leader coordination per-Member (parallel)    → 3 calls
  R2: Member-1/2/3 refine + summarize (parallel)   → 3 calls
  R3: Leader synthesis (final plan only here)      → 1 call

The output schema appears ONLY in the synthesis prompt — sub-agents return
findings, not plans. The user's styled query is injected once via the
`{task_instance}` placeholder of each agent's system prompt.
"""
from typing import Dict, List, AsyncGenerator, Tuple
import asyncio
import json
import logging
import re

from .base import BaseTopologyExecutor
from ...models import TopologyConfig, AgentConfig, ExecutionMessage
from ...llm.base import LLMMessage
from ...thinking_style.prompts_paper_style import (
    ORCHESTRATOR_PLANNING_USER,
    ORCHESTRATOR_COORDINATION_USER,
    ORCHESTRATOR_SYNTHESIS_USER,
    SUB_AGENT_START_USER,
    SUB_AGENT_COORDINATION_USER,
)

logger = logging.getLogger(__name__)


class CentralizedExecutor(BaseTopologyExecutor):
    """Paper-style centralized topology executor."""

    async def execute(
        self,
        topology: TopologyConfig,
        agents: Dict[str, AgentConfig],
        input_message: str,
        conversation_history: List[Dict[str, str]] = None,
    ) -> AsyncGenerator[ExecutionMessage, None]:
        logger.info(f"Starting centralized (paper-style) with {len(agents)} agents")

        leader = None
        members: List[AgentConfig] = []
        for agent_id in topology.agents:
            a = agents.get(agent_id)
            if not a:
                continue
            if a.topology_role == "Leader":
                leader = a
            elif a.topology_role == "Member":
                members.append(a)

        if leader is None or not members:
            yield self.create_message("system", "user", "Error: missing leader or members")
            return

        # Split input_message into reference + styled_query.
        # Orchestrator's system prompt gets BOTH (it is the only agent allowed
        # to read the user's styled request). Sub-agents' system prompt gets
        # ONLY the reference data — the styled query is intentionally hidden
        # from them so it only reaches their behaviour through the leader's
        # planning + coordination guidance (user msgs).
        reference_block, styled_query = self._split_input(input_message)
        orch_ref_and_query = self._build_orch_ref_and_query(reference_block, styled_query)
        sub_ref_only = reference_block
        leader = leader.model_copy(update={
            "instructions": leader.instructions.format(task_instance=orch_ref_and_query)
        })
        members = [
            m.model_copy(update={"instructions": m.instructions.format(task_instance=sub_ref_only)})
            for m in members
        ]

        # ============== R1: Leader planning ==============
        planning_user = ORCHESTRATOR_PLANNING_USER.format(num_agents=len(members))
        planning_response = await self.call_agent(
            leader, [LLMMessage(role="user", content=planning_user)]
        )
        yield self.create_message(
            leader.name, "all", planning_response,
            {"round": 1, "type": "planning"},
        )

        subtasks = self._parse_planning_json(planning_response, members)
        # Fallback: if JSON parse failed for some member, give them the styled query as objective.
        for m in members:
            if m.id not in subtasks:
                subtasks[m.id] = {
                    "objective": styled_query or "Build a complete trip plan candidate.",
                    "focus": "(fallback: planning JSON missing for this member)",
                }

        # ============== R1: Members work in parallel ==============
        r1_findings = await self._members_work_r1(members, subtasks)
        for mid, output in r1_findings.items():
            agent = next(m for m in members if m.id == mid)
            yield self.create_message(
                agent.name, leader.name, output,
                {"round": 1, "type": "findings"},
            )

        # ============== R2: Leader coordination per Member (parallel) ==============
        r2_guidance = await self._leader_coordinate_per_member(
            leader, members, subtasks, r1_findings
        )
        for mid, guidance in r2_guidance.items():
            target = next(m for m in members if m.id == mid)
            yield self.create_message(
                leader.name, target.name, guidance,
                {"round": 2, "type": "coordination", "target": target.name},
            )

        # ============== R2: Members refine in parallel ==============
        r2_findings = await self._members_refine_r2(members, r2_guidance, r1_findings)
        for mid, output in r2_findings.items():
            agent = next(m for m in members if m.id == mid)
            yield self.create_message(
                agent.name, leader.name, output,
                {"round": 2, "type": "findings"},
            )

        # ============== R3: Leader synthesis ==============
        all_findings_str = self._format_all_findings(members, r1_findings, r2_findings)
        synth_user = ORCHESTRATOR_SYNTHESIS_USER.format(all_findings=all_findings_str)
        final_plan = await self.call_agent(
            leader, [LLMMessage(role="user", content=synth_user)]
        )
        yield self.create_message(
            leader.name, "output", final_plan,
            {"round": 3, "type": "final_synthesis"},
        )
        logger.info("Centralized (paper-style) execution complete")

    # ---------- helpers ----------

    def _split_input(self, input_message: str) -> Tuple[str, str]:
        """Returns (reference_block, styled_query) split on '\\n\\nQuery: '."""
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
        self, response: str, members: List[AgentConfig]
    ) -> Dict[str, Dict[str, str]]:
        """Parse Leader's JSON planning output → {member_id: {objective, focus}}.
        Returns empty dict on parse failure (caller falls back per member)."""
        match = re.search(r"\{[\s\S]*\}", response)
        if not match:
            logger.warning("Planning JSON not found in Leader response")
            return {}
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            m2 = re.search(r'"subtasks"\s*:\s*(\[[\s\S]*?\])', response)
            if not m2:
                logger.warning("Planning JSON malformed and no subtasks array recoverable")
                return {}
            try:
                data = {"subtasks": json.loads(m2.group(1))}
            except json.JSONDecodeError:
                logger.warning("Planning JSON subtasks array malformed")
                return {}

        subtasks_list = data.get("subtasks") if isinstance(data, dict) else None
        if not isinstance(subtasks_list, list):
            return {}

        result: Dict[str, Dict[str, str]] = {}
        for i, sub in enumerate(subtasks_list):
            if i >= len(members):
                break
            if not isinstance(sub, dict):
                continue
            result[members[i].id] = {
                "objective": str(sub.get("objective", "")),
                "focus": str(sub.get("focus", "")),
            }
        return result

    async def _members_work_r1(
        self,
        members: List[AgentConfig],
        subtasks: Dict[str, Dict[str, str]],
    ) -> Dict[str, str]:
        async def work_one(m: AgentConfig) -> Tuple[str, str]:
            sub = subtasks.get(m.id, {"objective": "", "focus": ""})
            user_msg = SUB_AGENT_START_USER.format(
                orchestrator_objective=sub["objective"],
                orchestrator_focus=sub["focus"],
            )
            output = await self.call_agent(m, [LLMMessage(role="user", content=user_msg)])
            return m.id, output

        results = await asyncio.gather(*[work_one(m) for m in members])
        return dict(results)

    async def _leader_coordinate_per_member(
        self,
        leader: AgentConfig,
        members: List[AgentConfig],
        subtasks: Dict[str, Dict[str, str]],
        r1_findings: Dict[str, str],
    ) -> Dict[str, str]:
        async def coord_for(target: AgentConfig) -> Tuple[str, str]:
            sub = subtasks.get(target.id, {"objective": "", "focus": ""})
            team_context_parts = []
            for other in members:
                if other.id == target.id:
                    continue
                team_context_parts.append(
                    f"[{other.name}]: {r1_findings.get(other.id, '(no findings)')}"
                )
            team_context = "\n\n".join(team_context_parts) if team_context_parts else "(none)"
            user_msg = ORCHESTRATOR_COORDINATION_USER.format(
                round_num=2,
                agent_id=target.name,
                agent_objective=sub["objective"],
                agent_strategy=sub["focus"],
                agent_findings_summary=r1_findings.get(target.id, "(no findings yet)"),
                team_context=team_context,
            )
            guidance = await self.call_agent(leader, [LLMMessage(role="user", content=user_msg)])
            return target.id, guidance

        results = await asyncio.gather(*[coord_for(m) for m in members])
        return dict(results)

    async def _members_refine_r2(
        self,
        members: List[AgentConfig],
        r2_guidance: Dict[str, str],
        r1_findings: Dict[str, str],
    ) -> Dict[str, str]:
        async def refine_one(m: AgentConfig) -> Tuple[str, str]:
            user_msg = SUB_AGENT_COORDINATION_USER.format(
                round_num=2,
                orchestrator_guidance=r2_guidance.get(m.id, "(no guidance)"),
                previous_findings=r1_findings.get(m.id, "(no previous findings)"),
                peer_section="",
            )
            output = await self.call_agent(m, [LLMMessage(role="user", content=user_msg)])
            return m.id, output

        results = await asyncio.gather(*[refine_one(m) for m in members])
        return dict(results)

    def _format_all_findings(
        self,
        members: List[AgentConfig],
        r1_findings: Dict[str, str],
        r2_findings: Dict[str, str],
    ) -> str:
        parts = []
        for m in members:
            parts.append(f"=== {m.name} ===")
            parts.append(f"[Round 1 findings]\n{r1_findings.get(m.id, '(none)')}")
            parts.append(f"[Round 2 findings]\n{r2_findings.get(m.id, '(none)')}")
        return "\n\n".join(parts)
