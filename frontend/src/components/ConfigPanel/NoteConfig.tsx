import { useCanvasStore } from '../../store';
import { Node } from '../../types';

interface NoteConfigProps {
  node: Node;
}

export const NoteConfig = ({ node }: NoteConfigProps) => {
  const updateNode = useCanvasStore(state => state.updateNode);
  const setSelectedNode = useCanvasStore(state => state.setSelectedNode);

  return (
    <>
      {/* Header */}
      <div className="flex justify-between p-4 border-b border-[#262626]">
        <h3 className="text-base">Note</h3>
        <button
          className="bg-transparent border-none text-[#666] text-xl cursor-pointer hover:text-white"
          onClick={() => setSelectedNode(null)}
        >
          ×
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 p-4 overflow-y-auto">
        {/* Note content */}
        <div className="mb-4">
          <label className="block text-xs text-[#a3a3a3] mb-1.5">Content</label>
          <textarea
            className="w-full min-h-[150px] bg-[#262626] border border-[#333] rounded-lg px-3 py-2.5 text-white text-sm resize-y focus:outline-none focus:border-[#6366f1]"
            placeholder="Add a comment or annotation..."
            value={(node.config?.content as string) || ''}
            onChange={(e) => updateNode(node.id, { config: { ...node.config, content: e.target.value } })}
          />
        </div>
      </div>
    </>
  );
};
