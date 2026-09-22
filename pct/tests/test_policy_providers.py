"""Test 4-8 della specifica: NO_EVIDENCE, guardia collider, l'indice non decide,
nessun ranking, rebuild deterministico. Piu' le proprieta' della policy condivisa.
"""

from __future__ import annotations

import pathlib
import re

import numpy as np
import pytest

from evidence import (ActionEvidence, Conditions, Evidence, RareEvent, Status,
                      assert_pre_decision, empty_if_starved)
from evidence_agg import AggregateProvider
from evidence_param import ParametricProvider
from evidence_prec import PrecedentProvider
from policy import PolicyConfig, decide
from runner import _folds, paired_bootstrap, run_phenomenon
from structure import (learn_structure, learn_structure_stable, stability)
from world import (ELIGIBLE_FOR_EXECUTION, ELIGIBLE_FOR_EXPLORATION, World,
                   with_only)

RADICE = pathlib.Path(__file__).resolve().parent.parent


def _providers(n=40_000, seed=77, phenomenon="effect_flip"):
    w = World(with_only(phenomenon, seed=seed, n_episodes=n))
    ep = w.generate()
    struttura, stima, val = _folds(ep)
    st = learn_structure(struttura)
    return (AggregateProvider(stima), ParametricProvider(stima),
            PrecedentProvider(stima, structure=st), val)


# ------------------------------------------------------- test 4: NO_EVIDENCE


def test_supporto_affamato_produce_no_evidence():
    ev = empty_if_starved(
        {0: ActionEvidence(0.5, ess=2.0, n=2, std_err=0.1)},
        ess_min=30.0, rare=(), conditioning="stato")
    assert ev.status is Status.NO_EVIDENCE
    assert ev.per_action == {}


def test_supporto_sufficiente_passa():
    ev = empty_if_starved(
        {0: ActionEvidence(0.5, ess=100.0, n=100, std_err=0.1)},
        ess_min=30.0, rare=(), conditioning="stato")
    assert ev.status is Status.OK and 0 in ev.per_action


def test_no_evidence_fa_ripiegare_la_policy_sul_default():
    cfg = PolicyConfig(epsilon_eval=0.0, safe_default=1)
    a = decide(Evidence(per_action={}, status=Status.NO_EVIDENCE),
               ELIGIBLE_FOR_EXECUTION, ELIGIBLE_FOR_EXPLORATION, cfg,
               np.random.default_rng(0))
    assert a == 1


def test_stato_non_visto_non_esplode():
    agg, par, prec, _ = _providers(n=8_000)
    c = Conditions(d=0, e=0, t=0)
    for p in (agg, par, prec):
        ev = p.query(31, ELIGIBLE_FOR_EXECUTION, c)
        assert isinstance(ev, Evidence)


# ------------------------------------------------- test 5: guardia collider


def test_le_condizioni_sono_solo_pre_decisione():
    """Conditions espone d, e, t. Nessun campo derivato dall'azione o dall'esito."""
    campi = set(Conditions.__dataclass_fields__)
    assert campi == {"d", "e", "t"}
    vietati = {"outcome", "success", "magnitude", "action", "reward"}
    assert not (campi & vietati)


@pytest.mark.parametrize("nome", ["outcome", "success", "magnitude", "action", "reward"])
def test_guardia_collider_rifiuta_variabile_post_azione(nome):
    """Guardia VIVA: non e' un controllo sui campi, e' un rifiuto a runtime."""
    with pytest.raises(ValueError, match="prima della decisione"):
        assert_pre_decision(nome)


def test_guardia_collider_rifiuta_condizione_non_dichiarata():
    with pytest.raises(ValueError, match="non dichiarata"):
        assert_pre_decision("luna_piena")


def test_guardia_collider_ammette_le_condizioni_dichiarate():
    for nome in ("d", "e"):
        assert_pre_decision(nome)


def test_i_provider_non_ricevono_mai_l_esito():
    import inspect
    for cls in (AggregateProvider, ParametricProvider, PrecedentProvider):
        firma = inspect.signature(cls.query)
        assert set(firma.parameters) == {"self", "state", "eligible", "conditions"}


