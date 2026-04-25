// Node Types
export type NodeType = 'start' | 'agent' | 'end' | 'note' | 'ifelse' | 'approval';

export interface Node {
  id: string;
  type: NodeType;
  x: number;
  y: number;
  name: string;
  config: Record<string, unknown>;
  topologyId: string | null;
  topologyRole: string | null;
  topologyColor: string | null;
}

// Topology Types
export type TopologyType = 'centralized' | 'sequential' | 'hierarchical' | 'p2p' | 'mesh' | 'cyclic';

export type EdgeType = 'bidirectional' | 'unidirectional';

export interface InternalEdge {
  id: string;
  from: string;
  to: string;
  type: EdgeType;
}

// If/Else Condition
export interface IfElseCondition {
  id: string;
  name?: string;
  condition: string;
}

export interface TopologyTemplate {
  id: string;
  type: TopologyType;
  x: number;
  y: number;
  width: number;
  height: number;
  name: string;
  color: string;
  maxTurns: number;
  timeout: number;
  earlyTermination: boolean;
  internalEdges: InternalEdge[];
  startAgentId: string | null;
}

// Connection between workflow-level nodes/topologies
export interface Connection {
  id: string;
  from: string;
  to: string;
  fromType: 'node' | 'template';
  fromPort?: number; // For ifelse: 0,1,2... for conditions, -1 for else
}

// Topology Definition (for sidebar)
export interface TopologyDefinition {
  id: TopologyType;
  name: string;
  subtitle: string;
  icon: string;
  masDesc: string;
  socialDesc: string;
  color: string;
  hasRoles: boolean;
  roles: string[];
  edgeType: EdgeType;
  autoConnect: boolean;
  autoEdgeOnRole: boolean;
  startPoint: string;
  endPoint: string;
  needsStartAgent: boolean;
  noLoops?: boolean;
}

// Node Definition (for sidebar)
export interface NodeDefinition {
  type: NodeType;
  name: string;
  icon: string;
  color: string;
  desc: string;
}

// Role Popup State
export interface RolePopupState {
  agentId: string;
  templateId: string;
  roles: string[];
  x: number;
  y: number;
}

// Chat Message
export interface ChatMessage {
  role: 'user' | 'assistant';
  text: string;
}

// Placeholder Node for visualization
export interface PlaceholderNode {
  x: number;
  y: number;
  label: string;
  isMain?: boolean;
}

// Placeholder Edge for visualization
export interface PlaceholderEdge {
  from: number;
  to: number;
  bidirectional?: boolean;
}

// Placeholder Configuration
export interface PlaceholderConfig {
  nodes: PlaceholderNode[];
  edges: PlaceholderEdge[];
}

// Drag State
export interface DragState {
  type: 'node' | 'topology';
  item: NodeDefinition | TopologyDefinition;
}

// Sidebar Drag Preview
export interface DragPreview {
  x: number;
  y: number;
}
