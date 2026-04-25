import { useCallback, RefObject } from 'react';
import { useCanvasStore } from '../../store';
import { Node } from '../../types';
import { getNodeColor, getNodeIcon } from '../../constants/nodeTypes';
import {
  APPROVAL_WIDTH,
  APPROVAL_HEADER_HEIGHT,
  APPROVAL_OPTION_HEIGHT,
  APPROVAL_PADDING,
  getApprovalHeight,
} from '../../constants/nodeDimensions';

interface ApprovalNodeProps {
  node: Node;
  canvasRef: RefObject<HTMLDivElement>;
  mode?: 'canvas' | 'chat';
}

export const ApprovalNode = ({ node, canvasRef, mode = 'canvas' }: ApprovalNodeProps) => {
  const selectedNode = useCanvasStore(state => state.selectedNode);
  const connecting = useCanvasStore(state => state.connecting);

  const setSelectedNode = useCanvasStore(state => state.setSelectedNode);
  const setSelectedTemplate = useCanvasStore(state => state.setSelectedTemplate);
  const setDraggingNode = useCanvasStore(state => state.setDraggingNode);
  const setDragOffset = useCanvasStore(state => state.setDragOffset);
  const deleteNode = useCanvasStore(state => state.deleteNode);
  const setConnecting = useCanvasStore(state => state.setConnecting);
  const addConnection = useCanvasStore(state => state.addConnection);

  const isSelected = selectedNode === node.id;
  const nodeColor = getNodeColor(node.type);
  const totalHeight = getApprovalHeight();

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.button !== 0) return;
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

  // Start connection from an output port (0 = Approve, 1 = Reject)
  const handleOutputMouseDown = useCallback((e: React.MouseEvent, portIndex: number) => {
    e.stopPropagation();
    setConnecting(node.id, 'node', portIndex);
  }, [node.id, setConnecting]);

  const connectingFromPort = useCanvasStore(state => state.connectingFromPort);

  // Handle connection end on input
  const handleInputMouseUp = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    if (connecting && connecting !== node.id) {
      addConnection(connecting, node.id, 'node', connectingFromPort ?? undefined);
    }
    setConnecting(null, null);
  }, [connecting, connectingFromPort, node.id, addConnection, setConnecting]);

  return (
    <div
      className={`absolute bg-[#1f1f1f] border-2 rounded-xl cursor-grab select-none ${
        isSelected ? 'selection-ring' : ''
      }`}
      style={{
        left: node.x,
        top: node.y,
        width: APPROVAL_WIDTH,
        height: totalHeight,
        borderColor: nodeColor,
        zIndex: 60,
      }}
      onMouseDown={handleMouseDown}
      onClick={handleClick}
    >
      {/* Header */}
      <div
        className="flex items-center gap-2 px-3 py-2.5 border-b border-[#333] rounded-t-[9px]"
        style={{
          borderTopColor: nodeColor,
          borderTopWidth: '3px',
          height: APPROVAL_HEADER_HEIGHT,
        }}
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
            className="bg-transparent border-none text-[#666] text-base cursor-pointer opacity-0 hover:opacity-100 hover:text-[#ef4444] transition-opacity"
            onClick={handleDelete}
            style={{ opacity: isSelected ? 1 : undefined }}
          >
            ×
          </button>
        )}
      </div>

      {/* Options */}
      <div style={{ padding: `${APPROVAL_PADDING}px 0` }}>
        {/* Approve option */}
        <div
          className="flex items-center justify-end px-3 text-[13px] text-[#a3a3a3]"
          style={{ height: APPROVAL_OPTION_HEIGHT }}
        >
          <span>Approve</span>
          {/* Output port for Approve */}
          <div
            className="absolute w-3 h-3 bg-[#22c55e] border-2 border-[#1f1f1f] rounded-full cursor-crosshair z-10 hover:bg-[#4ade80] transition-colors"
            style={{
              right: -6,
              top: APPROVAL_HEADER_HEIGHT + APPROVAL_PADDING + (APPROVAL_OPTION_HEIGHT / 2) - 6,
            }}
            onMouseDown={(e) => handleOutputMouseDown(e, 0)}
            title="Connect Approve path"
          />
        </div>

        {/* Reject option */}
        <div
          className="flex items-center justify-end px-3 text-[13px] text-[#a3a3a3]"
          style={{ height: APPROVAL_OPTION_HEIGHT }}
        >
          <span>Reject</span>
          {/* Output port for Reject */}
          <div
            className="absolute w-3 h-3 bg-[#ef4444] border-2 border-[#1f1f1f] rounded-full cursor-crosshair z-10 hover:bg-[#f87171] transition-colors"
            style={{
              right: -6,
              top: APPROVAL_HEADER_HEIGHT + APPROVAL_PADDING + APPROVAL_OPTION_HEIGHT + (APPROVAL_OPTION_HEIGHT / 2) - 6,
            }}
            onMouseDown={(e) => handleOutputMouseDown(e, 1)}
            title="Connect Reject path"
          />
        </div>
      </div>

      {/* Input port on left side */}
      <div
        className="absolute w-3 h-3 bg-[#505050] border-2 border-[#1f1f1f] rounded-full cursor-crosshair z-10 hover:bg-[#6366f1] transition-colors"
        style={{
          left: -6,
          top: totalHeight / 2 - 6,
        }}
        onMouseUp={handleInputMouseUp}
        title="Input"
      />
    </div>
  );
};
