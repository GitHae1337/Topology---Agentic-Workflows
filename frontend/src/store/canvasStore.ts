import { create } from 'zustand';
import {
  Node,
  TopologyTemplate,
  Connection,
  InternalEdge,
  NodeType,
  TopologyType,
  ChatMessage,
  RolePopupState,
  IfElseCondition,
} from '../types';

// Chat history types
interface ChatPanelMessage {
  id: string;
  role: 'user' | 'assistant' | 'system' | 'separator';
  content: string;
  from?: string;
}

interface ChatPanelLogEntry {
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
}

export interface ChatSession {
  id: string;
  title: string;
  topologyTypes: string[];
  createdAt: Date;
  firstMessage: string;
  messages: ChatPanelMessage[];
  logEntries: ChatPanelLogEntry[];
  workflowId: string | null;
  workflowHash: string;
}

// Current active chat session state
export interface CurrentChatState {
  messages: ChatPanelMessage[];
  logEntries: ChatPanelLogEntry[];
  workflowId: string | null;
  currentSessionId: string | null;
  lastWorkflowHash: string;
}
import { getTopologyDefinition, topologies } from '../constants/topologies';
import { getNodeColor } from '../constants/nodeTypes';
import { editLogApi } from '../api/editLog';
import { useSessionStore } from './sessionStore';

// Structural state captured per undo/redo step. Selection / drag / resize
// transients are intentionally excluded — they are not meaningful "edits".
export interface CanvasSnapshot {
  nodes: Node[];
  topologyTemplates: TopologyTemplate[];
  connections: Connection[];
}

const MAX_HISTORY = 100;

// Module-level helper for the per-mutation edit-log POST. Silent no-op when
// no session is active (e.g. tests, hot reload before initSession runs).
const logEdit = (
  action: string,
  payload: Record<string, unknown>,
  undoStackDepth: number,
): void => {
  const sessionId = useSessionStore.getState().sessionId;
  if (!sessionId) return;
  editLogApi.appendEdit({
    sessionId,
    timestamp: new Date().toISOString(),
    action,
    payload,
    undoStackDepth,
  });
};

interface CanvasState {
  // Canvas data
  nodes: Node[];
  topologyTemplates: TopologyTemplate[];
  connections: Connection[];

  // Selection state
  selectedNode: string | null;
  selectedNodes: string[];
  selectedTemplate: string | null;
  selectionBox: { startX: number; startY: number; endX: number; endY: number } | null;

  // Drag state
  draggingNode: string | null;
  draggingTopology: string | null;
  dragOffset: { x: number; y: number };

  // Connection drawing state
  connecting: string | null;
  connectingFrom: 'node' | 'template' | null;
  connectingFromPort: number | null;
  // True when the user started the connection by clicking an INPUT dot
  // (left side). Used to swap source/target at mouseup so the resulting
  // edge is always output→input direction even when the user dragged from
  // input to output.
  connectingFromInput: boolean;
  internalConnecting: { agentId: string; templateId: string } | null;

  // Resize state
  resizing: { id: string; type?: 'topology' | 'node' } | null;
  resizeStart: { x: number; y: number; width: number; height: number };

  // Role popup
  rolePopup: RolePopupState | null;

  // Chat
  chatMessages: ChatMessage[];

  // Edge error (for displaying loop prevention messages)
  edgeError: { message: string; details: string } | null;

  // Workflow metadata
  workflowName: string;

  // Chat history (persists across mode switches)
  chatHistory: ChatSession[];

  // Current active chat session (persists across mode switches)
  currentChat: CurrentChatState;

  // Node actions
  addNode: (type: NodeType, x: number, y: number) => void;
  updateNode: (id: string, updates: Partial<Node>) => void;
  deleteNode: (id: string) => void;
  setSelectedNode: (id: string | null) => void;
  setSelectedNodes: (ids: string[]) => void;
  clearSelection: () => void;
  setSelectionBox: (box: { startX: number; startY: number; endX: number; endY: number } | null) => void;
  selectNodesInBox: () => void;
  moveSelectedNodes: (dx: number, dy: number) => void;

  // Topology actions
  addTopologyTemplate: (type: TopologyType, x: number, y: number) => void;
  updateTopologyTemplate: (id: string, updates: Partial<TopologyTemplate>) => void;
  deleteTopologyTemplate: (id: string) => void;
  setSelectedTemplate: (id: string | null) => void;

