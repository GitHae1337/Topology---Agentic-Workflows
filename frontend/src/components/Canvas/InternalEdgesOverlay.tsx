import { useCanvasStore } from '../../store';
import { TopologyTemplate, Node } from '../../types';
import {
  NODE_WIDTH,
  NODE_HEIGHTS,
} from '../../constants/nodeDimensions';

interface InternalEdgesOverlayProps {
  topologyTemplates: TopologyTemplate[];
  mousePos: { x: number; y: number } | null;
}

// Connection point offsets for agents inside topology
const NODE_CENTER_X = NODE_WIDTH / 2;
const NODE_HEIGHT_CENTER = NODE_HEIGHTS.agentInTopology / 2;

// For vertical positioning (legacy - used by auto-connect topologies)
const INPUT_DOT_Y = 0;
const OUTPUT_DOT_Y = NODE_HEIGHTS.agentInTopology;

type ConnectionDirection = 'up' | 'down' | 'left' | 'right';

// Get connection point based on topology type, role, and edge direction
const getConnectionPoint = (
  agent: Node,
  templateType: string,
  otherAgent: Node,
  isFromAgent: boolean  // true if this is the source agent of the edge
): { x: number; y: number; direction: ConnectionDirection } => {
  const baseX = agent.x;
  const baseY = agent.y;

  // Sequential, P2P, Cyclic - LEFT/RIGHT positioning (horizontal)
  // From agent uses OUTPUT (right), To agent uses INPUT (left)
  if (templateType === 'sequential' || templateType === 'p2p' || templateType === 'cyclic') {
    if (isFromAgent) {
      // Output dot on RIGHT side
      return { x: baseX + NODE_WIDTH, y: baseY + NODE_HEIGHT_CENTER, direction: 'right' };
    } else {
      // Input dot on LEFT side
      return { x: baseX, y: baseY + NODE_HEIGHT_CENTER, direction: 'left' };
    }
  }

  // Centralized: Leader uses output (bottom), Member uses input (top) - vertical
  if (templateType === 'centralized') {
    if (agent.topologyRole === 'Leader') {
      return { x: baseX + NODE_CENTER_X, y: baseY + OUTPUT_DOT_Y, direction: 'down' };
    } else {
      return { x: baseX + NODE_CENTER_X, y: baseY + INPUT_DOT_Y, direction: 'up' };
    }
  }

  // Hierarchical - vertical positioning
  if (templateType === 'hierarchical') {
    if (agent.topologyRole === 'Manager') {
      return { x: baseX + NODE_CENTER_X, y: baseY + OUTPUT_DOT_Y, direction: 'down' };
    } else {
      if (otherAgent.topologyRole === 'Manager') {
        return { x: baseX + NODE_CENTER_X, y: baseY + INPUT_DOT_Y, direction: 'up' };
      } else {
        // Worker to Worker
        return { x: baseX + NODE_CENTER_X, y: baseY + OUTPUT_DOT_Y, direction: 'down' };
      }
    }
  }

  // Mesh - bidirectional, both agents use input dot (top) - vertical
  if (templateType === 'mesh') {
    return { x: baseX + NODE_CENTER_X, y: baseY + INPUT_DOT_Y, direction: 'up' };
  }

  return { x: baseX + NODE_CENTER_X, y: baseY + OUTPUT_DOT_Y, direction: 'down' };
};

// Generate curved path (no shortening - marker handles arrow placement)
const generateCurvedPath = (
  x1: number, y1: number, dir1: ConnectionDirection,
  x2: number, y2: number, dir2: ConnectionDirection
): string => {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const dist = Math.sqrt(dx * dx + dy * dy);

  // Control point distance
  const ctrlDist = Math.max(40, Math.min(100, dist * 0.5));

  let ctrl1X: number, ctrl1Y: number, ctrl2X: number, ctrl2Y: number;

  // Calculate control points based on direction
  if (dir1 === 'right') {
    ctrl1X = x1 + ctrlDist;
    ctrl1Y = y1;
  } else if (dir1 === 'left') {
    ctrl1X = x1 - ctrlDist;
    ctrl1Y = y1;
  } else if (dir1 === 'down') {
    ctrl1X = x1;
    ctrl1Y = y1 + ctrlDist;
  } else { // up
    ctrl1X = x1;
    ctrl1Y = y1 - ctrlDist;
  }

  if (dir2 === 'right') {
    ctrl2X = x2 + ctrlDist;
    ctrl2Y = y2;
  } else if (dir2 === 'left') {
    ctrl2X = x2 - ctrlDist;
    ctrl2Y = y2;
  } else if (dir2 === 'down') {
    ctrl2X = x2;
    ctrl2Y = y2 + ctrlDist;
  } else { // up
    ctrl2X = x2;
    ctrl2Y = y2 - ctrlDist;
  }

  return `M ${x1} ${y1} C ${ctrl1X} ${ctrl1Y}, ${ctrl2X} ${ctrl2Y}, ${x2} ${y2}`;
};

