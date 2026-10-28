import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { getEu, login as loginApi, logout as logoutApi, onDeconectare, type Rol, type Utilizator } from "./api/client";

type Auth = { eu: Utilizator | null; login: (u: string, p: string) => Promise<Utilizator | null>; logout: () => Promise<void> };
const Ctx = createContext<Auth>({ eu: null, login: async () => null, logout: async () => undefined });

export const homeFor = (u: Utilizator | null) => (!u ? "/" : u.rol === "admin" ? "/overview" : "/desk");

/** Who is signed in. The server enforces the role; this only remembers the user and clears the cache on change. */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [eu, setEu] = useState<Utilizator | null>(() => getEu());
  const qc = useQueryClient();
  useEffect(() => onDeconectare(() => setEu(null)), []);
  const login = useCallback(
    async (u: string, p: string) => {
      const x = await loginApi(u, p);
      if (x) {
        qc.clear();
        setEu(x);
      }
      return x;
    },
    [qc],
  );
  const logout = useCallback(async () => {
    await logoutApi();
    qc.clear();
    setEu(null);
  }, [qc]);
  const v = useMemo(() => ({ eu, login, logout }), [eu, login, logout]);
  return <Ctx.Provider value={v}>{children}</Ctx.Provider>;
}

export const useEu = () => useContext(Ctx);

/** Pages behind sign-in: no session → landing; wrong role → that user's own home. */
export function Protected({ role, children }: { role?: Rol; children: ReactNode }) {
  const { eu } = useEu();
  if (!eu) return <Navigate to="/" replace />;
  if (role && eu.rol !== role) return <Navigate to={homeFor(eu)} replace />;
  return <>{children}</>;
}