  // Internal edge actions
  // silent=true skips pushHistory + logEdit. Used by addAgentToTopology auto-connect
  // so a single agent-add triggers exactly one undo entry, not one per edge.
  addInternalEdge: (templateId: string, fromAgentId: string, toAgentId: string, silent?: boolean) => void;
  deleteInternalEdge: (templateId: string, edgeId: string) => void;

  // Connection actions
  addConnection: (from: string, to: string, fromType: 'node' | 'template', fromPort?: number) => void;
  deleteConnection: (id: string) => void;

  // If/Else condition actions
  addCondition: (nodeId: string) => void;
  updateCondition: (nodeId: string, conditionId: string, updates: Partial<IfElseCondition>) => void;
  deleteCondition: (nodeId: string, conditionId: string) => void;

  // Agent-topology actions
  addAgentToTopology: (agentId: string, templateId: string, role: string | null) => void;
  removeAgentFromTopology: (agentId: string) => void;

  // Drag actions
  setDraggingNode: (id: string | null) => void;
  setDraggingTopology: (id: string | null) => void;
  setDragOffset: (offset: { x: number; y: number }) => void;
  moveNode: (id: string, x: number, y: number) => void;
  moveTopology: (id: string, x: number, y: number) => void;

  // Connection drawing actions
  setConnecting: (id: string | null, fromType: 'node' | 'template' | null, fromPort?: number | null, fromInput?: boolean) => void;
  setInternalConnecting: (state: { agentId: string; templateId: string } | null) => void;

  // Resize actions
  setResizing: (state: { id: string; type?: 'topology' | 'node' } | null) => void;
  setResizeStart: (state: { x: number; y: number; width: number; height: number }) => void;
  resizeTopology: (id: string, width: number, height: number) => void;
  resizeNode: (id: string, width: number, height: number) => void;

  // Role popup actions
  setRolePopup: (state: RolePopupState | null) => void;

  // Chat actions
  addChatMessage: (message: ChatMessage) => void;
  clearChatMessages: () => void;

  // Edge error actions
  setEdgeError: (error: { message: string; details: string } | null) => void;

  // Workflow metadata actions
  setWorkflowName: (name: string) => void;

  // Chat history actions
  addChatSession: (session: ChatSession) => void;
  removeChatSession: (sessionId: string) => void;
  updateChatSession: (sessionId: string, updates: Partial<ChatSession>) => void;
  clearChatHistory: () => void;

  // Current chat actions
  setCurrentChat: (state: Partial<CurrentChatState>) => void;
  addCurrentChatMessage: (message: ChatPanelMessage) => void;
  addCurrentChatLogEntry: (entry: ChatPanelLogEntry) => void;
  clearCurrentChat: () => void;

  // Utility
  getAgentsInTopology: (templateId: string) => Node[];
  clearCanvas: () => void;
  resetForNewTrial: () => void;

  // History / undo-redo
  undoStack: CanvasSnapshot[];
  redoStack: CanvasSnapshot[];
  pushHistory: () => void;
  undo: () => void;
  redo: () => void;
  getUndoStackDepth: () => number;
}

