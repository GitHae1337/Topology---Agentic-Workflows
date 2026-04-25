# MAS Framework Implementation Reference

> This document serves as a comprehensive reference for the implemented Multi-Agent System Framework. Use this as context when continuing development.

---

## System Overview

The MAS Framework is a full-stack visual workflow builder for designing and executing multi-agent workflows with topology-aware orchestration.

```
CHI-Poster-2026/
├── frontend/                 # React + TypeScript (Port 3000)
│   ├── src/
│   │   ├── components/       # UI Components
│   │   │   ├── Canvas/       # Main drag-drop canvas
│   │   │   │   ├── Canvas.tsx
│   │   │   │   ├── ConnectionsLayer.tsx
│   │   │   │   └── InternalEdgesOverlay.tsx
│   │   │   ├── Sidebar/      # Node & Topology palettes
│   │   │   │   ├── Sidebar.tsx
│   │   │   │   ├── NodePalette.tsx
│   │   │   │   └── TopologyPalette.tsx
│   │   │   ├── ConfigPanel/  # Right panel configuration
│   │   │   │   ├── ConfigPanel.tsx
│   │   │   │   ├── AgentConfig.tsx
│   │   │   │   ├── TopologyConfig.tsx
│   │   │   │   ├── IfElseConfig.tsx
│   │   │   │   ├── NoteConfig.tsx
│   │   │   │   ├── ApprovalConfig.tsx
│   │   │   │   └── StartEndConfig.tsx
│   │   │   ├── ChatInput/    # Natural language commands
│   │   │   │   └── ChatInput.tsx
│   │   │   ├── ChatPanel/    # Chat mode panel
│   │   │   │   └── ChatPanel.tsx
│   │   │   ├── Node/         # Node components
│   │   │   │   ├── CanvasNode.tsx
│   │   │   │   ├── IfElseNode.tsx
│   │   │   │   ├── NoteNode.tsx
│   │   │   │   └── ApprovalNode.tsx
│   │   │   ├── TopologyTemplate/  # 6 topology containers
│   │   │   │   ├── TopologyTemplate.tsx
│   │   │   │   ├── PlaceholderVisualization.tsx
│   │   │   │   └── InternalEdges.tsx
│   │   │   └── common/       # Shared components
│   │   │       ├── RolePopup.tsx
│   │   │       └── DragPreview.tsx
│   │   ├── store/            # Zustand state management
│   │   │   ├── index.ts
│   │   │   └── canvasStore.ts
│   │   ├── types/            # TypeScript interfaces
│   │   │   └── index.ts
│   │   ├── constants/        # Node types, topology definitions, dimensions
│   │   │   ├── nodeTypes.ts
│   │   │   ├── topologies.ts
│   │   │   └── nodeDimensions.ts
│   │   ├── utils/            # Geometry, connections, placeholders
│   │   │   ├── geometry.ts
│   │   │   ├── connections.ts
│   │   │   └── placeholders.ts
│   │   ├── api/              # Backend API client
│   │   │   └── workflow.ts
│   │   ├── App.tsx           # Main app with canvas/chat mode toggle
│   │   ├── main.tsx          # React entry point
│   │   └── index.css         # Global styles with Tailwind
│   ├── package.json
│   ├── tailwind.config.js
│   ├── tsconfig.json
│   └── vite.config.ts
│
├── backend/                  # FastAPI + Python (Port 8000)
│   ├── app/
│   │   ├── main.py           # FastAPI application entry point
│   │   ├── api/              # REST endpoints
│   │   │   ├── workflows.py  # CRUD for workflows
│   │   │   ├── execute.py    # Execution with SSE streaming + approval resume
│   │   │   └── logs.py       # Chat log saving endpoint
│   │   ├── engine/           # Orchestration logic
│   │   │   ├── orchestrator.py       # Legacy orchestrator
│   │   │   ├── graph_orchestrator.py # Primary graph-based orchestrator
│   │   │   ├── message_router.py     # Message routing between agents
│   │   │   └── topologies/   # 7 topology executors
│   │   │       ├── base.py
│   │   │       ├── sequential.py
│   │   │       ├── centralized.py
│   │   │       ├── hierarchical.py
│   │   │       ├── p2p.py
│   │   │       ├── mesh.py
│   │   │       ├── dag.py
│   │   │       └── cyclic.py
│   │   ├── llm/              # LLM providers
│   │   │   ├── base.py       # LLMService interface + factory
│   │   │   └── providers/    # OpenAI
│   │   │       ├── openai_provider.py
│   │   │       └── anthropic_provider.py  # (Legacy, not used)
│   │   └── models/           # Pydantic models
│   │       ├── agent.py
│   │       ├── topology.py
│   │       └── workflow.py
│   ├── requirements.txt
│   ├── .env.example
│   └── workflows.db
│
├── mas-framework-prompt.md   # Original design spec
└── mas-framework-reference.md # This file
```

---

## Running the Project

