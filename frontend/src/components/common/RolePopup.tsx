import { useCanvasStore } from '../../store';

export const RolePopup = () => {
  const rolePopup = useCanvasStore(state => state.rolePopup);
  const setRolePopup = useCanvasStore(state => state.setRolePopup);
  const addAgentToTopology = useCanvasStore(state => state.addAgentToTopology);

  if (!rolePopup) return null;

  const handleRoleSelect = (role: string) => {
    addAgentToTopology(rolePopup.agentId, rolePopup.templateId, role);
  };

  const handleOverlayClick = () => {
    setRolePopup(null);
  };

  return (
    <div
      className="fixed inset-0 z-[1000]"
      onClick={handleOverlayClick}
    >
      <div
        className="fixed bg-[#1f1f1f] border border-[#333] rounded-xl p-3 shadow-[0_8px_32px_rgba(0,0,0,0.5)] z-[1001]"
        style={{
          left: rolePopup.x,
          top: rolePopup.y,
          transform: 'translate(-50%, -100%)',
          marginTop: '-10px',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="text-xs text-[#888] mb-2 text-center">Select Role</div>
        <div className="flex flex-col gap-1.5">
          {rolePopup.roles.map(role => (
            <button
              key={role}
              className="bg-[#262626] border border-[#333] rounded-lg px-5 py-2.5 text-white text-sm cursor-pointer transition-all hover:bg-[#333] hover:border-[#6366f1]"
              onClick={() => handleRoleSelect(role)}
            >
              {role}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};
