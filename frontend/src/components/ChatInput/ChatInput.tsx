import { useState, useCallback } from 'react';
import { useCanvasStore } from '../../store';
import { topologies } from '../../constants/topologies';

export const ChatInput = () => {
  const [input, setInput] = useState('');
  const chatMessages = useCanvasStore(state => state.chatMessages);
  const addChatMessage = useCanvasStore(state => state.addChatMessage);
  const clearChatMessages = useCanvasStore(state => state.clearChatMessages);
  const addNode = useCanvasStore(state => state.addNode);
  const addTopologyTemplate = useCanvasStore(state => state.addTopologyTemplate);
  const clearCanvas = useCanvasStore(state => state.clearCanvas);

  const processCommand = useCallback(() => {
    if (!input.trim()) return;

    const inputLower = input.toLowerCase();
    addChatMessage({ role: 'user', text: input });

    let response = '';

    // Add agent(s) command
    if (inputLower.includes('add agent') || inputLower.includes('new agent')) {
      const countMatch = inputLower.match(/(\d+)/);
      const count = countMatch ? parseInt(countMatch[1]) : 1;

      for (let i = 0; i < count; i++) {
        addNode('agent', 300 + Math.random() * 100, 150 + i * 80);
      }
      response = `Added ${count} agent(s).`;
    }
    // Add topology command
    else if (inputLower.includes('topology')) {
      const topoMatch = topologies.find(
        t => inputLower.includes(t.name.toLowerCase()) || inputLower.includes(t.id)
      );
      if (topoMatch) {
        addTopologyTemplate(topoMatch.id, 400, 200);
        response = `Added ${topoMatch.name} topology template.`;
      } else {
        response = 'Available: Centralized, Sequential, Hierarchical, P2P, Mesh, DAG, Cyclic';
      }
    }
    // Clear command
    else if (inputLower.includes('clear')) {
      clearCanvas();
      response = 'Canvas cleared.';
    }
    // Help / unknown command
    else {
      response = `Try "add agent", "add 3 agents", "add hierarchical topology", or "clear"`;
    }

    addChatMessage({ role: 'assistant', text: response });
    setInput('');
  }, [input, addChatMessage, addNode, addTopologyTemplate, clearCanvas]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      processCommand();
    }
  };

  return (
    <div className="bg-[#171717] border-t border-[#262626] px-5 py-3 flex-shrink-0">
      {/* Assistant responses only */}
      {chatMessages.filter(msg => msg.role === 'assistant').length > 0 && (
        <div className="max-h-20 overflow-y-auto mb-2.5">
          {chatMessages
            .filter(msg => msg.role === 'assistant')
            .slice(-3)
            .map((msg, i) => (
              <div
                key={i}
                className="flex items-center gap-2 bg-[#1a3a2e] px-2.5 py-1.5 rounded-lg text-[13px] mb-1.5"
              >
                <span className="flex-1 text-[#4ade80]">{msg.text}</span>
                <button
                  onClick={clearChatMessages}
                  className="text-[#4ade80] hover:text-white text-base leading-none"
                  title="Dismiss"
                >
                  ×
                </button>
              </div>
            ))}
        </div>
      )}

      {/* Input row */}
      <div className="flex gap-2.5">
        <input
          type="text"
          className="flex-1 bg-[#262626] border border-[#333] rounded-[10px] px-4 py-3 text-white text-sm focus:outline-none focus:border-[#6366f1] placeholder:text-[#666]"
          placeholder="Describe changes... (e.g., 'add 3 agents', 'add hierarchical topology')"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        <button
          className="w-11 h-11 bg-[#6366f1] border-none rounded-[10px] text-white text-lg cursor-pointer hover:bg-[#5558e3]"
          onClick={processCommand}
        >
          ↑
        </button>
      </div>
    </div>
  );
};
