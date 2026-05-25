"""Paper-style IndependentExecutor.

Per trial: 4 LLM calls total.
  - 3 Workers in parallel — each receives the user's task (reference + styled
    query) via the system prompt's `{task_instance}`, and a minimal start
    message ("Objective: Solve the task completely on your own. Begin!").
    No inter-worker communication.
  - 1 Aggregator — synthesizes the 3 worker plans into one final plan.

Framing follows ybkim95/agent-scaling (subagent.yaml + multiagent_independent.py),
adapted for our no-tools single-shot setup: workers each produce a full plan
(output schema lives in their system prompt) rather than iterating with tools.
"""
from typing import Dict, List, AsyncGenerator, Tuple
import asyncio
import logging

from .base import BaseTopologyExecutor
from ...models import TopologyConfig, AgentConfig, ExecutionMessage
from ...llm.base import LLMMessage
from ...thinking_style.prompts_paper_style import (
    INDEPENDENT_WORKER_START_USER,
    INDEPENDENT_AGGREGATOR_SYNTHESIS_USER,
)

logger = logging.getLogger(__name__)


class IndependentExecutor(BaseTopologyExecutor):
    """Paper-style Independent topology: N parallel workers + 1 aggregator."""

    async def execute(
        self,
        topology: TopologyConfig,
        agents: Dict[str, AgentConfig],
        input_message: str,
        conversation_history: List[Dict[str, str]] = None,
    ) -> AsyncGenerator[ExecutionMessage, None]:
        logger.info(f"Starting Independent (paper-style) with {len(agents)} agent(s)")

        workers: List[AgentConfig] = []
        aggregator: AgentConfig | None = None
        for agent_id in topology.agents:
            a = agents.get(agent_id)
            if not a:
                continue
            if a.topology_role == "Aggregator":
                aggregator = a
            elif a.topology_role == "Worker":
                workers.append(a)

        if not workers or aggregator is None:
            logger.error("Independent topology requires workers + 1 aggregator")
            yield self.create_message("system", "user", "Error: workers/aggregator missing")
            return

        # task_instance = reference + styled query (both workers and aggregator
        # see the full user task; there's no orchestrator to mediate).
        reference_block, styled_query = self._split_input(input_message)
        task_instance = self._build_task_instance(reference_block, styled_query)
        workers = [
            w.model_copy(update={"instructions": w.instructions.format(task_instance=task_instance)})
            for w in workers
        ]
        aggregator = aggregator.model_copy(update={
            "instructions": aggregator.instructions.format(task_instance=task_instance)
        })

        # ---------------- Workers in parallel ----------------
        async def call_worker(idx: int, worker: AgentConfig) -> Tuple[str, str]:
            user_msg = INDEPENDENT_WORKER_START_USER.format(worker_index=idx + 1)
            out = await self.call_agent(worker, [LLMMessage(role="user", content=user_msg)])
            logger.info(f"Worker {worker.name} produced {len(out)} chars")
            return worker.id, out

        worker_results: List[Tuple[str, str]] = await asyncio.gather(
            *[call_worker(i, w) for i, w in enumerate(workers)]
        )

        for worker_id, content in worker_results:
            worker = next(w for w in workers if w.id == worker_id)
            yield self.create_message(
                from_agent=worker.name,
                to_agent=aggregator.name,
                content=content,
                metadata={"role": "worker_output"},
            )

        # ---------------- Aggregator synthesis ----------------
        worker_plans_block = "\n\n".join(
            f"=== {next(w for w in workers if w.id == wid).name} ===\n{content}"
            for wid, content in worker_results
        )
        agg_user = INDEPENDENT_AGGREGATOR_SYNTHESIS_USER.format(
            worker_plans_block=worker_plans_block
        )
        logger.info(f"Calling Aggregator {aggregator.name}")
        final = await self.call_agent(
            aggregator, [LLMMessage(role="user", content=agg_user)]
        )
        logger.info(f"Aggregator produced {len(final)} chars")
        yield self.create_message(
            from_agent=aggregator.name,
            to_agent="user",
            content=final,
            metadata={"role": "final"},
        )

    # ---------- helpers ----------

    def _split_input(self, input_message: str) -> Tuple[str, str]:
        marker = "\n\nQuery: "
        idx = input_message.find(marker)
        if idx == -1:
            return input_message, ""
        return input_message[:idx], input_message[idx + len(marker):]

    def _build_task_instance(self, reference_block: str, styled_query: str) -> str:
        if reference_block and styled_query:
            return f"{reference_block}\n\nUser's styled request:\n{styled_query}"
        if styled_query:
            return f"User's styled request:\n{styled_query}"
        return reference_block