# ------------------------------------------- test 6: l'indice non decide mai


@pytest.mark.parametrize("campo", ["action", "chosen", "decision", "best"])
def test_evidence_rifiuta_un_azione_scelta(campo):
    with pytest.raises(TypeError, match="azione scelta"):
        Evidence(per_action={campo: ActionEvidence(0.0, 1.0, 1, 0.1)})


def test_evidence_rifiuta_qualunque_chiave_non_intera():
    """La guardia deve scattare sul TIPO, non su una lista di nomi noti."""
    with pytest.raises(TypeError, match="azione scelta"):
        Evidence(per_action={"qualsiasi_cosa": ActionEvidence(0.0, 1.0, 1, 0.1)})
    with pytest.raises(TypeError, match="azione scelta"):
        Evidence(per_action={True: ActionEvidence(0.0, 1.0, 1, 0.1)})


def test_unknown_e_un_output_possibile():
    """Status.UNKNOWN deve poter essere emesso, non essere codice morto."""
    ev = empty_if_starved({}, ess_min=30.0, rare=(), conditioning="stato",
                          unknown=(2,))
    assert ev.status is Status.UNKNOWN
    assert ev.unknown_actions == (2,)


def test_no_evidence_quando_il_vuoto_e_colmabile():
    ev = empty_if_starved({0: ActionEvidence(0.0, 1.0, 1, 0.1)}, ess_min=30.0,
                          rare=(), conditioning="stato", unknown=())
    assert ev.status is Status.NO_EVIDENCE


def test_evidence_non_ha_campi_di_ranking():
    campi = set(Evidence.__dataclass_fields__)
    assert not (campi & {"score", "rank", "recency", "weight", "priority"})


# --------------------------------------------- test 7: nessun ranking nel sorgente


def test_nessun_punteggio_composito_nei_provider():
    """Carta §7: uno score = recency x success x confidence viola l'atto costitutivo."""
    vietati = re.compile(r"\b(recency|rank\w*|priority)\b", re.IGNORECASE)
    # evidence.py e' escluso: e' il contratto che DEFINISCE i nomi vietati.
    # Si verifica separatamente che li' non ci sia nessun calcolo di punteggio.
    for nome in ("evidence_agg.py", "evidence_prec.py", "evidence_param.py"):
        testo = (RADICE / nome).read_text()
        codice = "\n".join(r for r in testo.splitlines()
                           if not r.strip().startswith("#"))
        # le docstring che VIETANO il ranking sono ammesse: si guarda il codice
        codice = re.sub(r'""".*?"""', "", codice, flags=re.S)
        assert not vietati.search(codice), f"termine di ranking in {nome}"


def test_il_contratto_nomina_i_vietati_solo_come_costanti():
    """In evidence.py 'rank'/'score' possono comparire SOLO nelle liste vietate."""
    testo = (RADICE / "evidence.py").read_text()
    codice = re.sub(r'""".*?"""', "", testo, flags=re.S)
    for riga in codice.splitlines():
        if re.search(r"\b(score|rank\w*|recency|priority)\b", riga, re.I):
            assert riga.lstrip().startswith(("NOMI_DI_", "#")) or \
                   "NOMI_DI_" in riga, f"uso sospetto di un termine di ranking: {riga!r}"


# ------------------------------------------ test 8: rebuild deterministico


def test_rebuild_due_volte_da_lo_stesso_indice():
    w = World(with_only("effect_flip", seed=5, n_episodes=20_000))
    ep = w.generate()
    struttura, stima, _ = _folds(ep)
    st = learn_structure(struttura)
    p1 = PrecedentProvider(stima, structure=st)
    p2 = PrecedentProvider(stima, structure=st)
    c = Conditions(d=1, e=1, t=0)
    for s in range(0, 32, 4):
        a = p1.query(s, ELIGIBLE_FOR_EXECUTION, c)
        b = p2.query(s, ELIGIBLE_FOR_EXECUTION, c)
        assert a.status is b.status
        assert {k: v.value_hat for k, v in a.per_action.items()} == \
               {k: v.value_hat for k, v in b.per_action.items()}


# --------------------------------------------------------- la policy condivisa


