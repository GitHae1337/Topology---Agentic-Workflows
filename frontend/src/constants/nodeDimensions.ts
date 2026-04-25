// ============================================
// Node Dimensions - Central Source of Truth
// ============================================

// Base node dimensions (used by most node types)
export const NODE_WIDTH = 160;

// Height calculations based on actual CSS:
// - Header: py-2.5 (20px) + icon h-6 (24px) + border-top (3px) + border-b (1px) = 48px
// - Content: py-2.5 (20px) + text-xs line-height (16px) = 36px
// - Container border: border-2 = 4px total (2px top + 2px bottom)
const NODE_HEADER_HEIGHT = 48;
const NODE_CONTENT_HEIGHT = 36;
const NODE_BORDER = 4;

// Node heights by type (total including borders)
export const NODE_HEIGHTS = {
  start: NODE_HEADER_HEIGHT + NODE_BORDER, // 52px
  end: NODE_HEADER_HEIGHT + NODE_BORDER, // 52px
  agent: NODE_HEADER_HEIGHT + NODE_CONTENT_HEIGHT + NODE_BORDER, // 88px - has content section
  agentInTopology: NODE_HEADER_HEIGHT + NODE_BORDER, // 52px - no content section when inside topology
  note: NODE_HEADER_HEIGHT + NODE_CONTENT_HEIGHT + NODE_BORDER, // 88px
  approval: NODE_HEADER_HEIGHT + NODE_CONTENT_HEIGHT + NODE_BORDER, // 88px
} as const;

// Visual offset for edge starting point (slightly below the output dot for better appearance)
const OUTPUT_EDGE_OFFSET = 6;

// If/Else node specific dimensions
export const IFELSE_WIDTH = 200;
export const IFELSE_HEADER_HEIGHT = 48;
export const IFELSE_CONDITION_HEIGHT = 44;
export const IFELSE_ELSE_HEIGHT = 44;
export const IFELSE_PADDING = 8;

// Approval node specific dimensions
export const APPROVAL_WIDTH = 180;
export const APPROVAL_HEADER_HEIGHT = 48;
export const APPROVAL_OPTION_HEIGHT = 40;
export const APPROVAL_PADDING = 8;

// ============================================
// Port Position Calculators
// ============================================

export interface PortPosition {
  x: number;
  y: number;
}

/**
 * Get the input port position for a node (where connections come IN)
 * Position is relative to canvas (absolute), not relative to node
 * Input is on the LEFT side for all nodes (except start which has no input)
 */
export const getNodeInputPosition = (
  nodeX: number,
  nodeY: number,
  nodeType: string,
  isInTopology: boolean
): PortPosition => {
  // Start nodes have no input
  if (nodeType === 'start') {
    return { x: nodeX, y: nodeY }; // Fallback, shouldn't be used
  }

  // End node: input on the left side, vertically centered
  if (nodeType === 'end') {
    return {
      x: nodeX,
      y: nodeY + NODE_HEIGHTS.end / 2,
    };
  }

  // Agent inside topology: shorter height
  if (nodeType === 'agent' && isInTopology) {
    return {
      x: nodeX,
      y: nodeY + NODE_HEIGHTS.agentInTopology / 2,
    };
  }

  // Agent outside topology
  if (nodeType === 'agent') {
    return {
      x: nodeX,
      y: nodeY + NODE_HEIGHTS.agent / 2,
    };
  }

  // Regular nodes: input on left side, vertically centered
  const height = NODE_HEIGHTS[nodeType as keyof typeof NODE_HEIGHTS] || NODE_HEADER_HEIGHT;
  return {
    x: nodeX,
    y: nodeY + height / 2,
  };
};

/**
 * Get the output port position for a node (where connections go OUT)
 * Position is relative to canvas (absolute), not relative to node
 * Output is on the RIGHT side for all nodes (except end which has no output)
 */
export const getNodeOutputPosition = (
  nodeX: number,
  nodeY: number,
  nodeType: string,
  isInTopology: boolean
): PortPosition => {
  // End nodes have no output
  if (nodeType === 'end') {
    return { x: nodeX + NODE_WIDTH, y: nodeY + NODE_HEIGHTS.end / 2 }; // Fallback, shouldn't be used
  }

  // Start node: output on the right side, vertically centered
  if (nodeType === 'start') {
    return {
      x: nodeX + NODE_WIDTH,
      y: nodeY + NODE_HEIGHTS.start / 2,
    };
  }

  // Agent inside topology: shorter height
  if (nodeType === 'agent' && isInTopology) {
    return {
      x: nodeX + NODE_WIDTH,
      y: nodeY + NODE_HEIGHTS.agentInTopology / 2,
    };
  }

  // Agent outside topology
  if (nodeType === 'agent') {
    return {
      x: nodeX + NODE_WIDTH,
      y: nodeY + NODE_HEIGHTS.agent / 2,
    };
  }

  // Regular nodes: output on right side, vertically centered
  const height = NODE_HEIGHTS[nodeType as keyof typeof NODE_HEIGHTS] || NODE_HEADER_HEIGHT;
  return {
    x: nodeX + NODE_WIDTH,
    y: nodeY + height / 2,
  };
};

