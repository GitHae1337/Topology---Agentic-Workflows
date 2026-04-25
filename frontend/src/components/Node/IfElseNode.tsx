import { useCallback, RefObject } from 'react';
import { useCanvasStore } from '../../store';
import { Node, IfElseCondition } from '../../types';
import { getNodeColor, getNodeIcon } from '../../constants/nodeTypes';

interface IfElseNodeProps {
  node: Node;
  canvasRef: RefObject<HTMLDivElement>;
  mode?: 'canvas' | 'chat';
}

export const IfElseNode = ({ node, canvasRef, mode = 'canvas' }: IfElseNodeProps) => {
  const selectedNode = useCanvasStore(state => state.selectedNode);
  const connecting = useCanvasStore(state => state.connecting);
  const connectingFromPort = useCanvasStore(state => state.connectingFromPort);

  const setSelectedNode = useCanvasStore(state => state.setSelectedNode);
  const setSelectedTemplate = useCanvasStore(state => state.setSelectedTemplate);
  const setDraggingNode = useCanvasStore(state => state.setDraggingNode);
  const setDragOffset = useCanvasStore(state => state.setDragOffset);
  const deleteNode = useCanvasStore(state => state.deleteNode);
  const setConnecting = useCanvasStore(state => state.setConnecting);
  const addConnection = useCanvasStore(state => state.addConnection);

  const isSelected = selectedNode === node.id;
  const nodeColor = getNodeColor(node.type);
  const conditions = (node.config?.conditions as IfElseCondition[]) || [];

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.button !== 0) return;
    const target = e.target as HTMLElement;
    if (target.closest('.connection-dot') || target.closest('.delete-btn')) return;
    e.stopPropagation();

    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;

    setDraggingNode(node.id);
    setDragOffset({
      x: e.clientX - rect.left - node.x,
      y: e.clientY - rect.top - node.y,
    });
    setSelectedNode(node.id);
    setSelectedTemplate(null);
  }, [node.id, node.x, node.y, canvasRef, setDraggingNode, setDragOffset, setSelectedNode, setSelectedTemplate]);

  const handleClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    setSelectedNode(node.id);
    setSelectedTemplate(null);
  }, [node.id, setSelectedNode, setSelectedTemplate]);

  const handleDelete = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    deleteNode(node.id);
  }, [node.id, deleteNode]);

  // Input connection (left side)
  const handleInputConnectionEnd = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    if (connecting && connecting !== node.id) {
      addConnection(connecting, node.id, 'node', connectingFromPort ?? undefined);
    }
    setConnecting(null, null);
  }, [connecting, connectingFromPort, node.id, addConnection, setConnecting]);

  // Output connection handlers for each port
  const handleOutputConnectionStart = useCallback((portIndex: number) => (e: React.MouseEvent) => {
    e.stopPropagation();
    setConnecting(node.id, 'node', portIndex);
  }, [node.id, setConnecting]);

  // Calculate node height based on conditions
  const headerHeight = 48;
  const conditionHeight = 44;
  const elseHeight = 44;
  const padding = 8;
  const totalHeight = headerHeight + (conditions.length * conditionHeight) + elseHeight + padding;

  return (
    <div
      className={`absolute bg-[#1f1f1f] border-2 rounded-xl cursor-grab select-none node-transition ${
        isSelected ? 'selection-ring' : ''
      }`}
      style={{
        left: node.x,
        top: node.y,
        width: 200,
        minHeight: totalHeight,
        borderColor: nodeColor,
        zIndex: 60,
      }}
      onMouseDown={handleMouseDown}
      onClick={handleClick}
    >
      {/* Header */}
      <div
        className="flex items-center gap-2 px-3 py-2.5 border-b border-[#333] rounded-t-[9px]"
        style={{ borderTopColor: nodeColor, borderTopWidth: '3px' }}
      >
        <div
          className="w-6 h-6 rounded-md flex items-center justify-center text-xs text-white"
          style={{ backgroundColor: nodeColor }}
        >
          {getNodeIcon(node.type)}
        </div>
        <span className="flex-1 text-[13px] font-medium truncate">{node.name}</span>
        {mode === 'canvas' && (
          <button
            className="delete-btn bg-transparent border-none text-[#666] text-base cursor-pointer opacity-0 hover:opacity-100 hover:text-[#ef4444] transition-opacity"
            onClick={handleDelete}
            style={{ opacity: isSelected ? 1 : undefined }}
          >
            ×
          </button>
        )}
      </div>

      {/* Condition boxes */}
      <div className="p-2 space-y-1">
        {conditions.map((condition, index) => (
          <div
            key={condition.id}
            className="relative bg-[#2a2a2a] rounded-lg px-3 py-2.5 text-xs text-[#888]"
          >
            <span className="truncate block pr-4">
              {condition.name || condition.condition || `Case ${index + 1}`}
            </span>
            {/* Output connection dot for this condition */}
            <div
              className="connection-dot absolute w-3 h-3 bg-[#404040] border-2 border-[#1f1f1f] rounded-full cursor-crosshair -right-1.5 top-1/2 -translate-y-1/2 z-10 hover:bg-[#6366f1] transition-colors"
              onMouseDown={handleOutputConnectionStart(index)}
              title={`Connect from ${condition.name || `Case ${index + 1}`}`}
            />
          </div>
        ))}

        {/* Else box */}
        <div className="relative bg-[#333] rounded-lg px-3 py-2.5 text-xs text-[#666]">
          <span>Else</span>
          {/* Output connection dot for else */}
          <div
            className="connection-dot absolute w-3 h-3 bg-[#404040] border-2 border-[#1f1f1f] rounded-full cursor-crosshair -right-1.5 top-1/2 -translate-y-1/2 z-10 hover:bg-[#6366f1] transition-colors"
            onMouseDown={handleOutputConnectionStart(-1)}
            title="Connect from Else"
          />
        </div>
      </div>

      {/* Input connection dot (left side) */}
      <div
        className="connection-dot absolute w-3 h-3 bg-[#404040] border-2 border-[#1f1f1f] rounded-full cursor-crosshair -left-1.5 top-1/2 -translate-y-1/2 z-10 hover:bg-[#6366f1] transition-colors"
        onMouseUp={handleInputConnectionEnd}
        title="Connect to this node"
      />
    </div>
  );
};
