import { useCanvasStore } from '../../store';
import { TopologyTemplate } from '../../types';
import { getTopologyDefinition } from '../../constants/topologies';

interface TopologyConfigProps {
  template: TopologyTemplate;
}

export const TopologyConfig = ({ template }: TopologyConfigProps) => {
  const getAgentsInTopology = useCanvasStore(state => state.getAgentsInTopology);
  const updateTopologyTemplate = useCanvasStore(state => state.updateTopologyTemplate);
  const setSelectedTemplate = useCanvasStore(state => state.setSelectedTemplate);

  const topo = getTopologyDefinition(template.type);
  const agentsInside = getAgentsInTopology(template.id);

  if (!topo) return null;

  return (
    <>
      {/* Header */}
      <div className="flex justify-between p-4 border-b border-[#262626]">
        <h3 className="text-base">Topology Settings</h3>
        <button
          className="bg-transparent border-none text-[#666] text-xl cursor-pointer hover:text-white"
          onClick={() => setSelectedTemplate(null)}
        >
          ×
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 p-4 overflow-y-auto">
        {/* Type badges */}
        <div className="mb-4 flex gap-2 items-center flex-wrap">
          <span
            className="inline-block px-3 py-1 rounded-xl text-xs text-white"
            style={{ backgroundColor: template.color }}
          >
            {template.name}
          </span>
          <span className="text-[11px] bg-[#333] px-2.5 py-1 rounded-[10px] text-[#aaa]">
            {topo.edgeType === 'bidirectional' ? '↔ Bidirectional' : '→ Unidirectional'}
          </span>
        </div>

        {/* Flow info */}
        <div className="bg-[#1a1a1a] rounded-[10px] p-3 mb-4">
          <div className="flex gap-2.5 mb-2">
            <span className="text-xs font-semibold text-[#888] min-w-[50px]">▶ Start</span>
            <span className="text-xs text-[#aaa]">{topo.startPoint}</span>
          </div>
          <div className="flex gap-2.5">
            <span className="text-xs font-semibold text-[#888] min-w-[50px]">■ End</span>
            <span className="text-xs text-[#aaa]">{topo.endPoint}</span>
          </div>
        </div>

        {/* Start Agent selector for topologies that need it */}
        {topo.needsStartAgent && (
          <div className="mb-4">
            <label className="block text-xs text-[#a3a3a3] mb-1.5">Start Agent</label>
            <select
              className="w-full bg-[#262626] border border-[#333] rounded-lg px-3 py-2.5 text-white text-sm focus:outline-none focus:border-[#6366f1]"
              value={template.startAgentId || ''}
              onChange={(e) => updateTopologyTemplate(template.id, { startAgentId: e.target.value || null })}
            >
              <option value="">Select start agent...</option>
              {agentsInside.map(agent => (
                <option key={agent.id} value={agent.id}>{agent.name}</option>
              ))}
            </select>
            {!template.startAgentId && agentsInside.length > 0 && (
              <span className="text-[11px] text-[#f59e0b] mt-1.5 block">⚠ Start agent required before run</span>
            )}
          </div>
        )}

        {/* Agents list */}
        <div className="mb-4">
          <label className="block text-xs text-[#a3a3a3] mb-1.5">
            Agents ({agentsInside.length})
          </label>
          <div className="bg-[#262626] rounded-lg p-2 mt-1.5">
            {agentsInside.map(agent => (
              <div
                key={agent.id}
                className={`flex justify-between items-center px-2 py-1.5 rounded-md gap-1.5 ${
                  template.startAgentId === agent.id ? 'bg-[rgba(99,102,241,0.2)]' : 'hover:bg-[#333]'
                }`}
              >
                <span className="text-sm">{agent.name}</span>
                {agent.topologyRole && (
                  <span className="text-[10px] bg-[#444] px-1.5 py-0.5 rounded-md">{agent.topologyRole}</span>
                )}
                {template.startAgentId === agent.id && (
                  <span className="text-[9px] bg-[#6366f1] px-1.5 py-0.5 rounded-md font-semibold">START</span>
                )}
              </div>
            ))}
            {agentsInside.length === 0 && (
              <span className="text-xs text-[#555]">Drag agents into topology</span>
            )}
          </div>
        </div>

        {/* Internal edges count */}
        <div className="mb-4">
          <label className="block text-xs text-[#a3a3a3] mb-1.5">
            Internal Edges ({template.internalEdges.length})
          </label>
          {topo.autoConnect && (
            <span className="text-[11px] text-[#888] mt-1 block">Auto-connected (Mesh)</span>
          )}
          {topo.autoEdgeOnRole && (
            <span className="text-[11px] text-[#888] mt-1 block">Auto-connected based on role</span>
          )}
        </div>

        {/* Max Turns/Rounds - not applicable for Sequential (DAG/FSM ends when last node completes) */}
        {template.type !== 'sequential' && (
          <div className="mb-4">
            <label className="block text-xs text-[#a3a3a3] mb-1.5">
              {template.type === 'mesh' || template.type === 'centralized' || template.type === 'hierarchical' || template.type === 'p2p' ? 'Max Rounds' : 'Max Turns'}
            </label>
            <input
              type="number"
              className="w-full bg-[#262626] border border-[#333] rounded-lg px-3 py-2.5 text-white text-sm focus:outline-none focus:border-[#6366f1]"
              value={template.maxTurns}
              onChange={(e) => updateTopologyTemplate(template.id, { maxTurns: parseInt(e.target.value) || 10 })}
              min={1}
              max={100}
            />
          </div>
        )}

        {/* Timeout - not applicable for Sequential */}
        {template.type !== 'sequential' && (
          <div className="mb-4">
            <label className="block text-xs text-[#a3a3a3] mb-1.5">Timeout (seconds)</label>
            <input
              type="number"
              className="w-full bg-[#262626] border border-[#333] rounded-lg px-3 py-2.5 text-white text-sm focus:outline-none focus:border-[#6366f1]"
              value={template.timeout}
              onChange={(e) => updateTopologyTemplate(template.id, { timeout: parseInt(e.target.value) || 180 })}
              min={30}
            />
          </div>
        )}

        {/* Early Termination - not applicable for Sequential */}
        {template.type !== 'sequential' && (
          <div className="mb-4">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                className="w-4 h-4 accent-[#6366f1]"
                checked={template.earlyTermination}
                onChange={(e) => updateTopologyTemplate(template.id, { earlyTermination: e.target.checked })}
              />
              <span className="text-sm">Early termination on completion</span>
            </label>
          </div>
        )}

      </div>
    </>
  );
};
