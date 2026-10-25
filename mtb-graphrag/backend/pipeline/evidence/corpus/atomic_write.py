"""Scrittura atomica del corpus promosso.

Una promozione che scrivesse i diciotto file uno per uno nella directory
definitiva avrebbe, fra il primo e l'ultimo, uno stato in cui il corpus esiste a
meta'. Un lettore che arrivasse in quel momento non troverebbe un errore:
troverebbe un corpus con meno claim, e non avrebbe modo di accorgersene. E' il
motivo per cui questo modulo esiste.

La sequenza e' fissa e ogni passo ha un punto di fallimento nominato, perche' i
test possano interromperla dove serve invece di simulare l'interruzione:

    snapshot → generazione in staging → validazione → confronto con la 1.4
    → manifest → rename → verifica post-write → registro

L'invariante e' uno solo, e vale a ogni punto di interruzione:

    o la directory definitiva contiene un corpus completo e verificato,
    o non e' stata toccata

Il registro prototipale viene aggiornato per ultimo e separatamente. Un registro
che puntasse a un corpus non ancora rinominato descriverebbe qualcosa che non
esiste; e se il rename riuscisse e il registro no, resterebbe una directory
inerte che nessuno raggiunge — che e' il verso giusto in cui sbagliare.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# I punti in cui la sequenza puo' essere interrotta. Sono nominati e non
# numerati: un test che dica `fail_at="before_rename"` resta leggibile se un
# giorno si aggiunge un passo in mezzo.
FAILURE_POINTS = (
    "after_snapshot",
    "after_generation",
    "after_validation",
    "after_manifest",
    "before_rename",
    "after_rename",
    "before_registry",
)

STAGING_PREFIX = ".staging-"
FAILED_PREFIX = ".failed-"
SUPERSEDED_PREFIX = ".superseded-"
ROLLBACK_LOG_FILE = "promotion_rollback_log.json"


class AtomicWriteError(RuntimeError):
    """La scrittura atomica non ha potuto completare la sequenza."""


class InjectedFailure(AtomicWriteError):
    """Interruzione richiesta da un test in un punto nominato della sequenza."""


class PostWriteVerificationError(AtomicWriteError):
    """Cio' che e' stato riletto dopo il rename non e' cio' che era stato scritto."""


@dataclass
class PromotionLog:
    """Il diario della promozione, che sopravvive anche quando la promozione no."""

    steps: list[dict[str, Any]] = field(default_factory=list)

    def record(self, step: str, **detail: Any) -> None:
        self.steps.append({"step": step, "outcome": "ok", **detail})

    def fail(self, step: str, reason: str, **detail: Any) -> None:
        self.steps.append(
            {"step": step, "outcome": "failed", "reason": reason, **detail}
        )

    def as_dict(self) -> dict[str, Any]:
        return {"steps": list(self.steps)}


@dataclass(frozen=True)
class WriteOutcome:
    """Esito di una promozione riuscita."""

    destination: Path
    files_written: tuple[str, ...]
    sha256: dict[str, str]
    staging_removed: bool
    superseded_path: str | None
    log: dict[str, Any]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def directory_hashes(directory: Path) -> dict[str, str]:
    """Impronta per file di una directory, vuota se la directory non esiste."""
    directory = Path(directory)
    if not directory.is_dir():
        return {}
    return {
        item.relative_to(directory).as_posix(): sha256_file(item)
        for item in sorted(directory.rglob("*"))
        if item.is_file()
    }


def _token(artifacts: Mapping[str, str]) -> str:
    """Suffisso della staging derivato dal contenuto, non dall'orologio.

    Un suffisso casuale renderebbe non riproducibile il nome della directory
    temporanea, e con esso il log che la cita. Derivarlo dal contenuto lascia
    l'artefatto deterministico e continua a impedire la collisione fra due
    promozioni di contenuti diversi.
    """
    payload = "\n".join(f"{name}:{sha256_text(text)}" for name, text in sorted(artifacts.items()))
    return sha256_text(payload)[:16]


def _write_tree(directory: Path, artifacts: Mapping[str, str]) -> None:
    directory.mkdir(parents=True, exist_ok=False)
    for name, text in sorted(artifacts.items()):
        (directory / name).write_text(text, encoding="utf-8", newline="\n")


def _abandon(staging: Path, log: PromotionLog, reason: str) -> Path | None:
    """Marca la staging come fallita e vi conserva il log, invece di cancellarla.

    Cancellare sarebbe piu' pulito e lascerebbe senza materiale chi deve capire
    perche' la promozione non e' passata. La directory resta, con un nome che ne
    dichiara lo stato, e non e' raggiungibile da nessun registro.
    """
    if not staging.exists():
        return None
    failed = staging.with_name(staging.name.replace(STAGING_PREFIX, FAILED_PREFIX, 1))
    if failed.exists():
        shutil.rmtree(failed)
    staging.rename(failed)
    log.fail("abandon", reason, failed_path=failed.name)
    (failed / ROLLBACK_LOG_FILE).write_text(
        json.dumps(log.as_dict(), ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return failed


def _check(fail_at: str | None, point: str, log: PromotionLog) -> None:
    if fail_at is None:
        return
    if fail_at not in FAILURE_POINTS:
        raise AtomicWriteError(
            f"punto di fallimento sconosciuto: {fail_at!r}; "
            f"attesi {list(FAILURE_POINTS)}"
        )
    if fail_at == point:
        log.fail(point, "injected_failure")
        raise InjectedFailure(f"interruzione richiesta in {point}")


def write_corpus_atomically(
    destination: Path,
    artifacts: Mapping[str, str],
    *,
    validate: Callable[[Path], Mapping[str, Any]] | None = None,
    manifest_name: str | None = None,
    fail_at: str | None = None,
    keep_superseded: bool = True,
) -> WriteOutcome:
    """Materializza `artifacts` in `destination` senza mai lasciarla incompleta.

    `validate` riceve la directory di staging gia' scritta e solleva se qualcosa
    non torna. Riceve la staging e non i testi in memoria di proposito: cio' che
    va validato e' il corpus come un lettore lo trovera', non come chi lo scrive
    crede di averlo prodotto.
    """
    destination = Path(destination)
    log = PromotionLog()

    snapshot = directory_hashes(destination)
    registry_existed = destination.exists()
    log.record(
        "snapshot",
        destination=destination.name,
        destination_existed=registry_existed,
        files_before=len(snapshot),
    )
    _check(fail_at, "after_snapshot", log)

    staging = destination.with_name(f"{destination.name}{STAGING_PREFIX}{_token(artifacts)}")
    if staging.exists():
        shutil.rmtree(staging)

    superseded: Path | None = None
    try:
        _write_tree(staging, artifacts)
        log.record("generate", staging=staging.name, files=len(artifacts))
        _check(fail_at, "after_generation", log)

        report: Mapping[str, Any] = {}
        if validate is not None:
            report = validate(staging)
            log.record("validate", **dict(report))
        _check(fail_at, "after_validation", log)

        written = {name: sha256_file(staging / name) for name in sorted(artifacts)}
        if manifest_name is not None and manifest_name not in artifacts:
            raise AtomicWriteError(f"manifest assente fra gli artefatti: {manifest_name}")
        log.record("manifest", manifest=manifest_name, hashed_files=len(written))
        _check(fail_at, "after_manifest", log)

        _check(fail_at, "before_rename", log)

        # Lo scambio: la vecchia directory viene spostata di lato *prima* che la
        # nuova prenda il suo nome, cosi' che il nome definitivo non sia mai
        # occupato da un contenuto parziale. Se il secondo rename fallisse, il
        # primo viene disfatto.
        if destination.exists():
            superseded = destination.with_name(
                f"{destination.name}{SUPERSEDED_PREFIX}{_token(artifacts)}"
            )
            if superseded.exists():
                shutil.rmtree(superseded)
            os.replace(destination, superseded)
        try:
            os.replace(staging, destination)
        except OSError:
            if superseded is not None and not destination.exists():
                os.replace(superseded, destination)
                superseded = None
            raise
        log.record("rename", destination=destination.name)
        _check(fail_at, "after_rename", log)

        reread = {name: sha256_file(destination / name) for name in sorted(artifacts)}
        if reread != written:
            diverged = sorted(
                name for name, digest in written.items() if reread.get(name) != digest
            )
            raise PostWriteVerificationError(
                f"post-write: {diverged} non coincidono con cio' che era stato scritto"
            )
        extra = sorted(set(directory_hashes(destination)) - set(artifacts))
        if extra:
            raise PostWriteVerificationError(
                f"post-write: la directory definitiva contiene file non previsti {extra}"
            )
        log.record("verify_post_write", files=len(reread))
        _check(fail_at, "before_registry", log)

    except BaseException as error:
        _abandon(staging, log, f"{type(error).__name__}: {error}")
        # Se lo scambio era gia' avvenuto, il contenuto precedente torna al suo
        # posto: la directory definitiva non resta mai in uno stato che nessuna
        # promozione ha prodotto.
        if superseded is not None and superseded.exists():
            if destination.exists():
                shutil.rmtree(destination)
            os.replace(superseded, destination)
            log.record("restore_previous", destination=destination.name)
        raise

    if superseded is not None and not keep_superseded:
        shutil.rmtree(superseded)
        superseded = None

    return WriteOutcome(
        destination=destination,
        files_written=tuple(sorted(artifacts)),
        sha256=written,
        staging_removed=not staging.exists(),
        superseded_path=superseded.name if superseded is not None else None,
        log=log.as_dict(),
    )


def write_json_atomically(path: Path, text: str) -> None:
    """Sostituzione atomica di un singolo file, per il registro prototipale.

    `os.replace` e' atomico rispetto ai lettori: chi apre il registro trova la
    versione precedente o quella nuova, mai un file troncato a meta' scrittura.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}{STAGING_PREFIX}{sha256_text(text)[:16]}")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    try:
        os.replace(temporary, path)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise


__all__ = [
    "FAILED_PREFIX",
    "FAILURE_POINTS",
    "ROLLBACK_LOG_FILE",
    "STAGING_PREFIX",
    "SUPERSEDED_PREFIX",
    "AtomicWriteError",
    "InjectedFailure",
    "PostWriteVerificationError",
    "PromotionLog",
    "WriteOutcome",
    "directory_hashes",
    "sha256_file",
    "sha256_text",
    "write_corpus_atomically",
    "write_json_atomically",
]
