import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

type Toast = { id: number; text: string; kind: "ok" | "fail" };
const Ctx = createContext<(text: string, kind?: Toast["kind"]) => void>(() => undefined);

/** A short confirmation at the bottom after an action (decision sent, rules saved). Disappears by itself. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [list, setList] = useState<Toast[]>([]);
  const show = useCallback((text: string, kind: Toast["kind"] = "ok") => {
    const id = Date.now() + Math.random();
    setList((l) => [...l, { id, text, kind }]);
    setTimeout(() => setList((l) => l.filter((t) => t.id !== id)), 4000);
  }, []);
  const v = useMemo(() => show, [show]);
  return (
    <Ctx.Provider value={v}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {list.map((t) => (
          <div key={t.id} className={`toast ${t.kind}`}>
            {t.text}
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}

export const useToast = () => useContext(Ctx);
