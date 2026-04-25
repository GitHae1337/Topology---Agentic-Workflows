import { useState, useCallback } from 'react';
import { Canvas } from './components/Canvas';
import { Sidebar } from './components/Sidebar';
import { ConfigPanel } from './components/ConfigPanel';
import { ChatPanel } from './components/ChatPanel';
import { ChatInput } from './components/ChatInput';
import { RolePopup } from './components/common/RolePopup';
import { DragPreview } from './components/common/DragPreview';
import { useCanvasStore } from './store';
import { IfElseCondition } from './types';
import { getTopologyDefinition } from './constants/topologies';
import { logsApi } from './api/workflow';

// Hook to get edge error from store
const useEdgeError = () => {
  const edgeError = useCanvasStore(state => state.edgeError);
  const setEdgeError = useCanvasStore(state => state.setEdgeError);
  return { edgeError, setEdgeError };
};

type AppMode = 'canvas' | 'chat';

interface ValidationError {
  message: string;
  details: string;
}

function App() {
  const [mode, setMode] = useState<AppMode>('canvas');
  const [validationError, setValidationError] = useState<ValidationError | null>(null);
  const nodes = useCanvasStore(state => state.nodes);
  const connections = useCanvasStore(state => state.connections);
  const topologyTemplates = useCanvasStore(state => state.topologyTemplates);
  const clearCanvas = useCanvasStore(state => state.clearCanvas);
  const currentChat = useCanvasStore(state => state.currentChat);
  const clearCurrentChat = useCanvasStore(state => state.clearCurrentChat);
  const workflowName = useCanvasStore(state => state.workflowName);
  const { edgeError, setEdgeError } = useEdgeError();

  // Save logs and clear canvas
  const handleClearCanvas = useCallback(async () => {
    const { messages, logEntries, workflowId } = currentChat;

    // Save logs if there are messages
    if (messages.length > 0) {
      console.log('[App] Saving logs before clearing canvas');
      const chatId = `${Date.now()}`;
      const serializedLogEntries = logEntries.map(entry => ({
        ...entry,
        timestamp: entry.timestamp instanceof Date ? entry.timestamp.toISOString() : entry.timestamp,
      }));

      await logsApi.save({
        chatId,
        workflowName: workflowName || 'Untitled',
        messages,
        logEntries: serializedLogEntries,
        workflowId,
        createdAt: new Date().toISOString(),
      });
    }

    // Clear both canvas and chat
    clearCanvas();
    clearCurrentChat();
    console.log('[App] Canvas and chat cleared');
  }, [currentChat, workflowName, clearCanvas, clearCurrentChat]);

  // Validate workflow before switching to chat mode
  const validateWorkflow = (): ValidationError | null => {
    // Check for Start node
    const hasStartNode = nodes.some(node => node.type === 'start');
    if (!hasStartNode) {
      return {
        message: 'Fix workflow issues before continuing',
        details: 'Workflow requires a Start node. Add a Start node to begin the workflow.',
      };
    }

    // Check for End node
    const hasEndNode = nodes.some(node => node.type === 'end');
    if (!hasEndNode) {
      return {
        message: 'Fix workflow issues before continuing',
        details: 'Workflow requires an End node. Add an End node to complete the workflow.',
      };
    }

    // Check If/Else conditions
    for (const node of nodes) {
      if (node.type === 'ifelse') {
        const conditions = (node.config?.conditions as IfElseCondition[]) || [];
        for (const condition of conditions) {
          if (!condition.condition || condition.condition.trim() === '') {
            return {
              message: 'Fix workflow issues before continuing',
              details: `If / else node "${node.name}" requires a condition expression. Enter a condition before previewing or publishing.`,
            };
          }
        }
      }
    }

    // Check for disconnected topologies
    if (topologyTemplates.length > 0) {
      const startNode = nodes.find(n => n.type === 'start');
      const endNode = nodes.find(n => n.type === 'end');

      if (startNode && endNode) {
        // Find all entities reachable from Start
        const reachableFromStart = new Set<string>();
        const queue = [startNode.id];
        while (queue.length > 0) {
          const current = queue.shift()!;
          if (reachableFromStart.has(current)) continue;
          reachableFromStart.add(current);
          connections
            .filter(c => c.from === current)
            .forEach(c => queue.push(c.to));
        }

        // Find all entities that can reach End (reverse traversal)
        const canReachEnd = new Set<string>();
        const reverseQueue = [endNode.id];
        while (reverseQueue.length > 0) {
          const current = reverseQueue.shift()!;
          if (canReachEnd.has(current)) continue;
          canReachEnd.add(current);
          connections
            .filter(c => c.to === current)
            .forEach(c => reverseQueue.push(c.from));
        }

        // Check each topology
        for (const template of topologyTemplates) {
          const isReachableFromStart = reachableFromStart.has(template.id);
          const canReachEndNode = canReachEnd.has(template.id);

          if (!isReachableFromStart && !canReachEndNode) {
            return {
              message: 'Fix workflow issues before continuing',
              details: `Topology "${template.name}" is not connected to the workflow. Connect it to Start and End nodes.`,
            };
          } else if (!isReachableFromStart) {
            return {
              message: 'Fix workflow issues before continuing',
              details: `Topology "${template.name}" is not reachable from the Start node. Add a connection from Start or another node.`,
            };
          } else if (!canReachEndNode) {
            return {
              message: 'Fix workflow issues before continuing',
              details: `Topology "${template.name}" cannot reach the End node. Add a connection to End or another node.`,
            };
          }
        }
      }
    }

    // Check for topologies without agents
    for (const template of topologyTemplates) {
      const agentsInTopology = nodes.filter(n => n.topologyId === template.id);
      if (agentsInTopology.length === 0) {
        return {
          message: 'Fix workflow issues before continuing',
          details: `Topology "${template.name}" has no agents. Add at least one agent to the topology.`,
        };
      }
    }

    // Check for topologies that require a start agent (P2P, Mesh, Cyclic)
    for (const template of topologyTemplates) {
      const topoDef = getTopologyDefinition(template.type);
      if (topoDef?.needsStartAgent && !template.startAgentId) {
        return {
          message: 'Fix workflow issues before continuing',
          details: `Topology "${template.name}" requires a start agent. Select a start agent in the topology settings.`,
        };
      }
    }

    return null;
  };

  const handleChatModeClick = () => {
    const error = validateWorkflow();
    if (error) {
      setValidationError(error);
    } else {
      setValidationError(null);
      setMode('chat');
    }
  };

  return (
    <div className="flex h-screen bg-[#0a0a0a] text-white">
      {/* Left Sidebar - hidden in chat mode */}
      {mode === 'canvas' && <Sidebar />}

      {/* Main Canvas Area */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Top Bar */}
        <div className="flex justify-between items-center px-5 py-3 bg-[#171717] border-b border-[#262626] flex-shrink-0">
          {/* Left spacer */}
          <div className="w-16"></div>

          {/* Mode Toggle - center */}
          <div className="flex bg-[#262626] rounded-full p-1">
            <button
              onClick={() => setMode('canvas')}
              className={`w-9 h-9 rounded-full flex items-center justify-center transition-colors ${
                mode === 'canvas' ? 'bg-[#404040] text-white' : 'text-[#888] hover:text-white'
              }`}
              title="Canvas Mode"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/>
                <path d="m15 5 4 4"/>
              </svg>
            </button>
            <button
              onClick={handleChatModeClick}
              className={`w-9 h-9 rounded-full flex items-center justify-center transition-colors ${
                mode === 'chat' ? 'bg-[#404040] text-white' : 'text-[#888] hover:text-white'
              }`}
              title="Chat Mode"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                <path d="M8 5v14l11-7z"/>
              </svg>
            </button>
          </div>

          {/* Clear button - right (only in canvas mode) */}
          {mode === 'canvas' ? (
            <button
              onClick={handleClearCanvas}
              className="px-3 py-1.5 bg-[#262626] hover:bg-[#333] border border-[#404040] rounded-lg text-[#a3a3a3] hover:text-white text-sm cursor-pointer transition-colors"
              title="Clear canvas"
            >
              Clear
            </button>
          ) : (
            <div className="w-16"></div>
          )}
        </div>

        {/* Validation Error Banner */}
        {validationError && (
          <div className="bg-[#3d1f1f] border-b border-[#5c2b2b] px-5 py-3 flex items-start gap-3 flex-shrink-0">
            <svg className="w-5 h-5 text-[#f87171] flex-shrink-0 mt-0.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
              <line x1="12" y1="9" x2="12" y2="13"/>
              <line x1="12" y1="17" x2="12.01" y2="17"/>
            </svg>
            <div className="flex-1">
              <p className="text-sm font-medium text-white">{validationError.message}</p>
              <p className="text-sm text-[#f87171] mt-0.5">• {validationError.details}</p>
            </div>
            <button
              onClick={() => setValidationError(null)}
              className="px-4 py-1.5 bg-[#dc2626] hover:bg-[#b91c1c] text-white text-sm font-medium rounded transition-colors"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Edge Error Banner (for loop prevention in sequential topology) */}
        {edgeError && (
          <div className="bg-[#3d1f1f] border-b border-[#5c2b2b] px-5 py-3 flex items-start gap-3 flex-shrink-0">
            <svg className="w-5 h-5 text-[#f87171] flex-shrink-0 mt-0.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
              <line x1="12" y1="9" x2="12" y2="13"/>
              <line x1="12" y1="17" x2="12.01" y2="17"/>
            </svg>
            <div className="flex-1">
              <p className="text-sm font-medium text-white">{edgeError.message}</p>
              <p className="text-sm text-[#f87171] mt-0.5">• {edgeError.details}</p>
            </div>
            <button
              onClick={() => setEdgeError(null)}
              className="px-4 py-1.5 bg-[#dc2626] hover:bg-[#b91c1c] text-white text-sm font-medium rounded transition-colors"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Canvas - with overlay to block interaction in chat mode */}
        <div className="flex-1 flex flex-col relative overflow-hidden">
          <Canvas mode={mode} />
          {mode === 'chat' && (
            <div className="absolute inset-0 bg-transparent cursor-not-allowed z-10" />
          )}
        </div>

        {/* HIDDEN: Chat Input - only in canvas mode */}
        {/* {mode === 'canvas' && <ChatInput />} */}
      </div>

      {/* Right Panel - Config or Chat based on mode */}
      {mode === 'canvas' ? <ConfigPanel /> : <ChatPanel />}

      {/* Role Selection Popup - only in canvas mode */}
      {mode === 'canvas' && <RolePopup />}

      {/* Drag Preview - only in canvas mode */}
      {mode === 'canvas' && <DragPreview />}
    </div>
  );
}

export default App;
