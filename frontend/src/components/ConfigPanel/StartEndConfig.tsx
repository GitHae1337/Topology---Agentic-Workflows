import { Node } from '../../types';
import { getNodeColor, getNodeIcon } from '../../constants/nodeTypes';
import { useCanvasStore } from '../../store';

interface StartEndConfigProps {
  node: Node;
}

export const StartEndConfig = ({ node }: StartEndConfigProps) => {
  const setSelectedNode = useCanvasStore(state => state.setSelectedNode);
  const nodeColor = getNodeColor(node.type);

  const title = node.type === 'start' ? 'Start' : 'End';
  const description = node.type === 'start'
    ? 'Entry point of the workflow'
    : 'End point of the workflow';

  return (
    <>
      {/* Header */}
      <div className="flex justify-between p-4 border-b border-[#262626]">
        <div className="flex items-center gap-2">
          <div
            className="w-6 h-6 rounded-md flex items-center justify-center text-xs text-white"
            style={{ backgroundColor: nodeColor }}
          >
            {getNodeIcon(node.type)}
          </div>
          <h3 className="text-base">{title}</h3>
        </div>
        <button
          className="bg-transparent border-none text-[#666] text-xl cursor-pointer hover:text-white"
          onClick={() => setSelectedNode(null)}
        >
          ×
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 p-4 overflow-y-auto">
        <p className="text-sm text-[#a3a3a3]">{description}</p>
      </div>
    </>
  );
};
