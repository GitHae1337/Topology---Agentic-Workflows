import { useState } from 'react';
import { coreNodes } from '../../constants/nodeTypes';
import { useCanvasStore } from '../../store';
import { NodeDefinition } from '../../types';

// Sidebar Core list. Start/End are auto-placed by resetForNewTrial and not
// user-removable; the Logic palette (ifelse/approval) is hidden for the study.
const VISIBLE_CORE_TYPES = new Set(['agent', 'note']);

export const NodePalette = () => {
  const addNode = useCanvasStore(state => state.addNode);
  const [dragItem, setDragItem] = useState<NodeDefinition | null>(null);

  const handleDragStart = (e: React.DragEvent, node: NodeDefinition) => {
    e.dataTransfer.setData('nodeType', JSON.stringify(node));
    e.dataTransfer.effectAllowed = 'move';
    setDragItem(node);
  };

  const handleDragEnd = () => {
    setDragItem(null);
  };

  const handleClick = (node: NodeDefinition) => {
    addNode(node.type, 300 + Math.random() * 100, 150 + Math.random() * 100);
  };

  const NodeItem = ({ node }: { node: NodeDefinition }) => (
    <div
      className="flex items-center gap-2.5 px-2.5 py-2 rounded-lg cursor-pointer mb-1 hover:bg-[#262626] transition-colors"
      draggable
      onDragStart={(e) => handleDragStart(e, node)}
      onDragEnd={handleDragEnd}
      onClick={() => handleClick(node)}
    >
      <div
        className="w-7 h-7 rounded-md flex items-center justify-center text-xs text-white flex-shrink-0"
        style={{ backgroundColor: node.color }}
      >
        {node.icon}
      </div>
      <span className="text-sm">{node.name}</span>
    </div>
  );

  return (
    <>
      {/* Core Nodes — Agent + Note only (Start/End not user-addable) */}
      <div className="mb-5">
        <span className="text-[11px] text-[#666] uppercase tracking-wider block mb-2">
          Core
        </span>
        {coreNodes.filter(node => VISIBLE_CORE_TYPES.has(node.type)).map(node => (
          <NodeItem key={node.type} node={node} />
        ))}
      </div>
      {/* Logic palette hidden for the study (ifelse / approval). */}
    </>
  );
};