// ============================================
// If/Else Node Port Calculators
// ============================================

/**
 * Calculate the total height of an if/else node based on conditions count
 */
export const getIfElseHeight = (conditionsCount: number): number => {
  return IFELSE_HEADER_HEIGHT + (conditionsCount * IFELSE_CONDITION_HEIGHT) + IFELSE_ELSE_HEIGHT + IFELSE_PADDING;
};

/**
 * Get the input port position for an if/else node (left side, vertically centered)
 */
export const getIfElseInputPosition = (
  nodeX: number,
  nodeY: number,
  conditionsCount: number
): PortPosition => {
  const totalHeight = getIfElseHeight(conditionsCount);
  return {
    x: nodeX,
    y: nodeY + totalHeight / 2,
  };
};

/**
 * Get the output port position for an if/else node condition or else branch
 * @param portIndex - 0, 1, 2... for conditions, -1 for else branch
 */
export const getIfElseOutputPosition = (
  nodeX: number,
  nodeY: number,
  portIndex: number,
  conditionsCount: number
): PortPosition => {
  const x = nodeX + IFELSE_WIDTH;

  let y: number;
  if (portIndex === -1) {
    // Else port - after all conditions
    y = nodeY + IFELSE_HEADER_HEIGHT + IFELSE_PADDING + (conditionsCount * IFELSE_CONDITION_HEIGHT) + (IFELSE_ELSE_HEIGHT / 2);
  } else {
    // Condition port
    y = nodeY + IFELSE_HEADER_HEIGHT + IFELSE_PADDING + (portIndex * IFELSE_CONDITION_HEIGHT) + (IFELSE_CONDITION_HEIGHT / 2);
  }

  return { x, y };
};

// ============================================
// Approval Node Port Calculators
// ============================================

/**
 * Calculate the total height of an approval node
 */
export const getApprovalHeight = (): number => {
  // Header + Approve option + Reject option + padding
  return APPROVAL_HEADER_HEIGHT + (2 * APPROVAL_OPTION_HEIGHT) + APPROVAL_PADDING;
};

/**
 * Get the input port position for an approval node (left side, vertically centered)
 */
export const getApprovalInputPosition = (
  nodeX: number,
  nodeY: number
): PortPosition => {
  const totalHeight = getApprovalHeight();
  return {
    x: nodeX,
    y: nodeY + totalHeight / 2,
  };
};

/**
 * Get the output port position for an approval node
 * @param portIndex - 0 for Approve, 1 for Reject
 */
export const getApprovalOutputPosition = (
  nodeX: number,
  nodeY: number,
  portIndex: number
): PortPosition => {
  const x = nodeX + APPROVAL_WIDTH;
  const y = nodeY + APPROVAL_HEADER_HEIGHT + APPROVAL_PADDING + (portIndex * APPROVAL_OPTION_HEIGHT) + (APPROVAL_OPTION_HEIGHT / 2);
  return { x, y };
};

// ============================================
// Topology Template Dimensions
// ============================================

export const TOPOLOGY_HEADER_HEIGHT = 40;

/**
 * Get input position for a topology template (left side, vertically centered)
 * Note: Total topology height = templateHeight + TOPOLOGY_HEADER_HEIGHT
 */
export const getTopologyInputPosition = (
  templateX: number,
  templateY: number,
  _templateWidth: number,
  templateHeight: number
): PortPosition => {
  const totalHeight = templateHeight + TOPOLOGY_HEADER_HEIGHT;
  return {
    x: templateX,
    y: templateY + totalHeight / 2,
  };
};

/**
 * Get output position for a topology template (right side, vertically centered)
 * Note: Total topology height = templateHeight + TOPOLOGY_HEADER_HEIGHT
 */
export const getTopologyOutputPosition = (
  templateX: number,
  templateY: number,
  templateWidth: number,
  templateHeight: number
): PortPosition => {
  const totalHeight = templateHeight + TOPOLOGY_HEADER_HEIGHT;
  return {
    x: templateX + templateWidth,
    y: templateY + totalHeight / 2,
  };
};

// ============================================
// Connection Direction Helpers
// ============================================

export type ConnectionDirection = 'horizontal' | 'vertical';

/**
 * Determine if a node's output is horizontal (right side) or vertical (bottom)
 * All nodes now have horizontal output (right side)
 */
export const getOutputDirection = (_nodeType: string): ConnectionDirection => {
  return 'horizontal';
};

/**
 * Determine if a node's input is horizontal (left side) or vertical (top)
 * All nodes now have horizontal input (left side)
 */
export const getInputDirection = (_nodeType: string): ConnectionDirection => {
  return 'horizontal';
};
