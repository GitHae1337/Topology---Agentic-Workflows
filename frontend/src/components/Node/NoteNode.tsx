import { useCallback, RefObject } from 'react';
import { useCanvasStore } from '../../store';
import { Node } from '../../types';
import { getNodeColor, getNodeIcon } from '../../constants/nodeTypes';

interface NoteNodeProps {
  node: Node;
  canvasRef: RefObject<HTMLDivElement>;
  mode?: 'canvas' | 'chat';
}

// Default dimensions for note nodes
const DEFAULT_WIDTH = 200;
const DEFAULT_HEIGHT = 100;

export const NoteNode = ({ node, canvasRef, mode = 'canvas' }: NoteNodeProps) => {
  const selectedNode = useCanvasStore(state => state.selectedNode);

  const setSelectedNode = useCanvasStore(state => state.setSelectedNode);
  const setSelectedTemplate = useCanvasStore(state => state.setSelectedTemplate);
  const setDraggingNode = useCanvasStore(state => state.setDraggingNode);
  const setDragOffset = useCanvasStore(state => state.setDragOffset);
  const deleteNode = useCanvasStore(state => state.deleteNode);
  const setResizing = useCanvasStore(state => state.setResizing);
  const setResizeStart = useCanvasStore(state => state.setResizeStart);

  const isSelected = selectedNode === node.id;
  const nodeColor = getNodeColor(node.type);

  // Get dimensions from config or use defaults
  const width = (node.config?.width as number) || DEFAULT_WIDTH;
  const height = (node.config?.height as number) || DEFAULT_HEIGHT;

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    // Don't start dragging if clicking on delete button or resize handle
    const target = e.target as HTMLElement;
    if (target.closest('.note-delete') || target.closest('.resize-handle')) return;

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

  const handleResizeStart = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    setResizing({ id: node.id, type: 'node' });
    setResizeStart({
      x: e.clientX,
      y: e.clientY,
      width: width,
      height: height,
    });
  }, [node.id, width, height, setResizing, setResizeStart]);

  const content = (node.config?.content as string) || '';

  return (
    <div
      className={`absolute bg-[#1f1f1f] border-2 rounded-xl cursor-grab select-none ${
        isSelected ? 'selection-ring' : ''
      }`}
      style={{
        left: node.x,
        top: node.y,
        width: width,
        height: height,
        borderColor: nodeColor,
        zIndex: 60,
      }}
      onMouseDown={handleMouseDown}
      onClick={handleClick}
    >
      {/* Header - compact with just icon and delete */}
      <div
        className="flex items-center gap-2 px-2.5 py-1.5 border-b border-[#333] rounded-t-[9px]"
        style={{ borderTopColor: nodeColor, borderTopWidth: '3px' }}
      >
        <div
          className="w-5 h-5 rounded-md flex items-center justify-center text-[10px] text-white flex-shrink-0"
          style={{ backgroundColor: nodeColor }}
        >
          {getNodeIcon(node.type)}
        </div>
        <span className="flex-1 text-xs text-[#a3a3a3] truncate">
          {content ? content.split('\n')[0].substring(0, 30) : 'Click to add note...'}
        </span>
        {mode === 'canvas' && (
          <button
            className="note-delete bg-transparent border-none text-[#666] text-sm cursor-pointer opacity-0 hover:opacity-100 hover:text-[#ef4444] transition-opacity"
            onClick={handleDelete}
            style={{ opacity: isSelected ? 1 : undefined }}
          >
            ×
          </button>
        )}
      </div>

      {/* Content area - displays the note text */}
      <div
        className="px-2.5 py-2 overflow-hidden"
        style={{ height: height - 36 }} // Subtract header height
      >
        <span className="text-xs text-[#d4d4d4] whitespace-pre-wrap break-words leading-relaxed">
          {content || <span className="text-[#666] italic">Click to add note...</span>}
        </span>
      </div>

      {/* Resize handle */}
      <div
        className="resize-handle absolute bottom-0 right-0 w-4 h-4 cursor-se-resize rounded-br-[9px] hover:opacity-100"
        style={{
          background: 'linear-gradient(135deg, transparent 50%, rgba(255,255,255,0.2) 50%)',
        }}
        onMouseDown={handleResizeStart}
      />
    </div>
  );
};
