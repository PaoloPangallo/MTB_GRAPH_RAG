import { lazy, Suspense } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import ResearchConsole from './research/ResearchConsole';
import { ARCHITECTURE_ROUTE, VERIFIABLE_PIPELINE_ROUTE, VERIFIABLE_PIPELINE_RUN_ROUTE } from './routes';

const ArchitectureExplorer = lazy(() => import('./architecture/ArchitectureExplorer'));

export default function App() {
  return <Routes>
    <Route path="/" element={<Navigate to={VERIFIABLE_PIPELINE_ROUTE} replace />} />
    <Route path={VERIFIABLE_PIPELINE_ROUTE} element={<ResearchConsole />} />
    <Route path={VERIFIABLE_PIPELINE_RUN_ROUTE} element={<ResearchConsole />} />
    <Route path={ARCHITECTURE_ROUTE} element={<Suspense fallback={<p role="status">Loading architecture explorer…</p>}><ArchitectureExplorer /></Suspense>} />
    <Route path="*" element={<Navigate to={VERIFIABLE_PIPELINE_ROUTE} replace />} />
  </Routes>;
}
