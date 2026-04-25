from .base import BaseTopologyExecutor, TopologyResult
from .centralized import CentralizedExecutor
from .sequential import SequentialExecutor
from .hierarchical import HierarchicalExecutor
from .p2p import P2PExecutor
from .mesh import MeshExecutor
from .dag import DAGExecutor
from .cyclic import CyclicExecutor

__all__ = [
    "BaseTopologyExecutor",
    "TopologyResult",
    "CentralizedExecutor",
    "SequentialExecutor",
    "HierarchicalExecutor",
    "P2PExecutor",
    "MeshExecutor",
    "DAGExecutor",
    "CyclicExecutor",
]

# Factory function to get executor by topology type
def get_executor(topology_type: str) -> BaseTopologyExecutor:
    """Get the appropriate executor for a topology type."""
    executors = {
        "centralized": CentralizedExecutor(),
        "sequential": SequentialExecutor(),
        "hierarchical": HierarchicalExecutor(),
        "p2p": P2PExecutor(),
        "mesh": MeshExecutor(),
        "dag": DAGExecutor(),
        "cyclic": CyclicExecutor(),
    }
    executor = executors.get(topology_type)
    if not executor:
        raise ValueError(f"Unknown topology type: {topology_type}")
    return executor
