import { useRef, useCallback, useState, useEffect } from 'react';
import { useCanvasStore, useSessionStore } from '../../store';
import { ConnectionsLayer } from './ConnectionsLayer';
import { InternalEdgesOverlay } from './InternalEdgesOverlay';
import { CanvasNode } from '../Node/CanvasNode';
import { IfElseNode } from '../Node/IfElseNode';
import { NoteNode } from '../Node/NoteNode';
import { ApprovalNode } from '../Node/ApprovalNode';
import { TopologyTemplate } from '../TopologyTemplate/TopologyTemplate';
import { isInsideTopology } from '../../utils/geometry';
import { getTopologyDefinition } from '../../constants/topologies';

interface CanvasProps {
  mode?: 'canvas' | 'chat';
}

export const Canvas = ({ mode = 'canvas' }: CanvasProps) => {
  const canvasRef = useRef<HTMLDivElement>(null);
  const [isSelecting, setIsSelecting] = useState(false);
  const [mousePos, setMousePos] = useState<{ x: number; y: number } | null>(null);

  const nodes = useCanvasStore(state => state.nodes);
  const topologyTemplates = useCanvasStore(state => state.topologyTemplates);
  const connecting = useCanvasStore(state => state.connecting);
  const internalConnecting = useCanvasStore(state => state.internalConnecting);
  const draggingNode = useCanvasStore(state => state.draggingNode);
  const draggingTopology = useCanvasStore(state => state.draggingTopology);
  const dragOffset = useCanvasStore(state => state.dragOffset);
  const resizing = useCanvasStore(state => state.resizing);
  const resizeStart = useCanvasStore(state => state.resizeStart);
  const selectionBox = useCanvasStore(state => state.selectionBox);
  const selectedNodes = useCanvasStore(state => state.selectedNodes);

  const setSelectedNodes = useCanvasStore(state => state.setSelectedNodes);
  const clearSelection = useCanvasStore(state => state.clearSelection);
  const setSelectionBox = useCanvasStore(state => state.setSelectionBox);
  const selectNodesInBox = useCanvasStore(state => state.selectNodesInBox);
  const moveSelectedNodes = useCanvasStore(state => state.moveSelectedNodes);
  const setSelectedTemplate = useCanvasStore(state => state.setSelectedTemplate);
  const setDraggingNode = useCanvasStore(state => state.setDraggingNode);
  const setDraggingTopology = useCanvasStore(state => state.setDraggingTopology);
  const moveNode = useCanvasStore(state => state.moveNode);
  const moveTopology = useCanvasStore(state => state.moveTopology);
  const setResizing = useCanvasStore(state => state.setResizing);
  const resizeTopology = useCanvasStore(state => state.resizeTopology);
  const resizeNode = useCanvasStore(state => state.resizeNode);
  const setInternalConnecting = useCanvasStore(state => state.setInternalConnecting);
  const setConnecting = useCanvasStore(state => state.setConnecting);
  const addNode = useCanvasStore(state => state.addNode);
  const addTopologyTemplate = useCanvasStore(state => state.addTopologyTemplate);
  const addAgentToTopology = useCanvasStore(state => state.addAgentToTopology);
  const removeAgentFromTopology = useCanvasStore(state => state.removeAgentFromTopology);
  const setRolePopup = useCanvasStore(state => state.setRolePopup);
  const deleteNode = useCanvasStore(state => state.deleteNode);

  // Keyboard event handler for deleting selected nodes
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Check if user is typing in an input field
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
        return;
      }

      // Backspace or Delete key to remove selected nodes
      if (e.key === 'Backspace' || e.key === 'Delete') {
        e.preventDefault();
        // Don't allow deletion in chat mode
        if (mode === 'chat') return;
        selectedNodes.forEach(nodeId => {
          deleteNode(nodeId);
        });
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectedNodes, deleteNode, mode]);

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;

    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    // Track mouse position while connecting (workflow-level or internal topology)
    if (connecting || internalConnecting) {
      setMousePos({ x, y });
    }

    // Handle resizing
    if (resizing) {
      const deltaX = e.clientX - resizeStart.x;
      const deltaY = e.clientY - resizeStart.y;

      if (resizing.type === 'node') {
        // Note node resizing with smaller minimums
        const newWidth = Math.max(120, resizeStart.width + deltaX);
        const newHeight = Math.max(60, resizeStart.height + deltaY);
        resizeNode(resizing.id, newWidth, newHeight);
      } else {
        // Topology resizing
        const newWidth = Math.max(250, resizeStart.width + deltaX);
        const newHeight = Math.max(180, resizeStart.height + deltaY);
        resizeTopology(resizing.id, newWidth, newHeight);
      }
      return;
    }

    // Handle node dragging
    if (draggingNode) {
      const newX = Math.max(0, x - dragOffset.x);
      const newY = Math.max(0, y - dragOffset.y);
      moveNode(draggingNode, newX, newY);
      return;
    }

    // Handle topology dragging
    if (draggingTopology) {
      const newX = x - dragOffset.x;
      const newY = y - dragOffset.y;
      moveTopology(draggingTopology, newX, newY);
    }
  }, [connecting, internalConnecting, draggingNode, draggingTopology, resizing, dragOffset, resizeStart, moveNode, moveTopology, resizeTopology, resizeNode]);

  const handleMouseUp = useCallback((e: React.MouseEvent) => {
    // Check if dropping agent into topology
    if (draggingNode) {
      const node = nodes.find(n => n.id === draggingNode);
      if (node && node.type === 'agent' && !node.topologyId) {
        for (const template of topologyTemplates) {
          if (isInsideTopology(node.x, node.y, template)) {
            const topo = getTopologyDefinition(template.type);
            if (!topo) continue;

            if (topo.hasRoles) {
              // Show role selection popup
              setRolePopup({
                agentId: node.id,
                templateId: template.id,
                roles: topo.roles,
                x: e.clientX,
                y: e.clientY,
              });
            } else {
              // Directly add to topology
              addAgentToTopology(node.id, template.id, null);
            }
            break;
          }
        }
      }

      // Check if dragging agent out of topology
      if (node && node.topologyId) {
        const template = topologyTemplates.find(t => t.id === node.topologyId);
        if (template && !isInsideTopology(node.x, node.y, template)) {
          removeAgentFromTopology(node.id);
        }
      }
    }

    setDraggingNode(null);
    setDraggingTopology(null);
    setResizing(null);
    setConnecting(null, null);
    setMousePos(null);
  }, [draggingNode, nodes, topologyTemplates, setDraggingNode, setDraggingTopology, setResizing, setConnecting, addAgentToTopology, removeAgentFromTopology, setRolePopup]);

  const handleCanvasClick = () => {
    clearSelection();
    setInternalConnecting(null);
  };

  // Time-to-First-Action capture. Runs on the FIRST mousedown OR drop anywhere
  // inside the canvas (including child nodes / topologies via capture phase).
  // markFirstClick is internally idempotent — only the first call is recorded.
  const handleFirstInteractionCapture = useCallback(() => {
    useSessionStore.getState().markFirstClick();
  }, []);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;

    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    // Check for node drop
    const nodeTypeData = e.dataTransfer.getData('nodeType');
    if (nodeTypeData) {
      const nodeType = JSON.parse(nodeTypeData);
      addNode(nodeType.type, x - 80, y - 30);
      return;
    }

    // Check for topology drop
    const topologyTypeData = e.dataTransfer.getData('topologyType');
    if (topologyTypeData) {
      const topoType = JSON.parse(topologyTypeData);
      addTopologyTemplate(topoType.id, x - 100, y - 50);
    }
  };

  return (
    <div
      ref={canvasRef}
      className="flex-1 relative overflow-auto canvas-grid"
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
      onClick={handleCanvasClick}
      onMouseDownCapture={handleFirstInteractionCapture}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
      onDropCapture={handleFirstInteractionCapture}
    >
      {/* Topology Templates (without internal edges) */}
      {topologyTemplates.map(template => (
        <TopologyTemplate key={template.id} template={template} canvasRef={canvasRef} mode={mode} />
      ))}

      {/* Nodes */}
      {nodes.map(node => {
        if (node.type === 'ifelse') {
          return <IfElseNode key={node.id} node={node} canvasRef={canvasRef} mode={mode} />;
        }
        if (node.type === 'note') {
          return <NoteNode key={node.id} node={node} canvasRef={canvasRef} mode={mode} />;
        }
        if (node.type === 'approval') {
          return <ApprovalNode key={node.id} node={node} canvasRef={canvasRef} mode={mode} />;
        }
        return <CanvasNode key={node.id} node={node} canvasRef={canvasRef} mode={mode} />;
      })}

      {/* SVG Connections Layer - rendered AFTER nodes to appear on top */}
      <ConnectionsLayer mousePos={mousePos} />

      {/* Internal Edges Overlay - rendered AFTER nodes to appear on top */}
      <InternalEdgesOverlay topologyTemplates={topologyTemplates} mousePos={mousePos} />
    </div>
  );
};