### Frontend
```bash
cd frontend
npm install
npm run dev
# Open http://localhost:3000
```

### Backend
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env  # Add API keys
uvicorn app.main:app --reload
# API at http://localhost:8000
```

### Environment Variables
```
OPENAI_API_KEY=your_key
```

### Session Logging
On startup, the backend creates a timestamped log folder at `backend/logs/YYYY-MM-DD-HH-MM/` for storing execution logs.

---

## Core Data Types

### Frontend Types (`frontend/src/types/index.ts`)

```typescript
// Node Types
type NodeType = 'start' | 'agent' | 'end' | 'note' | 'ifelse' | 'approval';

// Topology Types (6 types)
type TopologyType = 'centralized' | 'sequential' | 'hierarchical' | 'p2p' | 'mesh' | 'cyclic';

type EdgeType = 'bidirectional' | 'unidirectional';

interface Node {
  id: string;
  type: NodeType;
  x: number;
  y: number;
  name: string;
  config: Record<string, unknown>;
  topologyId: string | null;
  topologyRole: string | null;      // 'Hub'|'Spoke' or 'Manager'|'Worker'
  topologyColor: string | null;
}

interface InternalEdge {
  id: string;
  from: string;
  to: string;
  type: EdgeType;
}

interface IfElseCondition {
  id: string;
  name?: string;
  condition: string;
}

interface TopologyTemplate {
  id: string;
  type: TopologyType;
  x: number;
  y: number;
  width: number;
  height: number;
  name: string;
  color: string;
  maxTurns: number;
  timeout: number;
  earlyTermination: boolean;
  internalEdges: InternalEdge[];
  startAgentId: string | null;      // Required for P2P, Mesh, Cyclic
}

interface Connection {
  id: string;
  from: string;
  to: string;
  fromType: 'node' | 'template';
  fromPort?: number;                // For ifelse: 0,1,2... for conditions, -1 for else
                                    // For approval: 0 for Approve, 1 for Reject
}

interface TopologyDefinition {
  id: TopologyType;
  name: string;
  subtitle: string;
  icon: string;
  masDesc: string;
  socialDesc: string;
  color: string;
  hasRoles: boolean;
  roles: string[];
  edgeType: EdgeType;
  autoConnect: boolean;
  autoEdgeOnRole: boolean;
  startPoint: string;
  endPoint: string;
  needsStartAgent: boolean;
  noLoops?: boolean;                // For sequential topology
}

interface NodeDefinition {
  type: NodeType;
  name: string;
  icon: string;
  color: string;
  desc: string;
}

interface RolePopupState {
  agentId: string;
  templateId: string;
  roles: string[];
  x: number;
  y: number;
}

// Chat & Execution Types
interface ChatPanelMessage {
  id: string;
  role: 'user' | 'assistant' | 'system' | 'separator';
  content: string;
  from?: string;       // Agent name
}

interface ChatPanelLogEntry {
  id: string;
  from: string;
  to: string;
  content: string;
  timestamp: Date;
  metadata?: Record<string, unknown>;
}

interface ChatSession {
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

interface CurrentChatState {
  messages: ChatPanelMessage[];
  logEntries: ChatPanelLogEntry[];
  workflowId: string | null;
  currentSessionId: string | null;
  lastWorkflowHash: string;
}

interface PlaceholderNode {
  x: number;
  y: number;
  label: string;
  isMain?: boolean;
}

interface PlaceholderEdge {
  from: number;
  to: number;
  bidirectional?: boolean;
}

interface PlaceholderConfig {
  nodes: PlaceholderNode[];
  edges: PlaceholderEdge[];
}
```

### Backend Models (`backend/app/models/`)

```python
# agent.py
class AgentConfig(BaseModel):
    id: str
    name: str
    instructions: str = ""
    model: str = "gpt-4.1"           # Default model
    topology_id: Optional[str] = None
    topology_role: Optional[str] = None
    config: Dict[str, Any] = {}

    @property
    def provider(self) -> ModelProvider:  # Returns OpenAI

# topology.py
class TopologyType(str, Enum):
    CENTRALIZED = "centralized"
    SEQUENTIAL = "sequential"
    HIERARCHICAL = "hierarchical"
    P2P = "p2p"
    MESH = "mesh"
    DAG = "dag"
    CYCLIC = "cyclic"

class TopologyConfig(BaseModel):
    id: str
    type: TopologyType
    name: str
    agents: List[str]
    internal_edges: List[InternalEdge]
    max_turns: int = 3               # Default
    timeout: int = 180               # Default
    early_termination: bool = True
    start_agent_id: Optional[str] = None

# workflow.py
class WorkflowNodeType(str, Enum):
    START = "start"
    END = "end"
    AGENT = "agent"
    TOPOLOGY = "topology"
    IFELSE = "ifelse"
    APPROVAL = "approval"
    NOTE = "note"

class WorkflowNode(BaseModel):
    id: str
    type: WorkflowNodeType
    name: str
    config: Dict[str, Any]
    conditions: List[IfElseConditionModel]  # For ifelse nodes
    approval_message: Optional[str]         # For approval nodes

class WorkflowConnection(BaseModel):
    id: str
    from_id: str
    to_id: str
    from_type: str
    from_port: Optional[int]          # Branch port for ifelse/approval

class WorkflowDefinition(BaseModel):
    id: str
    name: str
    agents: List[AgentConfig]
    topologies: List[TopologyConfig]
    connections: List[WorkflowConnection]
    nodes: List[WorkflowNode]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
```

---

## Zustand Store (`frontend/src/store/canvasStore.ts`)

Key state and actions:

```typescript
interface CanvasState {
  // Canvas data
  nodes: Node[];
  topologyTemplates: TopologyTemplate[];
  connections: Connection[];

