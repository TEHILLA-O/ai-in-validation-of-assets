import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import { SCALES, type ScaleId } from "./format";
import type { Assumptions, CompanyItem, Dashboard, ModelPayload, ModelResult, Snapshot, Trace } from "./types";

interface Archive {
  runId: string;
  calculatedAt: string;
  snapshot: Snapshot;
  result: ModelResult;
  dashboard: Dashboard;
}

interface WorkspaceValue {
  companies: CompanyItem[];
  company: CompanyItem | null;
  setCompanyId: (id: string) => void;
  modelId: string | null;
  payload: ModelPayload | null;
  result: ModelResult | null;
  dashboard: Dashboard | null;
  snapshot: Snapshot | null;
  loading: boolean;
  error: string | null;
  scale: ScaleId;
  setScale: (scale: ScaleId) => void;
  divisor: number;
  theme: "light" | "dark";
  setTheme: (theme: "light" | "dark") => void;
  trace: Trace | null;
  openTrace: (id: string) => void;
  closeTrace: () => void;
  archive: Archive | null;
  viewRun: (runId: string) => Promise<void>;
  clearArchive: () => void;
  adoptModel: (modelId: string) => void;
  saveAssumptions: (mutate: (assumptions: Assumptions) => void, note: string) => Promise<void>;
  calculate: () => Promise<void>;
  refresh: () => Promise<void>;
}

const WorkspaceContext = createContext<WorkspaceValue | null>(null);

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [companyId, setCompanyId] = useState<string | null>(null);
  const [modelOverride, setModelOverride] = useState<string | null>(null);
  const [scale, setScale] = useState<ScaleId>("units");
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [trace, setTrace] = useState<Trace | null>(null);
  const [archive, setArchive] = useState<Archive | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
  }, [theme]);

  const companiesQuery = useQuery({
    queryKey: ["companies"],
    queryFn: () => api<{ items: CompanyItem[] }>("/companies"),
  });
  const companies = companiesQuery.data?.items ?? [];
  const company = companies.find((item) => item.id === companyId) ?? companies[0] ?? null;
  const modelId = modelOverride ?? company?.model_id ?? null;

  const modelQuery = useQuery({
    queryKey: ["model", modelId],
    queryFn: () => api<ModelPayload>(`/models/${modelId}`),
    enabled: Boolean(modelId),
  });

  const payload = modelQuery.data ?? null;
  const result = archive?.result ?? payload?.result ?? null;
  const dashboard = archive?.dashboard ?? payload?.dashboard ?? null;
  const snapshot = archive?.snapshot ?? payload?.snapshot ?? null;

  const value = useMemo<WorkspaceValue>(() => {
    const divisor = SCALES.find((item) => item.id === scale)?.divisor ?? 1;
    return {
      companies,
      company,
      setCompanyId: (id: string) => {
        setCompanyId(id);
        setModelOverride(null);
        setArchive(null);
      },
      modelId,
      payload,
      result,
      dashboard,
      snapshot,
      loading: companiesQuery.isLoading || modelQuery.isLoading,
      error: actionError || (companiesQuery.error instanceof Error ? companiesQuery.error.message : null) || (modelQuery.error instanceof Error ? modelQuery.error.message : null),
      scale,
      setScale,
      divisor,
      theme,
      setTheme,
      trace,
      openTrace: (id: string) => {
        const found = result?.traces.find((item) => item.id === id);
        setTrace(found ?? {
          id,
          label: "Trace is not on this stored run",
          period: null,
          formula: "Recalculate the model. The calculation engine stores the formula with the valuation run.",
          components: [],
          result: "",
          kind: "calculation",
          note: "An older saved run does not gain new traces until it is calculated again.",
        });
      },
      closeTrace: () => setTrace(null),
      archive,
      viewRun: async (runId: string) => {
        const run = await api<{
          run_id: string;
          created_at: string;
          input_snapshot: Snapshot;
          result: ModelResult;
          dashboard: Dashboard;
        }>(`/runs/${runId}`);
        setArchive({
          runId: run.run_id,
          calculatedAt: run.created_at,
          snapshot: run.input_snapshot,
          result: run.result,
          dashboard: run.dashboard,
        });
      },
      clearArchive: () => setArchive(null),
      adoptModel: (id: string) => {
        setModelOverride(id);
        setArchive(null);
      },
      saveAssumptions: async (mutate, note) => {
        if (!snapshot || !modelId || archive) return;
        const next = structuredClone(snapshot.assumptions);
        mutate(next);
        setActionError(null);
        try {
          const saved = await api<{ model_id: string }>(`/assumptions/${modelId}`, {
            method: "PUT",
            body: JSON.stringify({ assumptions: next, note }),
          });
          await api(`/models/${saved.model_id}/calculate`, { method: "POST" });
          setModelOverride(saved.model_id);
          await queryClient.invalidateQueries({ queryKey: ["model", saved.model_id] });
          await queryClient.invalidateQueries({ queryKey: ["companies"] });
        } catch (caught) {
          setActionError(caught instanceof Error ? caught.message : "The assumptions were not saved.");
        }
      },
      calculate: async () => {
        if (!modelId) return;
        setActionError(null);
        try {
          await api(`/models/${modelId}/calculate`, { method: "POST" });
          await queryClient.invalidateQueries({ queryKey: ["model", modelId] });
        } catch (caught) {
          setActionError(caught instanceof Error ? caught.message : "Calculation failed.");
        }
      },
      refresh: async () => {
        await queryClient.invalidateQueries({ queryKey: ["companies"] });
        if (modelId) await queryClient.invalidateQueries({ queryKey: ["model", modelId] });
      },
    };
  }, [companies, company, modelId, payload, result, dashboard, snapshot, companiesQuery.isLoading, companiesQuery.error, modelQuery.isLoading, modelQuery.error, actionError, scale, theme, trace, archive, queryClient]);

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspace(): WorkspaceValue {
  const value = useContext(WorkspaceContext);
  if (!value) throw new Error("Workspace is not available.");
  return value;
}
