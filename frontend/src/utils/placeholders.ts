import { PlaceholderConfig, TopologyType } from '../types';

export const getPlaceholderConfig = (
  topoType: TopologyType,
  width: number,
  height: number
): PlaceholderConfig => {
  const bodyW = width - 20;
  const bodyH = height - 20;
  const centerX = bodyW / 2;
  const centerY = bodyH / 2;

  switch (topoType) {
    case 'centralized':
      return {
        nodes: [
          { x: centerX, y: 30, label: 'Leader', isMain: true },
          { x: centerX - 80, y: bodyH - 40, label: 'Member' },
          { x: centerX, y: bodyH - 40, label: 'Member' },
          { x: centerX + 80, y: bodyH - 40, label: 'Member' },
        ],
        edges: [
          { from: 0, to: 1, bidirectional: true },
          { from: 0, to: 2, bidirectional: true },
          { from: 0, to: 3, bidirectional: true },
        ],
      };

    case 'sequential':
      return {
        nodes: [
          { x: 50, y: centerY, label: '1st' },
          { x: centerX, y: centerY, label: '2nd' },
          { x: bodyW - 50, y: centerY, label: '3rd' },
        ],
        edges: [
          { from: 0, to: 1 },
          { from: 1, to: 2 },
        ],
      };

    case 'hierarchical':
      return {
        nodes: [
          { x: centerX, y: 30, label: 'Manager', isMain: true },
          { x: centerX - 70, y: bodyH - 40, label: 'Worker' },
          { x: centerX + 70, y: bodyH - 40, label: 'Worker' },
        ],
        edges: [
          { from: 0, to: 1, bidirectional: true },
          { from: 0, to: 2, bidirectional: true },
        ],
      };

    case 'p2p':
      return {
        nodes: [
          { x: centerX, y: 25, label: 'Peer' },
          { x: centerX - 70, y: bodyH - 30, label: 'Peer' },
          { x: centerX + 70, y: bodyH - 30, label: 'Peer' },
        ],
        edges: [
          { from: 0, to: 1, bidirectional: true },
          { from: 1, to: 2, bidirectional: true },
          { from: 2, to: 0, bidirectional: true },
        ],
      };

    case 'mesh':
      return {
        nodes: [
          { x: centerX - 60, y: 30, label: 'Agent' },
          { x: centerX + 60, y: 30, label: 'Agent' },
          { x: centerX - 60, y: bodyH - 40, label: 'Agent' },
          { x: centerX + 60, y: bodyH - 40, label: 'Agent' },
        ],
        edges: [
          { from: 0, to: 1, bidirectional: true },
          { from: 0, to: 2, bidirectional: true },
          { from: 0, to: 3, bidirectional: true },
          { from: 1, to: 2, bidirectional: true },
          { from: 1, to: 3, bidirectional: true },
          { from: 2, to: 3, bidirectional: true },
        ],
      };

    case 'cyclic':
      return {
        nodes: [
          { x: centerX, y: 25, label: 'A' },
          { x: centerX - 70, y: bodyH - 30, label: 'B' },
          { x: centerX + 70, y: bodyH - 30, label: 'C' },
        ],
        edges: [
          { from: 0, to: 1 },
          { from: 1, to: 2 },
          { from: 2, to: 0 },
        ],
      };

    default:
      return { nodes: [], edges: [] };
  }
};
