from .base import BaseTopologyExecutor, TopologyResult
from .centralized import CentralizedExecutor
from .chain import ChainExecutor
from .hierarchical import HierarchicalExecutor
# from .p2p import P2PExecutor  # deprecated for the 5-topology study
from .mesh import MeshExecutor
# from .dag import DAGExecutor  # deprecated for the 5-topology study
from .cycle import CycleExecutor

__all__ = [
    "BaseTopologyExecutor",
    "TopologyResult",
    "CentralizedExecutor",
    "ChainExecutor",
    "HierarchicalExecutor",
    # "P2PExecutor",  # deprecated for the 5-topology study
    "MeshExecutor",
    # "DAGExecutor",  # deprecated for the 5-topology study
    "CycleExecutor",
]

# Factory function to get executor by topology type
def get_executor(topology_type: str) -> BaseTopologyExecutor:
    """Get the appropriate executor for a topology type."""
    executors = {
        "centralized": CentralizedExecutor(),
        "chain": ChainExecutor(),
        "hierarchical": HierarchicalExecutor(),
        # "p2p": P2PExecutor(),  # deprecated for the 5-topology study
        "mesh": MeshExecutor(),
        # "dag": DAGExecutor(),  # deprecated for the 5-topology study
        "cycle": CycleExecutor(),
    }
    executor = executors.get(topology_type)
    if not executor:
        raise ValueError(f"Unknown topology type: {topology_type}")
    return executor
