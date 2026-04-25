import { Node, TopologyTemplate, Connection, IfElseCondition } from '../types';

const API_BASE = '/api';

interface WorkflowData {
  id?: string;
  name: string;
  agents: AgentData[];
  topologies: TopologyData[];
  connections: ConnectionData[];
  nodes: WorkflowNodeData[];
}

interface AgentData {
  id: string;
  name: string;
  instructions: string;
  model: string;
  topology_id: string | null;
  topology_role: string | null;
}

interface TopologyData {
  id: string;
  type: string;
  name: string;
  agents: string[];
  internal_edges: InternalEdgeData[];
  max_turns: number;
  timeout: number;
  early_termination: boolean;
  start_agent_id: string | null;
}

interface InternalEdgeData {
  id: string;
  from: string;
  to: string;
  type: string;
}

interface ConnectionData {
  id: string;
  from_id: string;
  to_id: string;
  from_type: string;
  from_port?: number;
}

interface WorkflowNodeData {
  id: string;
  type: 'start' | 'end' | 'agent' | 'topology' | 'ifelse' | 'approval' | 'note';
  name: string;
  config: Record<string, unknown>;
  conditions?: Array<{ id: string; name?: string; condition: string }>;
  approval_message?: string;
}

interface ApprovalRequiredData {
  execution_id: string;
  node_id: string;
  message: string;
}

interface ExecutionMessage {
  id: string;
  from: string;
  to: string;
  content: string;
  timestamp: string;
  metadata: Record<string, unknown>;
}

interface ConversationMessage {
  role: 'user' | 'assistant';
  content: string;
}

// Convert frontend state to API format
export const convertToApiFormat = (
  nodes: Node[],
  topologyTemplates: TopologyTemplate[],
  connections: Connection[],
  workflowName: string = 'Untitled Workflow'
): WorkflowData => {
  // Convert agents
  const agents: AgentData[] = nodes
    .filter(n => n.type === 'agent')
    .map(n => ({
      id: n.id,
      name: n.name,
      instructions: (n.config?.instructions as string) || '',
      model: (n.config?.model as string) || 'gpt-4o',
      topology_id: n.topologyId,
      topology_role: n.topologyRole,
    }));

  // Convert topologies
  const topologies: TopologyData[] = topologyTemplates.map(t => ({
    id: t.id,
    type: t.type,
    name: t.name,
    agents: nodes.filter(n => n.topologyId === t.id).map(n => n.id),
    internal_edges: t.internalEdges.map(e => ({
      id: e.id,
      from: e.from,
      to: e.to,
      type: e.type,
    })),
    max_turns: t.maxTurns,
    timeout: t.timeout,
    early_termination: t.earlyTermination,
    start_agent_id: t.startAgentId,
  }));

  // Convert connections (including from_port for branching)
  const connectionData: ConnectionData[] = connections.map(c => ({
    id: c.id,
    from_id: c.from,
    to_id: c.to,
    from_type: c.fromType,
    from_port: c.fromPort,
  }));

  // Convert workflow nodes (start, end, ifelse, approval, note)
  const workflowNodes: WorkflowNodeData[] = nodes
    .filter(n => ['start', 'end', 'ifelse', 'approval', 'note'].includes(n.type))
    .map(n => {
      const nodeData: WorkflowNodeData = {
        id: n.id,
        type: n.type as WorkflowNodeData['type'],
        name: n.name,
        config: n.config,
      };

      // For ifelse nodes, include conditions
      if (n.type === 'ifelse') {
        nodeData.conditions = (n.config?.conditions as IfElseCondition[]) || [];
      }

      // For approval nodes, include message
      if (n.type === 'approval') {
        nodeData.approval_message = (n.config?.message as string) || '';
      }

      return nodeData;
    });

  return {
    name: workflowName,
    agents,
    topologies,
    connections: connectionData,
    nodes: workflowNodes,
  };
};

