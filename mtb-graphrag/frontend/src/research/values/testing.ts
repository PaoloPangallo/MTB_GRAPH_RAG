/**
 * Asserzione condivisa: nel DOM non deve comparire la coercizione di un oggetto.
 *
 * Vive in un modulo proprio perché serve a molte suite — i renderer, gli stage
 * inspector, la console intera. Un controllo riscritto ogni volta si sarebbe
 * indebolito da qualche parte.
 */

/** Fallisce se il sottoalbero contiene `[object Object]` o `[object Array]`. */
export function expectNoObjectObject(container: HTMLElement): void {
  const text = container.textContent ?? '';
  const match = /\[object \w+\]/.exec(text);
  if (match) {
    const at = Math.max(0, match.index - 80);
    throw new Error(
      `Trovato "${match[0]}" nel DOM: un valore strutturato è stato reso come stringa.\n`
      + `Contesto: …${text.slice(at, match.index + 120)}…`,
    );
  }
}