  // Selection state
  selectedNode: string | null;
  selectedNodes: string[];           // Multi-select support
  selectedTemplate: string | null;
  selectionBox: { startX: number; startY: number; endX: number; endY: number } | null;

  // Drag state
  draggingNode: string | null;
  draggingTopology: string | null;
  dragOffset: { x: number; y: number };

  // Connection drawing state
  connecting: string | null;
  connectingFrom: 'node' | 'template' | null;
  connectingFromPort: number | null; // For IfElse/Approval port connections
  internalConnecting: { agentId: string; templateId: string } | null;

  // Resize state
  resizing: { id: string; type?: 'topology' | 'node' } | null;
  resizeStart: { x: number; y: number; width: number; height: number };

  // Role popup
  rolePopup: RolePopupState | null;

  // Edge error (for loop prevention messages)
  edgeError: { message: string; details: string } | null;

  // Chat state
  chatMessages: ChatMessage[];
  chatHistory: ChatSession[];
  currentChat: CurrentChatState;

  // Workflow metadata
  workflowName: string;

  // Node actions
  addNode: (type: NodeType, x: number, y: number) => void;
  updateNode: (id: string, updates: Partial<Node>) => void;
  deleteNode: (id: string) => void;
  setSelectedNode: (id: string | null) => void;
  setSelectedNodes: (ids: string[]) => void;
  clearSelection: () => void;
  setSelectionBox: (box: {...} | null) => void;
  selectNodesInBox: () => void;
  moveSelectedNodes: (dx: number, dy: number) => void;

  // Topology actions
  addTopologyTemplate: (type: TopologyType, x: number, y: number) => void;
  updateTopologyTemplate: (id: string, updates: Partial<TopologyTemplate>) => void;
  deleteTopologyTemplate: (id: string) => void;
  setSelectedTemplate: (id: string | null) => void;

  // Internal edge actions (with constraint validation)
  addInternalEdge: (templateId: string, fromAgentId: string, toAgentId: string) => void;
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
  setConnecting: (id: string | null, fromType: 'node' | 'template' | null, fromPort?: number | null) => void;
  setInternalConnecting: (state: { agentId: string; templateId: string } | null) => void;

  // Resize actions
  setResizing: (state: { id: string; type?: 'topology' | 'node' } | null) => void;
  setResizeStart: (state: { x: number; y: number; width: number; height: number }) => void;
  resizeTopology: (id: string, width: number, height: number) => void;
  resizeNode: (id: string, width: number, height: number) => void;

  // Role popup actions
  setRolePopup: (state: RolePopupState | null) => void;

  // Chat actions
  setCurrentChat: (state: CurrentChatState) => void;
  addCurrentChatMessage: (message: ChatPanelMessage) => void;
  addCurrentChatLogEntry: (entry: ChatPanelLogEntry) => void;
  clearCurrentChat: () => void;
  addChatSession: (session: ChatSession) => void;
  removeChatSession: (id: string) => void;
  updateChatSession: (id: string, updates: Partial<ChatSession>) => void;
  clearChatHistory: () => void;

  // Edge error actions
  setEdgeError: (error: { message: string; details: string } | null) => void;

  // Workflow metadata actions
  setWorkflowName: (name: string) => void;

