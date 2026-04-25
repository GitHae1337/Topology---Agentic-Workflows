import { TopologyTemplate, Node } from '../types';
import {
  NODE_WIDTH,
  NODE_HEIGHTS,
  TOPOLOGY_HEADER_HEIGHT,
} from '../constants/nodeDimensions';

export const isInsideTopology = (
  agentX: number,
  agentY: number,
  template: TopologyTemplate
): boolean => {
  const agentCenterX = agentX + NODE_WIDTH / 2;
  const agentCenterY = agentY + NODE_HEIGHTS.agent / 2;
  return (
    agentCenterX > template.x &&
    agentCenterX < template.x + template.width &&
    agentCenterY > template.y + TOPOLOGY_HEADER_HEIGHT &&
    agentCenterY < template.y + template.height + TOPOLOGY_HEADER_HEIGHT
  );
};

export const getEntityPosition = (
  entityId: string,
  nodes: Node[],
  topologyTemplates: TopologyTemplate[]
): { x: number; y: number; height: number } | null => {
  const node = nodes.find(n => n.id === entityId);
  if (node) {
    // Determine node height based on type and whether it's in a topology
    const height = node.topologyId
      ? NODE_HEIGHTS.agentInTopology
      : (NODE_HEIGHTS[node.type as keyof typeof NODE_HEIGHTS] || NODE_HEIGHTS.agent);

    return {
      x: node.x + NODE_WIDTH / 2,
      y: node.y,
      height: height
    };
  }

  const template = topologyTemplates.find(t => t.id === entityId);
  if (template) {
    return {
      x: template.x + template.width / 2,
      y: template.y,
      height: template.height + TOPOLOGY_HEADER_HEIGHT
    };
  }

  return null;
};

export const calculateBezierPath = (
  x1: number,
  y1: number,
  x2: number,
  y2: number,
  offset = 40
): string => {
  return `M ${x1} ${y1} C ${x1} ${y1 + offset}, ${x2} ${y2 - offset}, ${x2} ${y2}`;
};

export const calculateArrowTransform = (
  x1: number,
  y1: number,
  x2: number,
  y2: number
): { angle: number; endX: number; endY: number } => {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const len = Math.sqrt(dx * dx + dy * dy);
  const nx = dx / len;
  const ny = dy / len;
  const arrowOffset = 10;

  return {
    angle: Math.atan2(dy, dx) * 180 / Math.PI,
    endX: x2 - nx * arrowOffset,
    endY: y2 - ny * arrowOffset,
  };
};