const generateId = (prefix: string): string => `${prefix}-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

export const useCanvasStore = create<CanvasState>((set, get) => ({
  // Initial state
  nodes: [
    { id: 'start-1', type: 'start', x: 100, y: 80, name: 'Start', config: {}, topologyId: null, topologyRole: null, topologyColor: null }
  ],
  topologyTemplates: [],
  connections: [],
  selectedNode: null,
  selectedNodes: [],
  selectedTemplate: null,
  selectionBox: null,
  draggingNode: null,
  draggingTopology: null,
  dragOffset: { x: 0, y: 0 },
  connecting: null,
  connectingFrom: null,
  connectingFromPort: null,
  connectingFromInput: false,
  internalConnecting: null,
  resizing: null,
  resizeStart: { x: 0, y: 0, width: 0, height: 0 },
  rolePopup: null,
  chatMessages: [],
  edgeError: null,
  workflowName: 'New agent',
  chatHistory: [],
  currentChat: {
    messages: [],
    logEntries: [],
    workflowId: null,
    currentSessionId: null,
    lastWorkflowHash: '',
  },
  undoStack: [],
  redoStack: [],

  // Node actions
  addNode: (type, x, y) => {
    const nodes = get().nodes;
    const agentCount = nodes.filter(n => n.type === 'agent').length;

    // Initialize config based on node type
    let config: Record<string, unknown> = {};
    let name = type.charAt(0).toUpperCase() + type.slice(1);

    if (type === 'agent') {
      name = `Agent ${agentCount + 1}`;
    } else if (type === 'ifelse') {
      name = 'If / else';
      config = {
        conditions: [
          { id: generateId('cond'), name: '', condition: '' }
        ] as IfElseCondition[]
      };
    }

    const newNode: Node = {
      id: generateId(type),
      type,
      x,
      y,
      name,
      config,
      topologyId: null,
      topologyRole: null,
      topologyColor: null,
    };
    get().pushHistory();
    set({ nodes: [...nodes, newNode], selectedNode: newNode.id, selectedTemplate: null });
    logEdit('add_node', { nodeId: newNode.id, type, x, y }, get().undoStack.length);
  },

  updateNode: (id, updates) => {
    get().pushHistory();
    set({ nodes: get().nodes.map(n => n.id === id ? { ...n, ...updates } : n) });
    logEdit('update_node', { nodeId: id, updates }, get().undoStack.length);
  },

  deleteNode: (id) => {
    const node = get().nodes.find(n => n.id === id);
    if (!node) return;

    // Start/End are trial-permanent placeholders — refuse to delete.
    if (node.type === 'start' || node.type === 'end') {
      console.log(`[canvasStore] deleteNode refused for ${node.type} (${id})`);
      return;
    }

    get().pushHistory();

    // Remove from topology edges if in a topology
    if (node.topologyId) {
      set({
        topologyTemplates: get().topologyTemplates.map(t =>
          t.id === node.topologyId
            ? {
                ...t,
                internalEdges: t.internalEdges.filter(e => e.from !== id && e.to !== id),
                startAgentId: t.startAgentId === id ? null : t.startAgentId,
              }
            : t
        ),
      });
    }

    set({
      nodes: get().nodes.filter(n => n.id !== id),
      connections: get().connections.filter(c => c.from !== id && c.to !== id),
      selectedNode: get().selectedNode === id ? null : get().selectedNode,
    });

    logEdit(
      'delete_node',
      { nodeId: id, nodeType: node.type, nodeName: node.name },
      get().undoStack.length,
    );
  },

  setSelectedNode: (id) => set({ selectedNode: id, selectedNodes: id ? [id] : [], selectedTemplate: id ? null : get().selectedTemplate }),

  setSelectedNodes: (ids) => set({ selectedNodes: ids, selectedNode: ids.length === 1 ? ids[0] : null, selectedTemplate: null }),

  clearSelection: () => set({ selectedNode: null, selectedNodes: [], selectedTemplate: null, selectionBox: null }),

  setSelectionBox: (box) => set({ selectionBox: box }),

  selectNodesInBox: () => {
    const { selectionBox, nodes } = get();
    if (!selectionBox) return;

    const minX = Math.min(selectionBox.startX, selectionBox.endX);
    const maxX = Math.max(selectionBox.startX, selectionBox.endX);
    const minY = Math.min(selectionBox.startY, selectionBox.endY);
    const maxY = Math.max(selectionBox.startY, selectionBox.endY);

    const selectedIds = nodes
      .filter(n => {
        const nodeRight = n.x + 160;
        const nodeBottom = n.y + 60;
        return n.x < maxX && nodeRight > minX && n.y < maxY && nodeBottom > minY;
      })
      .map(n => n.id);

    set({ selectedNodes: selectedIds, selectedNode: selectedIds.length === 1 ? selectedIds[0] : null, selectionBox: null });
  },

  moveSelectedNodes: (dx, dy) => {
    const { selectedNodes, nodes } = get();
    set({
      nodes: nodes.map(n =>
        selectedNodes.includes(n.id)
          ? { ...n, x: Math.max(0, n.x + dx), y: Math.max(0, n.y + dy) }
          : n
      ),
    });
  },

  // Topology actions
  addTopologyTemplate: (type, x, y) => {
    const topo = getTopologyDefinition(type);
    if (!topo) return;

    const newTemplate: TopologyTemplate = {
      id: generateId('topo'),
      type,
      x,
      y,
      width: 350,
      height: 250,
      name: topo.name,
      color: topo.color,
      maxTurns: 3,
      timeout: 180,
      earlyTermination: true,
      internalEdges: [],
      startAgentId: null,
    };
    get().pushHistory();
    set({ topologyTemplates: [...get().topologyTemplates, newTemplate] });
    logEdit('add_topology', { templateId: newTemplate.id, type, x, y }, get().undoStack.length);
  },

  updateTopologyTemplate: (id, updates) => {
    get().pushHistory();
    set({
      topologyTemplates: get().topologyTemplates.map(t =>
        t.id === id ? { ...t, ...updates } : t
      ),
    });
    logEdit('update_topology', { templateId: id, updates }, get().undoStack.length);
  },

  deleteTopologyTemplate: (id) => {
    get().pushHistory();
    // Remove all agents from this topology
    set({
      nodes: get().nodes.map(n =>
        n.topologyId === id
          ? { ...n, topologyId: null, topologyRole: null, topologyColor: null }
          : n
      ),
      topologyTemplates: get().topologyTemplates.filter(t => t.id !== id),
      connections: get().connections.filter(c => c.from !== id && c.to !== id),
      selectedTemplate: get().selectedTemplate === id ? null : get().selectedTemplate,
    });
    logEdit('delete_topology', { templateId: id }, get().undoStack.length);
  },

  setSelectedTemplate: (id) => set({ selectedTemplate: id, selectedNode: id ? null : get().selectedNode }),

  // Internal edge actions
  addInternalEdge: (templateId, fromAgentId, toAgentId, silent = false) => {
    const template = get().topologyTemplates.find(t => t.id === templateId);
    if (!template) return;

    const topo = getTopologyDefinition(template.type);
    if (!topo) return;

    // Check for DAG cycle prevention
    if (topo.noLoops) {
      const wouldCreateCycle = (fromId: string, toId: string, edges: InternalEdge[]): boolean => {
        const visited = new Set<string>();
        const stack = [toId];
        while (stack.length > 0) {
          const current = stack.pop()!;
          if (current === fromId) return true;
          if (visited.has(current)) continue;
          visited.add(current);
          edges.filter(e => e.from === current).forEach(e => stack.push(e.to));
        }
        return false;
      };

      if (wouldCreateCycle(fromAgentId, toAgentId, template.internalEdges)) {
        set({
          edgeError: {
            message: 'Cannot form loops in Chain topology',
            details: 'Chain topology requires a linear pipeline structure. Loops are not allowed.',
          },
        });
        return;
      }
    }

    // 'p2p' deprecated for the 5-topology study; connection-limit guard kept for reference
    // // P2P constraint: each agent can connect to exactly 2 other agents
    // if (template.type === 'p2p') {
    //   const countConnections = (agentId: string) => {
    //     return template.internalEdges.filter(
    //       e => e.from === agentId || e.to === agentId
    //     ).length;
    //   };
    //
    //   const fromConnections = countConnections(fromAgentId);
    //   const toConnections = countConnections(toAgentId);
    //
    //   if (fromConnections >= 2 || toConnections >= 2) {
    //     set({
    //       edgeError: {
    //         message: 'Connection limit reached in Peer-to-Peer topology',
    //         details: 'Each agent can connect to exactly 2 other agents in P2P topology.',
    //       },
    //     });
    //     return;
    //   }
    // }

    // Check if edge already exists (including reverse for bidirectional)
    const exists = template.internalEdges.find(e => e.from === fromAgentId && e.to === toAgentId);
    if (exists) return;

    // For bidirectional, also check reverse - only need one edge per pair
    if (topo.edgeType === 'bidirectional') {
      const reverseExists = template.internalEdges.find(e => e.from === toAgentId && e.to === fromAgentId);
      if (reverseExists) return;
    }

    const newEdge: InternalEdge = {
      id: generateId('ie'),
      from: fromAgentId,
      to: toAgentId,
      type: topo.edgeType,
    };

    if (!silent) {
      get().pushHistory();
    }

    set({
      topologyTemplates: get().topologyTemplates.map(t =>
        t.id === templateId ? { ...t, internalEdges: [...template.internalEdges, newEdge] } : t
      ),
    });

    if (!silent) {
      logEdit(
        'add_internal_edge',
        { edgeId: newEdge.id, templateId, from: fromAgentId, to: toAgentId, edgeType: topo.edgeType },
        get().undoStack.length,
      );
    }
  },

  deleteInternalEdge: (templateId, edgeId) => {
    get().pushHistory();
    set({
      topologyTemplates: get().topologyTemplates.map(t =>
        t.id === templateId
          ? { ...t, internalEdges: t.internalEdges.filter(e => e.id !== edgeId) }
          : t
      ),
    });
    logEdit('delete_internal_edge', { templateId, edgeId }, get().undoStack.length);
  },

  // Connection actions
  addConnection: (from, to, fromType, fromPort) => {
    const exists = get().connections.find(c => c.from === from && c.to === to && c.fromPort === fromPort);
    if (exists) return;

    const newConnection: Connection = {
      id: generateId('conn'),
      from,
      to,
      fromType,
      fromPort,
    };
    get().pushHistory();
    set({ connections: [...get().connections, newConnection] });
    logEdit(
      'add_connection',
      { connectionId: newConnection.id, from, to, fromType, fromPort: fromPort ?? null },
      get().undoStack.length,
    );
  },

  deleteConnection: (id) => {
    get().pushHistory();
    set({ connections: get().connections.filter(c => c.id !== id) });
    logEdit('delete_connection', { connectionId: id }, get().undoStack.length);
  },

  // If/Else condition actions
  addCondition: (nodeId) => {
    const node = get().nodes.find(n => n.id === nodeId);
    if (!node || node.type !== 'ifelse') return;

    const conditions = (node.config?.conditions as IfElseCondition[]) || [];
    const newCondition: IfElseCondition = {
      id: generateId('cond'),
      name: '',
      condition: '',
    };

    get().pushHistory();
    set({
      nodes: get().nodes.map(n =>
        n.id === nodeId
          ? { ...n, config: { ...n.config, conditions: [...conditions, newCondition] } }
          : n
      ),
    });
    logEdit('add_condition', { nodeId, conditionId: newCondition.id }, get().undoStack.length);
  },

  updateCondition: (nodeId, conditionId, updates) => {
    const node = get().nodes.find(n => n.id === nodeId);
    if (!node || node.type !== 'ifelse') return;

    const conditions = (node.config?.conditions as IfElseCondition[]) || [];
    const updatedConditions = conditions.map(c =>
      c.id === conditionId ? { ...c, ...updates } : c
    );

    get().pushHistory();
    set({
      nodes: get().nodes.map(n =>
        n.id === nodeId
          ? { ...n, config: { ...n.config, conditions: updatedConditions } }
          : n
      ),
    });
    logEdit('update_condition', { nodeId, conditionId, updates }, get().undoStack.length);
  },

  deleteCondition: (nodeId, conditionId) => {
    const node = get().nodes.find(n => n.id === nodeId);
    if (!node || node.type !== 'ifelse') return;

    const conditions = (node.config?.conditions as IfElseCondition[]) || [];
    // Don't allow deleting if only one condition remains
    if (conditions.length <= 1) return;

    const filteredConditions = conditions.filter(c => c.id !== conditionId);

    // Also remove any connections from this port
    const portIndex = conditions.findIndex(c => c.id === conditionId);

    get().pushHistory();
    set({
      nodes: get().nodes.map(n =>
        n.id === nodeId
          ? { ...n, config: { ...n.config, conditions: filteredConditions } }
          : n
      ),
      connections: get().connections.filter(c => !(c.from === nodeId && c.fromPort === portIndex)),
    });
    logEdit('delete_condition', { nodeId, conditionId }, get().undoStack.length);
  },

  // Agent-topology actions
  addAgentToTopology: (agentId, templateId, role) => {
    const template = get().topologyTemplates.find(t => t.id === templateId);
    if (!template) return;

    const topo = getTopologyDefinition(template.type);
    if (!topo) return;

    // Single history push for this whole user-initiated action; the deferred
    // auto-edges in setTimeout below run with silent=true so they coalesce
    // into this same undo step.
    get().pushHistory();

    // Handle Leader/Manager replacement: demote existing to Member/Worker
    let updatedNodes = get().nodes;
    let updatedTemplates = get().topologyTemplates;

    if (role === 'Leader' || role === 'Manager') {
      const demoteRole = role === 'Leader' ? 'Member' : 'Worker';
      const existingLeader = updatedNodes.find(
        n => n.topologyId === templateId && n.topologyRole === role
      );

      if (existingLeader) {
        console.log(`Demoting existing ${role} (${existingLeader.name}) to ${demoteRole}`);
        // Demote existing Leader/Manager to Member/Worker
        updatedNodes = updatedNodes.map(n =>
          n.id === existingLeader.id ? { ...n, topologyRole: demoteRole } : n
        );
        // Clear internal edges (will be recreated by autoEdgeOnRole)
        updatedTemplates = updatedTemplates.map(t =>
          t.id === templateId ? { ...t, internalEdges: [] } : t
        );
      }
    }

    // Update nodes with new agent assignment
    set({
      nodes: updatedNodes.map(n =>
        n.id === agentId
          ? { ...n, topologyId: templateId, topologyRole: role, topologyColor: template.color }
          : n
      ),
      topologyTemplates: updatedTemplates,
      rolePopup: null,
    });

    // Auto-connect for mesh topology
    if (topo.autoConnect) {
      setTimeout(() => {
        const agents = get().getAgentsInTopology(templateId);
        const edges: InternalEdge[] = [];

        for (let i = 0; i < agents.length; i++) {
          for (let j = 0; j < agents.length; j++) {
            if (i !== j) {
              edges.push({
                id: generateId(`ie-mesh-${i}-${j}`),
                from: agents[i].id,
                to: agents[j].id,
                type: 'bidirectional',
              });
            }
          }
        }

        set({
          topologyTemplates: get().topologyTemplates.map(t =>
            t.id === templateId ? { ...t, internalEdges: edges } : t
          ),
        });
      }, 50);
    }

    // Auto-connect for Chain topology (link by insertion order)
    // Connect the new agent to the end of the current chain
    if (template.type === 'chain') {
      setTimeout(() => {
        const currentTemplate = get().topologyTemplates.find(t => t.id === templateId);
        if (!currentTemplate) return;

        const agentsInTopo = get().nodes.filter(n => n.topologyId === templateId);

        // If this is the first agent, nothing to connect
        if (agentsInTopo.length <= 1) return;

        // Find the "tail" agent - the one with no outgoing edges
        // This is the last agent in the current chain
        const outgoingAgents = new Set(currentTemplate.internalEdges.map(e => e.from));
        const tailAgent = agentsInTopo.find(a => a.id !== agentId && !outgoingAgents.has(a.id));

        if (tailAgent) {
          // Connect tail to the new agent. silent=true: this auto-edge is part of
          // the parent addAgentToTopology cognitive action, not its own undo step.
          get().addInternalEdge(templateId, tailAgent.id, agentId, true);
        }
      }, 50);
    }

    // Auto-connect for role-based topologies (centralized, hierarchical)
    if (topo.autoEdgeOnRole && role) {
      setTimeout(() => {
        const agentsInTopo = get().nodes.filter(n => n.topologyId === templateId && n.id !== agentId);

        if (topo.id === 'centralized') {
          if (role === 'Leader') {
            agentsInTopo.filter(a => a.topologyRole === 'Member').forEach(member => {
              get().addInternalEdge(templateId, agentId, member.id, true);
            });
          } else if (role === 'Member') {
            const leader = agentsInTopo.find(a => a.topologyRole === 'Leader');
            if (leader) {
              get().addInternalEdge(templateId, leader.id, agentId, true);
            }
          }
        } else if (topo.id === 'hierarchical') {
          const workers = agentsInTopo.filter(a => a.topologyRole === 'Worker');

          if (role === 'Manager') {
            // Connect Manager to all Workers
            workers.forEach(worker => {
              get().addInternalEdge(templateId, agentId, worker.id, true);
            });
            // Connect Workers to each other
            for (let i = 0; i < workers.length; i++) {
              for (let j = i + 1; j < workers.length; j++) {
                get().addInternalEdge(templateId, workers[i].id, workers[j].id, true);
              }
            }
          } else if (role === 'Worker') {
            // Connect to Manager
            const manager = agentsInTopo.find(a => a.topologyRole === 'Manager');
            if (manager) {
              get().addInternalEdge(templateId, manager.id, agentId, true);
            }
            // Connect to all other Workers
            workers.forEach(worker => {
              get().addInternalEdge(templateId, agentId, worker.id, true);
            });
          }
        }
      }, 100);
    }

    // Single high-level log entry for the user's action. Auto-edges fired by
    // the setTimeouts above modify state silently and appear in the same
    // history snapshot that pushHistory() captured at function start.
    logEdit(
      'add_agent_to_topology',
      { agentId, templateId, role, topologyType: template.type },
      get().undoStack.length,
    );
  },

  removeAgentFromTopology: (agentId) => {
    const agent = get().nodes.find(n => n.id === agentId);
    if (!agent || !agent.topologyId) return;

    const fromTemplateId = agent.topologyId;

    get().pushHistory();
    set({
      topologyTemplates: get().topologyTemplates.map(t =>
        t.id === fromTemplateId
          ? {
              ...t,
              internalEdges: t.internalEdges.filter(e => e.from !== agentId && e.to !== agentId),
              startAgentId: t.startAgentId === agentId ? null : t.startAgentId,
            }
          : t
      ),
      nodes: get().nodes.map(n =>
        n.id === agentId
          ? { ...n, topologyId: null, topologyRole: null, topologyColor: null }
          : n
      ),
    });
    logEdit(
      'remove_agent_from_topology',
      { agentId, fromTemplateId },
      get().undoStack.length,
    );
  },

  // Drag actions
  setDraggingNode: (id) => set({ draggingNode: id }),
  setDraggingTopology: (id) => set({ draggingTopology: id }),
  setDragOffset: (offset) => set({ dragOffset: offset }),

  moveNode: (id, x, y) => {
    set({ nodes: get().nodes.map(n => n.id === id ? { ...n, x, y } : n) });
  },

  moveTopology: (id, x, y) => {
    const template = get().topologyTemplates.find(t => t.id === id);
    if (!template) return;

    const dx = x - template.x;
    const dy = y - template.y;

    // Move all agents inside topology with it
    set({
      nodes: get().nodes.map(n =>
        n.topologyId === id ? { ...n, x: n.x + dx, y: n.y + dy } : n
      ),
      topologyTemplates: get().topologyTemplates.map(t =>
        t.id === id ? { ...t, x, y } : t
      ),
    });
  },

  // Connection drawing actions
  setConnecting: (id, fromType, fromPort = null, fromInput = false) => set({ connecting: id, connectingFrom: fromType, connectingFromPort: fromPort, connectingFromInput: fromInput }),
  setInternalConnecting: (state) => set({ internalConnecting: state }),

  // Resize actions
  setResizing: (state) => set({ resizing: state }),
  setResizeStart: (state) => set({ resizeStart: state }),

  resizeTopology: (id, width, height) => {
    set({
      topologyTemplates: get().topologyTemplates.map(t =>
        t.id === id ? { ...t, width: Math.max(250, width), height: Math.max(180, height) } : t
      ),
    });
  },

  resizeNode: (id, width, height) => {
    set({
      nodes: get().nodes.map(n =>
        n.id === id ? { ...n, config: { ...n.config, width: Math.max(120, width), height: Math.max(60, height) } } : n
      ),
    });
  },

  // Role popup actions
  setRolePopup: (state) => set({ rolePopup: state }),

  // Chat actions
  addChatMessage: (message) => set({ chatMessages: [...get().chatMessages, message] }),
  clearChatMessages: () => set({ chatMessages: [] }),

  // Edge error actions
  setEdgeError: (error) => set({ edgeError: error }),

  // Workflow metadata actions
  setWorkflowName: (name) => set({ workflowName: name }),

  // Chat history actions
  addChatSession: (session) => set({ chatHistory: [session, ...get().chatHistory] }),
  removeChatSession: (sessionId) => set({ chatHistory: get().chatHistory.filter(s => s.id !== sessionId) }),
  updateChatSession: (sessionId, updates) => set({
    chatHistory: get().chatHistory.map(s => s.id === sessionId ? { ...s, ...updates } : s)
  }),
  clearChatHistory: () => set({ chatHistory: [] }),

  // Current chat actions
  setCurrentChat: (state) => set({ currentChat: { ...get().currentChat, ...state } }),
  addCurrentChatMessage: (message) => set({
    currentChat: { ...get().currentChat, messages: [...get().currentChat.messages, message] }
  }),
  addCurrentChatLogEntry: (entry) => set({
    currentChat: { ...get().currentChat, logEntries: [...get().currentChat.logEntries, entry] }
  }),
  clearCurrentChat: () => set({
    currentChat: {
      messages: [],
      logEntries: [],
      workflowId: null,
      currentSessionId: null,
      lastWorkflowHash: '',
    }
  }),

  // Utility
  getAgentsInTopology: (templateId) => {
    return get().nodes.filter(n => n.topologyId === templateId);
  },

  clearCanvas: () => {
    // Preserve Start/End nodes (they're deletion-protected invariants per
    // the trial UX spec) — only strip user-added agents/templates.
    const preserved = get().nodes.filter(
      (n) => n.type === 'start' || n.type === 'end'
    );
    console.log(`[canvasStore] clearCanvas: keeping ${preserved.length} start/end nodes`);
    set({
      nodes: preserved,
      topologyTemplates: [],
      connections: [],
      selectedNode: null,
      selectedTemplate: null,
      chatMessages: [],
    });
  },

  // Reset to a clean trial-start state: Start + End placeholder, empty
  // templates/edges, empty undo/redo stacks, default workflow name. Used by
  // ResearcherLanding when beginning a new (participant, task) trial.
  resetForNewTrial: () => {
    console.log('[canvasStore] resetForNewTrial: clearing state for new trial');
    set({
      nodes: [
        { id: 'start-1', type: 'start', x: 100, y: 80, name: 'Start', config: {}, topologyId: null, topologyRole: null, topologyColor: null },
        { id: 'end-1', type: 'end', x: 700, y: 80, name: 'End', config: {}, topologyId: null, topologyRole: null, topologyColor: null }
      ],
      topologyTemplates: [],
      connections: [],
      selectedNode: null,
      selectedNodes: [],
      selectedTemplate: null,
      undoStack: [],
      redoStack: [],
      workflowName: 'New agent',
      chatMessages: [],
      // currentChat is the actual state ChatPanel reads (messages + log).
      // chatMessages alone isn't enough — clear it here too so a new trial
      // starts with empty chat / log.
      currentChat: {
        messages: [],
        logEntries: [],
        workflowId: null,
        currentSessionId: null,
        lastWorkflowHash: '',
      },
    });
  },

  // History / undo-redo
  // pushHistory must be called BEFORE applying any structural mutation, so the
  // captured snapshot represents the pre-mutation state we can revert to.
  pushHistory: () => {
    const { nodes, topologyTemplates, connections, undoStack } = get();
    const snapshot: CanvasSnapshot = {
      nodes: nodes.map(n => ({ ...n, config: { ...n.config } })),
      topologyTemplates: topologyTemplates.map(t => ({
        ...t,
        internalEdges: t.internalEdges.map(e => ({ ...e })),
      })),
      connections: connections.map(c => ({ ...c })),
    };

    const next = [...undoStack, snapshot];
    if (next.length > MAX_HISTORY) {
      next.splice(0, next.length - MAX_HISTORY);
    }

    // Any new structural action invalidates the redo path.
    set({ undoStack: next, redoStack: [] });
  },

  undo: () => {
    const { undoStack, redoStack, nodes, topologyTemplates, connections } = get();
    if (undoStack.length === 0) {
      console.log('[canvasStore] undo: stack empty');
      return;
    }

    const snapshot = undoStack[undoStack.length - 1];
    const newUndoStack = undoStack.slice(0, -1);

    // Save current state into redoStack before restoring.
    const currentSnapshot: CanvasSnapshot = {
      nodes: nodes.map(n => ({ ...n, config: { ...n.config } })),
      topologyTemplates: topologyTemplates.map(t => ({
        ...t,
        internalEdges: t.internalEdges.map(e => ({ ...e })),
      })),
      connections: connections.map(c => ({ ...c })),
    };

    set({
      nodes: snapshot.nodes,
      topologyTemplates: snapshot.topologyTemplates,
      connections: snapshot.connections,
      undoStack: newUndoStack,
      redoStack: [...redoStack, currentSnapshot],
    });

    console.log(`[canvasStore] undo applied. depth=${newUndoStack.length}`);

    const sessionId = useSessionStore.getState().sessionId;
    if (sessionId) {
      editLogApi.appendEvent({
        sessionId,
        timestamp: new Date().toISOString(),
        eventType: 'undo',
        payload: { undoStackDepth: newUndoStack.length },
      });
    }
  },

  redo: () => {
    const { undoStack, redoStack, nodes, topologyTemplates, connections } = get();
    if (redoStack.length === 0) {
      console.log('[canvasStore] redo: stack empty');
      return;
    }

    const snapshot = redoStack[redoStack.length - 1];
    const newRedoStack = redoStack.slice(0, -1);

    const currentSnapshot: CanvasSnapshot = {
      nodes: nodes.map(n => ({ ...n, config: { ...n.config } })),
      topologyTemplates: topologyTemplates.map(t => ({
        ...t,
        internalEdges: t.internalEdges.map(e => ({ ...e })),
      })),
      connections: connections.map(c => ({ ...c })),
    };

    set({
      nodes: snapshot.nodes,
      topologyTemplates: snapshot.topologyTemplates,
      connections: snapshot.connections,
      undoStack: [...undoStack, currentSnapshot],
      redoStack: newRedoStack,
    });

    console.log(`[canvasStore] redo applied. redo-depth=${newRedoStack.length}`);

    const sessionId = useSessionStore.getState().sessionId;
    if (sessionId) {
      editLogApi.appendEvent({
        sessionId,
        timestamp: new Date().toISOString(),
        eventType: 'redo',
        payload: { redoStackDepth: newRedoStack.length },
      });
    }
  },

  getUndoStackDepth: () => get().undoStack.length,
}));
