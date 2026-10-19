export type JsonMap = Record<string, string | null>;

export interface YearBundle {
  period_id: string;
  year: number;
  label: string;
  is_forecast: boolean;
  days: number;
  income: JsonMap;
  balance: JsonMap;
  cash_flow: JsonMap;
  working_capital: JsonMap;
  ppe: JsonMap;
  debt: JsonMap;
  revenue_bridge: JsonMap;
  ufcf: JsonMap;
  ratios: JsonMap;
}

export interface Trace {
  id: string;
  label: string;
  period: string | null;
  formula: string;
  components: [string, string][];
  result: string;
  kind: "fact" | "assumption" | "calculation";
  note: string;
}

export interface Check {
  name: string;
  period: string | null;
  expected: string | null;
  actual: string | null;
  difference: string | null;
  status: "pass" | "fail";
  severity: "fail" | "warning" | "info";
  cause: string;
}

export interface Sensitivity {
  name: string;
  row_label: string;
  column_label: string;
  row_keys: string[];
  column_keys: string[];
  values: (string | null)[][];
  statuses: string[][];
  base_row: number | null;
  base_column: number | null;
  note: string;
}

export interface DcfResult {
  convention: string | null;
  terminal_method: string | null;
  wacc: string | null;
  terminal_growth: string | null;
  exit_multiple: string | null;
  discount_factors: Record<string, string>;
  pv_ufcf: Record<string, string | null>;
  pv_explicit: string | null;
  terminal_value: string | null;
  pv_terminal: string | null;
  enterprise_value: string | null;
  terminal_share_of_ev: string | null;
  warnings: string[];
}

export interface EquityResult {
  interest_bearing_debt: string | null;
  debt_like_claims: string | null;
  minority_interest: string | null;
  preferred_securities: string | null;
  excess_cash: string | null;
  operating_cash: string | null;
  non_operating_assets: string | null;
  equity_value: string | null;
  diluted_shares: string | null;
  value_per_share: string | null;
  share_price: string | null;
  upside: string | null;
  notes: string[];
}

export interface WaccView {
  cost_of_equity: string | null;
  pre_tax_cost_of_debt: string | null;
  after_tax_cost_of_debt: string | null;
  equity_weight: string | null;
  debt_weight: string | null;
  wacc: string | null;
  capital_structure_method: string;
  warnings: string[];
}

export interface ModelResult {
  engine_version: string;
  company_name: string;
  currency: string;
  display_scale: string;
  synthetic: boolean;
  synthetic_notice: string;
  scenario_name: string;
  years: YearBundle[];
  wacc: WaccView | null;
  dcf: DcfResult | null;
  equity: EquityResult | null;
  checks: Check[];
  traces: Trace[];
  blocking_errors: string[];
  suggestions: Record<string, string>;
  cost_mode: string;
  cost_precedence_note: string;
  dependency_graph: [string, string[]][];
  scenarios: Record<string, ModelResult>;
  sensitivities: Sensitivity[];
  converged: boolean;
  circularity_notes: string[];
}

export interface Dashboard {
  currency: string;
  display_scale: string;
  scenario: string;
  synthetic: boolean;
  synthetic_notice: string;
  valuation_date: string | null;
  enterprise_value: string | null;
  equity_value: string | null;
  value_per_share: string | null;
  wacc: string | null;
  terminal_growth: string | null;
  terminal_method: string | null;
  discount_convention: string | null;
  projected_revenue_cagr: string | null;
  ebitda_margin: string | null;
  terminal_share: string | null;
  pv_explicit: string | null;
  pv_terminal: string | null;
  share_price: string | null;
  upside: string | null;
  passed_checks: number;
  failed_checks: number;
  series: {
    period: string;
    year: number;
    is_forecast: boolean;
    revenue: string | null;
    ebitda: string | null;
    ebitda_margin: string | null;
    ufcf: string | null;
  }[];
}

export interface Assumptions {
  name: string;
  forecast_years: number[];
  revenue_method: string;
  growth_rates: Record<string, string>;
  cost_mode: string;
  costs: Record<string, { method: string; flat_pct: string | null }>;
  flat_dso: string | null;
  flat_dio: string | null;
  flat_dpo: string | null;
  capex_method: string;
  capex_pct_revenue: string | null;
  tax_rate: string;
  interest_rate: string;
  interest_basis: string;
  interest_income_rate: string;
  minimum_cash: string;
  revolver_enabled: boolean;
  dividend_payout: string;
  wacc: Record<string, string | null> | null;
  valuation: Record<string, string | null> | null;
  notes: string;
  [key: string]: unknown;
}

export interface Snapshot {
  name: string;
  currency: string;
  synthetic: boolean;
  synthetic_notice: string;
  assumptions: Assumptions;
  historical: { year: number; label: string; sources: Record<string, { source?: string }> }[];
}

export interface ModelPayload {
  model_id: string;
  version_number: number;
  engine_version: string;
  snapshot: Snapshot;
  run_id: string | null;
  result: ModelResult | null;
  dashboard: Dashboard | null;
}

export interface CompanyItem {
  id: string;
  name: string;
  currency: string;
  synthetic: boolean;
  synthetic_notice: string;
  model_id: string | null;
  latest_run_id: string | null;
}
