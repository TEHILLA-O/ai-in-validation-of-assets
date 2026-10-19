import { Navigate, Route, Routes } from "react-router-dom";
import { getToken } from "./api";
import { Shell } from "./components";
import { WorkspaceProvider } from "./model";
import {
  AnalystPage,
  ChecksPage,
  CostPage,
  DcfPage,
  Login,
  Overview,
  ReportsPage,
  RevenuePage,
  ScenarioPage,
  SchedulePage,
  SensitivityPage,
  StatementPage,
  WaccPage,
} from "./pages";

function Private() {
  if (!getToken()) return <Navigate to="/login" replace />;
  return (
    <WorkspaceProvider>
      <Shell>
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/dcf" element={<DcfPage />} />
          <Route path="/income" element={<StatementPage kind="income" />} />
          <Route path="/balance" element={<StatementPage kind="balance" />} />
          <Route path="/cash-flow" element={<StatementPage kind="cash" />} />
          <Route path="/revenue" element={<RevenuePage />} />
          <Route path="/costs" element={<CostPage />} />
          <Route path="/schedules" element={<SchedulePage />} />
          <Route path="/wacc" element={<WaccPage />} />
          <Route path="/scenarios" element={<ScenarioPage />} />
          <Route path="/sensitivity" element={<SensitivityPage />} />
          <Route path="/checks" element={<ChecksPage />} />
          <Route path="/analyst" element={<AnalystPage />} />
          <Route path="/reports" element={<ReportsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Shell>
    </WorkspaceProvider>
  );
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/*" element={<Private />} />
    </Routes>
  );
}