export const InternalEdgesOverlay = ({ topologyTemplates, mousePos }: InternalEdgesOverlayProps) => {
  const nodes = useCanvasStore(state => state.nodes);
  const deleteInternalEdge = useCanvasStore(state => state.deleteInternalEdge);
  const internalConnecting = useCanvasStore(state => state.internalConnecting);

  return (
    <svg
      className="absolute top-0 left-0 w-full h-full pointer-events-none"
      style={{ zIndex: 50 }}
    >
      <defs>
        {/* Define arrow markers for each topology color */}
        {topologyTemplates.map(template => (
          <marker
            key={`arrow-${template.id}`}
            id={`arrow-${template.id}`}
            markerWidth="8"
            markerHeight="6"
            refX="8"
            refY="3"
            orient="auto"
          >
            <path d="M 0 0 L 8 3 L 0 6 Z" fill={template.color} />
          </marker>
        ))}
        {/* Reverse arrow markers for bidirectional edges */}
        {topologyTemplates.map(template => (
          <marker
            key={`arrow-reverse-${template.id}`}
            id={`arrow-reverse-${template.id}`}
            markerWidth="8"
            markerHeight="6"
            refX="0"
            refY="3"
            orient="auto"
          >
            <path d="M 8 0 L 0 3 L 8 6 Z" fill={template.color} />
          </marker>
        ))}
      </defs>

      {topologyTemplates.map(template => {
        // Filter duplicate bidirectional edges
        const processedPairs = new Set<string>();
        const filteredEdges = template.internalEdges.filter(edge => {
          if (edge.type === 'bidirectional') {
            const pairKey = [edge.from, edge.to].sort().join('-');
            if (processedPairs.has(pairKey)) return false;
            processedPairs.add(pairKey);
          }
          return true;
        });

        return filteredEdges.map(edge => {
          const fromAgent = nodes.find(n => n.id === edge.from);
          const toAgent = nodes.find(n => n.id === edge.to);
          if (!fromAgent || !toAgent) return null;

          const from = getConnectionPoint(fromAgent, template.type, toAgent, true);
          const to = getConnectionPoint(toAgent, template.type, fromAgent, false);

          const isBidirectional = edge.type === 'bidirectional';

          // Generate path (marker handles arrow placement)
          const pathD = generateCurvedPath(from.x, from.y, from.direction, to.x, to.y, to.direction);

          const midX = (from.x + to.x) / 2;
          const midY = (from.y + to.y) / 2;

          return (
            <g key={edge.id} className="internal-edge-group">
              {/* Curved path with arrow marker(s) */}
              <path
                d={pathD}
                stroke={template.color}
                strokeWidth="2"
                fill="none"
                opacity="0.85"
                markerEnd={`url(#arrow-${template.id})`}
                markerStart={isBidirectional ? `url(#arrow-reverse-${template.id})` : undefined}
              />

              {/* Delete button - only for topologies with manual edge drawing (P2P, Cyclic, Sequential) */}
              {/* Centralized, Hierarchical, Mesh auto-connect edges, so deletion is not allowed */}
              {(template.type === 'p2p' || template.type === 'cyclic' || template.type === 'sequential') && (
                <>
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
                </>
              )}
            </g>
          );
        });
      })}

      {/* Connection preview line for internal topology connections */}
      {internalConnecting && mousePos && (() => {
        const sourceAgent = nodes.find(n => n.id === internalConnecting.agentId);
        const template = topologyTemplates.find(t => t.id === internalConnecting.templateId);

        if (!sourceAgent || !template) return null;

        // Only show preview for manual connection topologies (sequential, p2p, cyclic)
        if (template.type !== 'sequential' && template.type !== 'p2p' && template.type !== 'cyclic') {
          return null;
        }

        // Calculate source position (output dot on RIGHT side)
        const x1 = sourceAgent.x + NODE_WIDTH;
        const y1 = sourceAgent.y + NODE_HEIGHT_CENTER;

        const x2 = mousePos.x;
        const y2 = mousePos.y;

        // Generate preview path (from right output to left input)
        const pathD = generateCurvedPath(x1, y1, 'right', x2, y2, 'left');

        return (
          <path
            d={pathD}
            stroke={template.color}
            strokeWidth="2"
            strokeDasharray="6 4"
            fill="none"
            opacity="0.7"
          />
        );
      })()}
    </svg>
  );
};
