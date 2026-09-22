"""CASCADE - Regressioni chiuse dalla verifica indipendente del 2026-09-18.

CorrectnessSuite. Ogni test qui CADEVA prima della correzione: sono invarianti,
non conservazione del comportamento precedente.

1. La barriera respingeva ~50% dei claim FEDELI perche' confrontava
   l'espansione binaria del float invece delle cifre decimali
   (`float("143.1118")` -> `143.11179999999998...` -> troncato a 4 decimali
   da' `1117`). Verde in suite solo perche' le fixture cadevano dal lato
   favorevole dell'errore di rappresentazione.
2. Il log degli esiti non registrava propensione, digest del contratto e
   fonte dell'etichetta: senza la propensione la stima off-policy (IPS /
   doubly-robust) e' impossibile, e NON e' recuperabile a posteriori.
"""

from decimal import Decimal

import pytest

from cascade.claim_barrier import (
    NumericClaim,
    _digits_are_prefix,
    canonical_payload_hash,
    check_numeric_claim,
    decimal_digits,
)
from cascade.outcome_log import OutcomeLog, OutcomeRecord

# cifre reali del math-kernel (zetazero 50, 40 digits)
IM_Z50 = "143.1118458076206327394051238689139299662"
IM_Z1 = "14.13472514173469379045725198356247027078"


def _evidenza(im: str, n: int, stdout: str = "deadbeef") -> dict:
    p = {"s": f"(0.5 + {im}j)", "Im": im, "Re": "0.5", "on_critical_line": True}
    return {
        "intent": "zero_nth", "params": {"n": n, "digits": 40}, "immutable": True,
        "machine": {"tool": "math-kernel:zeron", "args": [str(n), "40"],
                    "exit_code": 0, "stdout_hash": stdout, "parsed": p},
        "fact": {"kind": "zero_nth",
                 "expected": [{"label": "Im", "value": im, "float": float(im)},
                              {"label": "Re", "value": "0.5", "float": 0.5,
                               "boundary": True}],
                 "outcome": {"on_critical_line": True}, "payload": p},
    }


# --------------------------------------------------------------------------- #
# 1. barriera: le cifre non passano piu' da un float binario
# --------------------------------------------------------------------------- #


