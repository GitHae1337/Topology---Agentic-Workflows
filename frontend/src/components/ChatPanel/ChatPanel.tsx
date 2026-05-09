import { useState, useRef, useCallback, useEffect } from 'react';
import { useCanvasStore, ChatSession } from '../../store/canvasStore';
import { useSessionStore } from '../../store';
import { workflowApi, executeApi, convertToApiFormat, logsApi } from '../../api/workflow';
import { parsePlan, extractNarrative } from '../../utils/planParser';
import { PlanCard } from './PlanCard';

interface ApprovalData {
  execution_id: string;
  node_id: string;
  message: string;
}

type ViewMode = 'chat' | 'log';

interface LogEntryGroup {
  topologyInfo: { topologyId: string; topologyColor: string; topologyName: string } | null;
  entries: Array<{
    id: string;
    agent: string;
    content: string;
    timestamp: Date;
    topologyInfo?: {
      topologyId: string;
      topologyName: string;
      topologyColor: string;
    } | null;
    agentRole?: string | null;
  }>;
}

export const ChatPanel = () => {
  const [expandedLogs, setExpandedLogs] = useState<Set<string>>(new Set());
  const [viewMode, setViewMode] = useState<ViewMode>('chat');
  const [input, setInput] = useState('');
  const [isExecuting, setIsExecuting] = useState(false);
  const [approvalPending, setApprovalPending] = useState<ApprovalData | null>(null);
  const [showHistoryOverlay, setShowHistoryOverlay] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);
  const chatIdRef = useRef<string | null>(null);
  const chatCreatedAtRef = useRef<string | null>(null);

  // Resizable panel width — drag the left edge. Persisted to localStorage.
  // Bounds: min 280px, max 40% of window width (so the canvas + topbar
  // buttons stay usable).
  const [chatWidth, setChatWidth] = useState<number>(() => {
    const saved = localStorage.getItem('mas_chat_width');
    return saved ? parseInt(saved, 10) || 350 : 350;
  });
  const [isResizing, setIsResizing] = useState(false);

  useEffect(() => {
    if (!isResizing) return;
    const onMove = (e: MouseEvent) => {
      const proposed = window.innerWidth - e.clientX;
      const max = Math.floor(window.innerWidth * 0.4);
      const min = 280;
      const next = Math.max(min, Math.min(max, proposed));
      setChatWidth(next);
    };
    const onUp = () => {
      setIsResizing(false);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, [isResizing]);

  // Save width to localStorage whenever it stabilizes (after resize ends).
  useEffect(() => {
    if (!isResizing) {
      localStorage.setItem('mas_chat_width', String(chatWidth));
    }
  }, [chatWidth, isResizing]);

  // Input-area vertical resize. Drag the top edge of the input area to
  // grow/shrink it; bounds: min 90px, max 30% of window height.
  const [inputAreaHeight, setInputAreaHeight] = useState<number>(() => {
    const saved = localStorage.getItem('mas_input_height');
    return saved ? parseInt(saved, 10) || 110 : 110;
  });
  const [isResizingInput, setIsResizingInput] = useState(false);

  useEffect(() => {
    if (!isResizingInput) return;
    const onMove = (e: MouseEvent) => {
      const proposed = window.innerHeight - e.clientY;
      const max = Math.floor(window.innerHeight * 0.3);
      const min = 90;
      setInputAreaHeight(Math.max(min, Math.min(max, proposed)));
    };
    const onUp = () => setIsResizingInput(false);
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, [isResizingInput]);

  useEffect(() => {
    if (!isResizingInput) {
      localStorage.setItem('mas_input_height', String(inputAreaHeight));
    }
  }, [inputAreaHeight, isResizingInput]);

  // Get current chat state from store (persists across mode switches)
  const currentChat = useCanvasStore(state => state.currentChat);
  const setCurrentChat = useCanvasStore(state => state.setCurrentChat);
  const addCurrentChatMessage = useCanvasStore(state => state.addCurrentChatMessage);
  const addCurrentChatLogEntry = useCanvasStore(state => state.addCurrentChatLogEntry);
  const clearCurrentChat = useCanvasStore(state => state.clearCurrentChat);

  // Get chat history from store
  const chatHistory = useCanvasStore(state => state.chatHistory);
  const addChatSession = useCanvasStore(state => state.addChatSession);
  const removeChatSession = useCanvasStore(state => state.removeChatSession);
  const updateChatSession = useCanvasStore(state => state.updateChatSession);

  const { nodes, topologyTemplates, connections, workflowName } = useCanvasStore();

  // Destructure current chat for easier access
  const { messages, logEntries, workflowId, currentSessionId, lastWorkflowHash } = currentChat;

  // Compute hash from logical workflow state (ignores positions)
  const computeWorkflowHash = useCallback(() => {
    const logicalState = {
      nodes: nodes.map(n => ({
        id: n.id,
        type: n.type,
        name: n.name,
        config: n.config,
      })),
      topologyTemplates: topologyTemplates.map(t => ({
        id: t.id,
        type: t.type,
        name: t.name,
        agents: t.agents,
        config: t.config,
      })),
      connections: connections.map(c => ({
        from: c.from,
        to: c.to,
        fromPort: c.fromPort,
        toPort: c.toPort,
      })),
    };
    return JSON.stringify(logicalState);
  }, [nodes, topologyTemplates, connections]);

  // Get topology types for session title
  const getTopologyTypes = useCallback(() => {
    const types = topologyTemplates.map(t => t.type);
    const uniqueTypes = [...new Set(types)];
    return uniqueTypes.map(type => {
      // Capitalize first letter
      return type.charAt(0).toUpperCase() + type.slice(1);
    });
  }, [topologyTemplates]);

  const toggleLogEntry = (id: string) => {
    setExpandedLogs(prev => {
      const newSet = new Set(prev);
      if (newSet.has(id)) {
        newSet.delete(id);
      } else {
        newSet.add(id);
      }
      return newSet;
    });
  };

  // Get agent's topology role by name (for capturing at log entry creation time)
  const getAgentRole = useCallback((agentName: string): string | null => {
    const agent = nodes.find(n => n.name === agentName);
    return agent?.topologyRole || null;
  }, [nodes]);

  // Get agent's topology info (id, color, name) by agent name (for capturing at log entry creation time)
  const getAgentTopologyInfo = useCallback((agentName: string): { topologyId: string; topologyColor: string; topologyName: string } | null => {
    const agent = nodes.find(n => n.name === agentName);
    if (!agent?.topologyId) return null;
    const topology = topologyTemplates.find(t => t.id === agent.topologyId);
    if (!topology) return null;
    return {
      topologyId: topology.id,
      topologyColor: topology.color,
      topologyName: topology.name,
    };
  }, [nodes, topologyTemplates]);

  // Save current chat to file
  const saveCurrentChat = useCallback(async () => {
    // Get latest values directly from store to avoid stale closure
    const state = useCanvasStore.getState();
    const latestMessages = state.currentChat.messages;
    const latestLogEntries = state.currentChat.logEntries;
    const latestWorkflowId = state.currentChat.workflowId;
    const latestWorkflowName = state.workflowName;

    // Only save if there are messages
    if (latestMessages.length === 0) {
      console.log('[ChatPanel] No messages to save, skipping');
      return;
    }

    // Create chatId if not exists
    if (!chatIdRef.current) {
      chatIdRef.current = `${Date.now()}`;
      chatCreatedAtRef.current = new Date().toISOString();
      console.log('[ChatPanel] Created new chatId:', chatIdRef.current);
    }

    console.log('[ChatPanel] Saving chat:', chatIdRef.current, 'messages:', latestMessages.length);

    // Prepare log entries with serialized timestamps
    const serializedLogEntries = latestLogEntries.map(entry => ({
      ...entry,
      timestamp: entry.timestamp instanceof Date ? entry.timestamp.toISOString() : entry.timestamp,
    }));

    // Call the save API
    await logsApi.save({
      chatId: chatIdRef.current,
      workflowName: latestWorkflowName || 'Untitled',
      messages: latestMessages,
      logEntries: serializedLogEntries,
      workflowId: latestWorkflowId,
      createdAt: chatCreatedAtRef.current || new Date().toISOString(),
    });
  }, []);

  // Save chat on page unload (F5, close tab, navigate away)
  useEffect(() => {
    const handleBeforeUnload = () => {
      // Get latest values directly from store to avoid stale closure
      const state = useCanvasStore.getState();
      const latestMessages = state.currentChat.messages;
      const latestLogEntries = state.currentChat.logEntries;
      const latestWorkflowId = state.currentChat.workflowId;
      const latestWorkflowName = state.workflowName;

      // Only save if there are messages
      if (latestMessages.length === 0) {
        console.log('[ChatPanel] beforeunload: No messages to save');
        return;
      }

      // Create chatId if not exists
      if (!chatIdRef.current) {
        chatIdRef.current = `${Date.now()}`;
        chatCreatedAtRef.current = new Date().toISOString();
      }

      console.log('[ChatPanel] beforeunload: Saving chat via sendBeacon:', chatIdRef.current);

      // Prepare log entries with serialized timestamps
      const serializedLogEntries = latestLogEntries.map(entry => ({
        ...entry,
        timestamp: entry.timestamp instanceof Date ? entry.timestamp.toISOString() : entry.timestamp,
      }));

      // Prepare data
      const data = {
        chatId: chatIdRef.current,
        workflowName: latestWorkflowName || 'Untitled',
        messages: latestMessages,
        logEntries: serializedLogEntries,
        workflowId: latestWorkflowId,
        createdAt: chatCreatedAtRef.current || new Date().toISOString(),
      };

      // Use sendBeacon for reliable delivery during page unload
      const blob = new Blob([JSON.stringify(data)], { type: 'application/json' });
      navigator.sendBeacon('/api/logs/save', blob);
    };

    window.addEventListener('beforeunload', handleBeforeUnload);

    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
    };
  }, []);

  const handleSend = async () => {
    if (!input.trim() || isExecuting) return;

    // Check for workflow changes
    const currentHash = computeWorkflowHash();
    if (lastWorkflowHash && lastWorkflowHash !== currentHash && messages.length > 0) {
      // Workflow has changed, insert separator
      addCurrentChatMessage({
        id: `separator-${Date.now()}`,
        role: 'separator',
        content: 'Workflow changed',
      });
      addCurrentChatLogEntry({
        id: `log-separator-${Date.now()}`,
        agent: 'System',
        content: '--- Workflow changed ---',
        timestamp: new Date(),
      });
    }
    setCurrentChat({ lastWorkflowHash: currentHash });

    const userMessage = {
      id: `msg-${Date.now()}`,
      role: 'user' as const,
      content: input.trim(),
    };

    addCurrentChatMessage(userMessage);
    setInput('');
    setIsExecuting(true);

    // Save/update workflow first
    let currentWorkflowId = workflowId;
    const trialSessionId = useSessionStore.getState().sessionId;
    const workflowData = convertToApiFormat(nodes, topologyTemplates, connections, workflowName, trialSessionId);

    console.log('[ChatPanel] Saving workflow...');

    if (!currentWorkflowId) {
      const created = await workflowApi.create(workflowData);
      currentWorkflowId = created.id || '';
      setCurrentChat({ workflowId: currentWorkflowId });
      console.log('[ChatPanel] Workflow created:', currentWorkflowId);
    } else {
      await workflowApi.update(currentWorkflowId, workflowData);
      console.log('[ChatPanel] Workflow updated:', currentWorkflowId);
    }

    // Execute workflow with streaming
    console.log('[ChatPanel] Starting execution...');

    // Add user message to log
    addCurrentChatLogEntry({
      id: `log-${Date.now()}`,
      agent: 'User',
      content: userMessage.content,
      timestamp: new Date(),
    });

    // Build conversation history from previous messages (excluding separators and current message)
    const conversationHistory = messages
      .filter(m => m.role === 'user' || m.role === 'assistant')
      .map(m => ({
        role: m.role as 'user' | 'assistant',
        content: m.content,
      }));

    console.log('[ChatPanel] Conversation history:', conversationHistory.length, 'messages');

    abortControllerRef.current = executeApi.stream(
      currentWorkflowId,
      userMessage.content,
      (execMessage) => {
        console.log('[ChatPanel] Message:', execMessage);
        // Add to log entries (all intermediate messages)
        // Capture topology info at creation time so it persists even if topology is deleted
        const agentName = execMessage.from || 'Agent';
        addCurrentChatLogEntry({
          id: execMessage.id,
          agent: agentName,
          content: execMessage.content,
          timestamp: new Date(),
          topologyInfo: getAgentTopologyInfo(agentName),
          agentRole: getAgentRole(agentName),
        });
      },
      (result) => {
        console.log('[ChatPanel] Complete:', result);
        // Add only final answer to chat messages
        addCurrentChatMessage({
          id: `final-${Date.now()}`,
          role: 'assistant',
          content: result.output,
        });
        setIsExecuting(false);
        abortControllerRef.current = null;
        // Note: Log is saved on browser refresh, canvas clear, or unexpected shutdown - not after each execution
      },
      (error) => {
        console.error('[ChatPanel] Error:', error);
        const errorMsg = `Error: ${error.message}`;
        addCurrentChatMessage({
          id: `error-${Date.now()}`,
          role: 'system',
          content: errorMsg,
        });
        addCurrentChatLogEntry({
          id: `log-error-${Date.now()}`,
          agent: 'System',
          content: errorMsg,
          timestamp: new Date(),
        });
        setIsExecuting(false);
        abortControllerRef.current = null;
        // Save chat log after error (small delay for state to update)
        setTimeout(() => saveCurrentChat(), 100);
      },
      (approvalData) => {
        console.log('[ChatPanel] Approval required:', approvalData);
        setApprovalPending(approvalData);
        addCurrentChatLogEntry({
          id: `log-approval-${Date.now()}`,
          agent: 'System',
          content: `Approval required: ${approvalData.message}`,
          timestamp: new Date(),
        });
        setIsExecuting(false);
      },
      conversationHistory,
      useSessionStore.getState().taskId,
    );
  };

  const handleApprovalDecision = (decision: 'approve' | 'reject') => {
    if (!approvalPending || !workflowId) return;

    console.log('[ChatPanel] Decision:', decision);
    setApprovalPending(null);
    setIsExecuting(true);

    const decisionText = `Decision: ${decision === 'approve' ? 'Approved' : 'Rejected'}`;
    addCurrentChatMessage({
      id: `decision-${Date.now()}`,
      role: 'system',
      content: decisionText,
    });
    addCurrentChatLogEntry({
      id: `log-decision-${Date.now()}`,
      agent: 'User',
      content: decisionText,
      timestamp: new Date(),
    });

    abortControllerRef.current = executeApi.resume(
      workflowId,
      approvalPending.execution_id,
      decision,
      (execMessage) => {
        // Add to log entries
        // Capture topology info at creation time so it persists even if topology is deleted
        const agentName = execMessage.from || 'Agent';
        addCurrentChatLogEntry({
          id: execMessage.id,
          agent: agentName,
          content: execMessage.content,
          timestamp: new Date(),
          topologyInfo: getAgentTopologyInfo(agentName),
          agentRole: getAgentRole(agentName),
        });
      },
      (result) => {
        console.log('[ChatPanel] Resume complete:', result);
        // Add only final answer to chat
        addCurrentChatMessage({
          id: `final-${Date.now()}`,
          role: 'assistant',
          content: result.output,
        });
        setIsExecuting(false);
        abortControllerRef.current = null;
        // Note: Log is saved on browser refresh, canvas clear, or unexpected shutdown - not after each execution
      },
      (error) => {
        console.error('[ChatPanel] Resume error:', error);
        const errorMsg = `Error: ${error.message}`;
        addCurrentChatMessage({
          id: `error-${Date.now()}`,
          role: 'system',
          content: errorMsg,
        });
        addCurrentChatLogEntry({
          id: `log-error-${Date.now()}`,
          agent: 'System',
          content: errorMsg,
          timestamp: new Date(),
        });
        setIsExecuting(false);
        abortControllerRef.current = null;
        // Save chat log after resume error
        setTimeout(() => saveCurrentChat(), 100);
      },
      (approvalData) => {
        setApprovalPending(approvalData);
        addCurrentChatLogEntry({
          id: `log-approval-${Date.now()}`,
          agent: 'System',
          content: `Approval required: ${approvalData.message}`,
          timestamp: new Date(),
        });
        setIsExecuting(false);
      },
    );
  };

  const handleNewChat = async () => {
    // Save current chat to file before clearing (if there are messages)
    if (messages.length > 0) {
      console.log('[ChatPanel] Saving chat before creating new one');
      await saveCurrentChat();

      // Archive current session
      const firstUserMessage = messages.find(m => m.role === 'user');
      const newSession: ChatSession = {
        id: `session-${Date.now()}`,
        title: workflowName || 'Untitled',
        topologyTypes: getTopologyTypes(),
        createdAt: new Date(),
        firstMessage: firstUserMessage?.content || '',
        messages: [...messages],
        logEntries: [...logEntries],
        workflowId,
        workflowHash: lastWorkflowHash,
      };
      addChatSession(newSession);
    }

    // Clear current session
    clearCurrentChat();
    setApprovalPending(null);
    setIsExecuting(false);
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }

    // Reset chatId for new chat
    chatIdRef.current = null;
    chatCreatedAtRef.current = null;
    console.log('[ChatPanel] New chat started, chatId reset');
  };

  const restoreSession = (session: ChatSession) => {
    // Archive current session first if it has messages
    if (messages.length > 0 && currentSessionId !== session.id) {
      const firstUserMessage = messages.find(m => m.role === 'user');
      const currentSession: ChatSession = {
        id: currentSessionId || `session-${Date.now()}`,
        title: workflowName || 'Untitled',
        topologyTypes: getTopologyTypes(),
        createdAt: new Date(),
        firstMessage: firstUserMessage?.content || '',
        messages: [...messages],
        logEntries: [...logEntries],
        workflowId,
        workflowHash: lastWorkflowHash,
      };
      // Update or add to history
      if (currentSessionId && chatHistory.some(s => s.id === currentSessionId)) {
        updateChatSession(currentSessionId, currentSession);
      } else {
        addChatSession(currentSession);
      }
    }

    // Restore the selected session
    setCurrentChat({
      messages: session.messages,
      logEntries: session.logEntries,
      workflowId: session.workflowId,
      currentSessionId: session.id,
      lastWorkflowHash: session.workflowHash,
    });
    setShowHistoryOverlay(false);

    // Remove from history since it's now active
    removeChatSession(session.id);
  };

  const formatTime = (date: Date) => {
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  // Group consecutive log entries by topology (uses stored topologyInfo from each entry)
  const groupLogEntries = useCallback((): LogEntryGroup[] => {
    const groups: LogEntryGroup[] = [];

    for (const entry of logEntries) {
      // Use stored topology info from the entry (captured at creation time)
      const topologyInfo = entry.topologyInfo || null;
      const lastGroup = groups[groups.length - 1];

      // Check if this entry belongs to the same topology group as the last one
      const sameTopology = lastGroup &&
        lastGroup.topologyInfo?.topologyId === topologyInfo?.topologyId;

      if (sameTopology) {
        // Add to existing group
        lastGroup.entries.push(entry);
      } else {
        // Create new group
        groups.push({
          topologyInfo,
          entries: [entry],
        });
      }
    }

    return groups;
  }, [logEntries]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    // IME guard: while a Korean/Japanese/Chinese composition is in progress
    // (e.g. user is mid-character on Hangul), Enter is the IME's "commit"
    // signal — sending here would race the commit and the last char ends
    // up re-inserted into the cleared input. Skip until composition ends.
    if (e.nativeEvent.isComposing || (e.nativeEvent as KeyboardEvent).keyCode === 229) {
      return;
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div
      className="bg-[#171717] border-l border-[#262626] flex flex-col relative shrink-0"
      style={{ width: `${chatWidth}px` }}
    >
      {/* Drag handle on the left edge — wider hit zone than visible bar. */}
      <div
        onMouseDown={(e) => {
          e.preventDefault();
          setIsResizing(true);
        }}
        className={`absolute -left-1 top-0 bottom-0 w-2 cursor-col-resize z-30 group`}
        title="드래그해서 너비 조절"
      >
        <div className={`absolute left-1 top-0 bottom-0 w-px transition-colors ${isResizing ? 'bg-[#3b82f6]' : 'bg-transparent group-hover:bg-[#3b82f6]'}`} />
      </div>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-[#262626]">
        {/* Chat/Log Toggle */}
        <div className="flex bg-[#262626] rounded-full p-0.5">
          <button
            onClick={() => setViewMode('chat')}
            className={`px-3 py-1 rounded-full text-xs transition-colors ${
              viewMode === 'chat' ? 'bg-[#404040] text-white' : 'text-[#888] hover:text-white'
            }`}
          >
            Chat
          </button>
          <button
            onClick={() => setViewMode('log')}
            className={`px-3 py-1 rounded-full text-xs transition-colors ${
              viewMode === 'log' ? 'bg-[#404040] text-white' : 'text-[#888] hover:text-white'
            }`}
          >
            Log
          </button>
        </div>

        {/* History & New Chat Buttons */}
        <div className="flex items-center gap-1">
          {/* History Button */}
          <div className="relative group">
            <button
              onClick={() => setShowHistoryOverlay(!showHistoryOverlay)}
              className={`w-7 h-7 flex items-center justify-center hover:text-white hover:bg-[#262626] rounded-lg transition-colors ${
                showHistoryOverlay ? 'text-white bg-[#262626]' : 'text-[#a3a3a3]'
              }`}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10"/>
                <polyline points="12 6 12 12 16 14"/>
              </svg>
            </button>
            <div className="absolute top-full mt-1 left-1/2 -translate-x-1/2 px-2 py-1 bg-[#333] text-white text-[10px] rounded whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-30">
              Chat history
            </div>
          </div>

          {/* New Chat Button */}
          <div className="relative group">
            <button
              onClick={handleNewChat}
              className="w-7 h-7 flex items-center justify-center text-[#a3a3a3] hover:text-white hover:bg-[#262626] rounded-lg transition-colors"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M12 5v14M5 12h14"/>
              </svg>
            </button>
            <div className="absolute top-full mt-1 left-1/2 -translate-x-1/2 px-2 py-1 bg-[#333] text-white text-[10px] rounded whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-30">
              New chat
            </div>
          </div>
        </div>
      </div>

      {/* History Overlay */}
      {showHistoryOverlay && (
        <div className="absolute top-[52px] left-0 right-0 bottom-0 bg-[#171717]/95 backdrop-blur-sm z-20 flex flex-col">
          <div className="p-3 border-b border-[#262626]">
            <h3 className="text-sm font-medium text-white">Chat History</h3>
            <p className="text-[10px] text-[#666] mt-0.5">{chatHistory.length} saved session{chatHistory.length !== 1 ? 's' : ''}</p>
          </div>
          <div className="flex-1 overflow-y-auto">
            {chatHistory.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-center p-4">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-[#444] mb-3">
                  <circle cx="12" cy="12" r="10"/>
                  <polyline points="12 6 12 12 16 14"/>
                </svg>
                <p className="text-xs text-[#666]">No saved sessions yet.</p>
                <p className="text-[10px] text-[#555] mt-1">Click "+" to archive the current chat.</p>
              </div>
            ) : (
              <div className="p-2">
                {chatHistory.map((session) => (
                  <button
                    key={session.id}
                    onClick={() => restoreSession(session)}
                    className="w-full text-left p-3 rounded-lg hover:bg-[#262626] transition-colors mb-1"
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xs font-medium text-white truncate flex-1">
                        {session.title}
                        {session.topologyTypes.length > 0 && (
                          <span className="text-[#666] font-normal ml-1">
                            ({session.topologyTypes.join(', ')})
                          </span>
                        )}
                      </span>
                      <span className="text-[10px] text-[#666] flex-shrink-0">
                        {formatTime(session.createdAt)}
                      </span>
                    </div>
                    {session.firstMessage && (
                      <p className="text-[11px] text-[#888] truncate">
                        User: {session.firstMessage}
                      </p>
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className="p-3 border-t border-[#262626]">
            <button
              onClick={() => setShowHistoryOverlay(false)}
              className="w-full py-2 text-xs text-[#888] hover:text-white transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      )}

      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto p-4">
        {viewMode === 'chat' ? (
          // Chat View - User messages + final answers only
          messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center">
              <div className="w-12 h-12 rounded-xl bg-[#262626] flex items-center justify-center mb-4">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-[#666]">
                  <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/>
                  <path d="m15 5 4 4"/>
                </svg>
              </div>
              <h3 className="text-sm font-medium mb-1">Preview your agent</h3>
              <p className="text-xs text-[#666]">Prompt the agent as if you're the user.</p>
            </div>
          ) : (
            <div className="space-y-4">
              {messages.map((msg) => {
                if (msg.role === 'separator') {
                  return (
                    <div key={msg.id} className="flex items-center gap-2 py-2">
                      <div className="flex-1 h-px bg-[#404040]" />
                      <span className="text-[10px] text-[#666] px-2">Workflow changed</span>
                      <div className="flex-1 h-px bg-[#404040]" />
                    </div>
                  );
                }
                // For assistant messages, render natural-language commentary
                // (above) AND the parsed plan as a PlanCard (below) so chat
                // feels like a dialogue, not a silent plan dump. Falls back
                // to raw content when no plan is parseable.
                const parsedPlan = msg.role === 'assistant' ? parsePlan(msg.content) : null;
                const narrative = msg.role === 'assistant' && parsedPlan
                  ? extractNarrative(msg.content)
                  : '';
                return (
                  <div
                    key={msg.id}
                    className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                  >
                    <div
                      className={`px-3 py-2 rounded-xl text-sm ${
                        msg.role === 'user'
                          ? 'max-w-[80%] bg-[#3b82f6] text-white'
                          : msg.role === 'system'
                          ? 'max-w-[85%] bg-[#1a1a1a] text-[#888] border border-[#333]'
                          : 'max-w-[95%] w-full bg-[#262626] text-white'
                      }`}
                    >
                      {parsedPlan ? (
                        <div className="space-y-2">
                          {narrative && (
                            <div className="whitespace-pre-wrap leading-relaxed">
                              {narrative}
                            </div>
                          )}
                          <PlanCard plan={parsedPlan} />
                        </div>
                      ) : (
                        msg.content
                      )}
                    </div>
                  </div>
                );
              })}
              {/* Approval buttons */}
              {approvalPending && (
                <div className="p-3 bg-[#262626] rounded-xl border border-[#404040]">
                  <p className="text-xs text-[#888] mb-2">Approval Required</p>
                  <p className="text-sm text-white mb-3">{approvalPending.message}</p>
                  <div className="flex gap-2">
                    <button
                      onClick={() => handleApprovalDecision('approve')}
                      className="flex-1 py-2 bg-green-600 hover:bg-green-500 text-white text-sm rounded-lg"
                    >
                      Approve
                    </button>
                    <button
                      onClick={() => handleApprovalDecision('reject')}
                      className="flex-1 py-2 bg-red-600 hover:bg-red-500 text-white text-sm rounded-lg"
                    >
                      Reject
                    </button>
                  </div>
                </div>
              )}
            </div>
          )
        ) : (
          // Log View - All messages with agent names
          logEntries.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center">
              <div className="w-12 h-12 rounded-xl bg-[#262626] flex items-center justify-center mb-4">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-[#666]">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                  <polyline points="14 2 14 8 20 8"/>
                  <line x1="16" y1="13" x2="8" y2="13"/>
                  <line x1="16" y1="17" x2="8" y2="17"/>
                  <polyline points="10 9 9 9 8 9"/>
                </svg>
              </div>
              <h3 className="text-sm font-medium mb-1">Execution Log</h3>
              <p className="text-xs text-[#666]">Run the workflow to see the log.</p>
            </div>
          ) : (
            <div className="space-y-1">
              {groupLogEntries().map((group, groupIndex) => (
                group.topologyInfo ? (
                  // Topology group with colored container
                  <div
                    key={`group-${groupIndex}`}
                    className="rounded-lg overflow-hidden mb-2"
                    style={{
                      backgroundColor: `${group.topologyInfo.topologyColor}15`,
                      borderLeft: `3px solid ${group.topologyInfo.topologyColor}`,
                    }}
                  >
                    {/* Topology header */}
                    <div
                      className="px-2 py-1 text-[10px] font-medium"
                      style={{ color: group.topologyInfo.topologyColor }}
                    >
                      {group.topologyInfo.topologyName}
                    </div>
                    {/* Entries in this topology */}
                    <div className="px-1">
                      {group.entries.map((entry) => (
                        <div key={entry.id} className="text-sm">
                          <div
                            className="flex items-center gap-2 py-1.5 cursor-pointer hover:bg-black/10 rounded px-1"
                            onClick={() => toggleLogEntry(entry.id)}
                          >
                            <span className={`text-xs text-[#666] transition-transform duration-150 ${
                              expandedLogs.has(entry.id) ? 'rotate-90' : ''
                            }`}>
                              ›
                            </span>
                            <span
                              className="text-xs font-medium px-2 py-0.5 rounded"
                              style={{
                                backgroundColor: `${group.topologyInfo.topologyColor}30`,
                                color: group.topologyInfo.topologyColor,
                              }}
                            >
                              {entry.agent}
                              {entry.agentRole && (
                                <span className="ml-1 opacity-60">({entry.agentRole})</span>
                              )}
                            </span>
                            <span className="text-[10px] text-[#666]">
                              {entry.timestamp.toLocaleTimeString()}
                            </span>
                          </div>
                          {expandedLogs.has(entry.id) && (
                            <div
                              className="pl-5 py-2 text-[#ccc] border-l-2 ml-1 mb-1"
                              style={{ borderColor: `${group.topologyInfo.topologyColor}50` }}
                            >
                              {entry.content}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  // Non-topology entries (User, System, standalone agents)
                  <div key={`group-${groupIndex}`}>
                    {group.entries.map((entry) => (
                      <div key={entry.id} className="text-sm">
                        <div
                          className="flex items-center gap-2 py-1.5 cursor-pointer hover:bg-[#262626] rounded px-1 -mx-1"
                          onClick={() => toggleLogEntry(entry.id)}
                        >
                          <span className={`text-xs text-[#666] transition-transform duration-150 ${
                            expandedLogs.has(entry.id) ? 'rotate-90' : ''
                          }`}>
                            ›
                          </span>
                          <span className={`text-xs font-medium px-2 py-0.5 rounded ${
                            entry.agent === 'User'
                              ? 'bg-[#3b82f6]/20 text-[#3b82f6]'
                              : entry.agent === 'System'
                              ? 'bg-[#f59e0b]/20 text-[#f59e0b]'
                              : 'bg-[#22c55e]/20 text-[#22c55e]'
                          }`}>
                            {entry.agent}
                            {entry.agentRole && (
                              <span className="ml-1 opacity-60">({entry.agentRole})</span>
                            )}
                          </span>
                          <span className="text-[10px] text-[#666]">
                            {entry.timestamp.toLocaleTimeString()}
                          </span>
                        </div>
                        {expandedLogs.has(entry.id) && (
                          <div className="pl-5 py-2 text-[#ccc] border-l-2 border-[#333] ml-1 mb-1">
                            {entry.content}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )
              ))}
            </div>
          )
        )}
      </div>

      {/* Input Area — vertically resizable via top-edge drag handle. */}
      <div
        className="border-t border-[#262626] flex flex-col relative shrink-0"
        style={{ height: `${inputAreaHeight}px` }}
      >
        {/* Drag handle on the top edge */}
        <div
          onMouseDown={(e) => {
            e.preventDefault();
            setIsResizingInput(true);
          }}
          className="absolute -top-1 left-0 right-0 h-2 cursor-row-resize z-30 group"
          title="드래그해서 입력창 높이 조절"
        >
          <div
            className={`absolute top-1 left-0 right-0 h-px transition-colors ${
              isResizingInput ? 'bg-[#3b82f6]' : 'bg-transparent group-hover:bg-[#3b82f6]'
            }`}
          />
        </div>
        <div className="flex-1 p-4 overflow-hidden">
          <div className="bg-[#262626] rounded-xl px-4 py-3 h-full flex flex-col">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Send a message..."
              className="w-full flex-1 bg-transparent text-sm text-white placeholder-[#666] resize-none outline-none"
            />
            <div className="flex items-center justify-between mt-2 shrink-0">
              <button className="text-[#666] hover:text-white">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/>
                </svg>
              </button>
              <button
                onClick={handleSend}
                disabled={!input.trim() || isExecuting || !!approvalPending}
                className={`w-7 h-7 rounded-lg flex items-center justify-center transition-colors ${
                  input.trim() && !isExecuting && !approvalPending
                    ? 'bg-white text-black hover:bg-gray-200'
                    : 'bg-[#404040] text-[#666] cursor-not-allowed'
                }`}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 4l-1.41 1.41L16.17 11H4v2h12.17l-5.58 5.59L12 20l8-8z"/>
                </svg>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
