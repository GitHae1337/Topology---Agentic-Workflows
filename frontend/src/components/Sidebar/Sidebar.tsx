import { useState, useRef, useEffect } from 'react';
import { NodePalette } from './NodePalette';
import { TopologyPalette } from './TopologyPalette';
import { useCanvasStore } from '../../store';

export const Sidebar = () => {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const workflowName = useCanvasStore(state => state.workflowName);
  const setWorkflowName = useCanvasStore(state => state.setWorkflowName);

  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [isEditing]);

  const handleNameSubmit = () => {
    setIsEditing(false);
    if (!workflowName.trim()) {
      setWorkflowName('New agent');
    }
  };

  return (
    <div className="relative flex flex-shrink-0">
      {/* Sidebar Content */}
      <div
        className={`bg-[#141414] border-r border-[#262626] flex flex-col overflow-hidden transition-all duration-300 ease-in-out ${
          isCollapsed ? 'w-0 border-r-0' : 'w-60'
        }`}
      >
        <div className="w-60">
          {/* Header */}
          <div className="flex items-center px-4 py-4 border-b border-[#262626]">
            {isEditing ? (
              <input
                ref={inputRef}
                type="text"
                className="text-lg flex-1 bg-transparent border-b border-[#6366f1] outline-none text-white"
                value={workflowName}
                onChange={(e) => setWorkflowName(e.target.value)}
                onBlur={handleNameSubmit}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleNameSubmit();
                  if (e.key === 'Escape') {
                    setIsEditing(false);
                    if (!workflowName.trim()) setWorkflowName('New agent');
                  }
                }}
              />
            ) : (
              <h1
                className="text-lg flex-1 cursor-pointer hover:text-[#a3a3a3] transition-colors truncate"
                onClick={() => setIsEditing(true)}
                title="Click to edit workflow name"
              >
                {workflowName}
              </h1>
            )}
          </div>

          {/* Scrollable Content */}
          <div className="flex-1 p-3 overflow-hidden">
            <NodePalette />
            <TopologyPalette />
          </div>
        </div>
      </div>

      {/* Toggle Button */}
      <button
        onClick={() => setIsCollapsed(!isCollapsed)}
        className={`absolute top-1/2 -translate-y-1/2 w-5 h-10 bg-[#262626] hover:bg-[#333] border border-[#404040] rounded-r-md flex items-center justify-center cursor-pointer text-[#a3a3a3] hover:text-white transition-all duration-300 ease-in-out z-10 ${
          isCollapsed ? 'left-0' : 'left-60'
        }`}
      >
        {isCollapsed ? '›' : '‹'}
      </button>
    </div>
  );
};