// API functions
export const workflowApi = {
  // List all workflows
  list: async (): Promise<WorkflowData[]> => {
    const response = await fetch(`${API_BASE}/workflows`);
    if (!response.ok) throw new Error('Failed to fetch workflows');
    return response.json();
  },

  // Get a specific workflow
  get: async (id: string): Promise<WorkflowData> => {
    const response = await fetch(`${API_BASE}/workflows/${id}`);
    if (!response.ok) throw new Error('Failed to fetch workflow');
    return response.json();
  },

  // Create a new workflow
  create: async (data: WorkflowData): Promise<WorkflowData> => {
    const response = await fetch(`${API_BASE}/workflows`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!response.ok) throw new Error('Failed to create workflow');
    return response.json();
  },

  // Update a workflow
  update: async (id: string, data: Partial<WorkflowData>): Promise<WorkflowData> => {
    const response = await fetch(`${API_BASE}/workflows/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!response.ok) throw new Error('Failed to update workflow');
    return response.json();
  },

  // Delete a workflow
  delete: async (id: string): Promise<void> => {
    const response = await fetch(`${API_BASE}/workflows/${id}`, {
      method: 'DELETE',
    });
    if (!response.ok) throw new Error('Failed to delete workflow');
  },
};

export const executeApi = {
  // Execute workflow with streaming via POST + fetch ReadableStream
  stream: (
    workflowId: string,
    input: string,
    onMessage: (message: ExecutionMessage) => void,
    onComplete: (result: { output: string; turns_used: number }) => void,
    onError: (error: Error) => void,
    onApprovalRequired?: (data: ApprovalRequiredData) => void,
    history?: ConversationMessage[],
  ): AbortController => {
    const controller = new AbortController();

    fetch(`${API_BASE}/execute/${workflowId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ input, config_overrides: {}, history: history || [] }),
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`Execution failed: ${response.status}`);
        }
        if (!response.body) {
          throw new Error('No response body');
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const jsonStr = line.slice(6);
              if (jsonStr.trim()) {
                const data = JSON.parse(jsonStr);

                if (data.type === 'message') {
                  onMessage(data.data);
                } else if (data.type === 'complete') {
                  onComplete(data.data);
                } else if (data.type === 'approval_required' && onApprovalRequired) {
                  onApprovalRequired(data.data);
                }
              }
            }
          }
        }
      })
      .catch((error) => {
        if (error.name !== 'AbortError') {
          onError(error);
        }
      });

    return controller;
  },

  // Resume execution after approval decision
  resume: (
    workflowId: string,
    executionId: string,
    decision: 'approve' | 'reject',
    onMessage: (message: ExecutionMessage) => void,
    onComplete: (result: { output: string; turns_used: number }) => void,
    onError: (error: Error) => void,
    onApprovalRequired?: (data: ApprovalRequiredData) => void,
  ): AbortController => {
    const controller = new AbortController();

    fetch(`${API_BASE}/execute/${workflowId}/resume`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ execution_id: executionId, decision }),
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`Resume failed: ${response.status}`);
        }
        if (!response.body) {
          throw new Error('No response body');
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const jsonStr = line.slice(6);
              if (jsonStr.trim()) {
                const data = JSON.parse(jsonStr);

                if (data.type === 'message') {
                  onMessage(data.data);
                } else if (data.type === 'complete') {
                  onComplete(data.data);
                } else if (data.type === 'approval_required' && onApprovalRequired) {
                  onApprovalRequired(data.data);
                }
              }
            }
          }
        }
      })
      .catch((error) => {
        if (error.name !== 'AbortError') {
          onError(error);
        }
      });

    return controller;
  },

  // Execute workflow synchronously
  sync: async (
    workflowId: string,
    input: string,
    configOverrides?: Record<string, unknown>,
  ): Promise<{
    output: string;
    turns_used: number;
    duration_seconds: number;
    messages: ExecutionMessage[];
  }> => {
    const response = await fetch(`${API_BASE}/execute/${workflowId}/sync`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ input, config_overrides: configOverrides || {} }),
    });
    if (!response.ok) throw new Error('Failed to execute workflow');
    return response.json();
  },

  // Preview workflow (no LLM calls)
  preview: async (
    workflowId: string,
    input: string,
  ): Promise<{
    workflow_id: string;
    workflow_name: string;
    agent_count: number;
    topology_count: number;
    topologies: Array<{
      id: string;
      type: string;
      name: string;
      agents: string[];
      edge_count: number;
    }>;
  }> => {
    const response = await fetch(`${API_BASE}/execute/preview/${workflowId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ input, config_overrides: {} }),
    });
    if (!response.ok) throw new Error('Failed to preview workflow');
    return response.json();
  },
};

// Log saving API
interface SaveLogData {
  chatId: string;
  workflowName: string;
  messages: Array<{
    id: string;
    role: string;
    content: string;
  }>;
  logEntries: Array<{
    id: string;
    agent: string;
    content: string;
    timestamp: string;
    topologyInfo?: {
      topologyId: string;
      topologyName: string;
      topologyColor: string;
    } | null;
    agentRole?: string | null;
  }>;
  workflowId: string | null;
  createdAt: string;
}

export const logsApi = {
  // Save chat log to file
  save: async (data: SaveLogData): Promise<{ success: boolean; filepath: string }> => {
    console.log('[logsApi] Saving chat log:', data.chatId);
    const response = await fetch(`${API_BASE}/logs/save`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!response.ok) {
      const error = new Error(`Failed to save log: ${response.status}`);
      console.error('[logsApi] Save failed:', error);
      throw error;
    }
    const result = await response.json();
    console.log('[logsApi] Log saved successfully:', result.filepath);
    return result;
  },
};
