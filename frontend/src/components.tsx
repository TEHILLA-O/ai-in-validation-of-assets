import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { NAV } from "./lines";
import { useWorkspace } from "./model";
import { SCALES, chartNumber, formatMoney, formatPercent } from "./format";
import type { Dashboard, YearBundle } from "./types";

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `block px-3 py-2 text-sm ${isActive ? "bg-teal text-white" : "text-paper/80 hover:bg-white/10"}`;

export function Shell({ children }: { children: ReactNode }) {
  const workspace = useWorkspace();
  const scale = SCALES.find((item) => item.id === workspace.scale) ?? SCALES[0];
  return (
    <div className="min-h-screen bg-paper text-ink dark:bg-navy dark:text-paper">
      <div className="grid min-h-screen grid-cols-1 lg:grid-cols-[240px_1fr]">
        <aside className="bg-navy text-paper">
          <div className="border-b border-white/10 px-4 py-5">
            <div className="text-xs uppercase tracking-[0.2em] text-teal">ValuationLab</div>
            <div className="mt-1 text-lg font-medium">DCF workspace</div>
          </div>
          <nav className="py-3">
            {NAV.map(([path, label]) => (
              <NavLink key={path} to={path} end={path === "/"} className={linkClass}>{label}</NavLink>
            ))}
          </nav>
        </aside>
        <div className="min-w-0">
          <header className="flex flex-wrap items-center gap-3 border-b border-line bg-card px-4 py-3 dark:border-white/10 dark:bg-slate-900">
            <select
              className="border border-line bg-white px-2 py-1 text-sm dark:border-white/20 dark:bg-slate-800"
              value={workspace.company?.id ?? ""}
              onChange={(event) => workspace.setCompanyId(event.target.value)}
            >
              {workspace.companies.map((company) => (
                <option key={company.id} value={company.id}>{company.name}</option>
              ))}
            </select>
            <span className="font-mono text-xs">{workspace.company?.currency} · stored in absolute units</span>
            <select
              className="border border-line bg-white px-2 py-1 text-sm dark:border-white/20 dark:bg-slate-800"
              value={workspace.scale}
              onChange={(event) => workspace.setScale(event.target.value as typeof workspace.scale)}
            >
              {SCALES.map((item) => (
                <option key={item.id} value={item.id}>Display {item.label}</option>
              ))}
            </select>
            <button className="border border-line px-2 py-1 text-sm" type="button" onClick={() => workspace.setTheme(workspace.theme === "light" ? "dark" : "light")}>
              {workspace.theme === "light" ? "Dark" : "Light"}
            </button>
            <span className="ml-auto text-xs text-slate-500">Display scale: {scale.label}. It does not change the model.</span>
          </header>
          {workspace.snapshot?.synthetic && (
            <div className="bg-amber-100 px-4 py-2 text-sm text-amber-950">{workspace.snapshot.synthetic_notice}</div>
          )}
          {workspace.archive && (
            <div className="flex items-center justify-between bg-sky-100 px-4 py-2 text-sm text-sky-950">
              <span>Viewing stored valuation run {workspace.archive.runId} from {workspace.archive.calculatedAt}. Inputs are the ones used for that run.</span>
              <button type="button" className="underline" onClick={workspace.clearArchive}>Return to latest</button>
            </div>
          )}
          {workspace.error && <div className="bg-red-100 px-4 py-2 text-sm text-red-900">{workspace.error}</div>}
          <main className="p-4 lg:p-6">{workspace.loading ? <p>Loading the model…</p> : children}</main>
        </div>
      </div>
      {workspace.trace && (
        <aside className="fixed inset-y-0 right-0 z-30 w-full max-w-md overflow-auto border-l border-line bg-card p-5 shadow-xl dark:border-white/10 dark:bg-slate-900">
          <div className="text-xs uppercase tracking-widest text-teal">{workspace.trace.kind}</div>
          <h2 className="mt-1 text-xl font-medium">{workspace.trace.label}</h2>
          <p className="mt-3 font-mono text-sm">{workspace.trace.formula}</p>
          <dl className="mt-4 space-y-2 text-sm">
            {workspace.trace.components.map(([label, amount]) => (
              <div key={label} className="flex justify-between gap-4 border-b border-line py-1">
                <dt>{label}</dt>
                <dd className="font-mono">{amount}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-4 font-mono text-lg">{workspace.trace.result}</p>
          {workspace.trace.note && <p className="mt-3 text-sm text-slate-600 dark:text-slate-300">{workspace.trace.note}</p>}
          <button type="button" className="mt-5 border border-line px-3 py-1 text-sm" onClick={workspace.closeTrace}>Close</button>
        </aside>
      )}
    </div>
  );
}

export function Metric({
  label,
  value,
  traceId,
  percent = false,
}: {
  label: string;
  value: string | null | undefined;
  traceId?: string;
  percent?: boolean;
}) {
  const workspace = useWorkspace();
  const shown = percent ? formatPercent(value) : formatMoney(value, workspace.divisor);
  return (
    <button
      type="button"
      className="border border-line bg-card p-3 text-left dark:border-white/10 dark:bg-slate-900"
      onClick={() => traceId && workspace.openTrace(traceId)}
    >
      <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-1 font-mono text-2xl">{shown}</div>
    </button>
  );
}

const TOTALS = new Set(["gross_profit", "ebitda", "ebit", "ebt", "net_income", "total_assets", "total_liabilities", "total_equity", "total_liabilities_and_equity", "cash_from_operations", "cash_from_investing", "cash_from_financing", "closing_cash"]);

export function StatementGrid({
  years,
  lines,
  section,
}: {
  years: YearBundle[];
  lines: [string, string][];
  section: "income" | "balance" | "cash_flow" | "ratios" | "ufcf" | "working_capital" | "ppe" | "debt" | "revenue_bridge";
}) {
  const workspace = useWorkspace();
  const percent = section === "ratios";
  return (
    <div className="overflow-auto border border-line dark:border-white/10">
      <table className="min-w-full border-separate border-spacing-0 text-sm">
        <thead>
          <tr>
            <th className="sticky left-0 z-10 bg-navy px-3 py-2 text-left text-paper">Line</th>
            {years.map((year) => (
              <th key={year.year} className={`px-3 py-2 text-right ${year.is_forecast ? "bg-teal text-white" : "bg-navy text-paper"}`}>
                {year.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {lines.map(([key, label]) => (
            <tr key={key} className={TOTALS.has(key) ? "font-medium" : undefined}>
              <th className="sticky left-0 bg-card px-3 py-1 text-left font-normal dark:bg-slate-900">{label}</th>
              {years.map((year) => {
                const raw = year[section]?.[key];
                const rateLine = (percent && key !== "interest_coverage") || key.endsWith("_rate") || key.endsWith("_margin");
                const dayLine = key === "dso" || key === "dio" || key === "dpo";
                return (
                  <td key={year.year} className={`px-3 py-1 text-right font-mono ${year.is_forecast ? "bg-teal/10" : "bg-paper dark:bg-slate-950"}`}>
                    {rateLine ? formatPercent(raw) : dayLine ? (raw ?? "—") : formatMoney(raw, workspace.divisor)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function PerformanceCharts({ dashboard }: { dashboard: Dashboard }) {
  const workspace = useWorkspace();
  const scale = SCALES.find((item) => item.id === workspace.scale) ?? SCALES[0];
  const series = dashboard.series.map((row) => ({
    period: row.period,
    revenue: chartNumber(row.revenue, workspace.divisor),
    ebitda: chartNumber(row.ebitda, workspace.divisor),
    margin: row.ebitda_margin == null ? null : Number(row.ebitda_margin) * 100,
    ufcf: chartNumber(row.ufcf, workspace.divisor),
  }));
  const components = [
    { name: "Explicit UFCF", value: chartNumber(dashboard.pv_explicit, workspace.divisor) },
    { name: "Terminal value", value: chartNumber(dashboard.pv_terminal, workspace.divisor) },
  ];
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <ChartCard title={`Revenue and EBITDA (${scale.label})`}>
        <ResponsiveContainer width="100%" height={260}>
          <ComposedChart data={series}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="period" />
            <YAxis />
            <Tooltip />
            <Legend />
            <Bar dataKey="revenue" fill="#0d1b2a" name="Revenue" />
            <Bar dataKey="ebitda" fill="#0f6e6b" name="EBITDA" />
          </ComposedChart>
        </ResponsiveContainer>
      </ChartCard>
      <ChartCard title="EBITDA margin and unlevered free cash flow">
        <ResponsiveContainer width="100%" height={260}>
          <ComposedChart data={series}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="period" />
            <YAxis yAxisId="left" />
            <YAxis yAxisId="right" orientation="right" />
            <Tooltip />
            <Legend />
            <Bar yAxisId="left" dataKey="ufcf" fill="#8d3b32" name={`UFCF (${scale.label})`} />
            <Line yAxisId="right" dataKey="margin" stroke="#0f6e6b" name="EBITDA margin %" dot={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </ChartCard>
      <ChartCard title={`Enterprise value components (${scale.label})`}>
        <ResponsiveContainer width="100%" height={260}>
          <ComposedChart data={components}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="name" />
            <YAxis />
            <Tooltip />
            <Bar dataKey="value" fill="#0f6e6b" name="Present value" />
          </ComposedChart>
        </ResponsiveContainer>
      </ChartCard>
    </div>
  );
}

function ChartCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="border border-line bg-card p-3 dark:border-white/10 dark:bg-slate-900">
      <h3 className="mb-2 text-sm font-medium">{title}</h3>
      {children}
    </section>
  );
}

export function PageTitle({ title, detail }: { title: string; detail?: string }) {
  return (
    <header className="mb-4">
      <h1 className="text-2xl font-medium">{title}</h1>
      {detail && <p className="mt-1 max-w-3xl text-sm text-slate-600 dark:text-slate-300">{detail}</p>}
    </header>
  );
}
