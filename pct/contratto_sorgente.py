"""I DUE segnali da aggiungere alla sorgente -- e nient'altro.

Non e' una funzionalita' di PCT: e' cio' che il sistema che genera gli
episodi deve scrivere perche' la domanda principale diventi rispondibile. Finche'
mancano, «il fenomeno non c'e'» e «non riesco a vederlo» sono indistinguibili.

  1. SCALA DEI COSTI      un booleano perde la differenza fra «ritenta» e «hai
                          corrotto lo stato». Va DICHIARATA prima, non dedotta
                          dopo: un numero inventato a posteriori e' la stessa
                          patologia dell'ipotesi ristretta dopo aver visto i dati.

  2. ORDINE TEMPORALE     una condizione e' usabile solo se osservata PRIMA della
                          scelta. Non e' un'opinione sul campo: e' un confronto
                          fra due istanti, e qui viene verificato.

                          T0 osservazione condition
                          T1 costruzione state_key
                          T2 eligible_actions
                          T3 scelta action        <-- la linea
                          T4 esecuzione
                          T5 outcome
                          T6 outcome_magnitude

                          Qualunque cosa nasca da T4 in poi non puo' tornare
                          indietro e diventare una condition di T0.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

# --------------------------------------------------------------------- 1. costi

#: ESEMPIO, non una raccomandazione. I valori devono essere decisi dal
#: proprietario del dominio e congelati nella pre-registrazione: sono l'utilita'
#: dichiarata della carta §5.2, e decidono quali eventi dominano la media.
SCALA_ESEMPIO: Mapping[str, float] = {
    "VERIFY_PASS": +1.0,
    "VERIFY_FAIL": -1.0,
    "RETRY_REQUIRED": -2.0,
    "ROLLBACK": -10.0,
    "STATE_CORRUPTION": -100.0,
    "IRRECOVERABLE": -1000.0,
}


class ScalaNonDichiarata(ValueError):
    """Sollevata quando si chiede una magnitudine per un esito non nella scala."""


@dataclass(frozen=True)
class ScalaCosti:
    """Scala dichiarata degli esiti. Nessun valore di default: va scelta.

    `soglia_catastrofe` separa gli esiti che la media puo' assorbire da quelli
    che devono restare visibili come episodi singoli.
    """

    valori: Mapping[str, float]
    soglia_catastrofe: float
    versione: str

    def __post_init__(self) -> None:
        if not self.valori:
            raise ValueError("la scala dei costi non puo' essere vuota")
        if self.soglia_catastrofe <= 0:
            raise ValueError("soglia_catastrofe deve essere positiva")
        if not any(v > 0 for v in self.valori.values()):
            raise ValueError("serve almeno un esito positivo")
        if not any(v < 0 for v in self.valori.values()):
            raise ValueError("serve almeno un esito negativo")
        if not self.versione:
            raise ValueError("la scala deve avere una versione: entra nel "
                             "outcome_contract del record")

    def magnitudine(self, esito: str) -> float:
        if esito not in self.valori:
            raise ScalaNonDichiarata(
                f"esito '{esito}' non presente nella scala {self.versione}: "
                "va dichiarato prima, non convertito a occhio")
        return float(self.valori[esito])

    def e_catastrofico(self, esito: str) -> bool:
        return abs(self.magnitudine(esito)) >= self.soglia_catastrofe

    @property
    def outcome_contract(self) -> str:
        """Stringa da scrivere nel record: chi ha misurato e con quale scala."""
        return f"scala/{self.versione}@soglia={self.soglia_catastrofe:g}"


# ------------------------------------------------------------ 2. ordine temporale

FASI: tuple[str, ...] = (
    "condition_observed",     # T0
    "state_key_built",        # T1
    "eligible_actions",       # T2
    "action_chosen",          # T3  <-- la linea
    "executed",               # T4
    "outcome_observed",       # T5
    "magnitude_assigned",     # T6
)

INDICE_SCELTA: int = FASI.index("action_chosen")


class OrdineViolato(ValueError):
    """Una condizione e' nata dopo la scelta: e' un collider, non una condizione."""


@dataclass(frozen=True)
class Tempi:
    """Gli istanti delle fasi di un episodio. Servono solo i due che contano."""

    condition_observed: float
    action_chosen: float

    def verifica(self) -> None:
        if not (self.condition_observed < self.action_chosen):
            raise OrdineViolato(
                f"condizione osservata a {self.condition_observed} e azione scelta "
                f"a {self.action_chosen}: la condizione NON precede la scelta, "
                "quindi non e' utilizzabile (sarebbe un collider)")


def fase_di(nome_campo: str, fasi_note: Mapping[str, str]) -> str:
    """Restituisce la fase dichiarata di un campo, o solleva se non dichiarata."""
    if nome_campo not in fasi_note:
        raise ValueError(
            f"il campo '{nome_campo}' non dichiara in quale fase nasce: "
            "senza quella dichiarazione non si puo' sapere se e' pre-decisione")
    fase = fasi_note[nome_campo]
    if fase not in FASI:
        raise ValueError(f"fase sconosciuta '{fase}' per il campo '{nome_campo}'")
    return fase


def utilizzabile_come_condizione(nome_campo: str,
                                 fasi_note: Mapping[str, str]) -> bool:
    """True solo se il campo nasce PRIMA della scelta dell'azione."""
    return FASI.index(fase_di(nome_campo, fasi_note)) < INDICE_SCELTA


def valida_condizioni(campi: list[str], fasi_note: Mapping[str, str]) -> list[str]:
    """Filtra i campi utilizzabili, sollevando su quelli nati dopo la scelta."""
    ammessi = []
    for c in campi:
        if utilizzabile_come_condizione(c, fasi_note):
            ammessi.append(c)
        else:
            raise OrdineViolato(
                f"'{c}' nasce in fase '{fasi_note[c]}', cioe' a valle della "
                "scelta: non puo' essere una condizione")
    return ammessi
