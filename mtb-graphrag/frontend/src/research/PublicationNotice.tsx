import { Alert } from '@mui/material';
import type { Dossier } from './DossierView';

export default function PublicationNotice({ dossier }: { dossier: Dossier }) {
  const reconciliation = dossier.publication_integrity?.reconciliation_status;
  const fallbacks = dossier.source_unit_retrieval?.fallbacks ?? [];
  const deferred = (dossier.source_unit_retrieval?.selections ?? []).flatMap(selection => selection.excluded_documents ?? []).filter(document => document.reason_codes?.includes('DOCUMENT_DEFERRED_BY_PLAN'));
  const hasPublication = !!(dossier.publication_status || reconciliation || dossier.technical_run_status || dossier.run_status);
  if (!hasPublication && !fallbacks.length && !deferred.length) return null;
  const complete = dossier.publication_status === 'COMPLETE' && reconciliation === 'PASS' && dossier.technical_run_status === 'COMPLETED';
  return <>{hasPublication && <Alert severity={complete ? 'info' : reconciliation === 'FAIL' ? 'error' : 'warning'} sx={{ mb: 2 }}>
    {complete ? 'Dossier completo' : 'Dossier incompleto'} | Esecuzione: {dossier.technical_run_status ?? dossier.run_status ?? 'UNKNOWN'} | Riconciliazione: {reconciliation ?? 'UNKNOWN'}.
    {!complete && ' I record disponibili sono conservati; il dossier non risulta pubblicabile come completo.'}
    {' Questi stati descrivono esecuzione e pubblicazione, non la validita scientifica delle osservazioni.'}
    {dossier.documentary_projection_migration && ' Vista pubblica aggiornata dalla versione storica: ledger originale conservato e lettura narrativa ricostruita deterministicamente.'}
  </Alert>}
    {!!fallbacks.length && <Alert severity="warning" sx={{ mb: 2 }}>Recupero con limitazioni: in {fallbacks.length} operazioni è stato usato BM25 al posto del recupero neurale previsto. La selezione dei passaggi può cambiare; la copertura delle evidenze non è garantita.{fallbacks.some(item => item.reason?.includes('BUDGET')) ? ' È stato raggiunto un limite di elaborazione.' : ''} Questo limite è distinto dalla completezza della pubblicazione del dossier.</Alert>}
    {!!deferred.length && <Alert severity="warning" sx={{ mb: 2 }}>Documenti non esaminati per il limite di selezione: {deferred.length} operazioni rinviate. Un documento non esaminato non equivale ad assenza di evidenze.</Alert>}
  </>;
}
