import { useCallback, RefObject } from 'react';
import { useCanvasStore } from '../../store';
import { Node } from '../../types';
import { getNodeColor, getNodeIcon } from '../../constants/nodeTypes';

interface CanvasNodeProps {
  node: Node;
  canvasRef: RefObject<HTMLDivElement>;
  mode?: 'canvas' | 'chat';
}

export const CanvasNode = ({ node, canvasRef, mode = 'canvas' }: CanvasNodeProps) => {
  const selectedNode = useCanvasStore(state => state.selectedNode);
  const connecting = useCanvasStore(state => state.connecting);
  const internalConnecting = useCanvasStore(state => state.internalConnecting);
  const topologyTemplates = useCanvasStore(state => state.topologyTemplates);

  // Check if the node is in a topology that auto-connects edges (Centralized/Hierarchical/Mesh)
  const currentTopology = node.topologyId
    ? topologyTemplates.find(t => t.id === node.topologyId)
    : null;
  const isAutoConnectTopology = currentTopology?.type === 'centralized' || currentTopology?.type === 'hierarchical' || currentTopology?.type === 'mesh';

  const setSelectedNode = useCanvasStore(state => state.setSelectedNode);
  const setSelectedTemplate = useCanvasStore(state => state.setSelectedTemplate);
  const setDraggingNode = useCanvasStore(state => state.setDraggingNode);
  const setDragOffset = useCanvasStore(state => state.setDragOffset);
  const deleteNode = useCanvasStore(state => state.deleteNode);
  const setConnecting = useCanvasStore(state => state.setConnecting);
  const addConnection = useCanvasStore(state => state.addConnection);
  const setInternalConnecting = useCanvasStore(state => state.setInternalConnecting);
  const addInternalEdge = useCanvasStore(state => state.addInternalEdge);

  const isSelected = selectedNode === node.id;
  const nodeColor = node.topologyColor || getNodeColor(node.type);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.button !== 0) return;
    // Belt-and-suspenders: if mousedown originated from a connection dot
    // (which has data-dot="true"), skip node drag. This catches cases where
    // the dot's own stopPropagation didn't fire for whatever reason.
    const target = e.target as HTMLElement;
    if (target?.dataset?.dot === 'true') return;
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

  // Workflow-level connection handlers.
  // To support drawing connections in either direction (output→input OR
  // input→output) but always store them in canonical output→input direction,
  // we track which dot kind (input vs output) the user started from via
  // `connectingFromInput` in the store, and swap source/target at mouseup
  // when the start was an input dot.
  const handleConnectionStartFromOutput = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    setConnecting(node.id, 'node', null, false);
  }, [node.id, setConnecting]);

  const handleConnectionStartFromInput = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    setConnecting(node.id, 'node', null, true);
  }, [node.id, setConnecting]);

  const connectingFromPort = useCanvasStore(state => state.connectingFromPort);
  const connectingFromInput = useCanvasStore(state => state.connectingFromInput);

  const handleConnectionEndAtInput = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    if (connecting && connecting !== node.id) {
      if (connectingFromInput) {
        // Both sides input → invalid (no direction). Skip.
        setConnecting(null, null);
        return;
      }
      // Normal: source = output side, target = this input.
      addConnection(connecting, node.id, 'node', connectingFromPort ?? undefined);
    }
    setConnecting(null, null);
  }, [connecting, connectingFromPort, connectingFromInput, node.id, addConnection, setConnecting]);

  const handleConnectionEndAtOutput = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    if (connecting && connecting !== node.id) {
      if (!connectingFromInput) {
        // Both sides output → invalid. Skip.
        setConnecting(null, null);
        return;
      }
      // Reversed: source dot was input, end is output → swap so canonical
      // direction (output → input) is preserved.
      addConnection(node.id, connecting, 'node');
    }
    setConnecting(null, null);
  }, [connecting, connectingFromInput, node.id, addConnection, setConnecting]);

  // Internal topology connection handlers
  const handleInternalConnectionStart = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    if (node.topologyId) {
      setInternalConnecting({ agentId: node.id, templateId: node.topologyId });
    }
  }, [node.id, node.topologyId, setInternalConnecting]);

  const handleInternalConnectionEnd = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    if (internalConnecting && internalConnecting.agentId !== node.id && node.topologyId === internalConnecting.templateId) {
      addInternalEdge(internalConnecting.templateId, internalConnecting.agentId, node.id);
    }
    setInternalConnecting(null);
  }, [internalConnecting, node.id, node.topologyId, addInternalEdge, setInternalConnecting]);

  return (
    <div
      className={`absolute w-40 bg-[#1f1f1f] border-2 rounded-xl cursor-grab select-none node-transition ${
        isSelected ? 'selection-ring' : ''
      } ${node.topologyId ? 'border-[3px]' : ''}`}
      style={{
        left: node.x,
        top: node.y,
        borderColor: nodeColor,
        boxShadow: node.topologyColor ? `0 0 0 3px ${node.topologyColor}40` : undefined,
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
          style={{ backgroundColor: getNodeColor(node.type) }}
        >
          {getNodeIcon(node.type)}
        </div>
        <span className="flex-1 text-[13px] font-medium truncate">{node.name}</span>
        {node.topologyRole && (
          <span className="text-[9px] bg-white/15 px-1.5 py-0.5 rounded-lg">{node.topologyRole}</span>
        )}
        {/* Hide delete button on Start/End — those are trial-permanent. */}
        {mode === 'canvas' && node.type !== 'start' && node.type !== 'end' && (
          <button
            className="bg-transparent border-none text-[#666] text-base cursor-pointer opacity-0 hover:opacity-100 hover:text-[#ef4444] transition-opacity"
            onClick={handleDelete}
            style={{ opacity: isSelected ? 1 : undefined }}
          >
            ×
          </button>
        )}
      </div>

      {/* Content for agents outside topology */}
      {node.type === 'agent' && !node.topologyId && (
        <div className="px-3 py-2.5">
          <span className="text-xs text-[#666]">Drag into topology</span>
        </div>
      )}

      {/* Connection dots for agents inside topology (hidden for Centralized/Hierarchical which auto-connect) */}
      {node.type === 'agent' && node.topologyId && !isAutoConnectTopology && (
        <>
          {/* Internal input dot on left */}
          <div
            data-dot="true"
            className="absolute w-3 h-3 bg-[#505050] border-2 border-[#1f1f1f] rounded-full cursor-crosshair -left-1.5 top-1/2 -translate-y-1/2 z-10 hover:bg-[#6366f1] transition-colors"
            onMouseUp={handleInternalConnectionEnd}
            title="Connect from another agent"
          />
          {/* Internal output dot on right */}
          <div
            data-dot="true"
            className="absolute w-3 h-3 bg-[#505050] border-2 border-[#1f1f1f] rounded-full cursor-crosshair -right-1.5 top-1/2 -translate-y-1/2 z-10 hover:bg-[#6366f1] transition-colors"
            onMouseDown={handleInternalConnectionStart}
            title="Connect to another agent"
          />
        </>
      )}

      {/* Connection dots for nodes outside topology */}
      {/* Note nodes don't have connection dots - they're just annotations */}
      {/* Output dot on the right (for non-end/non-note nodes) — both
          mousedown (start) and mouseup (end if user dragged from input). */}
      {node.type !== 'end' && node.type !== 'note' && !node.topologyId && (
        <div
          data-dot="true"
          className="absolute w-3 h-3 bg-[#404040] border-2 border-[#1f1f1f] rounded-full cursor-crosshair -right-1.5 top-1/2 -translate-y-1/2 z-10 hover:bg-[#6366f1] transition-colors"
          onMouseDown={handleConnectionStartFromOutput}
          onMouseUp={handleConnectionEndAtOutput}
        />
      )}
      {/* Input dot on the left (for non-start/non-note nodes) — both
          mousedown (start, will be swapped) and mouseup (normal end). */}
      {node.type !== 'start' && node.type !== 'note' && !node.topologyId && (
        <div
          data-dot="true"
          className="absolute w-3 h-3 bg-[#404040] border-2 border-[#1f1f1f] rounded-full cursor-crosshair -left-1.5 top-1/2 -translate-y-1/2 z-10 hover:bg-[#6366f1] transition-colors"
          onMouseDown={handleConnectionStartFromInput}
          onMouseUp={handleConnectionEndAtInput}
        />
      )}
    </div>
  );
};