  // Utility
  getAgentsInTopology: (templateId: string) => Node[];
  clearCanvas: () => void;
}
```

### Store Behaviors

**Internal Edge Constraints:**
- Sequential topology: Prevents cycles via DFS validation
- P2P topology: Limits each agent to max 2 connections
- Prevents duplicate edges

**Role Auto-Demotion:**
- Adding a Hub demotes existing Hub to Spoke
- Adding a Manager demotes existing Manager to Worker

**Auto-Connection:**
- Mesh topology: Auto-connects all agent pairs
- Centralized/Hierarchical: Auto-connects on role assignment

### Initial State
```typescript
nodes: [
  { id: 'start-1', type: 'start', x: 100, y: 80, name: 'Start', config: {}, topologyId: null, topologyRole: null, topologyColor: null }
],
workflowName: 'New agent'
```

---

## 6 Topology Types

| Topology | Roles | Edge Type | Auto-Connect | Edge Deletable | Start Agent | Execution Pattern |
|----------|-------|-----------|--------------|----------------|-------------|-------------------|
| **Centralized** | Hub, Spoke | Bidirectional | On role assign | No | Hub | Hub assigns tasks, spokes execute in parallel |
| **Sequential** | None | Unidirectional | None | Yes | First in chain | Pipeline: output → next input (no loops) |
| **Hierarchical** | Manager, Worker | Bidirectional | On role assign | No | Manager | Manager delegates, workers report, peer discussions |
| **P2P** | None | Bidirectional | None | Yes | Required | Round-based with adjacent agent visibility |
| **Mesh** | None | Bidirectional | All pairs | No | Required | Debate rounds with full cumulative visibility |
| **Cyclic** | None | Unidirectional | None | Yes | Required | Iterative refinement loops |

### Topology Constants (`frontend/src/constants/topologies.ts`)

```typescript
const topologies: TopologyDefinition[] = [
  {
    id: 'centralized',
    name: 'Centralized',
    subtitle: 'Hub-Spoke',
    icon: '✦',
    masDesc: 'Single orchestrator routes all communication',
    socialDesc: 'Wheel/star network',
    color: '#f59e0b',
    hasRoles: true,
    roles: ['Hub', 'Spoke'],
    edgeType: 'bidirectional',
    autoConnect: false,
    autoEdgeOnRole: true,
    startPoint: 'Hub receives input',
    endPoint: 'Hub summarizes conversation for output',
    needsStartAgent: false,
  },
  {
    id: 'sequential',
    name: 'Sequential',
    subtitle: 'Pipeline',
    icon: '→',
    masDesc: "Output feeds next agent's input",
    socialDesc: 'Chain network',
    color: '#3b82f6',
    hasRoles: false,
    roles: [],
    edgeType: 'unidirectional',
    autoConnect: false,
    autoEdgeOnRole: false,
    startPoint: 'First agent receives input',
    endPoint: 'Last agent produces output',
    needsStartAgent: false,
    noLoops: true,  // Prevents cycle creation
  },
  {
    id: 'hierarchical',
    name: 'Hierarchical',
    subtitle: 'Tree',
    icon: '△',
    masDesc: 'Multi-level managers overseeing workers',
    socialDesc: 'Y-pattern or tree',
    color: '#8b5cf6',
    hasRoles: true,
    roles: ['Manager', 'Worker'],
    edgeType: 'bidirectional',
    autoConnect: false,
    autoEdgeOnRole: true,
    startPoint: 'Manager receives input',
    endPoint: 'Manager summarizes conversation for output',
    needsStartAgent: false,
  },
  {
    id: 'p2p',
    name: 'Peer-to-Peer',
    subtitle: 'P2P',
    icon: '○',
    masDesc: 'Agents communicate directly without coordinator',
    socialDesc: 'Circle or all-channel',
    color: '#22c55e',
    hasRoles: false,
    roles: [],
    edgeType: 'bidirectional',
    autoConnect: false,
    autoEdgeOnRole: false,
    startPoint: 'Specify start agent before run',
    endPoint: 'Last agent summarizes for output',
    needsStartAgent: true,
  },
  {
    id: 'mesh',
    name: 'Mesh',
    subtitle: 'Fully-Connected',
    icon: '◈',
    masDesc: 'Every agent can reach every other',
    socialDesc: 'All-channel (comcon)',
    color: '#ec4899',
    hasRoles: false,
    roles: [],
    edgeType: 'bidirectional',
    autoConnect: true,   // Auto-connects all pairs when agent added
    autoEdgeOnRole: false,
    startPoint: 'Specify start agent before run',
    endPoint: 'Last agent summarizes for output',
    needsStartAgent: true,
  },
  {
    id: 'cyclic',
    name: 'Cyclic',
    subtitle: 'Loop',
    icon: '↺',
    masDesc: 'Allows iterative refinement loops',
    socialDesc: 'Novel pattern',
    color: '#f97316',
    hasRoles: false,
    roles: [],
    edgeType: 'unidirectional',
    autoConnect: false,
    autoEdgeOnRole: false,
    startPoint: 'Specify start agent before run',
    endPoint: 'Last agent summarizes for output',
    needsStartAgent: true,
  },
];
```

---

## Node Types (`frontend/src/constants/nodeTypes.ts`)

```typescript
// Core Nodes
const coreNodes: NodeDefinition[] = [
  { type: 'start', name: 'Start', icon: '▶', color: '#6366f1', desc: 'Entry point' },
  { type: 'agent', name: 'Agent', icon: '▽', color: '#6366f1', desc: 'AI agent node' },
  { type: 'end', name: 'End', icon: '■', color: '#22c55e', desc: 'End workflow' },
  { type: 'note', name: 'Note', icon: '□', color: '#6b7280', desc: 'Add documentation' },
];

// Logic Nodes
const logicNodes: NodeDefinition[] = [
  { type: 'ifelse', name: 'If / else', icon: '⤷', color: '#f59e0b', desc: 'Conditional branch' },
  { type: 'approval', name: 'User approval', icon: '✋', color: '#f59e0b', desc: 'Human review' },
];

// Helper functions
getNodeDefinition(type): NodeDefinition
getNodeColor(type): string
getNodeIcon(type): string
```

---

## Node Dimensions (`frontend/src/constants/nodeDimensions.ts`)

Central source of truth for consistent node sizing and port positioning:

```typescript
// Base dimensions
const NODE_WIDTH = 160;

// Node heights by type
const NODE_HEIGHTS = {
  start: 52,           // Header only
  end: 52,             // Header only
  agent: 88,           // Header + content section
  agentInTopology: 52, // Header only when inside topology
  note: 88,            // Header + content
  approval: 88,        // Header + content
};

// IfElse node dimensions
const IFELSE_WIDTH = 200;
const IFELSE_HEADER_HEIGHT = 48;
const IFELSE_CONDITION_HEIGHT = 44;
const IFELSE_ELSE_HEIGHT = 44;
const IFELSE_PADDING = 8;

// Approval node dimensions
const APPROVAL_WIDTH = 180;
const APPROVAL_HEADER_HEIGHT = 48;
const APPROVAL_OPTION_HEIGHT = 40;
const APPROVAL_PADDING = 8;

// Topology header
const TOPOLOGY_HEADER_HEIGHT = 40;

// Port position calculators (LEFT side = input, RIGHT side = output)
getNodeInputPosition(nodeX, nodeY, nodeType, isInTopology): PortPosition   // Left side, vertically centered
getNodeOutputPosition(nodeX, nodeY, nodeType, isInTopology): PortPosition  // Right side, vertically centered
getIfElseInputPosition(nodeX, nodeY, conditionsCount): PortPosition
getIfElseOutputPosition(nodeX, nodeY, portIndex, conditionsCount): PortPosition
getApprovalInputPosition(nodeX, nodeY): PortPosition
getApprovalOutputPosition(nodeX, nodeY, portIndex): PortPosition  // 0=Approve, 1=Reject
getTopologyInputPosition(templateX, templateY, templateWidth, templateHeight): PortPosition
getTopologyOutputPosition(templateX, templateY, templateWidth, templateHeight): PortPosition

// Direction helpers (all horizontal - left/right)
getOutputDirection(nodeType): 'horizontal'
getInputDirection(nodeType): 'horizontal'
```

---

## App Modes (`frontend/src/App.tsx`)

The app has two modes toggled via the top bar:

1. **Canvas Mode** (default):
   - Sidebar visible for adding nodes/topologies
   - Canvas fully interactive
   - ChatInput visible for natural language commands
   - ConfigPanel shows on selection

2. **Chat Mode**:
   - Sidebar hidden
   - Canvas visible but non-interactive (overlay blocks interaction)
   - ChatPanel replaces ConfigPanel for executing/testing workflow

### Validation (Before Switching to Chat Mode)
- Must have at least one Start node
- Must have at least one End node
- All IfElse nodes must have condition expressions filled
- All topologies must be reachable from Start (BFS validation)
- All topologies must be able to reach End (reverse BFS validation)

---

## Frontend Components

### Canvas (`frontend/src/components/Canvas/Canvas.tsx`)
- Handles mouse events for drag-drop
- Renders TopologyTemplates and Nodes
- Manages drop-into-topology detection with role popup
- Keyboard support: Backspace/Delete removes selected nodes (disabled in chat mode)
- Supports multi-select with selection box
- Passes `mode` prop to child components to disable deletion in chat mode

### ConnectionsLayer (`frontend/src/components/Canvas/ConnectionsLayer.tsx`)
- SVG overlay for workflow-level connections
- Calculates bezier paths between nodes/topologies
- Handles different port positions for IfElse/Approval nodes
- Shows dashed preview line while drawing connection (including from topologies)
- Hover-to-reveal delete buttons on all workflow connections

### InternalEdgesOverlay (`frontend/src/components/Canvas/InternalEdgesOverlay.tsx`)
- SVG overlay for internal topology edges
- Arrow markers for edge direction
- Hover-to-reveal delete buttons on edges (only for P2P, Cyclic, Sequential)
- No delete buttons for auto-connected topologies (Centralized, Hierarchical, Mesh)
- Smart connection point calculation based on topology type and roles
- Shows dashed preview line while drawing internal connection

### CanvasNode (`frontend/src/components/Node/CanvasNode.tsx`)
- Draggable node with connection dots (left=input, right=output)
- Internal connection dots when inside topology (hidden for auto-connect topologies)
- Role badge display for Hub/Spoke/Manager/Worker
- Delete button on hover (hidden in chat mode)

### IfElseNode (`frontend/src/components/Node/IfElseNode.tsx`)
- Dynamic height based on number of conditions
- Output port per condition + else port (right side)
- Input port on left side

### NoteNode (`frontend/src/components/Node/NoteNode.tsx`)
- Resizable annotation node
- No connection ports (purely for documentation)
- Shows content preview in header

### ApprovalNode (`frontend/src/components/Node/ApprovalNode.tsx`)
- Human-in-the-loop approval step
- Approve (green) and Reject (red) output ports on right side
- Input port on left side

### TopologyTemplate (`frontend/src/components/TopologyTemplate/TopologyTemplate.tsx`)
- Resizable container with dashed border
- Shows placeholder visualization when empty
- Connection dots: left (input), right (output)
- Resize handle bottom-right
- Delete button hidden in chat mode

### PlaceholderVisualization (`frontend/src/components/TopologyTemplate/PlaceholderVisualization.tsx`)
- Dashed node/edge preview showing topology structure
- Different visualizations for each topology type

### Sidebar (`frontend/src/components/Sidebar/Sidebar.tsx`)
- Collapsible left panel
- Editable workflow name
- Contains NodePalette and TopologyPalette

### ConfigPanel (`frontend/src/components/ConfigPanel/ConfigPanel.tsx`)
- Routes to appropriate config based on selection:
  - AgentConfig: Name, instructions, model selection
  - TopologyConfig: Max turns, timeout, start agent selector
  - IfElseConfig: Condition expressions
  - NoteConfig: Note content
  - ApprovalConfig: Name and message
  - StartEndConfig: Start/End node configuration

### ChatInput (`frontend/src/components/ChatInput/ChatInput.tsx`)
Natural language commands:
- `add agent` / `add 3 agents`
- `add [topology-name] topology`
- `clear`

### ChatPanel (`frontend/src/components/ChatPanel/ChatPanel.tsx`)
- Execution panel for testing workflow
- Message history with user/assistant roles
- Log view with agent communication timeline
- Groups log entries by topology with color-coded containers
- Chat session history management

### RolePopup (`frontend/src/components/common/RolePopup.tsx`)
- Appears when dropping agent into role-based topology
- Allows selecting Hub/Spoke or Manager/Worker

---

## Key Utilities

### Geometry (`frontend/src/utils/geometry.ts`)
```typescript
isInsideTopology(agentX, agentY, template): boolean
getEntityPosition(entityId, nodes, topologyTemplates): {x, y, height} | null
calculateBezierPath(x1, y1, x2, y2, offset): string
calculateArrowTransform(x1, y1, x2, y2): {angle, endX, endY}
```

### Placeholders (`frontend/src/utils/placeholders.ts`)
```typescript
getPlaceholderConfig(topoType, width, height): PlaceholderConfig
// Returns nodes and edges for dashed visualization per topology type
```

### Connections (`frontend/src/utils/connections.ts`)
```typescript
wouldCreateCycle(fromId, toId, edges): boolean  // For DAG/Sequential validation
findEntryNodes(agentIds, edges): string[]
findTerminalNodes(agentIds, edges): string[]
topologicalSort(agentIds, edges): string[]
```

---

## API Client (`frontend/src/api/workflow.ts`)

### Data Conversion
```typescript
convertToApiFormat(nodes, topologyTemplates, connections, workflowName): WorkflowData
```

### Workflow API
```typescript
workflowApi.list(): Promise<WorkflowData[]>
workflowApi.get(id): Promise<WorkflowData>
workflowApi.create(data): Promise<WorkflowData>
workflowApi.update(id, data): Promise<WorkflowData>
workflowApi.delete(id): Promise<void>
```

### Execute API
```typescript
executeApi.stream(workflowId, input, onMessage, onComplete, onError): EventSource
executeApi.resume(workflowId, executionId, decision): Promise  // Resume after approval
executeApi.sync(workflowId, input, configOverrides?): Promise<ExecutionResult>
executeApi.preview(workflowId, input): Promise<PreviewResult>
```

### Logs API
```typescript
logsApi.save(data): Promise<{ filepath: string }>
// Saves chat log to backend session folder
```

---

## Backend Execution System

### Graph Orchestrator (`backend/app/engine/graph_orchestrator.py`) - PRIMARY

The main orchestration engine that executes workflows by traversing a connection graph.

**ExecutionContext:**
```python
@dataclass
class ExecutionContext:
    workflow_id: str
    execution_id: str
    user_input: str
    current_output: str
    variables: Dict[str, Any]
    message_history: List[ExecutionMessage]
```

**ConditionEvaluator:**
- Safely evaluates If/Else conditions
- Operators: `==`, `!=`, `>`, `<`, `>=`, `<=`, `contains`, `startswith`, `endswith`
- Pattern format: `"variable operator value"` (e.g., `"output contains error"`)
- Supports variables: `input`, `output`, `true`, `false`, custom context variables
- Supports dot notation for nested variables

**Execution Flow:**
1. Find START node
2. Follow connections to next nodes
3. Handle node types:
   - **TOPOLOGY**: Execute topology with agents
   - **AGENT**: Call standalone agent with LLM
   - **IFELSE**: Evaluate conditions, follow matching branch (port)
   - **APPROVAL**: Pause execution, store context, wait for resume
   - **NOTE**: Pass through (documentation)
   - **END**: Terminate
4. Update context with outputs
5. Continue until END node or error

**Parallel Execution:**
- Multiple nodes from START execute in parallel
- Each gets independent context copy
- Results concatenated with `"\n\n"` separator

### Base Topology Executor (`backend/app/engine/topologies/base.py`)

```python
class BaseTopologyExecutor(ABC):
    @abstractmethod
    async def execute(
        self,
        topology: TopologyConfig,
        agents: Dict[str, AgentConfig],
        input_message: str,
    ) -> AsyncGenerator[ExecutionMessage, None]:
        pass

