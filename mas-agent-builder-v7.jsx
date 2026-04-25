import React, { useState, useCallback, useRef, useEffect } from 'react';

const MASAgentBuilder = () => {
  // Canvas state
  const [nodes, setNodes] = useState([
    { id: 'start-1', type: 'start', x: 100, y: 80, name: 'Start' }
  ]);
  const [connections, setConnections] = useState([]);
  const [selectedNode, setSelectedNode] = useState(null);
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [draggingNode, setDraggingNode] = useState(null);
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 });
  
  // Topology templates on canvas
  const [topologyTemplates, setTopologyTemplates] = useState([]);
  const [draggingTopology, setDraggingTopology] = useState(null);
  
  // Connecting state
  const [connecting, setConnecting] = useState(null);
  const [connectingFrom, setConnectingFrom] = useState(null);
  
  // Internal topology connecting
  const [internalConnecting, setInternalConnecting] = useState(null);
  
  // Role selection popup
  const [rolePopup, setRolePopup] = useState(null);
  
  // Chat input
  const [chatInput, setChatInput] = useState('');
  const [chatMessages, setChatMessages] = useState([]);
  
  // Drag from sidebar
  const [sidebarDrag, setSidebarDrag] = useState(null);
  const [dragPreview, setDragPreview] = useState(null);

  // Resizing state
  const [resizing, setResizing] = useState(null);
  const [resizeStart, setResizeStart] = useState({ x: 0, y: 0, width: 0, height: 0 });

  const canvasRef = useRef(null);

  // Node types
  const nodeTypes = {
    core: [
      { type: 'start', name: 'Start', icon: '▶', color: '#6366f1', desc: 'Entry point' },
      { type: 'agent', name: 'Agent', icon: '▽', color: '#6366f1', desc: 'AI agent node' },
      { type: 'end', name: 'End', icon: '■', color: '#22c55e', desc: 'End workflow' },
      { type: 'note', name: 'Note', icon: '□', color: '#6b7280', desc: 'Add documentation' },
    ],
    logic: [
      { type: 'ifelse', name: 'If / else', icon: '⤷', color: '#f59e0b', desc: 'Conditional branch' },
      { type: 'approval', name: 'User approval', icon: '✋', color: '#f59e0b', desc: 'Human review' },
    ]
  };

  // Topology definitions with edge types and start/end info
  const topologies = [
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
      needsStartAgent: false
    },
    { 
      id: 'sequential', 
      name: 'Sequential', 
      subtitle: 'Pipeline',
      icon: '→',
      masDesc: 'Output feeds next agent\'s input',
      socialDesc: 'Chain network',
      color: '#3b82f6',
      hasRoles: false,
      roles: [],
      edgeType: 'unidirectional',
      autoConnect: false,
      autoEdgeOnRole: false,
      startPoint: 'First agent receives input',
      endPoint: 'Last agent produces output',
      needsStartAgent: false
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
      needsStartAgent: false
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
      needsStartAgent: true
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
      autoConnect: true,
      autoEdgeOnRole: false,
      startPoint: 'Specify start agent before run',
      endPoint: 'Last agent summarizes for output',
      needsStartAgent: true
    },
    { 
      id: 'dag', 
      name: 'DAG', 
      subtitle: 'Directed Acyclic',
      icon: '▷',
      masDesc: 'Directed flow without cycles',
      socialDesc: 'Extended chain',
      color: '#14b8a6',
      hasRoles: false,
      roles: [],
      edgeType: 'unidirectional',
      autoConnect: false,
      autoEdgeOnRole: false,
      noLoops: true,
      startPoint: 'First agent receives input',
      endPoint: 'Last agent produces output',
      needsStartAgent: false
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
      needsStartAgent: true
    },
  ];

  // Placeholder configurations for each topology type
  const getPlaceholderConfig = (topoType, width, height) => {
    const bodyW = width - 20;
    const bodyH = height - 20;
    const centerX = bodyW / 2;
    const centerY = bodyH / 2;
    
    switch (topoType) {
      case 'centralized':
        return {
          nodes: [
            { x: centerX, y: 30, label: 'Hub', isMain: true },
            { x: centerX - 80, y: bodyH - 40, label: 'Spoke' },
            { x: centerX, y: bodyH - 40, label: 'Spoke' },
            { x: centerX + 80, y: bodyH - 40, label: 'Spoke' },
          ],
          edges: [
            { from: 0, to: 1, bidirectional: true },
            { from: 0, to: 2, bidirectional: true },
            { from: 0, to: 3, bidirectional: true },
          ]
        };
      case 'sequential':
        return {
          nodes: [
            { x: 50, y: centerY, label: '1st' },
            { x: centerX, y: centerY, label: '2nd' },
            { x: bodyW - 50, y: centerY, label: '3rd' },
          ],
          edges: [
            { from: 0, to: 1 },
            { from: 1, to: 2 },
          ]
        };
      case 'hierarchical':
        return {
          nodes: [
            { x: centerX, y: 30, label: 'Manager', isMain: true },
            { x: centerX - 70, y: bodyH - 40, label: 'Worker' },
            { x: centerX + 70, y: bodyH - 40, label: 'Worker' },
          ],
          edges: [
            { from: 0, to: 1, bidirectional: true },
            { from: 0, to: 2, bidirectional: true },
          ]
        };
      case 'p2p':
        return {
          nodes: [
            { x: centerX, y: 25, label: 'Peer' },
            { x: centerX - 70, y: bodyH - 30, label: 'Peer' },
            { x: centerX + 70, y: bodyH - 30, label: 'Peer' },
          ],
          edges: [
            { from: 0, to: 1, bidirectional: true },
            { from: 1, to: 2, bidirectional: true },
            { from: 2, to: 0, bidirectional: true },
          ]
        };
      case 'mesh':
        // 4 agents for mesh
        return {
          nodes: [
            { x: centerX - 60, y: 30, label: 'Agent' },
            { x: centerX + 60, y: 30, label: 'Agent' },
            { x: centerX - 60, y: bodyH - 40, label: 'Agent' },
            { x: centerX + 60, y: bodyH - 40, label: 'Agent' },
          ],
          edges: [
            { from: 0, to: 1, bidirectional: true },
            { from: 0, to: 2, bidirectional: true },
            { from: 0, to: 3, bidirectional: true },
            { from: 1, to: 2, bidirectional: true },
            { from: 1, to: 3, bidirectional: true },
            { from: 2, to: 3, bidirectional: true },
          ]
        };
      case 'dag':
        // Proper DAG without loops
        return {
          nodes: [
            { x: 50, y: centerY, label: 'A' },
            { x: centerX - 30, y: 30, label: 'B' },
            { x: centerX - 30, y: bodyH - 40, label: 'C' },
            { x: bodyW - 50, y: centerY, label: 'D' },
          ],
          edges: [
            { from: 0, to: 1 },
            { from: 0, to: 2 },
            { from: 1, to: 3 },
            { from: 2, to: 3 },
          ]
        };
      case 'cyclic':
        return {
          nodes: [
            { x: centerX, y: 25, label: 'A' },
            { x: centerX - 70, y: bodyH - 30, label: 'B' },
            { x: centerX + 70, y: bodyH - 30, label: 'C' },
          ],
          edges: [
            { from: 0, to: 1 },
            { from: 1, to: 2 },
            { from: 2, to: 0 },
          ]
        };
      default:
        return { nodes: [], edges: [] };
    }
  };

  // Add node to canvas
  const addNode = (nodeType, x, y) => {
    const newNode = {
      id: `${nodeType.type}-${Date.now()}`,
      type: nodeType.type,
      x: x || 300 + Math.random() * 100,
      y: y || 150 + nodes.length * 80,
      name: nodeType.type === 'agent' ? `Agent ${nodes.filter(n => n.type === 'agent').length + 1}` : nodeType.name,
      config: {},
      topologyId: null,
      topologyRole: null
    };
    
    setNodes([...nodes, newNode]);
    setSelectedNode(newNode.id);
    setSelectedTemplate(null);
  };

  // Add topology template to canvas
  const addTopologyTemplate = (topoType, x, y) => {
    const topo = topologies.find(t => t.id === topoType);
    
    const newTemplate = {
      id: `topo-${Date.now()}`,
      type: topoType,
      x: x || 400,
      y: y || 200,
      width: 350,
      height: 250,
      name: topo.name,
      color: topo.color,
      maxTurns: 10,
      timeout: 300,
      earlyTermination: true,
      internalEdges: [],
      startAgentId: null
    };
    
    setTopologyTemplates([...topologyTemplates, newTemplate]);
  };

  // Get agents inside a topology
  const getAgentsInTopology = (topoId) => {
    return nodes.filter(n => n.topologyId === topoId);
  };

  // Check if agent is inside topology bounds
  const isInsideTopology = (agentX, agentY, template) => {
    const agentCenterX = agentX + 80;
    const agentCenterY = agentY + 30;
    return (
      agentCenterX > template.x &&
      agentCenterX < template.x + template.width &&
      agentCenterY > template.y + 40 &&
      agentCenterY < template.y + template.height + 40
    );
  };

  // Check for cycles in DAG
  const wouldCreateCycle = (fromId, toId, edges) => {
    const visited = new Set();
    const stack = [toId];
    
    while (stack.length > 0) {
      const current = stack.pop();
      if (current === fromId) return true;
      if (visited.has(current)) continue;
      visited.add(current);
      
      edges.filter(e => e.from === current).forEach(e => stack.push(e.to));
    }
    return false;
  };

  // Add internal edge within topology
  const addInternalEdge = (templateId, fromAgentId, toAgentId, skipBidirectional = false) => {
    const template = topologyTemplates.find(t => t.id === templateId);
    if (!template) return;
    
    const topo = topologies.find(t => t.id === template.type);
    
    // Check for DAG loop prevention
    if (topo.noLoops) {
      if (wouldCreateCycle(fromAgentId, toAgentId, template.internalEdges)) {
        alert('Cannot create edge: would create a cycle in DAG');
        return;
      }
    }
    
    // Check if edge already exists
    const exists = template.internalEdges.find(
      e => e.from === fromAgentId && e.to === toAgentId
    );
    if (exists) return;
    
    const newEdge = {
      id: `ie-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      from: fromAgentId,
      to: toAgentId,
      type: topo.edgeType
    };
    
    setTopologyTemplates(prev => prev.map(t => 
      t.id === templateId ? {
        ...t,
        internalEdges: [...t.internalEdges, newEdge]
      } : t
    ));
    
    // For bidirectional, also add reverse edge
    if (topo.edgeType === 'bidirectional' && !skipBidirectional) {
      const reverseExists = template.internalEdges.find(
        e => e.from === toAgentId && e.to === fromAgentId
      );
      if (!reverseExists) {
        setTimeout(() => {
          setTopologyTemplates(prev => prev.map(t => {
            if (t.id !== templateId) return t;
            const alreadyExists = t.internalEdges.find(e => e.from === toAgentId && e.to === fromAgentId);
            if (alreadyExists) return t;
            return {
              ...t,
              internalEdges: [...t.internalEdges, {
                id: `ie-${Date.now()}-r-${Math.random().toString(36).substr(2, 9)}`,
                from: toAgentId,
                to: fromAgentId,
                type: topo.edgeType
              }]
            };
          }));
        }, 10);
      }
    }
  };

  // Auto-connect all agents in mesh topology
  const autoConnectMesh = (templateId) => {
    const agents = getAgentsInTopology(templateId);
    const edges = [];
    
    for (let i = 0; i < agents.length; i++) {
      for (let j = 0; j < agents.length; j++) {
        if (i !== j) {
          edges.push({
            id: `ie-mesh-${i}-${j}-${Math.random().toString(36).substr(2, 9)}`,
            from: agents[i].id,
            to: agents[j].id,
            type: 'bidirectional'
          });
        }
      }
    }
    
    setTopologyTemplates(prev => prev.map(t => 
      t.id === templateId ? { ...t, internalEdges: edges } : t
    ));
  };

  // Auto-connect edges for centralized/hierarchical when agent added with role
  const autoConnectRoleBasedEdges = (templateId, newAgentId, role) => {
    const template = topologyTemplates.find(t => t.id === templateId);
    if (!template) return;
    
    const topo = topologies.find(t => t.id === template.type);
    const agentsInTopo = nodes.filter(n => n.topologyId === templateId && n.id !== newAgentId);
    
    if (topo.id === 'centralized') {
      if (role === 'Hub') {
        // Connect hub to all existing spokes
        agentsInTopo.filter(a => a.topologyRole === 'Spoke').forEach(spoke => {
          addInternalEdge(templateId, newAgentId, spoke.id);
        });
      } else if (role === 'Spoke') {
        // Connect spoke to hub
        const hub = agentsInTopo.find(a => a.topologyRole === 'Hub');
        if (hub) {
          addInternalEdge(templateId, hub.id, newAgentId);
        }
      }
    } else if (topo.id === 'hierarchical') {
      if (role === 'Manager') {
        // Connect manager to all existing workers
        agentsInTopo.filter(a => a.topologyRole === 'Worker').forEach(worker => {
          addInternalEdge(templateId, newAgentId, worker.id);
        });
      } else if (role === 'Worker') {
        // Connect worker to manager
        const manager = agentsInTopo.find(a => a.topologyRole === 'Manager');
        if (manager) {
          addInternalEdge(templateId, manager.id, newAgentId);
        }
      }
    }
  };

  // Handle adding agent to topology
  const handleAgentToTopology = (agentId, templateId, role = null) => {
    const template = topologyTemplates.find(t => t.id === templateId);
    const topo = topologies.find(t => t.id === template.type);
    
    setNodes(prev => prev.map(n => 
      n.id === agentId ? { 
        ...n, 
        topologyId: templateId, 
        topologyRole: role,
        topologyColor: template.color
      } : n
    ));
    
    // Auto-connect for mesh topology
    if (topo.autoConnect) {
      setTimeout(() => autoConnectMesh(templateId), 50);
    }
    
    // Auto-connect for role-based topologies (centralized, hierarchical)
    if (topo.autoEdgeOnRole && role) {
      setTimeout(() => autoConnectRoleBasedEdges(templateId, agentId, role), 100);
    }
    
    setRolePopup(null);
  };

  // Remove agent from topology
  const removeAgentFromTopology = (agentId) => {
    const agent = nodes.find(n => n.id === agentId);
    if (!agent || !agent.topologyId) return;
    
    const templateId = agent.topologyId;
    
    // Remove internal edges involving this agent
    setTopologyTemplates(prev => prev.map(t => 
      t.id === templateId ? {
        ...t,
        internalEdges: t.internalEdges.filter(e => e.from !== agentId && e.to !== agentId),
        startAgentId: t.startAgentId === agentId ? null : t.startAgentId
      } : t
    ));
    
    setNodes(prev => prev.map(n => 
      n.id === agentId ? { 
        ...n, 
        topologyId: null, 
        topologyRole: null,
        topologyColor: null
      } : n
    ));
  };

  // Drag handlers
  const handleMouseDown = (e, node) => {
    if (e.button !== 0) return;
    e.stopPropagation();
    const rect = canvasRef.current.getBoundingClientRect();
    setDraggingNode(node.id);
    setDragOffset({
      x: e.clientX - rect.left - node.x,
      y: e.clientY - rect.top - node.y
    });
    setSelectedNode(node.id);
    setSelectedTemplate(null);
  };

  const handleTemplateMouseDown = (e, template) => {
    if (e.target.closest('.template-delete') || e.target.closest('.resize-handle')) return;
    e.stopPropagation();
    const rect = canvasRef.current.getBoundingClientRect();
    setDraggingTopology(template.id);
    setDragOffset({ x: e.clientX - rect.left - template.x, y: e.clientY - rect.top - template.y });
    setSelectedTemplate(template.id);
    setSelectedNode(null);
  };

  // Resize handlers
  const handleResizeStart = (e, containerId) => {
    e.stopPropagation();
    e.preventDefault();
    const container = topologyTemplates.find(t => t.id === containerId);
    
    if (container) {
      setResizing({ id: containerId });
      setResizeStart({
        x: e.clientX,
        y: e.clientY,
        width: container.width,
        height: container.height
      });
    }
  };

  const handleMouseMove = (e) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    if (sidebarDrag) {
      setDragPreview({ x: e.clientX, y: e.clientY });
      return;
    }

    // Handle resizing
    if (resizing) {
      const deltaX = e.clientX - resizeStart.x;
      const deltaY = e.clientY - resizeStart.y;
      const newWidth = Math.max(250, resizeStart.width + deltaX);
      const newHeight = Math.max(180, resizeStart.height + deltaY);
      
      setTopologyTemplates(topologyTemplates.map(t => 
        t.id === resizing.id ? { ...t, width: newWidth, height: newHeight } : t
      ));
      return;
    }

    if (draggingNode) {
      const node = nodes.find(n => n.id === draggingNode);
      const newX = Math.max(0, x - dragOffset.x);
      const newY = Math.max(0, y - dragOffset.y);
      
      setNodes(nodes.map(n => 
        n.id === draggingNode ? { ...n, x: newX, y: newY } : n
      ));
    }

    if (draggingTopology) {
      const deltaX = x - dragOffset.x;
      const deltaY = y - dragOffset.y;
      const template = topologyTemplates.find(t => t.id === draggingTopology);
      
      if (template) {
        const dx = deltaX - template.x;
        const dy = deltaY - template.y;
        
        // Move all agents inside topology with it
        setNodes(nodes.map(n => 
          n.topologyId === draggingTopology ? { ...n, x: n.x + dx, y: n.y + dy } : n
        ));
        
        setTopologyTemplates(topologyTemplates.map(t =>
          t.id === draggingTopology ? { ...t, x: deltaX, y: deltaY } : t
        ));
      }
    }
  };

  const handleMouseUp = (e) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    
    if (sidebarDrag && rect) {
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      
      if (x > 0 && y > 0) {
        if (sidebarDrag.isTopology) {
          addTopologyTemplate(sidebarDrag.type, x - 100, y - 50);
        } else {
          addNode(sidebarDrag, x - 80, y - 30);
        }
      }
    }
    
    // Check if dropping agent into topology
    if (draggingNode) {
      const node = nodes.find(n => n.id === draggingNode);
      if (node && node.type === 'agent' && !node.topologyId) {
        for (const template of topologyTemplates) {
          if (isInsideTopology(node.x, node.y, template)) {
            const topo = topologies.find(t => t.id === template.type);
            
            if (topo.hasRoles) {
              // Show role selection popup
              setRolePopup({
                agentId: node.id,
                templateId: template.id,
                roles: topo.roles,
                x: e.clientX,
                y: e.clientY
              });
            } else {
              // Directly add to topology
              handleAgentToTopology(node.id, template.id);
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
    setSidebarDrag(null);
    setDragPreview(null);
    setResizing(null);
  };

  const handleSidebarDragStart = (item, isTopology = false) => {
    setSidebarDrag({ ...item, isTopology });
  };

  // Internal connection handlers
  const startInternalConnection = (agentId, templateId, e) => {
    e.stopPropagation();
    setInternalConnecting({ agentId, templateId });
  };

  const endInternalConnection = (agentId, e) => {
    e.stopPropagation();
    if (internalConnecting && internalConnecting.agentId !== agentId) {
      const agent = nodes.find(n => n.id === agentId);
      if (agent && agent.topologyId === internalConnecting.templateId) {
        addInternalEdge(internalConnecting.templateId, internalConnecting.agentId, agentId);
      }
    }
    setInternalConnecting(null);
  };

  // Delete handlers
  const deleteNode = (nodeId) => {
    if (nodeId.startsWith('start-')) return;
    
    // Remove from topology edges
    const node = nodes.find(n => n.id === nodeId);
    if (node?.topologyId) {
      setTopologyTemplates(topologyTemplates.map(t => 
        t.id === node.topologyId ? {
          ...t,
          internalEdges: t.internalEdges.filter(e => e.from !== nodeId && e.to !== nodeId),
          startAgentId: t.startAgentId === nodeId ? null : t.startAgentId
        } : t
      ));
    }
    
    setNodes(nodes.filter(n => n.id !== nodeId));
    setConnections(connections.filter(c => c.from !== nodeId && c.to !== nodeId));
    setSelectedNode(null);
  };

  const deleteTopology = (topoId) => {
    // Remove all agents from this topology
    setNodes(nodes.map(n => 
      n.topologyId === topoId ? { ...n, topologyId: null, topologyRole: null, topologyColor: null } : n
    ));
    setTopologyTemplates(topologyTemplates.filter(t => t.id !== topoId));
    setConnections(connections.filter(c => c.from !== topoId && c.to !== topoId));
    setSelectedTemplate(null);
  };

  // Delete internal edge
  const deleteInternalEdge = (templateId, edgeId) => {
    setTopologyTemplates(topologyTemplates.map(t => 
      t.id === templateId ? {
        ...t,
        internalEdges: t.internalEdges.filter(e => e.id !== edgeId)
      } : t
    ));
  };

  // Connection handlers
  const startConnection = (entityId, type, e) => {
    e.stopPropagation();
    setConnecting(entityId);
    setConnectingFrom(type);
  };

  const endConnection = (entityId, e) => {
    e.stopPropagation();
    if (connecting && connecting !== entityId) {
      const exists = connections.find(c => c.from === connecting && c.to === entityId);
      if (!exists) {
        setConnections([...connections, { 
          from: connecting, 
          to: entityId, 
          id: `conn-${Date.now()}`,
          fromType: connectingFrom
        }]);
      }
    }
    setConnecting(null);
    setConnectingFrom(null);
  };

  // Chat processing
  const processChat = () => {
    if (!chatInput.trim()) return;
    
    const input = chatInput.toLowerCase();
    setChatMessages([...chatMessages, { role: 'user', text: chatInput }]);
    
    let response = '';
    
    if (input.includes('add agent') || input.includes('new agent')) {
      const count = parseInt(input.match(/(\d+)/)?.[1]) || 1;
      for (let i = 0; i < count; i++) {
        const newNode = {
          id: `agent-${Date.now()}-${i}`,
          type: 'agent',
          x: 300 + Math.random() * 100,
          y: 150 + (nodes.length + i) * 80,
          name: `Agent ${nodes.filter(n => n.type === 'agent').length + i + 1}`,
          config: {}
        };
        setNodes(prev => [...prev, newNode]);
      }
      response = `Added ${count} agent(s).`;
    } 
    else if (input.includes('topology')) {
      const topoMatch = topologies.find(t => input.includes(t.name.toLowerCase()) || input.includes(t.id));
      if (topoMatch) {
        addTopologyTemplate(topoMatch.id, 400, 200);
        response = `Added ${topoMatch.name} topology template.`;
      } else {
        response = 'Available: Centralized, Sequential, Hierarchical, P2P, Mesh, DAG, Cyclic';
      }
    }
    else if (input.includes('clear')) {
      setNodes([{ id: 'start-1', type: 'start', x: 100, y: 80, name: 'Start' }]);
      setConnections([]);
      setTopologyTemplates([]);
      response = 'Canvas cleared.';
    }
    else {
      response = `Try "add agent", "add hierarchical topology", or "clear"`;
    }
    
    setChatMessages(prev => [...prev, { role: 'assistant', text: response }]);
    setChatInput('');
  };

  // Get node info
  const getNodeColor = (type) => {
    const allTypes = [...nodeTypes.core, ...nodeTypes.logic];
    return allTypes.find(t => t.type === type)?.color || '#6b7280';
  };

  const getNodeIcon = (type) => {
    const allTypes = [...nodeTypes.core, ...nodeTypes.logic];
    return allTypes.find(t => t.type === type)?.icon || '?';
  };

  // Get entity position for connections
  const getEntityPosition = (entityId) => {
    const node = nodes.find(n => n.id === entityId);
    if (node) return { x: node.x + 80, y: node.y + 25, height: 50 };
    
    const template = topologyTemplates.find(t => t.id === entityId);
    if (template) return { x: template.x + template.width / 2, y: template.y, height: template.height + 40 };
    
    return null;
  };

  // Render connection lines
  const renderConnections = () => {
    return connections.map(conn => {
      const fromPos = getEntityPosition(conn.from);
      const toPos = getEntityPosition(conn.to);
      if (!fromPos || !toPos) return null;
      
      const x1 = fromPos.x;
      const y1 = fromPos.y + fromPos.height;
      const x2 = toPos.x;
      const y2 = toPos.y;
      
      return (
        <g key={conn.id}>
          <defs>
            <marker id={`arrow-${conn.id}`} markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
              <polygon points="0 0, 10 3.5, 0 7" fill="#4b5563" />
            </marker>
          </defs>
          <path
            d={`M ${x1} ${y1} C ${x1} ${y1 + 40}, ${x2} ${y2 - 40}, ${x2} ${y2}`}
            stroke="#4b5563"
            strokeWidth="2"
            fill="none"
            markerEnd={`url(#arrow-${conn.id})`}
          />
        </g>
      );
    });
  };

  // Render placeholder visualization
  const renderPlaceholder = (template) => {
    const config = getPlaceholderConfig(template.type, template.width, template.height);
    const topo = topologies.find(t => t.id === template.type);
    
    return (
      <svg className="placeholder-layer" style={{ width: '100%', height: '100%' }}>
        {/* Edges */}
        {config.edges.map((edge, i) => {
          const from = config.nodes[edge.from];
          const to = config.nodes[edge.to];
          
          // Calculate direction for arrow
          const dx = to.x - from.x;
          const dy = to.y - from.y;
          const len = Math.sqrt(dx * dx + dy * dy);
          const nx = dx / len;
          const ny = dy / len;
          
          // Shorten line for arrow
          const arrowSize = 8;
          const endX = to.x - nx * arrowSize;
          const endY = to.y - ny * arrowSize;
          
          return (
            <g key={`edge-${i}`}>
              <line
                x1={from.x} y1={from.y}
                x2={endX} y2={endY}
                stroke={template.color}
                strokeWidth="2"
                strokeDasharray="4"
                opacity="0.3"
              />
              {/* Arrow head using > shape */}
              <text
                x={to.x}
                y={to.y}
                fontSize="12"
                fill={template.color}
                opacity="0.4"
                textAnchor="middle"
                dominantBaseline="middle"
                transform={`rotate(${Math.atan2(dy, dx) * 180 / Math.PI}, ${to.x}, ${to.y})`}
              >›</text>
              
              {edge.bidirectional && (
                <>
                  <line
                    x1={to.x + ny * 6} y1={to.y - nx * 6}
                    x2={from.x + ny * 6} y2={from.y - nx * 6}
                    stroke={template.color}
                    strokeWidth="2"
                    strokeDasharray="4"
                    opacity="0.2"
                  />
                  <text
                    x={from.x + ny * 6}
                    y={from.y - nx * 6}
                    fontSize="12"
                    fill={template.color}
                    opacity="0.3"
                    textAnchor="middle"
                    dominantBaseline="middle"
                    transform={`rotate(${Math.atan2(-dy, -dx) * 180 / Math.PI}, ${from.x + ny * 6}, ${from.y - nx * 6})`}
                  >›</text>
                </>
              )}
            </g>
          );
        })}
        
        {/* Nodes */}
        {config.nodes.map((node, i) => (
          <g key={`node-${i}`}>
            <rect
              x={node.x - 35}
              y={node.y - 15}
              width="70"
              height="30"
              rx="8"
              fill="transparent"
              stroke={template.color}
              strokeWidth="2"
              strokeDasharray="4"
              opacity="0.4"
            />
            <text
              x={node.x}
              y={node.y + 5}
              fontSize="11"
              fill={template.color}
              textAnchor="middle"
              opacity="0.5"
            >
              {node.label}
            </text>
          </g>
        ))}
      </svg>
    );
  };

  // Render internal edges within topology
  const renderInternalEdges = (template) => {
    const topo = topologies.find(t => t.id === template.type);
    if (!topo) return null;
    
    return template.internalEdges.map(edge => {
      const fromAgent = nodes.find(n => n.id === edge.from);
      const toAgent = nodes.find(n => n.id === edge.to);
      if (!fromAgent || !toAgent) return null;
      
      // Calculate positions relative to topology
      const x1 = fromAgent.x - template.x + 80;
      const y1 = fromAgent.y - template.y - 40 + 60;
      const x2 = toAgent.x - template.x + 80;
      const y2 = toAgent.y - template.y - 40 + 10;
      
      // Calculate midpoint for delete button
      const midX = (x1 + x2) / 2;
      const midY = (y1 + y2) / 2;
      
      // Calculate direction for arrow
      const dx = x2 - x1;
      const dy = y2 - y1;
      const len = Math.sqrt(dx * dx + dy * dy);
      const nx = dx / len;
      const ny = dy / len;
      
      // End point shortened for arrow
      const arrowOffset = 10;
      const endX = x2 - nx * arrowOffset;
      const endY = y2 - ny * arrowOffset;
      
      // Control points for curve
      const ctrl1X = x1;
      const ctrl1Y = y1 + 30;
      const ctrl2X = endX;
      const ctrl2Y = endY - 30;
      
      return (
        <g key={edge.id} className="internal-edge-group">
          <path
            d={`M ${x1} ${y1} C ${ctrl1X} ${ctrl1Y}, ${ctrl2X} ${ctrl2Y}, ${endX} ${endY}`}
            stroke={template.color}
            strokeWidth="2"
            fill="none"
            opacity="0.7"
            className="internal-edge-line"
          />
          {/* Arrow using > shape */}
          <text
            x={x2}
            y={y2}
            fontSize="14"
            fill={template.color}
            opacity="0.9"
            textAnchor="middle"
            dominantBaseline="middle"
            style={{ fontWeight: 'bold' }}
            transform={`rotate(${Math.atan2(dy, dx) * 180 / Math.PI}, ${x2}, ${y2})`}
          >›</text>
          
          <circle
            cx={midX}
            cy={midY}
            r="8"
            fill="#1f1f1f"
            stroke={template.color}
            strokeWidth="1"
            className="edge-delete-btn"
            style={{ cursor: 'pointer', opacity: 0 }}
            onClick={(e) => { e.stopPropagation(); deleteInternalEdge(template.id, edge.id); }}
          />
          <text
            x={midX}
            y={midY + 4}
            fontSize="10"
            fill={template.color}
            textAnchor="middle"
            className="edge-delete-text"
            style={{ cursor: 'pointer', opacity: 0, pointerEvents: 'none' }}
          >×</text>
        </g>
      );
    });
  };

  // Right panel content
  const renderRightPanel = () => {
    if (selectedNode) {
      const node = nodes.find(n => n.id === selectedNode);
      if (!node) return null;
      
      return (
        <div className="right-panel">
          <div className="panel-header">
            <h3>Configure Agent</h3>
            <button className="close-btn" onClick={() => setSelectedNode(null)}>×</button>
          </div>
          <div className="panel-content">
            <div className="config-row">
              <label>Name</label>
              <input 
                type="text" 
                value={node.name || ''}
                onChange={(e) => setNodes(nodes.map(n => 
                  n.id === selectedNode ? { ...n, name: e.target.value } : n
                ))}
              />
            </div>
            {node.topologyId && (
              <div className="config-row">
                <label>Topology</label>
                <div className="topology-info">
                  <span className="topo-badge" style={{ backgroundColor: node.topologyColor }}>
                    {topologyTemplates.find(t => t.id === node.topologyId)?.name}
                  </span>
                  {node.topologyRole && (
                    <span className="role-badge">{node.topologyRole}</span>
                  )}
                </div>
              </div>
            )}
            <div className="config-row">
              <label>Instructions</label>
              <textarea placeholder="What does this agent do..." />
            </div>
            <div className="config-row">
              <label>Model</label>
              <select>
                <option>gpt-4o</option>
                <option>gpt-4o-mini</option>
              </select>
            </div>
          </div>
        </div>
      );
    }
    
    if (selectedTemplate) {
      const template = topologyTemplates.find(t => t.id === selectedTemplate);
      if (!template) return null;
      
      const topo = topologies.find(t => t.id === template.type);
      const agentsInside = getAgentsInTopology(template.id);
      
      return (
        <div className="right-panel">
          <div className="panel-header">
            <h3>Topology Settings</h3>
            <button className="close-btn" onClick={() => setSelectedTemplate(null)}>×</button>
          </div>
          <div className="panel-content">
            <div className="config-info">
              <span className="config-badge" style={{ backgroundColor: template.color }}>{template.name}</span>
              <span className="edge-type-badge">{topo.edgeType === 'bidirectional' ? '↔ Bidirectional' : '→ Unidirectional'}</span>
            </div>
            
            <div className="flow-info">
              <div className="flow-item">
                <span className="flow-label">▶ Start</span>
                <span className="flow-desc">{topo.startPoint}</span>
              </div>
              <div className="flow-item">
                <span className="flow-label">■ End</span>
                <span className="flow-desc">{topo.endPoint}</span>
              </div>
            </div>
            
            {topo.needsStartAgent && (
              <div className="config-row">
                <label>Start Agent</label>
                <select 
                  value={template.startAgentId || ''}
                  onChange={(e) => setTopologyTemplates(topologyTemplates.map(t => 
                    t.id === selectedTemplate ? { ...t, startAgentId: e.target.value || null } : t
                  ))}
                >
                  <option value="">Select start agent...</option>
                  {agentsInside.map(agent => (
                    <option key={agent.id} value={agent.id}>{agent.name}</option>
                  ))}
                </select>
                {!template.startAgentId && agentsInside.length > 0 && (
                  <span className="warning-hint">⚠ Start agent required before run</span>
                )}
              </div>
            )}
            
            <div className="config-row">
              <label>Agents ({agentsInside.length})</label>
              <div className="agents-list">
                {agentsInside.map(agent => (
                  <div key={agent.id} className={`agent-item ${template.startAgentId === agent.id ? 'is-start' : ''}`}>
                    <span>{agent.name}</span>
                    {agent.topologyRole && <span className="role-tag">{agent.topologyRole}</span>}
                    {template.startAgentId === agent.id && <span className="start-tag">START</span>}
                  </div>
                ))}
                {agentsInside.length === 0 && <span className="empty-hint">Drag agents into topology</span>}
              </div>
            </div>
            
            <div className="config-row">
              <label>Internal Edges ({template.internalEdges.length})</label>
              {topo.autoConnect && <span className="auto-hint">Auto-connected (Mesh)</span>}
              {topo.autoEdgeOnRole && <span className="auto-hint">Auto-connected based on role</span>}
            </div>
            
            <div className="config-row">
              <label>Max Turns</label>
              <input 
                type="number" 
                value={template.maxTurns}
                onChange={(e) => setTopologyTemplates(topologyTemplates.map(t => 
                  t.id === selectedTemplate ? { ...t, maxTurns: parseInt(e.target.value) || 10 } : t
                ))}
                min={1} max={100}
              />
            </div>
            <div className="config-row">
              <label>Timeout (seconds)</label>
              <input 
                type="number" 
                value={template.timeout}
                onChange={(e) => setTopologyTemplates(topologyTemplates.map(t => 
                  t.id === selectedTemplate ? { ...t, timeout: parseInt(e.target.value) || 300 } : t
                ))}
                min={30}
              />
            </div>
            <div className="config-row checkbox-row">
              <label>
                <input 
                  type="checkbox" 
                  checked={template.earlyTermination}
                  onChange={(e) => setTopologyTemplates(topologyTemplates.map(t => 
                    t.id === selectedTemplate ? { ...t, earlyTermination: e.target.checked } : t
                  ))}
                />
                <span>Early termination on completion</span>
              </label>
            </div>
            <div className="config-row">
              <label>Size (W × H)</label>
              <div className="size-inputs">
                <input 
                  type="number" 
                  value={template.width}
                  onChange={(e) => setTopologyTemplates(topologyTemplates.map(t => 
                    t.id === selectedTemplate ? { ...t, width: Math.max(250, parseInt(e.target.value) || 250) } : t
                  ))}
                  min={250}
                />
                <span>×</span>
                <input 
                  type="number" 
                  value={template.height}
                  onChange={(e) => setTopologyTemplates(topologyTemplates.map(t => 
                    t.id === selectedTemplate ? { ...t, height: Math.max(180, parseInt(e.target.value) || 180) } : t
                  ))}
                  min={180}
                />
              </div>
            </div>
          </div>
        </div>
      );
    }
    
    return null;
  };

  return (
    <div className="agent-builder">
      {/* Left Sidebar */}
      <div className="sidebar">
        <div className="sidebar-header">
          <button className="back-btn">‹</button>
          <h1>New agent</h1>
          <span className="draft-badge">Draft</span>
        </div>
        
        <div className="node-list">
          <div className="node-category">
            <span className="category-label">Core</span>
            {nodeTypes.core.map(node => (
              <div 
                key={node.type}
                className="node-item"
                draggable
                onDragStart={() => handleSidebarDragStart(node)}
                onClick={() => addNode(node)}
              >
                <div className="node-icon" style={{ backgroundColor: node.color }}>{node.icon}</div>
                <span className="node-name">{node.name}</span>
              </div>
            ))}
          </div>
          
          <div className="node-category">
            <span className="category-label">Logic</span>
            {nodeTypes.logic.map(node => (
              <div 
                key={node.type}
                className="node-item"
                draggable
                onDragStart={() => handleSidebarDragStart(node)}
                onClick={() => addNode(node)}
              >
                <div className="node-icon" style={{ backgroundColor: node.color }}>{node.icon}</div>
                <span className="node-name">{node.name}</span>
              </div>
            ))}
          </div>
          
          <div className="node-category topology-section">
            <span className="category-label">Topology Templates</span>
            <div className="topology-list">
              {topologies.map(topo => (
                <div 
                  key={topo.id}
                  className="topology-item"
                  draggable
                  onDragStart={() => handleSidebarDragStart({ type: topo.id, ...topo }, true)}
                  onClick={() => addTopologyTemplate(topo.id)}
                >
                  <div className="topo-icon-wrap" style={{ backgroundColor: topo.color }}>{topo.icon}</div>
                  <div className="topo-info">
                    <span className="topo-name">{topo.name}</span>
                    <span className="topo-subtitle">{topo.subtitle}</span>
                  </div>
                  <div className="topo-tooltip">
                    <strong>MAS:</strong> {topo.masDesc}<br/>
                    <strong>Social:</strong> {topo.socialDesc}<br/>
                    <strong>Edge:</strong> {topo.edgeType === 'bidirectional' ? '↔ Bidirectional' : '→ Unidirectional'}
                    {topo.autoConnect && <><br/><em>Auto-connects all agents</em></>}
                    {topo.autoEdgeOnRole && <><br/><em>Auto-connects by role</em></>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Main Canvas Area */}
      <div className="main-area">
        <div className="top-bar">
          <div className="tab-area">
            <span className="tab active">Workflow</span>
          </div>
          <div className="top-actions">
            <button className="preview-btn">▶ Preview</button>
            <button className="publish-btn">Publish</button>
          </div>
        </div>

        <div 
          className="canvas"
          ref={canvasRef}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
          onClick={() => { setSelectedNode(null); setSelectedTemplate(null); setInternalConnecting(null); }}
        >
          <svg className="connections-layer">
            {renderConnections()}
          </svg>

          {/* Topology Templates */}
          {topologyTemplates.map(template => {
            const topo = topologies.find(t => t.id === template.type);
            const hasAgents = getAgentsInTopology(template.id).length > 0;
            
            return (
              <div
                key={template.id}
                className={`topology-template ${selectedTemplate === template.id ? 'selected' : ''}`}
                style={{ 
                  left: template.x, 
                  top: template.y, 
                  borderColor: template.color, 
                  width: template.width, 
                  height: template.height + 40 
                }}
                onMouseDown={(e) => handleTemplateMouseDown(e, template)}
                onClick={(e) => { e.stopPropagation(); setSelectedTemplate(template.id); setSelectedNode(null); }}
              >
                <div className="template-header" style={{ backgroundColor: template.color }}>
                  <span className="template-name">{template.name} Topology</span>
                  <span className="template-edge-type">{topo.edgeType === 'bidirectional' ? '↔' : '→'}</span>
                  <button className="template-delete" onClick={(e) => { e.stopPropagation(); deleteTopology(template.id); }}>×</button>
                </div>
                <div className="template-body" style={{ height: template.height }}>
                  {/* Placeholder when no agents */}
                  {!hasAgents && renderPlaceholder(template)}
                  
                  {/* Internal edges */}
                  <svg className="internal-edges-layer" style={{ width: '100%', height: '100%' }}>
                    {renderInternalEdges(template)}
                  </svg>
                </div>
                {/* Connection dots */}
                <div className="connect-dot top" onMouseUp={(e) => endConnection(template.id, e)} />
                <div className="connect-dot bottom" onMouseDown={(e) => startConnection(template.id, 'template', e)} />
                {/* Resize handle */}
                <div 
                  className="resize-handle"
                  onMouseDown={(e) => handleResizeStart(e, template.id)}
                />
              </div>
            );
          })}
          
          {/* Regular Nodes */}
          {nodes.map(node => (
            <div
              key={node.id}
              className={`canvas-node ${node.type} ${selectedNode === node.id ? 'selected' : ''} ${node.topologyId ? 'in-topology' : ''}`}
              style={{ 
                left: node.x, 
                top: node.y,
                borderColor: node.topologyColor || getNodeColor(node.type),
                boxShadow: node.topologyColor ? `0 0 0 3px ${node.topologyColor}40` : undefined
              }}
              onMouseDown={(e) => handleMouseDown(e, node)}
              onClick={(e) => { e.stopPropagation(); setSelectedNode(node.id); setSelectedTemplate(null); }}
            >
              <div className="node-header" style={{ borderColor: node.topologyColor || getNodeColor(node.type) }}>
                <div className="node-icon-small" style={{ backgroundColor: getNodeColor(node.type) }}>{getNodeIcon(node.type)}</div>
                <span className="node-title">{node.name}</span>
                {node.topologyRole && <span className="node-role-badge">{node.topologyRole}</span>}
                {node.type !== 'start' && (
                  <button className="node-delete" onClick={(e) => { e.stopPropagation(); deleteNode(node.id); }}>×</button>
                )}
              </div>
              
              {node.type === 'agent' && !node.topologyId && (
                <div className="node-content">
                  <span className="node-hint">Drag into topology</span>
                </div>
              )}
              
              {/* Connection dots for agents inside topology */}
              {node.type === 'agent' && node.topologyId && (
                <>
                  <div 
                    className="connect-dot top internal-top"
                    onMouseUp={(e) => endInternalConnection(node.id, e)}
                    title="Connect from another agent"
                  />
                  <div 
                    className="connect-dot bottom internal-bottom"
                    onMouseDown={(e) => startInternalConnection(node.id, node.topologyId, e)}
                    title="Connect to another agent"
                  />
                </>
              )}
              
              {/* Connection dots for nodes outside topology */}
              {node.type !== 'end' && !node.topologyId && (
                <div className="connect-dot bottom" onMouseDown={(e) => startConnection(node.id, 'node', e)} />
              )}
              {node.type !== 'start' && !node.topologyId && (
                <div className="connect-dot top" onMouseUp={(e) => endConnection(node.id, e)} />
              )}
            </div>
          ))}
        </div>

        <div className="chat-area">
          {chatMessages.length > 0 && (
            <div className="chat-messages">
              {chatMessages.slice(-3).map((msg, i) => (
                <div key={i} className={`chat-msg ${msg.role}`}>{msg.text}</div>
              ))}
            </div>
          )}
          <div className="chat-input-row">
            <input
              type="text"
              className="chat-input"
              placeholder="Describe changes... (e.g., 'add 3 agents', 'add hierarchical topology')"
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && processChat()}
            />
            <button className="chat-send" onClick={processChat}>↑</button>
          </div>
        </div>
      </div>

      {/* Right Panel */}
      {renderRightPanel()}

      {/* Role Selection Popup */}
      {rolePopup && (
        <div className="role-popup-overlay" onClick={() => setRolePopup(null)}>
          <div 
            className="role-popup" 
            style={{ left: rolePopup.x, top: rolePopup.y }}
            onClick={e => e.stopPropagation()}
          >
            <div className="role-popup-header">Select Role</div>
            <div className="role-popup-options">
              {rolePopup.roles.map(role => (
                <button 
                  key={role}
                  className="role-option"
                  onClick={() => handleAgentToTopology(rolePopup.agentId, rolePopup.templateId, role)}
                >
                  {role}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {dragPreview && sidebarDrag && (
        <div className="drag-preview" style={{ left: dragPreview.x + 10, top: dragPreview.y + 10 }}>
          {sidebarDrag.isTopology ? sidebarDrag.name : sidebarDrag.name}
        </div>
      )}

      <style>{`
        * { box-sizing: border-box; margin: 0; padding: 0; }
        .agent-builder { display: flex; height: 100vh; background: #0a0a0a; color: #fff; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
        
        .sidebar { width: 240px; background: #141414; border-right: 1px solid #262626; display: flex; flex-direction: column; }
        .sidebar-header { display: flex; align-items: center; gap: 12px; padding: 16px; border-bottom: 1px solid #262626; }
        .back-btn { background: none; border: none; color: #a3a3a3; font-size: 20px; cursor: pointer; }
        .sidebar-header h1 { font-size: 18px; flex: 1; }
        .draft-badge { font-size: 11px; background: #262626; padding: 3px 8px; border-radius: 10px; color: #a3a3a3; }
        
        .node-list { flex: 1; padding: 12px; overflow-y: auto; }
        .node-category { margin-bottom: 20px; }
        .category-label { font-size: 11px; color: #666; text-transform: uppercase; letter-spacing: 0.5px; display: block; margin-bottom: 8px; }
        .node-item { display: flex; align-items: center; gap: 10px; padding: 8px 10px; border-radius: 8px; cursor: pointer; margin-bottom: 4px; transition: background 0.15s; }
        .node-item:hover { background: #262626; }
        .node-icon { width: 28px; height: 28px; border-radius: 6px; display: flex; align-items: center; justify-content: center; font-size: 12px; color: #fff; flex-shrink: 0; }
        .node-name { font-size: 14px; }

        .topology-section { margin-top: 16px; padding-top: 16px; border-top: 1px solid #262626; }
        .topology-list { margin-top: 8px; }
        .topology-item { display: flex; align-items: center; gap: 10px; padding: 8px 10px; border-radius: 8px; cursor: pointer; margin-bottom: 4px; position: relative; }
        .topology-item:hover { background: #262626; }
        .topology-item:hover .topo-tooltip { opacity: 1; visibility: visible; }
        .topo-icon-wrap { width: 28px; height: 28px; border-radius: 6px; display: flex; align-items: center; justify-content: center; font-size: 12px; color: #fff; }
        .topo-info { flex: 1; display: flex; flex-direction: column; }
        .topo-name { font-size: 13px; }
        .topo-subtitle { font-size: 10px; color: #666; }
        .topo-tooltip { position: absolute; left: 100%; top: 0; margin-left: 8px; background: #262626; border: 1px solid #333; border-radius: 8px; padding: 10px 12px; font-size: 11px; line-height: 1.5; width: 220px; opacity: 0; visibility: hidden; transition: all 0.2s; z-index: 100; }

        .main-area { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
        .top-bar { display: flex; justify-content: space-between; align-items: center; padding: 12px 20px; background: #171717; border-bottom: 1px solid #262626; flex-shrink: 0; }
        .tab-area { display: flex; gap: 8px; }
        .tab { padding: 8px 16px; border-radius: 8px; font-size: 14px; color: #a3a3a3; cursor: pointer; }
        .tab.active { background: #262626; color: #fff; }
        .top-actions { display: flex; gap: 10px; }
        .preview-btn, .publish-btn { padding: 8px 16px; border-radius: 8px; font-size: 14px; cursor: pointer; border: none; font-family: inherit; }
        .preview-btn { background: #262626; color: #fff; }
        .publish-btn { background: #22c55e; color: #000; font-weight: 500; }

        .canvas { flex: 1; position: relative; overflow: auto; background: radial-gradient(circle at 1px 1px, #262626 1px, transparent 0); background-size: 24px 24px; }
        .connections-layer { position: absolute; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; }

        .canvas-node { position: absolute; width: 160px; background: #1f1f1f; border: 2px solid #333; border-radius: 12px; cursor: grab; user-select: none; transition: box-shadow 0.2s, border-color 0.2s; }
        .canvas-node:active { cursor: grabbing; }
        .canvas-node.selected { box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.5); }
        .canvas-node.in-topology { border-width: 3px; }
        .node-header { display: flex; align-items: center; gap: 8px; padding: 10px 12px; border-bottom: 1px solid #333; border-top: 3px solid; border-radius: 9px 9px 0 0; }
        .node-icon-small { width: 24px; height: 24px; border-radius: 6px; display: flex; align-items: center; justify-content: center; font-size: 12px; color: #fff; }
        .node-title { flex: 1; font-size: 13px; font-weight: 500; }
        .node-role-badge { font-size: 9px; background: rgba(255,255,255,0.15); padding: 2px 6px; border-radius: 8px; }
        .node-delete { background: none; border: none; color: #666; font-size: 16px; cursor: pointer; opacity: 0; transition: opacity 0.15s; }
        .canvas-node:hover .node-delete { opacity: 1; }
        .node-delete:hover { color: #ef4444; }
        .node-content { padding: 10px 12px; }
        .node-hint { font-size: 12px; color: #666; }

        .connect-dot { position: absolute; width: 12px; height: 12px; background: #404040; border: 2px solid #1f1f1f; border-radius: 50%; cursor: crosshair; left: 50%; transform: translateX(-50%); z-index: 10; transition: background 0.15s; }
        .connect-dot:hover { background: #6366f1; }
        .connect-dot.top { top: -6px; }
        .connect-dot.bottom { bottom: -6px; }
        .connect-dot.internal-top { background: #505050; }
        .connect-dot.internal-bottom { background: #505050; }
        .connect-dot.internal-top:hover, .connect-dot.internal-bottom:hover { background: #6366f1; }

        .topology-template { position: absolute; background: rgba(30, 30, 35, 0.95); border: 2px dashed; border-radius: 16px; cursor: grab; }
        .topology-template.selected { box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.5); }
        .template-header { display: flex; align-items: center; justify-content: space-between; padding: 10px 14px; border-radius: 14px 14px 0 0; color: #fff; gap: 8px; }
        .template-name { font-size: 13px; font-weight: 600; flex: 1; }
        .template-edge-type { font-size: 12px; opacity: 0.8; }
        .template-delete { background: none; border: none; color: rgba(255,255,255,0.6); font-size: 18px; cursor: pointer; }
        .template-delete:hover { color: #fff; }
        .template-body { position: relative; padding: 10px; overflow: visible; }
        .placeholder-layer { position: absolute; top: 0; left: 0; pointer-events: none; }
        .internal-edges-layer { position: absolute; top: 0; left: 0; pointer-events: none; overflow: visible; }
        .internal-edge-group:hover .edge-delete-btn, .internal-edge-group:hover .edge-delete-text { opacity: 1 !important; }
        .edge-delete-btn { pointer-events: auto; }

        .resize-handle { position: absolute; bottom: 0; right: 0; width: 16px; height: 16px; cursor: se-resize; background: linear-gradient(135deg, transparent 50%, rgba(255,255,255,0.3) 50%); border-radius: 0 0 14px 0; }
        .resize-handle:hover { background: linear-gradient(135deg, transparent 50%, rgba(99, 102, 241, 0.6) 50%); }

        .chat-area { background: #171717; border-top: 1px solid #262626; padding: 12px 20px; flex-shrink: 0; }
        .chat-messages { max-height: 80px; overflow-y: auto; margin-bottom: 10px; }
        .chat-msg { padding: 6px 10px; border-radius: 8px; font-size: 13px; margin-bottom: 6px; }
        .chat-msg.user { background: #262626; text-align: right; }
        .chat-msg.assistant { background: #1a3a2e; color: #4ade80; }
        .chat-input-row { display: flex; gap: 10px; }
        .chat-input { flex: 1; background: #262626; border: 1px solid #333; border-radius: 10px; padding: 12px 16px; color: #fff; font-size: 14px; font-family: inherit; }
        .chat-input:focus { outline: none; border-color: #6366f1; }
        .chat-input::placeholder { color: #666; }
        .chat-send { width: 44px; height: 44px; background: #6366f1; border: none; border-radius: 10px; color: #fff; font-size: 18px; cursor: pointer; }

        .right-panel { width: 300px; background: #171717; border-left: 1px solid #262626; display: flex; flex-direction: column; }
        .panel-header { display: flex; justify-content: space-between; padding: 16px; border-bottom: 1px solid #262626; }
        .panel-header h3 { font-size: 16px; }
        .close-btn { background: none; border: none; color: #666; font-size: 20px; cursor: pointer; }
        .panel-content { flex: 1; padding: 16px; overflow-y: auto; }
        .config-row { margin-bottom: 16px; }
        .config-row label { display: block; font-size: 12px; color: #a3a3a3; margin-bottom: 6px; }
        .config-row input, .config-row textarea, .config-row select { width: 100%; background: #262626; border: 1px solid #333; border-radius: 8px; padding: 10px 12px; color: #fff; font-size: 14px; font-family: inherit; }
        .config-row textarea { min-height: 80px; resize: vertical; }
        .config-row input:focus, .config-row textarea:focus { outline: none; border-color: #6366f1; }
        .config-info { margin-bottom: 16px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
        .config-badge { display: inline-block; padding: 4px 12px; border-radius: 12px; font-size: 12px; color: #fff; }
        .edge-type-badge { font-size: 11px; background: #333; padding: 4px 10px; border-radius: 10px; color: #aaa; }
        .checkbox-row label { display: flex; align-items: center; gap: 8px; cursor: pointer; }
        .checkbox-row input[type="checkbox"] { width: 16px; height: 16px; accent-color: #6366f1; }

        .flow-info { background: #1a1a1a; border-radius: 10px; padding: 12px; margin-bottom: 16px; }
        .flow-item { display: flex; gap: 10px; margin-bottom: 8px; }
        .flow-item:last-child { margin-bottom: 0; }
        .flow-label { font-size: 12px; font-weight: 600; color: #888; min-width: 50px; }
        .flow-desc { font-size: 12px; color: #aaa; }

        .topology-info { display: flex; gap: 8px; align-items: center; margin-top: 6px; }
        .topo-badge { padding: 4px 10px; border-radius: 8px; font-size: 11px; color: #fff; }
        .role-badge { padding: 4px 10px; border-radius: 8px; font-size: 11px; background: #333; color: #aaa; }

        .agents-list { background: #262626; border-radius: 8px; padding: 8px; margin-top: 6px; }
        .agent-item { display: flex; justify-content: space-between; align-items: center; padding: 6px 8px; border-radius: 6px; gap: 6px; }
        .agent-item:hover { background: #333; }
        .agent-item.is-start { background: rgba(99, 102, 241, 0.2); }
        .role-tag { font-size: 10px; background: #444; padding: 2px 6px; border-radius: 6px; }
        .start-tag { font-size: 9px; background: #6366f1; padding: 2px 6px; border-radius: 6px; font-weight: 600; }
        .empty-hint { font-size: 12px; color: #555; }
        .auto-hint { font-size: 11px; color: #888; margin-top: 4px; display: block; }
        .warning-hint { font-size: 11px; color: #f59e0b; margin-top: 6px; display: block; }

        .size-inputs { display: flex; align-items: center; gap: 8px; }
        .size-inputs input { width: 80px; }
        .size-inputs span { color: #666; }

        .role-popup-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; z-index: 1000; }
        .role-popup { position: fixed; background: #1f1f1f; border: 1px solid #333; border-radius: 12px; padding: 12px; box-shadow: 0 8px 32px rgba(0,0,0,0.5); transform: translate(-50%, -100%); margin-top: -10px; z-index: 1001; }
        .role-popup-header { font-size: 12px; color: #888; margin-bottom: 8px; text-align: center; }
        .role-popup-options { display: flex; flex-direction: column; gap: 6px; }
        .role-option { background: #262626; border: 1px solid #333; border-radius: 8px; padding: 10px 20px; color: #fff; font-size: 14px; cursor: pointer; transition: all 0.15s; }
        .role-option:hover { background: #333; border-color: #6366f1; }

        .drag-preview { position: fixed; background: #6366f1; color: #fff; padding: 8px 16px; border-radius: 8px; font-size: 13px; pointer-events: none; z-index: 9999; opacity: 0.9; }
      `}</style>
    </div>
  );
};

export default MASAgentBuilder;
