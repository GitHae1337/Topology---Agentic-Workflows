import { useCanvasStore } from '../../store';
import { TopologyTemplate, Node } from '../../types';

interface InternalEdgesProps {
  template: TopologyTemplate;
}

// Node dimensions
const NODE_WIDTH = 160;
const NODE_HEIGHT = 60;
const NODE_CENTER_X = NODE_WIDTH / 2; // 80

// Connection point offsets from node top-left
const INPUT_DOT_Y = 0;      // Top of node
const OUTPUT_DOT_Y = NODE_HEIGHT; // Bottom of node

// Arrow offset - how far outside the node the arrow should be drawn
const ARROW_OFFSET = 12;

// Get connection point based on topology type and role
const getConnectionPoint = (
  agent: Node,
  templateType: string,
  otherAgent: Node,
  templateX: number,
  templateY: number
): { x: number; y: number; direction: 'up' | 'down' } => {
  const baseX = agent.x - templateX + NODE_CENTER_X;
  const baseY = agent.y - templateY;

  // Unidirectional topologies (Chain) - standard output→input
  if (templateType === 'chain') {
    // Determine direction based on relative Y position
    if (agent.y < otherAgent.y) {
      // This agent is above, use output (bottom)
      return { x: baseX, y: baseY + OUTPUT_DOT_Y, direction: 'down' };
    } else {
      // This agent is below, use input (top)
      return { x: baseX, y: baseY + INPUT_DOT_Y, direction: 'up' };
    }
  }

  // Centralized: Leader uses output, Member uses input
  if (templateType === 'centralized') {
    if (agent.topologyRole === 'Leader') {
      return { x: baseX, y: baseY + OUTPUT_DOT_Y, direction: 'down' };
    } else {
      return { x: baseX, y: baseY + INPUT_DOT_Y, direction: 'up' };
    }
  }

  // Hierarchical
  if (templateType === 'hierarchical') {
    if (agent.topologyRole === 'Manager') {
      return { x: baseX, y: baseY + OUTPUT_DOT_Y, direction: 'down' };
    } else {
      // Worker
      if (otherAgent.topologyRole === 'Manager') {
        return { x: baseX, y: baseY + INPUT_DOT_Y, direction: 'up' };
      } else {
        // Worker to Worker - use output (bottom)
        return { x: baseX, y: baseY + OUTPUT_DOT_Y, direction: 'down' };
      }
    }
  }

  // Mesh, Cycle - use input dot (top)
  if (templateType === 'mesh' || templateType === 'cycle') {
    return { x: baseX, y: baseY + INPUT_DOT_Y, direction: 'up' };
  }

  // Default
  return { x: baseX, y: baseY + OUTPUT_DOT_Y, direction: 'down' };
};

// Generate curved path with proper control points
const generateCurvedPath = (
  x1: number, y1: number, dir1: 'up' | 'down',
  x2: number, y2: number, dir2: 'up' | 'down'
): string => {
  // Calculate distance for control point offset
  const dx = x2 - x1;
  const dy = y2 - y1;
  const dist = Math.sqrt(dx * dx + dy * dy);

  // Control point distance based on distance between points
  const ctrlDist = Math.max(30, Math.min(80, dist * 0.4));

  // Control points extend in the direction of the connection point
  const ctrl1X = x1;
  const ctrl1Y = dir1 === 'down' ? y1 + ctrlDist : y1 - ctrlDist;
  const ctrl2X = x2;
  const ctrl2Y = dir2 === 'down' ? y2 + ctrlDist : y2 - ctrlDist;

  return `M ${x1} ${y1} C ${ctrl1X} ${ctrl1Y}, ${ctrl2X} ${ctrl2Y}, ${x2} ${y2}`;
};

// Draw arrow head
const drawArrow = (
  x: number, y: number,
  direction: 'up' | 'down',
  color: string,
  offset: number = ARROW_OFFSET
): JSX.Element => {
  const size = 6;
  // Arrow points in the opposite direction of the connection (into the node)
  const tipY = direction === 'up' ? y - offset : y + offset;
  const baseY = direction === 'up' ? tipY - size : tipY + size;

  return (
    <path
      d={`M ${x - size} ${baseY} L ${x} ${tipY} L ${x + size} ${baseY}`}
      stroke={color}
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      fill="none"
    />
  );
};

export const InternalEdges = ({ template }: InternalEdgesProps) => {
  const nodes = useCanvasStore(state => state.nodes);
  const deleteInternalEdge = useCanvasStore(state => state.deleteInternalEdge);

  // Filter out duplicate bidirectional edges (keep only one per pair)
  const processedPairs = new Set<string>();
  const filteredEdges = template.internalEdges.filter(edge => {
    if (edge.type === 'bidirectional') {
      const pairKey = [edge.from, edge.to].sort().join('-');
      if (processedPairs.has(pairKey)) return false;
      processedPairs.add(pairKey);
    }
    return true;
  });

  return (
    <svg
      className="absolute overflow-visible pointer-events-none"
      style={{
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        zIndex: 100  // Ensure edges render above nodes
      }}
    >
      {filteredEdges.map(edge => {
        const fromAgent = nodes.find(n => n.id === edge.from);
        const toAgent = nodes.find(n => n.id === edge.to);
        if (!fromAgent || !toAgent) return null;

        // Get connection points
        const from = getConnectionPoint(fromAgent, template.type, toAgent, template.x, template.y + 40);
        const to = getConnectionPoint(toAgent, template.type, fromAgent, template.x, template.y + 40);

        // Generate curved path
        const pathD = generateCurvedPath(from.x, from.y, from.direction, to.x, to.y, to.direction);

        // Calculate midpoint for delete button (approximate)
        const midX = (from.x + to.x) / 2;
        const midY = (from.y + to.y) / 2;

        const isBidirectional = edge.type === 'bidirectional';

        return (
          <g key={edge.id} className="internal-edge-group">
            {/* Main curved path */}
            <path
              d={pathD}
              stroke={template.color}
              strokeWidth="2"
              fill="none"
              opacity="0.8"
            />

            {/* Arrow at 'to' end - always shown */}
            {drawArrow(to.x, to.y, to.direction, template.color)}

            {/* Arrow at 'from' end - only for bidirectional */}
            {isBidirectional && drawArrow(from.x, from.y, from.direction, template.color)}

            {/* Delete button - visible on hover via CSS */}
            <circle
              cx={midX}
              cy={midY}
              r="10"
              fill="#1f1f1f"
              stroke={template.color}
              strokeWidth="1.5"
              className="edge-delete-btn"
              style={{ cursor: 'pointer', opacity: 0, pointerEvents: 'auto' }}
              onClick={(e) => {
                e.stopPropagation();
                deleteInternalEdge(template.id, edge.id);
              }}
            />
            <text
              x={midX}
              y={midY + 4}
              fontSize="12"
              fill={template.color}
              textAnchor="middle"
              className="edge-delete-text"
              style={{ cursor: 'pointer', opacity: 0, pointerEvents: 'none' }}
            >
              ×
            </text>
          </g>
        );
      })}
    </svg>
  );
};
