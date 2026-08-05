/**
 * Composizione delle rotte.
 *
 * La pipeline verificabile è la rotta principale e la radice vi reindirizza.
 * Prima le due viste convivevano dietro un `useState` nella stessa pagina, con
 * la vista storica come schermata iniziale: uno screenshot della home mostrava
 * `qualified_claim_repository/1.4` e i Qualified Claim della V3 precedente, e
 * nulla nell'interfaccia diceva che non fosse la pipeline nuova.
 *
 * Separarle in rotte distinte rende quella confusione impossibile da fare per
 * distrazione, e dà alla run un URL proprio — quindi un refresh che non perde
 * la trace.
 */

import { Navigate, Route, Routes } from 'react-router-dom';
import LegacyV3Console from './legacy/LegacyV3Console';
import ResearchConsole from './research/ResearchConsole';
import { LEGACY_V3_ROUTE, VERIFIABLE_PIPELINE_ROUTE, VERIFIABLE_PIPELINE_RUN_ROUTE } from './routes';

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to={VERIFIABLE_PIPELINE_ROUTE} replace />} />
      <Route path={VERIFIABLE_PIPELINE_ROUTE} element={<ResearchConsole />} />
      <Route path={VERIFIABLE_PIPELINE_RUN_ROUTE} element={<ResearchConsole />} />
      <Route path={LEGACY_V3_ROUTE} element={<LegacyV3Console />} />
      <Route path="*" element={<Navigate to={VERIFIABLE_PIPELINE_ROUTE} replace />} />
    </Routes>
  );
}
