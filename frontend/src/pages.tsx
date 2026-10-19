import { useState } from "react";
import { Link } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { api, clearToken, setToken } from "./api";
import { Metric, PageTitle, PerformanceCharts, StatementGrid } from "./components";
import { formatMoney, formatPercent } from "./format";
import { BALANCE_LINES, CASH_LINES, INCOME_LINES, RATIO_LINES } from "./lines";
import { useWorkspace } from "./model";
import type { Assumptions } from "./types";

const rate = z.string().regex(/^-?\d+(\.\d+)?$/, "Use a decimal such as 0.10, not a percent sign.");

const loginSchema = z.object({
  username: z.string().min(1),
  password: z.string().min(1),
});

export function Login() {
  const form = useForm<z.infer<typeof loginSchema>>({ resolver: zodResolver(loginSchema) });
  const [message, setMessage] = useState<string | null>(null);
  async function onSubmit(values: z.infer<typeof loginSchema>) {
    setMessage(null);
    try {
      const response = await api<{ token: string }>("/auth/login", { method: "POST", body: JSON.stringify(values) });
      setToken(response.token);
      window.location.assign("/");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Login failed");
    }
  }
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center bg-paper px-6">
      <p className="text-xs uppercase tracking-[0.2em] text-teal">ValuationLab</p>
      <h1 className="mt-2 text-3xl font-medium">Sign in</h1>
      <p className="mt-2 text-sm text-slate-600">The documented demo account is demo / demo-valuationlab. It opens the synthetic Northline model.</p>
      <form className="mt-6 space-y-3" onSubmit={form.handleSubmit(onSubmit)}>
        <label className="block text-sm">Username
          <input className="mt-1 w-full border border-line px-2 py-1" {...form.register("username")} />
        </label>
        <label className="block text-sm">Password
          <input type="password" className="mt-1 w-full border border-line px-2 py-1" {...form.register("password")} />
        </label>
        {message && <p className="text-sm text-signal">{message}</p>}
        <button className="bg-navy px-4 py-2 text-paper" type="submit">Enter the model</button>
      </form>
    </main>
  );
}

export function Overview() {
  const { dashboard, result } = useWorkspace();
  if (!dashboard || !result) return <EmptyModel />;
  return (
    <div className="space-y-6">
      <section className="border border-line bg-card p-5 dark:border-white/10 dark:bg-slate-900">
        <div className="text-xs uppercase tracking-[0.18em] text-teal">Enterprise value · {dashboard.scenario} case</div>
        <div className="mt-2">
          <Hero />
        </div>
        <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
          {dashboard.currency}, absolute units stored, shown in the selected display scale.
          Valuation date {dashboard.valuation_date ?? "not set"}.
          Discounting is {dashboard.discount_convention}. Terminal method is {dashboard.terminal_method}.
        </p>
      </section>
      <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-5">
        <Metric label="Equity value" value={dashboard.equity_value} traceId="dcf.equity_value" />
        <Metric label="Value per share" value={dashboard.value_per_share} traceId="dcf.equity_value" />
        <Metric label="WACC" value={dashboard.wacc} traceId="wacc.wacc" percent />
        <Metric label="Terminal growth" value={dashboard.terminal_growth} traceId="dcf.terminal_growth" percent />
        <Metric label="Revenue CAGR" value={dashboard.projected_revenue_cagr} traceId="forecast.revenue_cagr" percent />
        <Metric label="EBITDA margin" value={dashboard.ebitda_margin} traceId="forecast.ebitda_margin" percent />
        <Metric label="Terminal share of EV" value={dashboard.terminal_share} traceId="dcf.terminal_share" percent />
        <Metric label="Explicit forecast value" value={dashboard.pv_explicit} traceId="dcf.enterprise_value" />
        <Metric label="PV of terminal value" value={dashboard.pv_terminal} traceId="dcf.enterprise_value" />
        <Metric label="Upside vs dated price" value={dashboard.upside} traceId="dcf.upside" percent />
      </div>
      <p className="text-sm">
        {dashboard.passed_checks} checks passed, {dashboard.failed_checks} failed.{" "}
        <Link className="text-teal underline" to="/checks">Open the model checks</Link>
      </p>
      <PerformanceCharts dashboard={dashboard} />
      {result.blocking_errors.length > 0 && (
        <section className="border border-signal bg-red-50 p-4 text-sm">
          {result.blocking_errors.map((error) => <p key={error}>{error}</p>)}
        </section>
      )}
    </div>
  );
}

function Hero() {
  const { dashboard, divisor, openTrace } = useWorkspace();
  if (!dashboard) return null;
  return (
    <button type="button" className="text-left" onClick={() => openTrace("dcf.enterprise_value")}>
      <div className="font-mono text-5xl font-medium tracking-tight">{formatMoney(dashboard.enterprise_value, divisor, 2)}</div>
      <div className="mt-1 text-sm text-teal">Inspect the calculation</div>
    </button>
  );
}

