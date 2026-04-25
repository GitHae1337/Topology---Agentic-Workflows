import { topologies } from '../../constants/topologies';
import { useCanvasStore } from '../../store';
import { TopologyDefinition } from '../../types';

export const TopologyPalette = () => {
  const addTopologyTemplate = useCanvasStore(state => state.addTopologyTemplate);

  const handleDragStart = (e: React.DragEvent, topo: TopologyDefinition) => {
    e.dataTransfer.setData('topologyType', JSON.stringify(topo));
    e.dataTransfer.effectAllowed = 'move';
  };

  const handleClick = (topo: TopologyDefinition) => {
    addTopologyTemplate(topo.id, 400, 200);
  };

  return (
    <div className="mt-4 pt-4 border-t border-[#262626]">
      <span className="text-[11px] text-[#666] uppercase tracking-wider block mb-2">
        Topology Templates
      </span>
      <div className="mt-2">
        {topologies.map(topo => (
          <div
            key={topo.id}
            className="flex items-center gap-2.5 px-2.5 py-2 rounded-lg cursor-pointer mb-1 hover:bg-[#262626]"
            draggable
            onDragStart={(e) => handleDragStart(e, topo)}
            onClick={() => handleClick(topo)}
          >
            <div
              className="w-7 h-7 rounded-md flex items-center justify-center text-xs text-white"
              style={{ backgroundColor: topo.color }}
            >
              {topo.icon}
            </div>
            <div className="flex-1 flex flex-col">
              <span className="text-[13px]">{topo.name}</span>
              <span className="text-[10px] text-[#666]">{topo.subtitle}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
