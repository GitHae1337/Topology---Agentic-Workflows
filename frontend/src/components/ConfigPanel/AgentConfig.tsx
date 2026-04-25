import { useCanvasStore } from '../../store';
import { Node } from '../../types';

interface AgentConfigProps {
  node: Node;
}

export const AgentConfig = ({ node }: AgentConfigProps) => {
  const topologyTemplates = useCanvasStore(state => state.topologyTemplates);
  const updateNode = useCanvasStore(state => state.updateNode);
  const setSelectedNode = useCanvasStore(state => state.setSelectedNode);

  const template = node.topologyId ? topologyTemplates.find(t => t.id === node.topologyId) : null;

  return (
    <>
      {/* Header */}
      <div className="flex justify-between p-4 border-b border-[#262626]">
        <h3 className="text-base">Configure Agent</h3>
        <button
          className="bg-transparent border-none text-[#666] text-xl cursor-pointer hover:text-white"
          onClick={() => setSelectedNode(null)}
        >
          ×
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 p-4 overflow-y-auto">
        {/* Name */}
        <div className="mb-4">
          <label className="block text-xs text-[#a3a3a3] mb-1.5">Name</label>
          <input
            type="text"
            className="w-full bg-[#262626] border border-[#333] rounded-lg px-3 py-2.5 text-white text-sm focus:outline-none focus:border-[#6366f1]"
            value={node.name}
            onChange={(e) => updateNode(node.id, { name: e.target.value })}
          />
        </div>

        {/* Topology membership */}
        {node.topologyId && (
          <div className="mb-4">
            <label className="block text-xs text-[#a3a3a3] mb-1.5">Topology</label>
            <div className="flex gap-2 items-center mt-1.5">
              <span
                className="px-2.5 py-1 rounded-lg text-[11px] text-white"
                style={{ backgroundColor: node.topologyColor || '#333' }}
              >
                {template?.name}
              </span>
              {node.topologyRole && (
                <span className="px-2.5 py-1 rounded-lg text-[11px] bg-[#333] text-[#aaa]">
                  {node.topologyRole}
                </span>
              )}
            </div>
          </div>
        )}

        {/* Instructions */}
        <div className="mb-4">
          <label className="block text-xs text-[#a3a3a3] mb-1.5">Instructions</label>
          <textarea
            className="w-full min-h-[80px] bg-[#262626] border border-[#333] rounded-lg px-3 py-2.5 text-white text-sm resize-y focus:outline-none focus:border-[#6366f1]"
            placeholder="What does this agent do..."
            value={(node.config?.instructions as string) || ''}
            onChange={(e) => updateNode(node.id, { config: { ...node.config, instructions: e.target.value } })}
          />
        </div>

        {/* Model selection */}
        <div className="mb-4">
          <label className="block text-xs text-[#a3a3a3] mb-1.5">Model</label>
          <select
            className="w-full bg-[#262626] border border-[#333] rounded-lg px-3 py-2.5 text-white text-sm focus:outline-none focus:border-[#6366f1]"
            value={(node.config?.model as string) || 'gpt-4.1'}
            onChange={(e) => updateNode(node.id, { config: { ...node.config, model: e.target.value } })}
          >
            <option value="gpt-4.1">GPT-4.1</option>
            <option value="gpt-5">GPT-5</option>
            <option value="gpt-5.2">GPT-5.2</option>
            <option value="gpt-5-nano">GPT-5 Nano</option>
            <option value="gpt-5-mini">GPT-5 Mini</option>
          </select>
        </div>
      </div>
    </>
  );
};