class TestCifreNonPassanoDaFloat:
    @pytest.mark.parametrize("precision", [1, 2, 4, 8, 15, 17, 25, 30, 37])
    def test_prefisso_fedele_sempre_accettato(self, precision):
        """Un troncamento ESATTO delle cifre attese non puo' mai essere respinto."""
        declared = IM_Z50[: IM_Z50.index(".") + 1 + precision]
        assert _digits_are_prefix(declared, IM_Z50, precision) is True

    def test_il_caso_che_cadeva_dal_lato_sfavorevole(self):
        """143.1118 e' esattamente il valore su cui l'espansione binaria stava
        SOTTO e il troncamento dava '1117' invece di '1118'."""
        assert _digits_are_prefix("143.1118", IM_Z50, 4) is True
        assert _digits_are_prefix(143.1118, IM_Z50, 4) is True   # anche da float

    def test_nessun_falso_negativo_su_valori_casuali(self):
        """Il claim e' SEMPRE un prefisso esatto: zero respinte su tutti i casi."""
        import random
        rng = random.Random(20260918)
        respinti = 0
        for _ in range(500):
            ip = rng.randint(1, 999)
            fp = "".join(rng.choice("0123456789") for _ in range(30))
            atteso = f"{ip}.{fp}"
            for prec in (4, 8, 12):
                if not _digits_are_prefix(atteso[: atteso.index(".") + 1 + prec],
                                          atteso, prec):
                    respinti += 1
        assert respinti == 0, f"{respinti} claim fedeli respinti"

    def test_cifra_alterata_resta_respinta(self):
        """La correzione non allarga la maglia: alterare una cifra e' REJECT."""
        rotto = "143.1118458017206327394051238689139299662"   # 10a decimale
        assert _digits_are_prefix(rotto, IM_Z50, 12) is False

    def test_precision_oltre_le_cifre_disponibili_respinta(self):
        """Dichiarare 50 decimali quando l'evidenza ne ha 37 e' un claim falso."""
        assert _digits_are_prefix(IM_Z50, IM_Z50, 50) is False
        assert _digits_are_prefix(IM_Z50, IM_Z50, 38) is False   # ne ha 37

    def test_precision_oltre_le_cifre_dichiarate_respinta(self):
        """Dichiarare 25 decimali avendone scritti 4: le cifre implicite sono
        zeri, e 143.1118000... non coincide con 143.1118458..."""
        assert _digits_are_prefix("143.1118", IM_Z50, 25) is False

    def test_zeri_impliciti_sono_cifre(self):
        """42.5 vale esattamente 42.5000: un'evidenza con zeri finali combacia."""
        assert _digits_are_prefix("42.5", "42.5000", 4) is True
        assert _digits_are_prefix(42.5, "42.5000", 4) is True
        assert _digits_are_prefix("42.5", "42.5001", 4) is False

    def test_segno_discorde_respinto(self):
        """-143.11 non e' un prefisso di +143.11."""
        assert _digits_are_prefix("-143.1118", IM_Z50, 4) is False

    def test_quaranta_cifre_verificabili_con_stringa(self):
        """Il motivo per cui la barriera esiste: i 40 decimali del kernel.
        Con un float sono irraggiungibili; con una stringa si verificano."""
        ev = _evidenza(IM_Z50, 50)
        claim = NumericClaim(
            operation="zeron", arguments=("50", "40"), subject_id="zero-50",
            value=IM_Z50, unit="Im", precision=37,
            evidence_ref=canonical_payload_hash(ev))
        assert check_numeric_claim(claim, ev).ok is True

    def test_decimal_accettato(self):
        ev = _evidenza(IM_Z50, 50)
        claim = NumericClaim(
            operation="zeron", arguments=("50", "40"), subject_id="zero-50",
            value=Decimal(IM_Z50), unit="Im", precision=37,
            evidence_ref=canonical_payload_hash(ev))
        assert check_numeric_claim(claim, ev).ok is True

    def test_valore_non_numerico_rifiutato_alla_costruzione(self):
        with pytest.raises((ValueError, ArithmeticError, TypeError)):
            NumericClaim(operation="zeron", arguments=("1",), subject_id="z",
                         value="quasi 143", unit="Im", precision=4)

    def test_decimal_digits_non_usa_espansione_binaria(self):
        assert decimal_digits(143.1118) == "143.1118"
        assert decimal_digits("143.1118") == "143.1118"
        assert decimal_digits(Decimal("143.1118")) == "143.1118"
        assert decimal_digits(0.00001) == "0.00001"      # mai notazione esponenziale


# --------------------------------------------------------------------------- #
# 2. log degli esiti: i tre campi che non si recuperano dopo
# --------------------------------------------------------------------------- #


def _rec(**kw) -> OutcomeRecord:
    base = dict(request_id="r1", action="EPISODIC", raw_confidence=0.7,
                measured_p=None, escalated=False, approved=True, outcome=True,
                touched=0.0)
    base.update(kw)
    return OutcomeRecord(**base)