def test_evento_raro_esclude_l_azione():
    cfg = PolicyConfig(epsilon_eval=0.0, safe_default=0, catastrophe_threshold=100.0)
    per_action = {0: ActionEvidence(-0.5, 100.0, 100, 0.01),
                  2: ActionEvidence(+0.9, 100.0, 100, 0.01)}
    raro = RareEvent(action=2, magnitude=-1000.0, conditions=Conditions(0, 0, 0))

    senza = decide(Evidence(per_action=per_action), ELIGIBLE_FOR_EXECUTION,
                   ELIGIBLE_FOR_EXPLORATION, cfg, np.random.default_rng(0))
    con = decide(Evidence(per_action=per_action, rare_events=(raro,)),
                 ELIGIBLE_FOR_EXECUTION, ELIGIBLE_FOR_EXPLORATION, cfg,
                 np.random.default_rng(0))
    assert senza == 2, "senza l'evento raro la policy sceglie l'azione col valore alto"
    assert con == 0, "con l'evento raro quell'azione esce dalle candidate"


def test_esplorazione_non_tocca_mai_l_azione_catastrofica():
    cfg = PolicyConfig(epsilon_eval=0.999)
    rng = np.random.default_rng(0)
    scelte = {decide(Evidence(per_action={}), ELIGIBLE_FOR_EXECUTION,
                     ELIGIBLE_FOR_EXPLORATION, cfg, rng) for _ in range(500)}
    assert scelte <= set(ELIGIBLE_FOR_EXPLORATION)
    assert 2 not in scelte


def test_lcb_preferisce_la_stima_piu_sicura():
    cfg = PolicyConfig(epsilon_eval=0.0)
    per_action = {0: ActionEvidence(0.50, 100.0, 100, 0.01),   # LCB ~ 0.48
                  1: ActionEvidence(0.60, 100.0, 100, 0.30)}   # LCB ~ 0.01
    a = decide(Evidence(per_action=per_action), ELIGIBLE_FOR_EXECUTION,
               ELIGIBLE_FOR_EXPLORATION, cfg, np.random.default_rng(0))
    assert a == 0


# ----------------------------------------------------------------- struttura


def test_la_struttura_ammette_e_solo_quando_inverte_l_effetto():
    """Il criterio della carta §4.2: la condizione entra solo se cambia l'effetto."""
    con_flip = run_phenomenon("effect_flip", seed=101, n_episodes=40_000)
    senza = run_phenomenon(None, seed=101, n_episodes=40_000)
    assert con_flip.cond_e > 0.50, "con l'inversione, e deve essere ammessa"
    assert senza.cond_e == 0.0, "senza inversione, e non deve essere ammessa"
    # d ha SEMPRE due livelli popolati: e' su d che si vede se il criterio
    # ammette per davvero solo cio' che cambia l'effetto relativo
    # d ha sempre due livelli popolati, quindi il criterio puo' davvero sbagliare:
    # si tollera qualche falso positivo isolato, non un'ammissione di massa
    assert senza.cond_d <= 0.10, (
        f"d ammessa nel {senza.cond_d:.1%} degli stati senza cambio di effetto")
    assert con_flip.cond_d <= 0.10, "d non inverte l'effetto: non va ammessa in massa"


def test_la_pipeline_usa_la_selezione_per_stabilita():
    """Spec §10.3: una condizione entra solo se sopravvive al ricampionamento."""
    import inspect, runner
    src = inspect.getsource(runner.run_phenomenon)
    assert "learn_structure_stable" in src
    assert "learn_structure(" not in src


def test_stabilita_e_piu_severa_del_fit_singolo():
    w = World(with_only("effect_flip", seed=9, n_episodes=30_000))
    struttura, _, _ = _folds(w.generate())
    singolo = learn_structure(struttura)
    stabile = learn_structure_stable(struttura, n_boot=8, seed=1)
    assert stabile.use_e.sum() <= singolo.use_e.sum()
    assert stabile.use_d.sum() <= singolo.use_d.sum() + 1


