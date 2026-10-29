// Hook-uri React Query peste stratul de date: cache per resursă, invalidare după decizii / rescan.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { DecizieInput, ParametriCoada } from "../types/api";
import {
  getBirou, getCaz, getCoada, getConfig, getConfigDiff, getConfigLista, getContext, getEchipa, getFeedback, getIstoric, getMetrici, getModel,
  getStareLlm, getSumar, getUtilizatori, postDecizie, postPropunere, postRescan, postRezultat, postVerifica, putConfig,
} from "./client";

export const chei = {
  context: ["context"] as const,
  sumar: ["sumar"] as const,
  metrici: ["metrici"] as const,
  coada: (p: ParametriCoada) => ["coada", p] as const,
  caz: (id: string) => ["caz", id] as const,
  istoric: (id: string) => ["istoric", id] as const,
  echipa: ["echipa"] as const,
  feedback: ["feedback"] as const,
  model: ["model"] as const,
  config: ["config"] as const,
  configFisier: (n: string) => ["config", n] as const,
  configDiff: (n: string) => ["config", n, "diff"] as const,
  birou: ["birou"] as const,
  utilizatori: ["utilizatori"] as const,
  propunere: (id: string) => ["propunere", id] as const,
  stareLlm: ["llm", "stare"] as const,
};

export const useContext = () => useQuery({ queryKey: chei.context, queryFn: getContext, staleTime: 60_000 });
export const useSumar = () => useQuery({ queryKey: chei.sumar, queryFn: getSumar });
export const useBirou = () => useQuery({ queryKey: chei.birou, queryFn: getBirou });
export const useUtilizatori = () => useQuery({ queryKey: chei.utilizatori, queryFn: getUtilizatori, staleTime: 5 * 60_000 });
export const useMetrici = () => useQuery({ queryKey: chei.metrici, queryFn: getMetrici, staleTime: 60_000 });
export const useCoada = (p: ParametriCoada) => useQuery({ queryKey: chei.coada(p), queryFn: () => getCoada(p), placeholderData: (prev) => prev });
export const useCaz = (id: string) => useQuery({ queryKey: chei.caz(id), queryFn: () => getCaz(id), enabled: !!id });
export const useIstoric = (id: string) => useQuery({ queryKey: chei.istoric(id), queryFn: () => getIstoric(id), enabled: !!id });
export const useEchipa = () => useQuery({ queryKey: chei.echipa, queryFn: getEchipa, staleTime: 5 * 60_000 });
export const useFeedback = () => useQuery({ queryKey: chei.feedback, queryFn: getFeedback });
export const useModel = () => useQuery({ queryKey: chei.model, queryFn: getModel, staleTime: 5 * 60_000 });
export const useConfigLista = () => useQuery({ queryKey: chei.config, queryFn: getConfigLista });
export const useConfigFisier = (n: string) => useQuery({ queryKey: chei.configFisier(n), queryFn: () => getConfig(n), enabled: !!n });
/** Agentul LLM: propunerea unui caz, comună paginii cazului și paginii de decizie (serverul o ține în cache). */
export const usePropunere = (id: string, enabled = true) =>
  useQuery({ queryKey: chei.propunere(id), queryFn: () => postPropunere(id), enabled: !!id && enabled, staleTime: Infinity, retry: false });
export const useStareLlm = () => useQuery({ queryKey: chei.stareLlm, queryFn: getStareLlm, staleTime: 60_000 });
export function useRegenereaza(id: string) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: () => postPropunere(id, true), onSuccess: (p) => qc.setQueryData(chei.propunere(id), p) });
}
export const useConfigDiff = (n: string) => useQuery({ queryKey: chei.configDiff(n), queryFn: () => getConfigDiff(n), enabled: !!n });

export function useDecizie(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (d: DecizieInput) => postDecizie(id, d),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: chei.istoric(id) });
      qc.invalidateQueries({ queryKey: chei.sumar });
      qc.invalidateQueries({ queryKey: chei.feedback });
      qc.invalidateQueries({ queryKey: chei.birou });
      qc.invalidateQueries({ queryKey: ["coada"] });
    },
  });
}

export function useRezultat(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (rezultat: "ramas" | "plecat") => postRezultat(id, rezultat),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: chei.istoric(id) });
      qc.invalidateQueries({ queryKey: chei.feedback });
    },
  });
}

export const useVerifica = (id: string) => useMutation({ mutationFn: () => postVerifica(id) });

export function useSalveazaConfig(n: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (text: string) => putConfig(n, text),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: chei.config });
      qc.invalidateQueries({ queryKey: chei.configDiff(n) });
      qc.invalidateQueries({ queryKey: chei.context });
    },
  });
}

export function useRescan() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: postRescan, onSuccess: () => qc.invalidateQueries() });
}
