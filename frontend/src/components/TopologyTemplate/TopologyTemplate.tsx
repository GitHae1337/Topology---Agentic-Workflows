import { useCallback, RefObject } from 'react';
import { useCanvasStore } from '../../store';
import { TopologyTemplate as TopologyTemplateType } from '../../types';
import { getTopologyDefinition } from '../../constants/topologies';
import { PlaceholderVisualization } from './PlaceholderVisualization';

interface TopologyTemplateProps {
  template: TopologyTemplateType;
  canvasRef: RefObject<HTMLDivElement>;
  mode?: 'canvas' | 'chat';
}

export const TopologyTemplate = ({ template, canvasRef, mode = 'canvas' }: TopologyTemplateProps) => {
  const selectedTemplate = useCanvasStore(state => state.selectedTemplate);
  const connecting = useCanvasStore(state => state.connecting);

  const setSelectedTemplate = useCanvasStore(state => state.setSelectedTemplate);
  const setSelectedNode = useCanvasStore(state => state.setSelectedNode);
  const setDraggingTopology = useCanvasStore(state => state.setDraggingTopology);
  const setDragOffset = useCanvasStore(state => state.setDragOffset);
  const setResizing = useCanvasStore(state => state.setResizing);
  const setResizeStart = useCanvasStore(state => state.setResizeStart);
  const deleteTopologyTemplate = useCanvasStore(state => state.deleteTopologyTemplate);
  const setConnecting = useCanvasStore(state => state.setConnecting);
  const addConnection = useCanvasStore(state => state.addConnection);
  const getAgentsInTopology = useCanvasStore(state => state.getAgentsInTopology);

  const topo = getTopologyDefinition(template.type);
  const isSelected = selectedTemplate === template.id;
  const hasAgents = getAgentsInTopology(template.id).length > 0;

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    // Don't start dragging if clicking on delete button, resize handle, or
    // a connection dot (data-dot="true"). The dots have their own onMouseDown
    // (output) or onMouseUp (input); template drag would hijack input dot.
    const target = e.target as HTMLElement;
    if (target.closest('.template-delete') || target.closest('.resize-handle')) return;
    if (target?.dataset?.dot === 'true') return;

    e.stopPropagation();
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;

    setDraggingTopology(template.id);
    setDragOffset({
      x: e.clientX - rect.left - template.x,
      y: e.clientY - rect.top - template.y,
    });
    setSelectedTemplate(template.id);
    setSelectedNode(null);
  }, [template.id, template.x, template.y, canvasRef, setDraggingTopology, setDragOffset, setSelectedTemplate, setSelectedNode]);

  const handleClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    setSelectedTemplate(template.id);
    setSelectedNode(null);
  }, [template.id, setSelectedTemplate, setSelectedNode]);

  const handleDelete = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    deleteTopologyTemplate(template.id);
  }, [template.id, deleteTopologyTemplate]);

  const handleResizeStart = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    setResizing({ id: template.id });
    setResizeStart({
      x: e.clientX,
      y: e.clientY,
      width: template.width,
      height: template.height,
    });
  }, [template.id, template.width, template.height, setResizing, setResizeStart]);

  // Bidirectional connection drawing — start from either dot, but always
  // canonicalize to output→input direction at mouseup (swap if started from
  // an input dot). Mirrors the CanvasNode logic.
  const handleConnectionStartFromOutput = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    setConnecting(template.id, 'template', null, false);
  }, [template.id, setConnecting]);

  const handleConnectionStartFromInput = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    setConnecting(template.id, 'template', null, true);
  }, [template.id, setConnecting]);

  const connectingFromPort = useCanvasStore(state => state.connectingFromPort);
  const connectingFromInput = useCanvasStore(state => state.connectingFromInput);

  const handleConnectionEndAtInput = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    if (connecting && connecting !== template.id) {
      if (connectingFromInput) {
        setConnecting(null, null);
        return;
      }
      addConnection(connecting, template.id, 'template', connectingFromPort ?? undefined);
    }
    setConnecting(null, null);
  }, [connecting, connectingFromPort, connectingFromInput, template.id, addConnection, setConnecting]);

  const handleConnectionEndAtOutput = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    if (connecting && connecting !== template.id) {
      if (!connectingFromInput) {
        setConnecting(null, null);
        return;
      }
      addConnection(template.id, connecting, 'template');
    }
    setConnecting(null, null);
  }, [connecting, connectingFromInput, template.id, addConnection, setConnecting]);

  return (
    <div
      className={`absolute bg-[rgba(30,30,35,0.95)] border-2 border-dashed rounded-2xl cursor-grab ${
        isSelected ? 'selection-ring' : ''
      }`}
      style={{
        left: template.x,
        top: template.y,
        borderColor: template.color,
        width: template.width,
        height: template.height + 40, // Account for header
      }}
      onMouseDown={handleMouseDown}
      onClick={handleClick}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-3.5 py-2.5 rounded-t-[14px] text-white gap-2"
        style={{ backgroundColor: template.color }}
      >
        <span className="text-[13px] font-semibold flex-1">{template.name} Topology</span>
        <span className="text-xs opacity-80">
          {topo?.edgeType === 'bidirectional' ? '↔' : '→'}
        </span>
        {mode === 'canvas' && (
          <button
            className="template-delete bg-transparent border-none text-white/60 text-lg cursor-pointer hover:text-white"
            onClick={handleDelete}
          >
            ×
          </button>
        )}
      </div>

      {/* Body */}
      <div className="relative p-2.5 overflow-visible" style={{ height: template.height }}>
        {/* Placeholder when no agents */}
        {!hasAgents && (
          <PlaceholderVisualization template={template} />
        )}
        {/* Internal edges are now rendered in Canvas via InternalEdgesOverlay */}
      </div>

      {/* Connection dots - Input on left, Output on right.
          Both dots support mousedown (start) and mouseup (end). When the user
          drags from input → output, source/target are swapped at mouseup so
          stored direction is always output → input. */}
      <div
        data-dot="true"
        className="absolute w-3 h-3 bg-[#404040] border-2 border-[#1f1f1f] rounded-full cursor-crosshair -left-1.5 top-1/2 -translate-y-1/2 z-10 hover:bg-[#6366f1] transition-colors"
        onMouseDown={handleConnectionStartFromInput}
        onMouseUp={handleConnectionEndAtInput}
      />
      <div
        data-dot="true"
        className="absolute w-3 h-3 bg-[#404040] border-2 border-[#1f1f1f] rounded-full cursor-crosshair -right-1.5 top-1/2 -translate-y-1/2 z-10 hover:bg-[#6366f1] transition-colors"
        onMouseDown={handleConnectionStartFromOutput}
        onMouseUp={handleConnectionEndAtOutput}
      />


      {/* Resize handle */}
      <div
        className="resize-handle absolute bottom-0 right-0 w-4 h-4 cursor-se-resize rounded-br-[14px] hover:opacity-100"
        style={{
          background: 'linear-gradient(135deg, transparent 50%, rgba(255,255,255,0.3) 50%)',
        }}
        onMouseDown={handleResizeStart}
      />
    </div>
  );
};
