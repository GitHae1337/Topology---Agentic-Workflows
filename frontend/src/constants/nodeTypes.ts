import { NodeDefinition } from '../types';

export const coreNodes: NodeDefinition[] = [
  { type: 'start', name: 'Start', icon: '▶', color: '#6366f1', desc: 'Entry point' },
  { type: 'agent', name: 'Agent', icon: '▽', color: '#6366f1', desc: 'AI agent node' },
  { type: 'end', name: 'End', icon: '■', color: '#22c55e', desc: 'End workflow' },
  { type: 'note', name: 'Note', icon: '□', color: '#6b7280', desc: 'Add documentation' },
];

export const logicNodes: NodeDefinition[] = [
  { type: 'ifelse', name: 'If / else', icon: '⤷', color: '#f59e0b', desc: 'Conditional branch' },
  // HIDDEN: approval node
  // { type: 'approval', name: 'User approval', icon: '✋', color: '#f59e0b', desc: 'Human review' },
];

export const allNodes: NodeDefinition[] = [...coreNodes, ...logicNodes];

export const getNodeDefinition = (type: string): NodeDefinition | undefined => {
  return allNodes.find(n => n.type === type);
};

export const getNodeColor = (type: string): string => {
  return getNodeDefinition(type)?.color || '#6b7280';
};

export const getNodeIcon = (type: string): string => {
  return getNodeDefinition(type)?.icon || '?';
};
