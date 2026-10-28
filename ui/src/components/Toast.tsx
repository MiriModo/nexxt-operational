import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

type Toast = { id: number; text: string; fel: "ok" | "fail" };
const Ctx = createContext<(text: string, fel?: Toast["fel"]) => void>(() => undefined);

/** O confirmare scurtă, jos, după o acțiune (decizie trimisă, configurație salvată). Dispare singură. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [lista, setLista] = useState<Toast[]>([]);
  const arata = useCallback((text: string, fel: Toast["fel"] = "ok") => {
    const id = Date.now() + Math.random();
    setLista((l) => [...l, { id, text, fel }]);
    setTimeout(() => setLista((l) => l.filter((t) => t.id !== id)), 4000);
  }, []);
  const v = useMemo(() => arata, [arata]);
  return (
    <Ctx.Provider value={v}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {lista.map((t) => (
          <div key={t.id} className={`toast ${t.fel}`}>
            {t.text}
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}

export const useToast = () => useContext(Ctx);
