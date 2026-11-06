"use client";

import { createContext, useCallback, useContext, useState } from "react";

// One tooltip for the whole page. Marks call show() on hover and on keyboard focus, so
// both give the same details. Content is plain text, never HTML.

export type Tip = { value: string; label: string; detail?: string };
type Position = { x: number; y: number };
type TooltipApi = {
  show: (tip: Tip, at: Position) => void;
  hide: () => void;
};

const Context = createContext<TooltipApi>({ show: () => {}, hide: () => {} });

export function TooltipProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<{ tip: Tip; at: Position } | null>(null);
  const show = useCallback((tip: Tip, at: Position) => setState({ tip, at }), []);
  const hide = useCallback(() => setState(null), []);
  return (
    <Context.Provider value={{ show, hide }}>
      {children}
      {state && (
        <div
          className="tooltip"
          role="status"
          style={{
            left: Math.min(state.at.x + 14, window.innerWidth - 260),
            top: state.at.y + 14,
          }}
        >
          <strong>{state.tip.value}</strong>
          <span>{state.tip.label}</span>
          {state.tip.detail && <em>{state.tip.detail}</em>}
        </div>
      )}
    </Context.Provider>
  );
}

// Props to spread on a mark: pointer and keyboard both show the tooltip.
export function useTip() {
  const { show, hide } = useContext(Context);
  return (tip: Tip) => ({
    tabIndex: 0,
    "aria-label": [tip.label, tip.value, tip.detail].filter(Boolean).join(", "),
    onPointerMove: (event: React.PointerEvent) => show(tip, { x: event.clientX, y: event.clientY }),
    onPointerLeave: hide,
    onFocus: (event: React.FocusEvent) => {
      const box = (event.currentTarget as HTMLElement).getBoundingClientRect();
      show(tip, { x: box.left + box.width / 2, y: box.bottom });
    },
    onBlur: hide,
  });
}
