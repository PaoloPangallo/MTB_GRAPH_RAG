import { describe, expect, it } from 'vitest';
import { architectureEdges, demoScenarios } from './model';

const scenario = (id: string) => demoScenarios.find((item) => item.id === id)!;

describe('architecture model reflects verification-family boundaries', () => {
  it('routes EVIDENCE_STATEMENT from quote authentication to its deterministic policy', () => {
    expect(architectureEdges.some((edge) => edge.id === 'quote-statement' && edge.from === 'quote' && edge.to === 'statement')).toBe(true);
    expect(scenario('retrieval').events.some((event) => event.nodeId === 'structural')).toBe(false);
  });

  it('routes drug mismatches to record disposition and never to semantic alignment', () => {
    const rejection = scenario('structural-rejection');
    expect(architectureEdges.some((edge) => edge.id === 'structural-blocked' && edge.to === 'disposition')).toBe(true);
    expect(rejection.events.find((event) => event.nodeId === 'disposition')?.edgeId).toBe('structural-blocked');
    expect(rejection.events.some((event) => event.nodeId === 'semantic')).toBe(false);
  });

  it('keeps TRIAL and KG_ONLY on distinct routes without semantic efficacy claims', () => {
    const trial = scenario('families-trial');
    const kg = scenario('families-kg');
    expect(trial.family).toContain('TRIAL');
    expect(trial.events.some((event) => event.nodeId === 'semantic')).toBe(false);
    expect(trial.events.some((event) => event.nodeId === 'structural')).toBe(false);
    expect(kg.events.at(-3)?.edgeId).toBe('gca-kg-only');
    expect(kg.events.some((event) => ['documents', 'sourceunits', 'rrf', 'reader', 'quote'].includes(event.nodeId))).toBe(false);
  });

  it('uses no edge when a partial run stops before any next stage is executed', () => {
    const partial = scenario('fallback-partial');
    const notExecuted = partial.events.find((event) => event.title === 'Verifica non eseguita');
    expect(notExecuted?.nodeId).toBe('structural');
    expect(notExecuted?.edgeId).toBe('quote-structural');
    expect(partial.dossierStatus).toContain('ACCOUNTING FAIL');
  });
});