class TestPropensioneEProvenienza:
    def test_i_tre_campi_esistono_e_fanno_round_trip(self, tmp_path):
        log = OutcomeLog(tmp_path / "o.jsonl")
        log.record(_rec(selection_probability=0.25, contract_digest="abc123",
                        label_source="mechanical"))
        riletto = OutcomeLog(tmp_path / "o.jsonl").load().records()[0]
        assert riletto.selection_probability == 0.25
        assert riletto.contract_digest == "abc123"
        assert riletto.label_source == "mechanical"

    def test_propensione_zero_rifiutata(self):
        """Se l'azione e' stata scelta, la sua probabilita' non era zero: uno
        zero renderebbe infinito il peso IPS."""
        with pytest.raises(ValueError):
            _rec(selection_probability=0.0)

    def test_propensione_fuori_range_rifiutata(self):
        with pytest.raises(ValueError):
            _rec(selection_probability=1.5)

    def test_label_source_e_un_insieme_chiuso(self):
        with pytest.raises(ValueError):
            _rec(label_source="a occhio")
        for buona in OutcomeRecord.LABEL_SOURCES:
            assert _rec(label_source=buona).label_source == buona

    def test_metriche_dichiarano_la_lacuna(self, tmp_path):
        """La log deve DIRE cosa non si potra' fare con essa, non tacerlo."""
        log = OutcomeLog(tmp_path / "o.jsonl")
        log.record(_rec(request_id="a", selection_probability=0.5))
        log.record(_rec(request_id="b"))          # senza propensione
        m = log.metrics()
        assert m["with_propensity"] == 1
        assert m["off_policy_ready"] is False

    def test_off_policy_ready_quando_tutte_hanno_propensione(self, tmp_path):
        log = OutcomeLog(tmp_path / "o.jsonl")
        log.record(_rec(request_id="a", selection_probability=0.5))
        log.record(_rec(request_id="b", selection_probability=0.9))
        assert log.metrics()["off_policy_ready"] is True

    def test_righe_v1_restano_leggibili(self, tmp_path):
        """Compatibilita': una log scritta prima dei tre campi si ricarica."""
        p = tmp_path / "o.jsonl"
        p.write_text(
            '{"request_id":"vecchio","action":"DIRECT","raw_confidence":0.6,'
            '"measured_p":null,"escalated":false,"approved":true,"outcome":true,'
            '"touched":0.0,"version":1}\n', encoding="utf-8")
        rec = OutcomeLog(p).load().records()[0]
        assert rec.request_id == "vecchio"
        assert rec.selection_probability is None    # assente, non inventata
        assert rec.label_source is None

    def test_stima_ips_possibile_con_la_propensione(self, tmp_path):
        """La ragione per cui il campo esiste: valutare offline una politica
        MAI eseguita, pesando per l'inverso della propensione.

        Log generato da eps-greedy con eps=0.40 su K=4 rami:
            p(preferito) = 1 - eps + eps/K = 0.70   -> 70 casi
            p(alternativo) = eps/K        = 0.10   -> 10 casi per ramo
        EPISODIC (il preferito) riesce nel 50% dei casi; DEEP sempre.
        La media grezza e' distorta verso il ramo piu' osservato; IPS no.
        """
        log = OutcomeLog(tmp_path / "o.jsonl")
        p_pref, p_expl = 0.70, 0.10
        for i in range(70):
            log.record(_rec(request_id=f"p{i}", action="EPISODIC",
                            outcome=(i % 2 == 0), selection_probability=p_pref))
        for ramo in ("DEEP", "CONVERGENCE", "DIRECT"):
            for i in range(10):
                log.record(_rec(request_id=f"{ramo}{i}", action=ramo,
                                outcome=(ramo == "DEEP"),
                                selection_probability=p_expl))
        recs = log.records()
        assert len(recs) == 100
        assert log.metrics()["off_policy_ready"] is True

        def ips(azione: str) -> float:
            return sum((1.0 if r.outcome else 0.0)
                       * (1.0 if r.action == azione else 0.0)
                       / r.selection_probability for r in recs) / len(recs)

        # politica "sempre DEEP": mai eseguita come politica, stimata dai log
        assert ips("DEEP") == pytest.approx(1.0)
        # politica "sempre EPISODIC": riesce a meta'
        assert ips("EPISODIC") == pytest.approx(0.5)
        # la media grezza NON distingue le due politiche
        grezza = sum(1 for r in recs if r.outcome) / len(recs)
        assert grezza == pytest.approx(0.45)
