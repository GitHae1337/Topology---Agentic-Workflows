import { InternalEdge } from '../types';

export const wouldCreateCycle = (
  fromId: string,
  toId: string,
  edges: InternalEdge[]
): boolean => {
  const visited = new Set<string>();
  const stack = [toId];

  while (stack.length > 0) {
    const current = stack.pop()!;
    if (current === fromId) return true;
    if (visited.has(current)) continue;
    visited.add(current);

    edges.filter(e => e.from === current).forEach(e => stack.push(e.to));
  }
  return false;
};

export const findEntryNodes = (agentIds: string[], edges: InternalEdge[]): string[] => {
  const hasIncoming = new Set(edges.map(e => e.to));
  return agentIds.filter(id => !hasIncoming.has(id));
};

export const findTerminalNodes = (agentIds: string[], edges: InternalEdge[]): string[] => {
  const hasOutgoing = new Set(edges.map(e => e.from));
  return agentIds.filter(id => !hasOutgoing.has(id));
};

export const topologicalSort = (agentIds: string[], edges: InternalEdge[]): string[] => {
  const inDegree = new Map<string, number>();
  const adjacency = new Map<string, string[]>();

  agentIds.forEach(id => {
    inDegree.set(id, 0);
    adjacency.set(id, []);
  });

  edges.forEach(edge => {
    inDegree.set(edge.to, (inDegree.get(edge.to) || 0) + 1);
    adjacency.get(edge.from)?.push(edge.to);
  });

  const queue: string[] = [];
  inDegree.forEach((degree, id) => {
    if (degree === 0) queue.push(id);
  });

  const result: string[] = [];
  while (queue.length > 0) {
    const current = queue.shift()!;
    result.push(current);

    adjacency.get(current)?.forEach(neighbor => {
      const newDegree = (inDegree.get(neighbor) || 0) - 1;
      inDegree.set(neighbor, newDegree);
      if (newDegree === 0) queue.push(neighbor);
    });
  }

  return result;
};
