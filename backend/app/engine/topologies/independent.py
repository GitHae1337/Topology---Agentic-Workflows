from typing import Dict, List, AsyncGenerator, Tuple
import asyncio
import logging

from .base import BaseTopologyExecutor
from ...models import TopologyConfig, AgentConfig, ExecutionMessage
from ...llm.base import LLMMessage

logger = logging.getLogger(__name__)


class IndependentExecutor(BaseTopologyExecutor):
    """
    Independent MAS executor.

    PDF arXiv:2512.08296: A={a_1,...,a_n}, C=∅, Ω=aggregator. N workers run
    in parallel on identical input with no inter-agent communication; one
    aggregator agent then synthesizes their outputs into a final answer.
    The aggregator is part of the Independent topology by definition — it
    realises Ω, the synthesis-only output function.
    """

    async def execute(
        self,
        topology: TopologyConfig,
        agents: Dict[str, AgentConfig],
        input_message: str,
        conversation_history: List[Dict[str, str]] = None,
    ) -> AsyncGenerator[ExecutionMessage, None]:
        logger.info(f"Starting Independent execution with {len(agents)} agent(s)")

        workers: List[AgentConfig] = []
        aggregator: AgentConfig | None = None
        for agent_id in topology.agents:
            agent = agents.get(agent_id)
            if not agent:
                continue
            if agent.topology_role == "Aggregator":
                aggregator = agent
            elif agent.topology_role == "Worker":
                workers.append(agent)

        if not workers:
            logger.error("Independent topology requires at least one Worker")
            yield self.create_message("system", "user", "Error: no Worker agents")
            return
        if not aggregator:
            logger.error("Independent topology requires one Aggregator (Ω)")
            yield self.create_message("system", "user", "Error: no Aggregator agent")
            return

        logger.info(
            f"Workers: {[w.name for w in workers]}, Aggregator: {aggregator.name}"
        )

        # ------------------------------------------------------------------
        # 1. Parallel worker calls — each sees ONLY the user input (C=∅)
        # ------------------------------------------------------------------
        user_msg = self.format_user_prompt_with_task(input_message)

        async def call_worker(worker: AgentConfig) -> Tuple[str, str]:
            logger.info(f"Calling Worker {worker.name}")
            out = await self.call_agent(
                worker,
                [LLMMessage(role="user", content=user_msg)],
            )
            logger.info(f"Worker {worker.name} produced {len(out)} chars")
            return worker.id, out

        worker_results: List[Tuple[str, str]] = await asyncio.gather(
            *[call_worker(w) for w in workers]
        )

        for worker_id, content in worker_results:
            yield self.create_message(
                from_agent=worker_id,
                to_agent=aggregator.id,
                content=content,
                metadata={"role": "worker_output"},
            )

        # ------------------------------------------------------------------
        # 2. Aggregator synthesizes worker outputs (Ω = synthesis-only)
        # ------------------------------------------------------------------
        worker_block = "\n\n".join(
            f"=== {agents[wid].name} ===\n{content}" for wid, content in worker_results
        )
        agg_prompt = (
            f"Original task:\n{input_message}\n\n"
            f"You are the Aggregator. The following are independent plans from "
            f"{len(workers)} workers. Synthesize them into ONE final plan that "
            f"satisfies every constraint, in the required output format. "
            f"Resolve disagreements yourself; do not invent items absent from all "
            f"workers' outputs.\n\n"
            f"Worker plans:\n{worker_block}"
        )
        logger.info(f"Calling Aggregator {aggregator.name}")
        final = await self.call_agent(
            aggregator,
            [LLMMessage(role="user", content=agg_prompt)],
        )
        logger.info(f"Aggregator produced {len(final)} chars")

        yield self.create_message(
            from_agent=aggregator.id,
            to_agent="user",
            content=final,
            metadata={"role": "final"},
        )
