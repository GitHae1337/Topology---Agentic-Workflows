import { useEffect } from 'react';
import { useCanvasStore } from '../store';

// Returns true when the keyboard event originated inside a text-editing
// surface; we must NOT swallow the browser's native text undo in that case.
const isEditingTextTarget = (target: EventTarget | null): boolean => {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true;
  if (target.isContentEditable) return true;
  return false;
};

export const useUndoRedoKeys = (): void => {
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (isEditingTextTarget(event.target)) return;

      // Cross-platform modifier check. We treat Cmd (mac) and Ctrl (win/linux)
      // identically — typical web-app convention.
      const mod = event.metaKey || event.ctrlKey;
      if (!mod) return;

      const key = event.key.toLowerCase();
      const isUndo = key === 'z' && !event.shiftKey;
      const isRedo = (key === 'z' && event.shiftKey) || key === 'y';

      if (isUndo) {
        event.preventDefault();
        useCanvasStore.getState().undo();
      } else if (isRedo) {
        event.preventDefault();
        useCanvasStore.getState().redo();
      }
    };

    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);
};