    async def call_agent(self, agent: AgentConfig, conversation: List[LLMMessage]) -> str
    def check_early_termination(self, content: str) -> bool
    def get_adjacency_list(self, topology: TopologyConfig) -> Dict[str, List[str]]
    def create_message(self, from_agent, to_agent, content, metadata) -> ExecutionMessage
```

**Early Termination Signals:** `[TASK_COMPLETE]`, `[DONE]`, `[FINISHED]`, `FINAL ANSWER:`, `In conclusion,`

### Topology Executors

**Centralized (Hub-Spoke)** - `topologies/centralized.py`
- **Execution Flow:**
  1. Hub receives task and decomposes into subtasks using `[ASSIGN:AgentName]` format
  2. Spoke agents execute assigned subtasks in parallel
  3. Hub reviews all results, can assign new tasks or synthesize
  4. Terminates when Hub outputs `[FINAL SYNTHESIS]` or completion signals
- **Features:** Multi-round coordination, parallel sub-agent execution, context tracking per round

**Sequential (Pipeline)** - `topologies/sequential.py`
- **Execution Flow:**
  1. Find entry node (no incoming edges) via DFS
  2. Execute agents in order following edges
  3. Each agent receives previous agent's output
  4. Terminal agent produces final output
- **Features:** Position info (first/middle/last agent), output chaining

**Hierarchical (Manager-Worker)** - `topologies/hierarchical.py`
- **Execution Flow:**
  1. Manager decomposes task into worker subtasks using `[ASSIGN:WorkerName]` format
  2. Workers execute assigned tasks in parallel
  3. Manager can instruct peer discussions: `[PEER:WorkerA,WorkerB] instruction`
  4. Peer rounds enable cross-verification between worker pairs (parallel)
  5. Manager synthesizes all findings plus peer results with `[FINAL SYNTHESIS]`
- **Features:** Peer discussion capability, separate tracking of worker outputs and peer results

**P2P (Peer-to-Peer)** - `topologies/p2p.py`
- **Execution Flow:**
  1. Round 1: All agents receive same task independently (parallel reasoning)
  2. Round 2+: Each agent sees ONLY adjacent agents' responses (based on edges)
  3. Repeat until max rounds, consensus, or early termination
  4. Start agent synthesizes via majority voting
- **Features:** Round-based execution, adjacency-based visibility, convergence detection

**Mesh (Debate)** - `topologies/mesh.py`
- **Execution Flow:**
  1. Round 1: All agents receive task simultaneously (parallel)
  2. Round 2+: All agents see COMPLETE CUMULATIVE HISTORY from all previous rounds
  3. Agents can detect and report consensus with `CONSENSUS REACHED:`
  4. Start agent performs majority voting synthesis
- **Features:** Full visibility, cumulative history, consensus detection (majority)

**DAG** - `topologies/dag.py`
- **Execution Flow:**
  1. Identify entry nodes (no incoming edges) and terminal nodes (no outgoing edges)
  2. Execute entry nodes in parallel with input
  3. When node completes, trigger downstream nodes whose dependencies are satisfied
  4. Nodes with multiple inputs wait for ALL predecessors to complete
  5. Terminal nodes produce final outputs
- **Features:** Dependency-based execution with in-degree tracking, multi-input handling

**Cyclic** - `topologies/cyclic.py`
- **Execution Flow:**
  1. Start agent receives input
  2. Agents iterate following edges (cycles allowed)
  3. Each iteration refines previous output with new context
  4. Terminates at max_turns or when `TASK COMPLETE:` signal detected
- **Features:** Supports cycles, iteration tracking, output history per agent

### Executor Factory (`backend/app/engine/topologies/__init__.py`)

```python
def get_executor(topology_type: str) -> BaseTopologyExecutor:
    executors = {
        "centralized": CentralizedExecutor(),
        "sequential": SequentialExecutor(),
        "hierarchical": HierarchicalExecutor(),
        "p2p": P2PExecutor(),
        "mesh": MeshExecutor(),
        "dag": DAGExecutor(),
        "cyclic": CyclicExecutor(),
    }
    return executors[topology_type]
```

---

## API Endpoints

### Workflows (`/api/workflows`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | List all workflows |
| GET | `/{id}` | Get workflow by ID |
| POST | `/` | Create workflow |
| PUT | `/{id}` | Update workflow |
| DELETE | `/{id}` | Delete workflow |

### Execution (`/api/execute`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/{workflow_id}` | Execute with SSE streaming |
| POST | `/{workflow_id}/resume` | Resume after approval |
| POST | `/{workflow_id}/sync` | Execute synchronously |
| POST | `/preview/{workflow_id}` | Preview without LLM calls |

### Logs (`/api/logs`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/save` | Save chat log to session folder |

### SSE Event Format
```json
// Message event
{"type": "message", "data": {"id": "msg-1", "from": "agent-1", "to": "agent-2", "content": "..."}}

// Approval pause event
{"type": "approval_required", "data": {"execution_id": "...", "node_id": "...", "message": "..."}}

// Complete event
{"type": "complete", "data": {"output": "...", "turns_used": 8}}
```

---

## LLM Integration

### Service Factory (`backend/app/llm/base.py`)
```python
class LLMServiceFactory:
    @classmethod
    def get_service(cls, model: str) -> LLMService:
        return OpenAIService()  # Only OpenAI supported
```

### OpenAI Provider (`backend/app/llm/providers/openai_provider.py`)

**Supported Models:**
- `gpt-4.1` (default)
- `gpt-5`
- `gpt-5.2`
- `gpt-5-nano`
- `gpt-5-mini`

**Features:**
- Uses `responses.create` API for all models
- Web search tool support
- Reasoning effort configuration (medium) for reasoning models
- Robust response content extraction

---

## Styling (`frontend/src/index.css`)

Key CSS classes:
- `.canvas-grid` - Dot grid background pattern
- `.selection-ring` - Blue selection highlight
- `.node-transition` - Smooth transitions for nodes
- `.internal-edge-group:hover` - Shows delete button on edge hover

---

## Database

SQLite file: `backend/workflows.db`

Schema:
```sql
CREATE TABLE workflows (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    data TEXT NOT NULL,  -- JSON blob
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

---

## Common Development Tasks

### Adding a New Node Type
1. Add to `NodeType` in `frontend/src/types/index.ts`
2. Add definition to `frontend/src/constants/nodeTypes.ts`
3. Add height constant to `frontend/src/constants/nodeDimensions.ts`
4. Create node component in `frontend/src/components/Node/`
5. Create config component in `frontend/src/components/ConfigPanel/`
6. Handle rendering in `Canvas.tsx`
7. Handle config routing in `ConfigPanel.tsx`

### Adding a New Topology Type
1. Add to `TopologyType` enum (frontend types + backend models)
2. Add definition to `frontend/src/constants/topologies.ts`
3. Add placeholder config in `frontend/src/utils/placeholders.ts`
4. Create executor in `backend/app/engine/topologies/`
5. Register in executor factory

### Modifying Agent Configuration
1. Update `AgentConfig.tsx` for UI
2. Update `AgentConfig` model in `backend/app/models/agent.py`
3. Update `convertToApiFormat` in `frontend/src/api/workflow.ts`

---

## Testing Checklist

### Frontend
- [ ] Drag nodes from sidebar to canvas
- [ ] Click nodes in sidebar to add at random position
- [ ] Drag topology templates to canvas
- [ ] Drop agent into topology → role popup (Centralized/Hierarchical)
- [ ] Drop agent into topology → auto-connect (Mesh)
- [ ] Draw internal edges between agents (P2P/Sequential/Cyclic)
- [ ] Sequential topology prevents loop creation
- [ ] P2P topology limits agent connections to 2
- [ ] Resize topology template
- [ ] Resize note node
- [ ] IfElse node conditions work with port connections
- [ ] Approval node Approve/Reject paths connect correctly
- [ ] Configuration panels update state
- [ ] Chat commands work
- [ ] Multi-select nodes with selection box
- [ ] Delete selected nodes with Backspace/Delete (disabled in chat mode)
- [ ] Canvas/Chat mode toggle with validation
- [ ] Workflow name editable in sidebar
- [ ] Connection preview shows for topologies
- [ ] Internal connection preview shows for sequential/p2p/cyclic

### Backend
- [ ] `POST /api/workflows` creates workflow
- [ ] `GET /api/workflows/{id}` returns workflow
- [ ] `POST /api/execute/{id}` streams messages
- [ ] Centralized topology assigns tasks and executes in parallel
- [ ] Hierarchical topology supports peer discussions
- [ ] P2P topology uses round-based execution with adjacency visibility
- [ ] Mesh topology uses cumulative history and consensus detection
- [ ] Each topology executor runs correctly
- [ ] Approval pause/resume works
- [ ] `POST /api/logs/save` saves chat log

---

## Original Spec Reference

For detailed design requirements, see `mas-framework-prompt.md`:
- Topology behavior specifications
- Visual interaction patterns
- Execution logic for each topology type