def test_stability_selection_e_riproducibile():
    w = World(with_only("effect_flip", seed=9, n_episodes=30_000))
    struttura, _, _ = _folds(w.generate())
    f1 = stability(struttura, n_boot=5, seed=3)
    f2 = stability(struttura, n_boot=5, seed=3)
    np.testing.assert_array_equal(f1[1], f2[1])
    assert f1[1].max() > 0.5, "almeno uno stato deve selezionare e stabilmente"


# ------------------------------------------------------------------- runner


def test_bootstrap_appaiato_rifiuta_lunghezze_diverse():
    with pytest.raises(ValueError, match="stessi episodi"):
        paired_bootstrap(np.zeros(10), np.zeros(9))


def test_bootstrap_appaiato_su_differenza_nulla_contiene_zero():
    x = np.random.default_rng(0).normal(size=5_000)
    d, lo, hi = paired_bootstrap(x, x.copy(), n_boot=200, seed=1)
    assert d == 0.0 and lo <= 0.0 <= hi


def test_i_bracci_decidono_sugli_stessi_episodi():
    c = run_phenomenon(None, seed=101, n_episodes=30_000)
    lunghezze = {a.regret_per_episode.shape[0] for a in c.arms.values()}
    assert len(lunghezze) == 1


# --------------------------------------------- contratto della sorgente (2 segnali)


def test_scala_costi_rifiuta_un_esito_non_dichiarato():
    from contratto_sorgente import SCALA_ESEMPIO, ScalaCosti, ScalaNonDichiarata
    sc = ScalaCosti(SCALA_ESEMPIO, soglia_catastrofe=50.0, versione="t")
    with pytest.raises(ScalaNonDichiarata, match="dichiarato prima"):
        sc.magnitudine("QUALCOSA_DI_NUOVO")


def test_scala_costi_distingue_ritenta_da_corrompi():
    from contratto_sorgente import SCALA_ESEMPIO, ScalaCosti
    sc = ScalaCosti(SCALA_ESEMPIO, soglia_catastrofe=50.0, versione="t")
    assert not sc.e_catastrofico("RETRY_REQUIRED")
    assert sc.e_catastrofico("STATE_CORRUPTION")
    assert sc.magnitudine("IRRECOVERABLE") < sc.magnitudine("RETRY_REQUIRED")


def test_scala_costi_deve_essere_versionata():
    from contratto_sorgente import SCALA_ESEMPIO, ScalaCosti
    with pytest.raises(ValueError, match="versione"):
        ScalaCosti(SCALA_ESEMPIO, soglia_catastrofe=50.0, versione="")


def test_ordine_temporale_rifiuta_una_condizione_nata_dopo_la_scelta():
    from contratto_sorgente import OrdineViolato, Tempi
    with pytest.raises(OrdineViolato, match="NON precede"):
        Tempi(condition_observed=10.0, action_chosen=5.0).verifica()
    Tempi(condition_observed=1.0, action_chosen=2.0).verifica()


def test_un_campo_post_esecuzione_non_puo_essere_condizione():
    from contratto_sorgente import OrdineViolato, valida_condizioni
    with pytest.raises(OrdineViolato, match="a valle della"):
        valida_condizioni(["escalated"], {"escalated": "executed"})
    assert valida_condizioni(["diff"], {"diff": "condition_observed"}) == ["diff"]


def test_un_campo_senza_fase_dichiarata_e_rifiutato():
    from contratto_sorgente import utilizzabile_come_condizione
    with pytest.raises(ValueError, match="non dichiara in quale fase"):
        utilizzabile_come_condizione("misterioso", {})


def test_il_rilevatore_distingue_assente_da_non_osservabile():
    from detector import Stato, rileva_coda_pesante
    import numpy as np
    vero = rileva_coda_pesante(np.array([1.0, -1.0, -1000.0]), magnitudini_vere=True)
    niente = rileva_coda_pesante(np.array([1.0, -1.0]), magnitudini_vere=True)
    cieco = rileva_coda_pesante(np.array([1.0, -1.0]), magnitudini_vere=False)
    assert vero.stato is Stato.RILEVATO
    assert niente.stato is Stato.ASSENTE
    assert cieco.stato is Stato.NON_OSSERVABILE
    assert not cieco.presente and not niente.presente   # ma per ragioni diverse
