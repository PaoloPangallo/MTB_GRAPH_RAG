(function (root) {
  'use strict';
  const tabs = ['sintesi', 'contratti', 'controlli', 'codice'];
  const examples = ['melanoma', 'studio', 'diagnostica'];

  function parseLocation(hash, data) {
    const raw = String(hash || '').replace(/^#/, '');
    const separator = raw.indexOf('?');
    const phase = separator < 0 ? raw : raw.slice(0, separator);
    const query = new URLSearchParams(separator < 0 ? '' : raw.slice(separator + 1));
    const example = query.get('esempio');
    const tab = query.get('vista');
    return {
      phase: [...data.phases, ...(data.macros || [])].some(item => item.id === phase) ? phase : 'panoramica',
      example: examples.includes(example) ? example : 'melanoma',
      tab: tabs.includes(tab) ? tab : 'sintesi'
    };
  }

  function serialize(state) {
    return '#' + state.phase + '?esempio=' + encodeURIComponent(state.example) + '&vista=' + encodeURIComponent(state.tab);
  }

  function neighbors(id, data) {
    const macros = (data.macros || []).map(item => item.id);
    const order = ['panoramica', ...(macros.includes(id) || (id === 'panoramica' && macros.length) ? macros : data.phases.map(phase => phase.id))];
    const index = Math.max(0, order.indexOf(id));
    return { previous: order[index - 1] || null, next: order[index + 1] || null };
  }

  function flowFor(phase) {
    return phase.flow;
  }

  function searchPhases(query, data) {
    const text = String(query).trim().toLocaleLowerCase('it');
    return data.phases.filter(phase => [phase.number, phase.title, phase.summary, phase.component]
      .join(' ').toLocaleLowerCase('it').includes(text));
  }

  const api = { tabs, examples, parseLocation, serialize, neighbors, flowFor, searchPhases };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  root.ArchitectureState = api;
})(globalThis);
