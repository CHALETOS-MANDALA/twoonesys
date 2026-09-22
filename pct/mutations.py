"""Cancello di mutazione (spec §6): una proprieta' che sopravvive alla propria
mutazione NON e' provata, e la build fallisce.

Ogni mutazione rompe di proposito una riga precisa e dichiara quale test DEVE
morire. Se muore, la proprieta' e' coperta. Se sopravvive, il test e' teatro.

Uso:  python3 mutations.py         (esce 1 se una mutazione sopravvive)
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass

RADICE = pathlib.Path(__file__).resolve().parent


@dataclass(frozen=True)
class Mutazione:
    nome: str
    file: str
    cerca: str
    sostituisci: str
    test_che_deve_morire: str
    proprieta: str


MUTAZIONI: tuple[Mutazione, ...] = (
    Mutazione(
        nome="propensione_ignorata",
        file="estimators.py",
        cerca="    w = 1.0 / propensity",
        sostituisci="    w = np.ones_like(propensity)",
        test_che_deve_morire="tests/test_estimators.py::test_3_hajek_recupera_la_verita_la_media_no",
        proprieta="la pesatura per propensione corregge il confondimento"),
    Mutazione(
        nome="condizioni_ignorate",
        file="evidence_prec.py",
        cerca='        if livello == "stato+e":\n            return pos[ep.e[pos] == cond.e]',
        sostituisci='        if livello == "stato+e":\n            return pos',
        test_che_deve_morire="tests/test_regimi.py::test_B_vince_su_effect_flip",
        proprieta="il condizionamento su e produce il vantaggio in EFFECT_FLIP"),
    Mutazione(
        nome="esclusione_evento_raro_nella_policy",
        file="policy.py",
        cerca="""    vietate = {ev.action for ev in evidence.rare_events
               if ev.magnitude <= -cfg.catastrophe_threshold}""",
        sostituisci="    vietate = set()",
        test_che_deve_morire="tests/test_policy_providers.py::test_evento_raro_esclude_l_azione",
        proprieta="un evento raro grave esclude l'azione dalle candidate"),
    Mutazione(
        nome="regola_eventi_rari_ignorata",
        file="structure.py",
        cerca="        use_d[s] |= _eventi_rari_concentrati(struttura, in_s, struttura.d)",
        sostituisci="        use_d[s] |= False",
        test_che_deve_morire="tests/test_regimi.py::test_B_evita_la_catastrofe",
        proprieta="la regola dichiarata sugli eventi rari ammette la condizione"),
    Mutazione(
        nome="media_al_posto_di_hajek_in_B",
        file="evidence_prec.py",
        cerca="                est = hajek(ep.magnitude[sel], ep.prop[sel])",
        sostituisci="                est = naive_mean(ep.magnitude[sel])",
        test_che_deve_morire="tests/test_regimi.py::test_B_non_peggiora_su_confound",
        proprieta="B usa lo stimatore corretto dentro il provider"),
    Mutazione(
        nome="struttura_sempre_attiva",
        file="structure.py",
        cerca="        if se > 0 and abs(did) > Z_DID * se:\n            return True",
        sostituisci="        if se > 0:\n            return True",
        test_che_deve_morire="tests/test_policy_providers.py::test_la_struttura_ammette_e_solo_quando_inverte_l_effetto",
        proprieta="una condizione entra solo se cambia l'effetto relativo"),
    Mutazione(
        nome="guardia_collider_disattivata",
        file="evidence.py",
        cerca='    if nome in CONDIZIONI_VIETATE:',
        sostituisci='    if False:',
        test_che_deve_morire="tests/test_policy_providers.py::test_guardia_collider_rifiuta_variabile_post_azione",
        proprieta="una variabile post-azione non puo' entrare nella state_key"),
)


def _esegui(cartella: pathlib.Path, test: str) -> bool:
    """True se il test PASSA nella cartella data."""
    r = subprocess.run([sys.executable, "-m", "pytest", test, "-q", "--no-header",
                        "-x", "-p", "no:cacheprovider"],
                       cwd=cartella, capture_output=True, text=True, timeout=1800)
    return r.returncode == 0


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        base = pathlib.Path(tmp) / "pct"
        shutil.copytree(RADICE, base, ignore=shutil.ignore_patterns(
            "__pycache__", ".pytest_cache"))

        print("verifica preliminare: i test bersaglio passano sul codice sano")
        sani: dict[str, bool] = {}
        for m in MUTAZIONI:
            if m.test_che_deve_morire not in sani:
                sani[m.test_che_deve_morire] = _esegui(base, m.test_che_deve_morire)
                stato = "ok" if sani[m.test_che_deve_morire] else "GIA' ROSSO"
                print(f"  {stato:>10}  {m.test_che_deve_morire}")
        if not all(sani.values()):
            print("\nalcuni test bersaglio non passano sul codice sano: "
                  "la prova di mutazione non ha senso finche' la suite non e' verde")
            return 1

        print("\nmutazioni")
        uccise = 0
        for m in MUTAZIONI:
            f = base / m.file
            originale = f.read_text()
            if m.cerca not in originale:
                print(f"  {'NON APPLICATA':>13}  {m.nome}: testo non trovato in {m.file}")
                return 1
            f.write_text(originale.replace(m.cerca, m.sostituisci, 1))
            try:
                sopravvive = _esegui(base, m.test_che_deve_morire)
            finally:
                f.write_text(originale)
            if sopravvive:
                print(f"  {'SOPRAVVIVE':>13}  {m.nome}  -> '{m.proprieta}' NON e' provata")
            else:
                uccise += 1
                print(f"  {'uccisa':>13}  {m.nome}  ({m.proprieta})")

        tasso = uccise / len(MUTAZIONI)
        print(f"\ntasso di uccisione: {uccise}/{len(MUTAZIONI)} = {tasso:.0%}")
        if uccise < len(MUTAZIONI):
            print("CANCELLO CHIUSO: una proprieta' sopravvive alla propria mutazione.")
            return 1
        print("cancello aperto: ogni proprieta' dichiarata muore con la sua mutazione.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
