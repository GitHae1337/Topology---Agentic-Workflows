import { useCanvasStore } from '../../store';
import { Node, IfElseCondition } from '../../types';

interface IfElseConfigProps {
  node: Node;
}

export const IfElseConfig = ({ node }: IfElseConfigProps) => {
  const addCondition = useCanvasStore(state => state.addCondition);
  const updateCondition = useCanvasStore(state => state.updateCondition);
  const deleteCondition = useCanvasStore(state => state.deleteCondition);
  const deleteNode = useCanvasStore(state => state.deleteNode);

  const conditions = (node.config?.conditions as IfElseCondition[]) || [];

  return (
    <>
      {/* Header */}
      <div className="flex justify-between items-center p-4 border-b border-[#262626]">
        <h3 className="text-base font-medium">If / else</h3>
        <div className="flex items-center gap-2">
          <button
            className="bg-transparent border-none text-[#666] text-lg cursor-pointer hover:text-white"
            title="Duplicate"
          >
            ⧉
          </button>
          <button
            className="bg-transparent border-none text-[#666] text-lg cursor-pointer hover:text-[#ef4444]"
            onClick={() => deleteNode(node.id)}
            title="Delete"
          >
            🗑
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 p-4 overflow-y-auto">
        <p className="text-xs text-[#888] mb-4">
          Create conditions to branch your workflow
        </p>

        {/* Conditions list */}
        <div className="space-y-4">
          {conditions.map((condition, index) => (
            <div key={condition.id} className="border-b border-[#333] pb-4">
              {/* Condition header */}
              <div className="flex justify-between items-center mb-2">
                <span className="text-sm text-white">{index === 0 ? 'If' : 'Else if'}</span>
                {conditions.length > 1 && (
                  <button
                    className="bg-transparent border-none text-[#666] text-sm cursor-pointer hover:text-[#ef4444]"
                    onClick={() => deleteCondition(node.id, condition.id)}
                    title="Delete condition"
                  >
                    🗑
                  </button>
                )}
              </div>

              {/* Case name input */}
              <input
                type="text"
                className="w-full bg-[#262626] border border-[#333] rounded-lg px-3 py-2 text-white text-sm mb-2 focus:outline-none focus:border-[#6366f1]"
                placeholder="Case name (optional)"
                value={condition.name || ''}
                onChange={(e) => updateCondition(node.id, condition.id, { name: e.target.value })}
              />

              {/* Condition expression */}
              <textarea
                className="w-full min-h-[60px] bg-[#262626] border border-[#333] rounded-lg px-3 py-2 text-white text-sm resize-y focus:outline-none focus:border-[#6366f1]"
                placeholder="Enter condition, e.g. input == 5"
                value={condition.condition || ''}
                onChange={(e) => updateCondition(node.id, condition.id, { condition: e.target.value })}
              />

            </div>
          ))}
        </div>

        {/* Add condition button */}
        <button
          className="flex items-center gap-1.5 text-sm text-[#6366f1] bg-transparent border-none cursor-pointer mt-4 hover:text-[#818cf8]"
          onClick={() => addCondition(node.id)}
        >
          <span>+</span>
          <span>Add</span>
        </button>
      </div>
    </>
  );
};
