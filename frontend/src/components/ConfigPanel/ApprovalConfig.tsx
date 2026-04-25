import { useCanvasStore } from '../../store';
import { Node } from '../../types';

interface ApprovalConfigProps {
  node: Node;
}

export const ApprovalConfig = ({ node }: ApprovalConfigProps) => {
  const updateNode = useCanvasStore(state => state.updateNode);
  const setSelectedNode = useCanvasStore(state => state.setSelectedNode);

  return (
    <>
      {/* Header */}
      <div className="flex justify-between p-4 border-b border-[#262626]">
        <div>
          <h3 className="text-base">User approval</h3>
          <p className="text-xs text-[#666] mt-1">Pause for a human to approve or reject a step</p>
        </div>
        <button
          className="bg-transparent border-none text-[#666] text-xl cursor-pointer hover:text-white self-start"
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

        {/* Message */}
        <div className="mb-4">
          <label className="block text-xs text-[#a3a3a3] mb-1.5">Message</label>
          <textarea
            className="w-full min-h-[100px] bg-[#262626] border border-[#333] rounded-lg px-3 py-2.5 text-white text-sm resize-y focus:outline-none focus:border-[#6366f1]"
            placeholder="Describe the message to show the user. Eg. ok to proceed?"
            value={(node.config?.message as string) || ''}
            onChange={(e) => updateNode(node.id, { config: { ...node.config, message: e.target.value } })}
          />
        </div>
      </div>
    </>
  );
};
