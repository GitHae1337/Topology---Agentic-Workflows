import { useCanvasStore } from '../../store';
import { calculateBezierPath } from '../../utils/geometry';
import { IfElseCondition } from '../../types';
import {
  getNodeInputPosition,
  getNodeOutputPosition,
  getIfElseInputPosition,
  getIfElseOutputPosition,
  getApprovalInputPosition,
  getApprovalOutputPosition,
  getTopologyInputPosition,
  getTopologyOutputPosition,
  getOutputDirection,
  getInputDirection,
} from '../../constants/nodeDimensions';

interface ConnectionsLayerProps {
  mousePos: { x: number; y: number } | null;
}

export const ConnectionsLayer = ({ mousePos }: ConnectionsLayerProps) => {
  const connections = useCanvasStore(state => state.connections);
  const nodes = useCanvasStore(state => state.nodes);
  const topologyTemplates = useCanvasStore(state => state.topologyTemplates);
  const connecting = useCanvasStore(state => state.connecting);
  const connectingFromPort = useCanvasStore(state => state.connectingFromPort);
  const connectingFromInput = useCanvasStore(state => state.connectingFromInput);
  const deleteConnection = useCanvasStore(state => state.deleteConnection);

  return (
    <svg className="absolute top-0 left-0 w-full h-full pointer-events-none" style={{ zIndex: 40 }}>
      {connections.map(conn => {
        const fromNode = nodes.find(n => n.id === conn.from);
        const toNode = nodes.find(n => n.id === conn.to);
        const fromTemplate = topologyTemplates.find(t => t.id === conn.from);
        const toTemplate = topologyTemplates.find(t => t.id === conn.to);

        let x1: number, y1: number;
        let x2: number, y2: number;
        let isHorizontalStart = false;
        let isHorizontalEnd = false;

        // Calculate FROM position
        if (fromNode?.type === 'ifelse' && conn.fromPort !== undefined) {
          const conditions = (fromNode.config?.conditions as IfElseCondition[]) || [];
          const pos = getIfElseOutputPosition(fromNode.x, fromNode.y, conn.fromPort, conditions.length);
          x1 = pos.x;
          y1 = pos.y;
          isHorizontalStart = true;
        } else if (fromNode?.type === 'approval' && conn.fromPort !== undefined) {
          const pos = getApprovalOutputPosition(fromNode.x, fromNode.y, conn.fromPort);
          x1 = pos.x;
          y1 = pos.y;
          isHorizontalStart = true;
        } else if (fromNode) {
          const pos = getNodeOutputPosition(fromNode.x, fromNode.y, fromNode.type, !!fromNode.topologyId);
          x1 = pos.x;
          y1 = pos.y;
          isHorizontalStart = getOutputDirection(fromNode.type) === 'horizontal';
        } else if (fromTemplate) {
          const pos = getTopologyOutputPosition(fromTemplate.x, fromTemplate.y, fromTemplate.width, fromTemplate.height);
          x1 = pos.x;
          y1 = pos.y;
        } else {
          return null;
        }

        // Calculate TO position
        if (toNode?.type === 'ifelse') {
          const conditions = (toNode.config?.conditions as IfElseCondition[]) || [];
          const pos = getIfElseInputPosition(toNode.x, toNode.y, conditions.length);
          x2 = pos.x;
          y2 = pos.y;
          isHorizontalEnd = true;
        } else if (toNode?.type === 'approval') {
          const pos = getApprovalInputPosition(toNode.x, toNode.y);
          x2 = pos.x;
          y2 = pos.y;
          isHorizontalEnd = true;
        } else if (toNode) {
          const pos = getNodeInputPosition(toNode.x, toNode.y, toNode.type, !!toNode.topologyId);
          x2 = pos.x;
          y2 = pos.y;
          isHorizontalEnd = getInputDirection(toNode.type) === 'horizontal';
        } else if (toTemplate) {
          const pos = getTopologyInputPosition(toTemplate.x, toTemplate.y, toTemplate.width, toTemplate.height);
          x2 = pos.x;
          y2 = pos.y;
        } else {
          return null;
        }

        // Generate bezier path based on connection directions
        let pathD: string;
        if (isHorizontalStart && isHorizontalEnd) {
          // Both horizontal: S-curve
          const midX = (x1 + x2) / 2;
          pathD = `M ${x1} ${y1} C ${midX} ${y1}, ${midX} ${y2}, ${x2} ${y2}`;
        } else if (isHorizontalStart) {
          // Horizontal start, vertical end
          const midX = x1 + Math.max(40, (x2 - x1) * 0.3);
          pathD = `M ${x1} ${y1} C ${midX} ${y1}, ${x2} ${y2 - 40}, ${x2} ${y2}`;
        } else if (isHorizontalEnd) {
          // Vertical start, horizontal end
          const midY = y1 + Math.max(40, (y2 - y1) * 0.3);
          pathD = `M ${x1} ${y1} C ${x1} ${midY}, ${x2 - 40} ${y2}, ${x2} ${y2}`;
        } else {
          pathD = calculateBezierPath(x1, y1, x2, y2, 40);
        }

        // Calculate midpoint for delete button
        const midX = (x1 + x2) / 2;
        const midY = (y1 + y2) / 2;

        return (
          <g key={conn.id} className="internal-edge-group">
            {/* Arrowhead marker - commented out
            <defs>
              <marker
                id={`arrow-${conn.id}`}
                markerWidth="8"
                markerHeight="6"
                refX="8"
                refY="3"
                orient="auto"
              >
                <path d="M 0 0 L 8 3 L 0 6 Z" fill="#4b5563" />
              </marker>
            </defs>
            */}
            <path
              d={pathD}
              stroke="#4b5563"
              strokeWidth="2"
              fill="none"
              // markerEnd={`url(#arrow-${conn.id})`}
            />
            {/* Delete button - shows on hover */}
            <circle
              cx={midX}
              cy={midY}
              r="10"
              fill="#1f1f1f"
              stroke="#4b5563"
              strokeWidth="1.5"
              className="edge-delete-btn"
              style={{ cursor: 'pointer', opacity: 0, pointerEvents: 'auto' }}
              onClick={(e) => {
                e.stopPropagation();
                deleteConnection(conn.id);
              }}
            />
            <text
              x={midX}
              y={midY + 4}
              fontSize="12"
              fill="#4b5563"
              textAnchor="middle"
              className="edge-delete-text"
              style={{ cursor: 'pointer', opacity: 0, pointerEvents: 'none' }}
            >
              ×
            </text>
          </g>
        );
      })}

      {/* Connection preview line while dragging */}
      {connecting && mousePos && (() => {
        const sourceNode = nodes.find(n => n.id === connecting);
        const sourceTemplate = topologyTemplates.find(t => t.id === connecting);

        if (!sourceNode && !sourceTemplate) return null;

        let x1: number, y1: number;
        let isHorizontalStart = false;

        // Calculate source position based on source type. When the user
        // started by clicking an INPUT dot (connectingFromInput=true), the
        // preview line should originate from the input (left) dot, not the
        // output (right) dot.
        if (sourceNode?.type === 'ifelse' && connectingFromPort !== null) {
          const conditions = (sourceNode.config?.conditions as IfElseCondition[]) || [];
          const pos = getIfElseOutputPosition(sourceNode.x, sourceNode.y, connectingFromPort, conditions.length);
          x1 = pos.x;
          y1 = pos.y;
          isHorizontalStart = true;
        } else if (sourceNode?.type === 'approval' && connectingFromPort !== null) {
          const pos = getApprovalOutputPosition(sourceNode.x, sourceNode.y, connectingFromPort);
          x1 = pos.x;
          y1 = pos.y;
          isHorizontalStart = true;
        } else if (sourceNode) {
          const pos = connectingFromInput
            ? getNodeInputPosition(sourceNode.x, sourceNode.y, sourceNode.type, !!sourceNode.topologyId)
            : getNodeOutputPosition(sourceNode.x, sourceNode.y, sourceNode.type, !!sourceNode.topologyId);
          x1 = pos.x;
          y1 = pos.y;
          isHorizontalStart = (connectingFromInput ? getInputDirection(sourceNode.type) : getOutputDirection(sourceNode.type)) === 'horizontal';
        } else if (sourceTemplate) {
          const pos = connectingFromInput
            ? getTopologyInputPosition(sourceTemplate.x, sourceTemplate.y, sourceTemplate.width, sourceTemplate.height)
            : getTopologyOutputPosition(sourceTemplate.x, sourceTemplate.y, sourceTemplate.width, sourceTemplate.height);
          x1 = pos.x;
          y1 = pos.y;
          // Topology output is vertical (bottom); input is horizontal (left).
          isHorizontalStart = connectingFromInput;
        } else {
          return null;
        }

        const x2 = mousePos.x;
        const y2 = mousePos.y;

        // Generate preview path
        let pathD: string;
        if (isHorizontalStart) {
          const midX = x1 + Math.max(40, (x2 - x1) * 0.3);
          pathD = `M ${x1} ${y1} C ${midX} ${y1}, ${x2} ${y2 - 40}, ${x2} ${y2}`;
        } else {
          pathD = calculateBezierPath(x1, y1, x2, y2, 40);
        }

        return (
          <path
            d={pathD}
            stroke="#6366f1"
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
