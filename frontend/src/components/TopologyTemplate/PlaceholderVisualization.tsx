import { TopologyTemplate } from '../../types';
import { getPlaceholderConfig } from '../../utils/placeholders';

interface PlaceholderVisualizationProps {
  template: TopologyTemplate;
}

export const PlaceholderVisualization = ({ template }: PlaceholderVisualizationProps) => {
  const config = getPlaceholderConfig(template.type, template.width, template.height);

  return (
    <svg className="absolute top-0 left-0 w-full h-full pointer-events-none">
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
              x1={from.x}
              y1={from.y}
              x2={endX}
              y2={endY}
              stroke={template.color}
              strokeWidth="2"
              strokeDasharray="4"
              opacity="0.3"
            />
            {/* Arrow head */}
            <text
              x={to.x}
              y={to.y}
              fontSize="12"
              fill={template.color}
              opacity="0.4"
              textAnchor="middle"
              dominantBaseline="middle"
              transform={`rotate(${Math.atan2(dy, dx) * 180 / Math.PI}, ${to.x}, ${to.y})`}
            >
              ›
            </text>

            {/* Bidirectional reverse edge */}
            {edge.bidirectional && (
              <>
                <line
                  x1={to.x + ny * 6}
                  y1={to.y - nx * 6}
                  x2={from.x + ny * 6}
                  y2={from.y - nx * 6}
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
                >
                  ›
                </text>
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