export function DcfPage() {
  const { result, divisor } = useWorkspace();
  if (!result?.dcf || !result.equity) return <EmptyModel />;
  const forecast = result.years.filter((year) => year.is_forecast);
  return (
    <div className="space-y-6">
      <PageTitle title="DCF valuation" detail="Unlevered free cash flow is discounted at WACC. Interest is not deducted inside UFCF. The selected terminal method drives enterprise value. The other method is a cross-check." />
      <Hero />
      <StatementGrid years={forecast} lines={[
        ["ebit", "EBIT"],
        ["unlevered_tax", "Unlevered tax"],
        ["nopat", "NOPAT"],
        ["depreciation_amortisation", "Depreciation and amortisation"],
        ["capex", "Capital expenditure"],
        ["disposal_proceeds", "Disposal proceeds"],
        ["change_in_nwc", "Increase in operating NWC"],
        ["other_adjustments", "Other adjustments"],
        ["ufcf", "Unlevered free cash flow"],
      ]} section="ufcf" />
      <div className="overflow-auto border border-line">
        <table className="min-w-full text-sm">
          <thead className="bg-navy text-paper"><tr><th className="px-3 py-2 text-left">Year</th><th className="px-3 py-2">UFCF</th><th className="px-3 py-2">Discount factor</th><th className="px-3 py-2">Present value</th></tr></thead>
          <tbody>
            {forecast.map((year) => (
              <tr key={year.year} className="border-t border-line">
                <td className="px-3 py-1">{year.label}</td>
                <td className="px-3 py-1 text-right font-mono">{formatMoney(year.ufcf.ufcf, divisor)}</td>
                <td className="px-3 py-1 text-right font-mono">{result.dcf?.discount_factors?.[year.period_id] ?? "—"}</td>
                <td className="px-3 py-1 text-right font-mono">{formatMoney(result.dcf?.pv_ufcf?.[year.period_id], divisor)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Bridge />
      <section>
        <h2 className="mb-2 text-lg">Dependency order</h2>
        <ol className="list-decimal space-y-1 pl-5 text-sm">
          {result.dependency_graph.map(([node]) => <li key={node}>{node}</li>)}
        </ol>
      </section>
    </div>
  );
}

function Bridge() {
  const { result, divisor } = useWorkspace();
  if (!result?.equity || !result.dcf) return null;
  const rows: [string, string | null | undefined][] = [
    ["Enterprise value", result.dcf.enterprise_value],
    ["Interest-bearing debt", result.equity.interest_bearing_debt],
    ["Debt-like claims", result.equity.debt_like_claims],
    ["Minority interest", result.equity.minority_interest],
    ["Preferred securities", result.equity.preferred_securities],
    ["Excess cash", result.equity.excess_cash],
    ["Operating cash retained", result.equity.operating_cash],
    ["Non-operating assets", result.equity.non_operating_assets],
    ["Equity value", result.equity.equity_value],
    ["Diluted shares", result.equity.diluted_shares],
    ["Value per share", result.equity.value_per_share],
    ["Dated share price", result.equity.share_price],
    ["Upside", result.equity.upside],
  ];
  return (
    <section>
      <h2 className="mb-2 text-lg">Enterprise value to equity value</h2>
      <p className="mb-2 text-sm text-slate-600">The bridge uses the last historical balance sheet. Forecast cash is not added again.</p>
      <table className="text-sm">
        <tbody>
          {rows.map(([label, value]) => (
            <tr key={label} className="border-t border-line">
              <td className="py-1 pr-8">{label}</td>
              <td className="py-1 text-right font-mono">{label === "Upside" ? formatPercent(value) : label === "Diluted shares" ? value ?? "—" : formatMoney(value, divisor)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <ul className="mt-3 list-disc pl-5 text-sm">{result.dcf.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
    </section>
  );
}

export function StatementPage({ kind }: { kind: "income" | "balance" | "cash" }) {
  const { result } = useWorkspace();
  if (!result) return <EmptyModel />;
  const lines = kind === "income" ? INCOME_LINES : kind === "balance" ? BALANCE_LINES : CASH_LINES;
  const section = kind === "cash" ? "cash_flow" : kind;
  const title = kind === "income" ? "Income statement" : kind === "balance" ? "Balance sheet" : "Cash flow statement";
  return (
    <div className="space-y-4">
      <PageTitle title={title} detail="Historical years are labelled with an A. Forecast years are labelled with an E and are shaded. Totals come from the calculation engine." />
      <StatementGrid years={result.years} lines={lines} section={section} />
      {kind === "income" && <StatementGrid years={result.years} lines={RATIO_LINES} section="ratios" />}
      {kind === "income" && <HistoricalEntry />}
    </div>
  );
}

export function RevenuePage() {
  const { result, snapshot, archive, saveAssumptions } = useWorkspace();
  if (!result || !snapshot) return <EmptyModel />;
  return (
    <div className="space-y-4">
      <PageTitle title="Revenue forecast" detail={`Active method: ${snapshot.assumptions.revenue_method}. Growth-rate forecasts use revenue in the prior year times one plus the rate for that year.`} />
      <StatementGrid years={result.years} lines={[["revenue", "Revenue"], ["prior_revenue", "Prior revenue"], ["growth_rate", "Growth rate"], ["volume_contribution", "Volume contribution"], ["price_contribution", "Price contribution"]]} section="revenue_bridge" />
      <GrowthForm disabled={Boolean(archive)} assumptions={snapshot.assumptions} onSave={saveAssumptions} />
    </div>
  );
}

export function CostPage() {
  const { result, snapshot, archive, saveAssumptions } = useWorkspace();
  if (!result || !snapshot) return <EmptyModel />;
  return (
    <div className="space-y-4">
      <PageTitle title="Operating costs" detail={result.cost_precedence_note} />
      <StatementGrid years={result.years} lines={INCOME_LINES.filter(([key]) => ["revenue", "cogs", "gross_profit", "personnel", "rd", "sales_marketing", "ga", "other_opex", "ebitda"].includes(key))} section="income" />
      <CostForm disabled={Boolean(archive)} assumptions={snapshot.assumptions} onSave={saveAssumptions} />
    </div>
  );
}

export function SchedulePage() {
  const { result, snapshot, archive, saveAssumptions } = useWorkspace();
  if (!result || !snapshot) return <EmptyModel />;
  return (
    <div className="space-y-4">
      <PageTitle title="Supporting schedules" detail="Working-capital balances in the forecast are period-end balances: revenue or COGS times days divided by the days in the year. Capex and debt flow into the cash flow statement and the balance sheet." />
      <h2 className="text-lg">Working capital</h2>
      <StatementGrid years={result.years} lines={[["accounts_receivable", "Accounts receivable"], ["inventory", "Inventory"], ["accounts_payable", "Accounts payable"], ["operating_nwc", "Operating NWC"], ["change_in_nwc", "Increase in NWC"], ["dso", "DSO"], ["dio", "DIO"], ["dpo", "DPO"]]} section="working_capital" />
      <h2 className="text-lg">PP&E</h2>
      <StatementGrid years={result.years} lines={[["opening", "Opening"], ["capex", "Capex"], ["depreciation", "Depreciation"], ["disposals_nbv", "Disposals"], ["impairment", "Impairment"], ["closing", "Closing"]]} section="ppe" />
      <h2 className="text-lg">Debt</h2>
      <StatementGrid years={result.years} lines={[["opening_short_term", "Opening current debt"], ["opening_long_term", "Opening long-term debt"], ["borrowings", "Borrowings"], ["repayments", "Repayments"], ["revolver_flow", "Revolver flow"], ["closing_debt", "Closing debt"], ["interest_expense", "Interest expense"], ["interest_income", "Interest income"]]} section="debt" />
      <ScheduleForm disabled={Boolean(archive)} assumptions={snapshot.assumptions} onSave={saveAssumptions} />
    </div>
  );
}

export function WaccPage() {
  const { result, snapshot, archive, saveAssumptions } = useWorkspace();
  if (!result?.wacc || !snapshot || !snapshot.assumptions.wacc) return <EmptyModel />;
  const rows = [
    ["Cost of equity", result.wacc.cost_of_equity],
    ["Pre-tax cost of debt", result.wacc.pre_tax_cost_of_debt],
    ["After-tax cost of debt", result.wacc.after_tax_cost_of_debt],
    ["Equity weight", result.wacc.equity_weight],
    ["Debt weight", result.wacc.debt_weight],
    ["WACC", result.wacc.wacc],
  ];
  return (
    <div className="space-y-4">
      <PageTitle title="WACC" detail={`Capital structure method: ${result.wacc.capital_structure_method}. Book equity is not treated as market equity. These inputs are manual and are not a live market feed.`} />
      <table className="text-sm">
        <tbody>
          {rows.map(([label, value]) => (
            <tr key={String(label)} className="border-t border-line">
              <td className="py-1 pr-8">{label}</td>
              <td className="py-1 text-right font-mono">{formatPercent(value == null ? null : String(value))}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <WaccForm disabled={Boolean(archive)} assumptions={snapshot.assumptions} onSave={saveAssumptions} />
    </div>
  );
}

export function ScenarioPage() {
  const { result, snapshot, divisor, archive } = useWorkspace();
  if (!result || !snapshot) return <EmptyModel />;
  const cases = [{ name: result.scenario_name, result }, ...Object.entries(result.scenarios).map(([caseName, caseResult]) => ({ name: caseName, result: caseResult }))];
  return (
    <div className="space-y-4">
      <PageTitle title="Scenarios" detail="Each case recalculates the statements from its own assumptions. Enterprise value is not scaled by a fixed percentage." />
      <div className="grid gap-3 md:grid-cols-3">
        {cases.map((item) => (
          <article key={item.name} className="border border-line bg-card p-3 dark:border-white/10 dark:bg-slate-900">
            <h2 className="text-lg">{item.name}</h2>
            <p className="mt-2 font-mono text-2xl">{formatMoney(item.result.dcf?.enterprise_value, divisor)}</p>
            <p className="text-sm">Equity {formatMoney(item.result.equity?.equity_value, divisor)}</p>
            <p className="text-sm">Per share {formatMoney(item.result.equity?.value_per_share, divisor)}</p>
          </article>
        ))}
      </div>
      <section className="max-w-lg border border-line p-4">
        <p className="mb-3 text-sm">Custom case: copy the base assumptions and replace every forecast growth rate with one rate. WACC and the terminal assumption stay as they are on the base case.</p>
        <CustomScenario disabled={Boolean(archive)} />
      </section>
    </div>
  );
}

function CustomScenario({ disabled }: { disabled: boolean }) {
  const { snapshot, modelId, refresh, adoptModel } = useWorkspace();
  const [name, setName] = useState("Custom");
  const [growth, setGrowth] = useState("0.12");
  const [message, setMessage] = useState<string | null>(null);
  if (!snapshot || !modelId) return null;
  return (
    <form className="max-w-lg space-y-3" onSubmit={async (event) => {
      event.preventDefault();
      const parsed = z.object({ name: z.string().min(1), growth: rate }).safeParse({ name, growth });
      if (!parsed.success) {
        setMessage(parsed.error.issues[0]?.message ?? "Check the inputs.");
        return;
      }
      const assumptions = structuredClone(snapshot.assumptions) as Assumptions;
      assumptions.name = parsed.data.name;
      for (const year of assumptions.forecast_years) assumptions.growth_rates[String(year)] = parsed.data.growth;
      const saved = await api<{ model_id: string }>(`/models/${modelId}/scenarios`, {
        method: "POST",
        body: JSON.stringify({ name: parsed.data.name, assumptions }),
      });
      await api(`/models/${saved.model_id}/calculate`, { method: "POST" });
      adoptModel(saved.model_id);
      setMessage(`Saved ${parsed.data.name} and recalculated.`);
      await refresh();
    }}>
      <label className="block text-sm">Scenario name
        <input disabled={disabled} className="mt-1 w-full border border-input bg-input px-2 py-1 font-mono text-blue-800" value={name} onChange={(event) => setName(event.target.value)} />
      </label>
      <label className="block text-sm">Growth rate applied to every forecast year
        <input disabled={disabled} className="mt-1 w-full border border-input bg-input px-2 py-1 font-mono text-blue-800" value={growth} onChange={(event) => setGrowth(event.target.value)} />
      </label>
      {message && <p className="text-sm">{message}</p>}
      <button disabled={disabled} className="bg-navy px-3 py-2 text-sm text-paper" type="submit">Save scenario and recalculate</button>
    </form>
  );
}

export function SensitivityPage() {
  const { result, divisor } = useWorkspace();
  if (!result) return <EmptyModel />;
  return (
    <div className="space-y-6">
      <PageTitle title="Sensitivity analysis" detail="Each cell is a recalculated enterprise value. Invalid combinations are marked and are not approximated." />
      {result.sensitivities.map((table) => (
        <section key={table.name}>
          <h2 className="text-lg">{table.name}</h2>
          <p className="mb-2 text-sm text-slate-600">{table.note}</p>
          <div className="overflow-auto border border-line">
            <table className="text-sm">
              <thead>
                <tr>
                  <th className="bg-navy px-2 py-1 text-left text-paper">{table.row_label} \ {table.column_label}</th>
                  {table.column_keys.map((column) => <th key={column} className="bg-navy px-2 py-1 text-paper">{formatPercent(column, 1)}</th>)}
                </tr>
              </thead>
              <tbody>
                {table.row_keys.map((row, rowIndex) => (
                  <tr key={row}>
                    <th className="bg-card px-2 py-1 text-left">{formatPercent(row, 1)}</th>
                    {table.values[rowIndex].map((value, columnIndex) => {
                      const base = rowIndex === table.base_row && columnIndex === table.base_column;
                      const invalid = table.statuses[rowIndex][columnIndex] !== "ok";
                      return (
                        <td key={`${row}-${columnIndex}`} className={`px-2 py-1 text-right font-mono ${base ? "bg-teal/30" : ""} ${invalid ? "text-signal" : ""}`}>
                          {invalid || value == null ? "n/m" : formatMoney(value, divisor, 0)}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}
    </div>
  );
}

export function ChecksPage() {
  const { result } = useWorkspace();
  if (!result) return <EmptyModel />;
  return (
    <div className="space-y-3">
      <PageTitle title="Model checks" detail={`${result.checks.filter((check) => check.status === "pass").length} passed, ${result.checks.filter((check) => check.status === "fail").length} failed. Differences within the configured tolerance can pass. Nothing is overwritten to force a pass.`} />
      {result.circularity_notes.map((note) => <p key={note} className="text-sm">{note}</p>)}
      <div className="overflow-auto border border-line">
        <table className="min-w-full text-sm">
          <thead className="bg-navy text-left text-paper">
            <tr>
              {["Check", "Period", "Expected", "Actual", "Difference", "Status", "Severity", "Cause"].map((heading) => <th key={heading} className="px-2 py-1">{heading}</th>)}
            </tr>
          </thead>
          <tbody>
            {result.checks.map((check, index) => (
              <tr key={`${check.name}-${check.period}-${index}`} className={check.status === "fail" ? "bg-red-50" : undefined}>
                <td className="px-2 py-1">{check.name}</td>
                <td className="px-2 py-1">{check.period ?? ""}</td>
                <td className="px-2 py-1 font-mono">{check.expected}</td>
                <td className="px-2 py-1 font-mono">{check.actual}</td>
                <td className="px-2 py-1 font-mono">{check.difference}</td>
                <td className="px-2 py-1">{check.status}</td>
                <td className="px-2 py-1">{check.severity}</td>
                <td className="px-2 py-1">{check.cause}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function AnalystPage() {
  const { modelId } = useWorkspace();
  const [topic, setTopic] = useState("enterprise_value");
  const [question, setQuestion] = useState("Why does the terminal value contribute what it does?");
  const [consent, setConsent] = useState(false);
  const [answer, setAnswer] = useState<null | {
    facts: string[];
    assumptions: string[];
    interpretation: string[];
    questions_for_the_analyst: string[];
    external_interpretation: string | null;
    external_model_used: boolean;
  }>(null);
  const [error, setError] = useState<string | null>(null);
  if (!modelId) return <EmptyModel />;
  return (
    <div className="space-y-4">
      <PageTitle title="AI analyst" detail="The explainer quotes the calculated model. It cannot change assumptions. An external language model is used only when an API key is configured and you consent. Raw uploaded filings are not sent." />
      <form className="space-y-3" onSubmit={async (event) => {
        event.preventDefault();
        setError(null);
        try {
          const response = await api<NonNullable<typeof answer>>(`/models/${modelId}/analyse`, {
            method: "POST",
            body: JSON.stringify({ topic, question, consent_to_send: consent }),
          });
          setAnswer(response);
        } catch (caught) {
          setError(caught instanceof Error ? caught.message : "The analyst request failed.");
        }
      }}>
        <select className="border border-line px-2 py-1" value={topic} onChange={(event) => setTopic(event.target.value)}>
          {["enterprise_value", "wacc", "margins", "history", "scenarios", "inconsistencies", "ratios", "plausibility", "filings", "questions"].map((item) => <option key={item} value={item}>{item}</option>)}
        </select>
        <textarea className="block w-full border border-line p-2" rows={3} value={question} onChange={(event) => setQuestion(event.target.value)} />
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} />
          I consent to send the prepared numerical brief, not source files, to the configured external model.
        </label>
        <button className="bg-navy px-3 py-2 text-sm text-paper" type="submit">Explain</button>
      </form>
      {error && <p className="text-sm text-signal">{error}</p>}
      {answer && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Brief title="Facts" items={answer.facts} />
          <Brief title="Assumptions" items={answer.assumptions} />
          <Brief title="Interpretation" items={answer.interpretation} />
          <Brief title="Questions for the analyst" items={answer.questions_for_the_analyst} />
          {answer.external_model_used && answer.external_interpretation && (
            <section className="border border-line p-3 lg:col-span-2">
              <h2 className="text-sm uppercase tracking-wide text-teal">External interpretation</h2>
              <p className="mt-2 whitespace-pre-wrap text-sm">{answer.external_interpretation}</p>
            </section>
          )}
        </div>
      )}
    </div>
  );
}

function Brief({ title, items }: { title: string; items: string[] }) {
  return (
    <section className="border border-line bg-card p-3 dark:border-white/10 dark:bg-slate-900">
      <h2 className="text-sm uppercase tracking-wide text-teal">{title}</h2>
      <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">{items.map((item) => <li key={item}>{item}</li>)}</ul>
    </section>
  );
}

export function ReportsPage() {
  const { modelId, company, refresh } = useWorkspace();
  const [runs, setRuns] = useState<{ run_id: string; created_at: string; enterprise_value: string | null; engine_version: string }[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const { viewRun } = useWorkspace();
  if (!modelId || !company) return <EmptyModel />;
  return (
    <div className="space-y-4">
      <PageTitle title="Reports and exports" detail="The workbook contains Excel formulas for the base-case statements, WACC, DCF and the WACC versus growth grid. Open it in Excel and calculate the workbook. Operating sensitivity grids inside the file are values produced by the engine and are labelled as such." />
      <button className="bg-teal px-3 py-2 text-sm text-white" type="button" onClick={async () => {
        const blob = await api<Blob>(`/models/${modelId}/export/excel`, { method: "POST" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `${company.name.replace(/\s+/g, "_")}_valuation.xlsx`;
        link.click();
        URL.revokeObjectURL(url);
      }}>Download Excel model</button>
      <form className="space-y-2" onSubmit={async (event) => {
        event.preventDefault();
        const data = new FormData(event.currentTarget);
        data.set("company_id", company.id);
        try {
          await api(`/financials/import`, { method: "POST", body: data });
          setMessage("Import stored. Review model checks after calculating. Blank cells were not turned into zeros.");
          await refresh();
        } catch (error) {
          setMessage(error instanceof Error ? error.message : "Import failed");
        }
      }}>
        <h2 className="text-lg">Import historical CSV or Excel</h2>
        <input name="file" type="file" accept=".csv,.xlsx,.xlsm,.pdf" />
        <button className="ml-2 border border-line px-3 py-1 text-sm" type="submit">Upload</button>
        {message && <p className="text-sm">{message}</p>}
      </form>
      <button className="text-sm underline" type="button" onClick={async () => {
        const response = await api<{ items: typeof runs }>(`/models/${modelId}/runs`);
        setRuns(response.items);
      }}>Load valuation history</button>
      <ul className="space-y-2 text-sm">
        {runs.map((run) => (
          <li key={run.run_id}>
            <button type="button" className="underline" onClick={() => viewRun(run.run_id)}>
              {run.created_at} · engine {run.engine_version} · EV {run.enterprise_value ?? "not calculated"}
            </button>
          </li>
        ))}
      </ul>
      <button className="text-sm underline" type="button" onClick={() => { clearToken(); window.location.assign("/login"); }}>Sign out</button>
    </div>
  );
}

function EmptyModel() {
  const { calculate } = useWorkspace();
  return (
    <div className="space-y-3">
      <p>This model version does not have a calculated valuation yet.</p>
      <button className="bg-navy px-3 py-2 text-sm text-paper" type="button" onClick={() => calculate()}>Calculate</button>
    </div>
  );
}

function fieldClass() {
  return "mt-1 w-full border border-blue-200 bg-input px-2 py-1 font-mono text-blue-800";
}

function GrowthForm({
  assumptions,
  disabled,
  onSave,
}: {
  assumptions: Assumptions;
  disabled: boolean;
  onSave: (mutate: (assumptions: Assumptions) => void, note: string) => Promise<void>;
}) {
  const years = assumptions.forecast_years.map(String);
  const shape: Record<string, z.ZodString> = {};
  const defaults: Record<string, string> = {};
  for (const year of years) {
    shape[year] = rate;
    defaults[year] = assumptions.growth_rates[year] ?? "";
  }
  const schema = z.object(shape);
  const form = useForm<Record<string, string>>({ resolver: zodResolver(schema), values: defaults });
  return (
    <form className="grid max-w-xl gap-3" onSubmit={form.handleSubmit(async (values) => {
      await onSave((next) => {
        for (const year of years) next.growth_rates[year] = values[year];
      }, "Updated revenue growth rates");
    })}>
      {years.map((year) => (
        <label key={year} className="text-sm">Growth {year}
          <input className={fieldClass()} {...form.register(year)} />
        </label>
      ))}
      <p className="text-xs text-signal">{Object.values(form.formState.errors)[0]?.message}</p>
      <button disabled={disabled} className="bg-navy px-3 py-2 text-sm text-paper" type="submit">Save growth and recalculate</button>
    </form>
  );
}

function CostForm({ assumptions, disabled, onSave }: { assumptions: Assumptions; disabled: boolean; onSave: (mutate: (assumptions: Assumptions) => void, note: string) => Promise<void> }) {
  const keys = ["cogs", "personnel", "rd", "sales_marketing", "ga", "other_opex"] as const;
  const defaults = Object.fromEntries(keys.map((key) => [key, assumptions.costs[key]?.flat_pct ?? "0"]));
  const schema = z.object({
    cogs: rate,
    personnel: rate,
    rd: rate,
    sales_marketing: rate,
    ga: rate,
    other_opex: rate,
  });
  const form = useForm<Record<string, string>>({ resolver: zodResolver(schema), values: defaults });
  return (
    <form className="grid max-w-xl gap-3" onSubmit={form.handleSubmit(async (values) => {
      await onSave((next) => {
        next.cost_mode = "line_item";
        for (const key of keys) {
          next.costs[key] = { ...(next.costs[key] ?? { method: "pct_revenue", flat_pct: "0" }), method: "pct_revenue", flat_pct: values[key] };
        }
      }, "Updated percentage-of-revenue costs");
    })}>
      {keys.map((key) => (
        <label key={key} className="text-sm">{key} as a share of revenue
          <input className={fieldClass()} {...form.register(key)} />
        </label>
      ))}
      <button disabled={disabled} className="bg-navy px-3 py-2 text-sm text-paper" type="submit">Save costs and recalculate</button>
    </form>
  );
}

function ScheduleForm({ assumptions, disabled, onSave }: { assumptions: Assumptions; disabled: boolean; onSave: (mutate: (assumptions: Assumptions) => void, note: string) => Promise<void> }) {
  const schema = z.object({
    flat_dso: rate, flat_dio: rate, flat_dpo: rate, capex_pct_revenue: rate, tax_rate: rate,
    interest_rate: rate, interest_income_rate: rate, minimum_cash: rate, dividend_payout: rate,
    interest_basis: z.enum(["opening", "average", "closing"]),
  });
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    values: {
      flat_dso: assumptions.flat_dso ?? "0",
      flat_dio: assumptions.flat_dio ?? "0",
      flat_dpo: assumptions.flat_dpo ?? "0",
      capex_pct_revenue: assumptions.capex_pct_revenue ?? "0",
      tax_rate: assumptions.tax_rate,
      interest_rate: assumptions.interest_rate,
      interest_income_rate: assumptions.interest_income_rate,
      minimum_cash: assumptions.minimum_cash,
      dividend_payout: assumptions.dividend_payout,
      interest_basis: (assumptions.interest_basis as "opening" | "average" | "closing") ?? "opening",
    },
  });
  return (
    <form className="grid max-w-xl gap-3 md:grid-cols-2" onSubmit={form.handleSubmit(async (values) => {
      await onSave((next) => {
        Object.assign(next, values);
        next.capex_method = "pct_revenue";
      }, "Updated schedule assumptions");
    })}>
      {(["flat_dso", "flat_dio", "flat_dpo", "capex_pct_revenue", "tax_rate", "interest_rate", "interest_income_rate", "minimum_cash", "dividend_payout"] as const).map((key) => (
        <label key={key} className="text-sm">{key.replaceAll("_", " ")}
          <input className={fieldClass()} {...form.register(key)} />
        </label>
      ))}
      <label className="text-sm">Interest basis
        <select className={fieldClass()} {...form.register("interest_basis")}>
          <option value="opening">opening</option>
          <option value="average">average</option>
          <option value="closing">closing</option>
        </select>
      </label>
      <button disabled={disabled} className="bg-navy px-3 py-2 text-sm text-paper" type="submit">Save schedules and recalculate</button>
    </form>
  );
}

function WaccForm({ assumptions, disabled, onSave }: { assumptions: Assumptions; disabled: boolean; onSave: (mutate: (assumptions: Assumptions) => void, note: string) => Promise<void> }) {
  const wacc = assumptions.wacc;
  const valuation = assumptions.valuation;
  if (!wacc || !valuation) return <p>WACC inputs are not on this model.</p>;
  const schema = z.object({
    risk_free_rate: rate,
    beta: rate,
    equity_risk_premium: rate,
    pre_tax_cost_of_debt: rate,
    marginal_tax_rate: rate,
    market_value_equity: rate,
    market_value_debt: rate,
    terminal_growth: rate,
    exit_ebitda_multiple: rate,
    diluted_shares: rate,
    terminal_method: z.enum(["gordon", "exit_multiple"]),
    discount_convention: z.enum(["end", "mid"]),
  });
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    values: {
      risk_free_rate: String(wacc.risk_free_rate ?? ""),
      beta: String(wacc.beta ?? ""),
      equity_risk_premium: String(wacc.equity_risk_premium ?? ""),
      pre_tax_cost_of_debt: String(wacc.pre_tax_cost_of_debt ?? ""),
      marginal_tax_rate: String(wacc.marginal_tax_rate ?? ""),
      market_value_equity: String(wacc.market_value_equity ?? ""),
      market_value_debt: String(wacc.market_value_debt ?? ""),
      terminal_growth: String(valuation.terminal_growth ?? ""),
      exit_ebitda_multiple: String(valuation.exit_ebitda_multiple ?? ""),
      diluted_shares: String(valuation.diluted_shares ?? ""),
      terminal_method: (valuation.terminal_method as "gordon" | "exit_multiple") ?? "gordon",
      discount_convention: (valuation.discount_convention as "end" | "mid") ?? "end",
    },
  });
  return (
    <form className="grid max-w-3xl gap-3 md:grid-cols-2" onSubmit={form.handleSubmit(async (values) => {
      await onSave((next) => {
        if (!next.wacc || !next.valuation) return;
        next.wacc.risk_free_rate = values.risk_free_rate;
        next.wacc.beta = values.beta;
        next.wacc.equity_risk_premium = values.equity_risk_premium;
        next.wacc.pre_tax_cost_of_debt = values.pre_tax_cost_of_debt;
        next.wacc.marginal_tax_rate = values.marginal_tax_rate;
        next.wacc.market_value_equity = values.market_value_equity;
        next.wacc.market_value_debt = values.market_value_debt;
        next.valuation.terminal_growth = values.terminal_growth;
        next.valuation.exit_ebitda_multiple = values.exit_ebitda_multiple;
        next.valuation.diluted_shares = values.diluted_shares;
        next.valuation.terminal_method = values.terminal_method;
        next.valuation.discount_convention = values.discount_convention;
      }, "Updated WACC and terminal assumptions");
    })}>
      {(["risk_free_rate", "beta", "equity_risk_premium", "pre_tax_cost_of_debt", "marginal_tax_rate", "market_value_equity", "market_value_debt", "terminal_growth", "exit_ebitda_multiple", "diluted_shares"] as const).map((key) => (
        <label key={key} className="text-sm">{key.replaceAll("_", " ")}
          <input className={fieldClass()} {...form.register(key)} />
        </label>
      ))}
      <label className="text-sm">Terminal method
        <select className={fieldClass()} {...form.register("terminal_method")}>
          <option value="gordon">gordon</option>
          <option value="exit_multiple">exit multiple</option>
        </select>
      </label>
      <label className="text-sm">Discount convention
        <select className={fieldClass()} {...form.register("discount_convention")}>
          <option value="end">end of year</option>
          <option value="mid">mid year</option>
        </select>
      </label>
      <p className="text-xs text-slate-500 md:col-span-2">Blue figures are inputs. Saving recalculates the full model. The workbook export remains an end-of-year formula model even if you select mid-year here.</p>
      <button disabled={disabled} className="bg-navy px-3 py-2 text-sm text-paper" type="submit">Save WACC and recalculate</button>
    </form>
  );
}

function HistoricalEntry() {
  const { company, refresh, adoptModel } = useWorkspace();
  const [message, setMessage] = useState<string | null>(null);
  const schema = z.object({
    year: z.coerce.number().int(),
    statement: z.enum(["income", "balance", "cash_flow"]),
    key: z.string().min(1),
    value: z.string(),
    source: z.string().min(3, "Record where the figure came from."),
  }).refine((value) => value.value === "" || /^-?\d+(\.\d+)?$/.test(value.value), { message: "Leave the amount blank or enter a number in absolute units." });
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { year: 2024, statement: "income", key: "revenue", value: "", source: "" },
  });
  if (!company) return null;
  const statement = form.watch("statement");
  const choices = statement === "income" ? INCOME_LINES : statement === "balance" ? BALANCE_LINES : CASH_LINES;
  return (
    <form className="grid max-w-3xl gap-3 border border-line p-4 md:grid-cols-2" onSubmit={form.handleSubmit(async (values) => {
      try {
        const saved = await api<{ model_id: string }>(`/financials/${company.id}`, {
          method: "PUT",
          body: JSON.stringify({
            lines: [{
              year: values.year,
              statement: values.statement,
              key: values.key,
              value: values.value === "" ? null : values.value,
              source: values.source,
            }],
          }),
        });
        await api(`/models/${saved.model_id}/calculate`, { method: "POST" });
        adoptModel(saved.model_id);
        setMessage("Stored as a new model version and recalculated. A blank amount is missing, not zero.");
        await refresh();
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "The line was not saved.");
      }
    })}>
      <h2 className="md:col-span-2 text-lg">Enter or correct a historical figure</h2>
      <label className="text-sm">Year<input className={fieldClass()} type="number" {...form.register("year")} /></label>
      <label className="text-sm">Statement
        <select className={fieldClass()} {...form.register("statement")}>
          <option value="income">income</option>
          <option value="balance">balance</option>
          <option value="cash_flow">cash flow</option>
        </select>
      </label>
      <label className="text-sm">Line
        <select className={fieldClass()} {...form.register("key")}>
          {choices.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
        </select>
      </label>
      <label className="text-sm">Amount in absolute currency units
        <input className={fieldClass()} {...form.register("value")} />
      </label>
      <label className="text-sm md:col-span-2">Source
        <input className={fieldClass()} {...form.register("source")} />
      </label>
      <p className="text-sm text-signal md:col-span-2">{form.formState.errors.source?.message || form.formState.errors.value?.message || message}</p>
      <button className="bg-navy px-3 py-2 text-sm text-paper" type="submit">Save historical line</button>
    </form>
  );
}
