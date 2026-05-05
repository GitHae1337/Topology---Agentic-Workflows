import { useCanvasStore } from '../../store';
import { AgentConfig } from './AgentConfig';
import { TopologyConfig } from './TopologyConfig';
import { IfElseConfig } from './IfElseConfig';
import { NoteConfig } from './NoteConfig';
import { ApprovalConfig } from './ApprovalConfig';
import { StartEndConfig } from './StartEndConfig';

export const ConfigPanel = () => {
  const selectedNodes = useCanvasStore(state => state.selectedNodes);
  const selectedTemplate = useCanvasStore(state => state.selectedTemplate);
  const nodes = useCanvasStore(state => state.nodes);
  const topologyTemplates = useCanvasStore(state => state.topologyTemplates);

  // Only show node config when exactly one node is selected
  const selectedNodeData = selectedNodes.length === 1
    ? nodes.find(n => n.id === selectedNodes[0])
    : null;
  const selectedTemplateData = selectedTemplate ? topologyTemplates.find(t => t.id === selectedTemplate) : null;

  // Hide ConfigPanel entirely for Start/End nodes — they have no useful
  // config and the description tooltip clutters the canvas.
  if (selectedNodeData && (selectedNodeData.type === 'start' || selectedNodeData.type === 'end')) {
    return null;
  }

  // Only show panel when something is selected
  if (!selectedNodeData && !selectedTemplateData) {
    // Show info when multiple nodes selected
    if (selectedNodes.length > 1) {
      return (
        <div className="w-[300px] bg-[#171717] border-l border-[#262626] flex flex-col p-4">
          <div className="text-[#a3a3a3] text-sm">
            {selectedNodes.length} nodes selected
          </div>
        </div>
      );
    }
    return null;
  }

  // Determine which config to show based on node type
  const renderNodeConfig = () => {
    if (!selectedNodeData) return null;

    if (selectedNodeData.type === 'start' || selectedNodeData.type === 'end') {
      return <StartEndConfig node={selectedNodeData} />;
    }

    if (selectedNodeData.type === 'ifelse') {
      return <IfElseConfig node={selectedNodeData} />;
    }

    if (selectedNodeData.type === 'note') {
      return <NoteConfig node={selectedNodeData} />;
    }

    if (selectedNodeData.type === 'approval') {
      return <ApprovalConfig node={selectedNodeData} />;
    }

    return <AgentConfig node={selectedNodeData} />;
  };

  return (
    <div className="w-[300px] bg-[#171717] border-l border-[#262626] flex flex-col">
      {renderNodeConfig()}
      {selectedTemplateData && <TopologyConfig template={selectedTemplateData} />}
    </div>
  );
};
