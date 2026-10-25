"""`artifact_hash_policy/2.0`: la forma sotto cui un'impronta viene presa.

La versione 1.0 non esisteva come documento. Era una convenzione implicita —
`Path.read_text(encoding="utf-8").encode("utf-8")` ripetuto nei punti dove
serviva un digest — e il difetto che ha prodotto e' rimasto invisibile per otto
fasi: `read_text` converte le fini riga secondo la piattaforma, quindi lo stesso
file dava digest diversi su macchine diverse, e nessuno dei due era dichiarato.
Una normalizzazione che nessuno ha scritto e' una normalizzazione che nessuno
puo' verificare.

La 2.0 dichiara tre cose:

1. **Si legge in byte.** `read_bytes()`, mai `read_text()`. Un'impronta e' una
   promessa sui byte; leggere in testo significa misurare il risultato di una
   conversione che dipende dalla macchina, e chiamarlo «il file».

2. **La forma canonica e' LF.** La normalizzazione e' esplicita e ha un nome
   (`NORMALIZATION`), cosi' che un artefatto possa dichiarare quale forma ha
   misurato invece di lasciarlo dedurre.

3. **Un CR isolato e' un errore, non una fine riga.** `\r\n` diventa `\n`; un
   `\r` che resta dopo quella sostituzione non e' un terminatore di riga in
   nessuna convenzione ancora in uso, ed e' molto piu' probabilmente un byte
   entrato per sbaglio. Convertirlo in silenzio significherebbe far combaciare
   due file che non sono lo stesso file — esattamente il genere di indulgenza
   che ha reso possibile il difetto della 1.0.

Le impronte prese sotto la convenzione implicita non vengono ricalcolate: sono
registrate in un erratum, con entrambe le forme e il codice della ragione. Vedi
`REASON_LEGACY_LINE_ENDING`.

**Questo modulo non si applica ai file binari.** Un `.xlsx` o un `.png` non ha
fini riga da normalizzare: sostituire `\r\n` nei suoi byte lo corrompe e basta.
Per un binario l'impronta canonica sono i byte grezzi, e chi lo tratta deve
saperlo — questa politica copre il testo.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

POLICY_VERSION = "artifact_hash_policy/2.0"

# La forma sotto cui la 2.0 misura. E' un valore dichiarato negli artefatti, non
# una nota: distingue un'impronta presa sotto questa politica da una presa prima.
NORMALIZATION = "lf"

# Perche' un'impronta storica non e' riproducibile da un checkout pulito. Non e'
# una scusa: e' una classificazione, e ha un test che la verifica.
REASON_LEGACY_LINE_ENDING = "LEGACY_LINE_ENDING_DEPENDENT_HASH"


class LoneCarriageReturnError(ValueError):
    """Un CR non seguito da LF. Non si normalizza, si segnala."""


def canonical_lf_bytes(data: bytes) -> bytes:
    """I byte nella forma canonica: CRLF diventa LF, un CR isolato e' un errore.

    Il rifiuto e' la parte che conta. Convertire anche il CR isolato renderebbe
    la funzione totale e la sua promessa piu' debole: due file diversi
    otterrebbero la stessa impronta, ed e' precisamente cio' che un'impronta
    deve impedire.
    """
    normalised = data.replace(b"\r\n", b"\n")
    if b"\r" in normalised:
        offset = normalised.index(b"\r")
        raise LoneCarriageReturnError(
            f"CR isolato all'offset {offset} della forma normalizzata: non e' "
            f"una fine riga e non viene convertito. I byte vanno corretti alla "
            f"fonte, non accomodati qui."
        )
    return normalised


def _as_bytes(source: Path | str | bytes) -> bytes:
    """`read_bytes()`, mai `read_text()`: e' l'intera ragione della 2.0."""
    if isinstance(source, bytes):
        return source
    return Path(source).read_bytes()


def canonical_lf_sha256(source: Path | str | bytes) -> str:
    """L'impronta canonica: sha256 dei byte normalizzati a LF."""
    return hashlib.sha256(canonical_lf_bytes(_as_bytes(source))).hexdigest()


def raw_sha256(source: Path | str | bytes) -> str:
    """L'impronta dei byte come stanno, senza nessuna normalizzazione.

    Serve per i binari, e per registrare la forma storica di un file di testo
    senza pretendere che sia canonica.
    """
    return hashlib.sha256(_as_bytes(source)).hexdigest()


@dataclass(frozen=True)
class HashRecord:
    """Le due impronte di un sorgente, e perche' non coincidono.

    `historical_raw_sha256` e' cio' che un artefatto congelato afferma;
    `canonical_lf_sha256` e' cio' che un checkout pulito produce. Tenerle
    entrambe e' il punto: una sola delle due costringerebbe a scegliere fra
    riscrivere la storia e mentire sul presente.
    """

    historical_raw_sha256: str
    canonical_lf_sha256: str
    reason_code: str = REASON_LEGACY_LINE_ENDING
    hash_policy_version: str = POLICY_VERSION
    normalization: str = NORMALIZATION

    @property
    def diverges(self) -> bool:
        return self.historical_raw_sha256 != self.canonical_lf_sha256

    def matches(self, data: Path | str | bytes) -> bool:
        """I byte dati sono quelli che la forma canonica promette?"""
        return canonical_lf_sha256(data) == self.canonical_lf_sha256

    def as_dict(self) -> dict[str, str]:
        return {
            "canonical_lf_sha256": self.canonical_lf_sha256,
            "hash_policy_version": self.hash_policy_version,
            "historical_raw_sha256": self.historical_raw_sha256,
            "normalization": self.normalization,
            "reason_code": self.reason_code,
        }

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> HashRecord:
        """Da JSON, con i campi obbligatori richiesti per nome.

        Nessun default silenzioso su `hash_policy_version` o `normalization`:
        un record che non dichiara sotto quale politica e' stato scritto e'
        esattamente il problema che la 2.0 esiste per chiudere.
        """
        missing = sorted(
            {
                "canonical_lf_sha256",
                "hash_policy_version",
                "historical_raw_sha256",
                "normalization",
                "reason_code",
            }
            - set(payload)
        )
        if missing:
            raise ValueError(f"record di hash incompleto, mancano: {missing}")
        return cls(
            historical_raw_sha256=payload["historical_raw_sha256"],
            canonical_lf_sha256=payload["canonical_lf_sha256"],
            reason_code=payload["reason_code"],
            hash_policy_version=payload["hash_policy_version"],
            normalization=payload["normalization"],
        )


__all__ = [
    "NORMALIZATION",
    "POLICY_VERSION",
    "REASON_LEGACY_LINE_ENDING",
    "HashRecord",
    "LoneCarriageReturnError",
    "canonical_lf_bytes",
    "canonical_lf_sha256",
    "raw_sha256",
]
