"""CASCADE - Layer 1: Motore Causale (Pearl Engine).

Implementazione reale della scala d'abduzione di Pearl:
1. Inferenza            -> credenze posteriori P(X | e)
2. Intervento (do)      -> P(Y | do(X=x)) con grafo mutilato
3. Controfattuale       -> abduzione -> azione -> predizione

A differenza del prototipo:
- i nodi portano distribuzioni di probabilita' reali (CPD), non valori deterministici;
- l'inferenza e' esatta (enumerazione su grafo topologico);
- i controfattuali eseguono i 3 passi completi ripartendo dall'evidenza osservata.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

import networkx as nx

# --------------------------------------------------------------------------- #
# Distribuzione
# --------------------------------------------------------------------------- #


class CPD:
    """CPD tabellare: P(self.variable | parents)."""

    def __init__(self, variable: str, parents: list[str], table: Mapping[tuple, Mapping[Any, float]]):
        self.variable = variable
        self.parents = parents
        self.table = table

    def prob(self, value: Any, parent_values: Mapping[str, Any]) -> float:
        if not self.parents:
            dist: Mapping[Any, float] = next(iter(self.table.values()))
            return dist.get(value, 0.0)
        key = tuple(parent_values[p] for p in self.parents)
        dist = self.table.get(key)
        if dist is None:  # pragma: no cover
            raise KeyError(f"Nessuna riga CPD per {self.variable} con parents {key}")
        return dist.get(value, 0.0)

    def support(self) -> list[Any]:
        if not self.parents:
            return list(next(iter(self.table.values())).keys())
        vals: set[Any] = set()
        for dist in self.table.values():
            vals.update(dist.keys())
        return list(vals)

    @staticmethod
    def point(variable: str, value: Any) -> "CPD":
        """CPD degenere P(var=value)=1 (per interventi)."""
        return CPD(variable, [], {(): {value: 1.0}})


class CausalNode:
    def __init__(self, id: str, cpd: CPD | None = None,
                 values: list[Any] | None = None):
        self.id = id
        self.cpd = cpd
        self.values: list[Any] = values or (cpd.support() if cpd else [True, False])

    @property
    def is_exogenous(self) -> bool:
        return self.cpd is None


# --------------------------------------------------------------------------- #
# Modello causale
# --------------------------------------------------------------------------- #


class CausalModel:
    def __init__(self) -> None:
        self.graph = nx.DiGraph()
        self.nodes: dict[str, CausalNode] = {}
        # ordine topologico mantenuto per l'enumerazione (valido finche' il
        # grafo e' riconosciuto DAG; viene ricalcolato su ogni mutilazione).
        self._topo: list[str] = []

    def add_variable(self, node: CausalNode, parents: list[str] | None = None) -> "CausalModel":
        parents = parents or []
        if node.cpd is not None and set(node.cpd.parents) != set(parents):
            raise ValueError(
                f"Parents del CPD di {node.id} non coincidono con gli archi"
            )
        self.nodes[node.id] = node
        self.graph.add_node(node.id)
        for p in parents:
            self.graph.add_edge(p, node.id)
        if not nx.is_directed_acyclic_graph(self.graph):
            raise ValueError(f"Ciclo causale rilevato aggiungendo {node.id}")
        self._topo = list(nx.topological_sort(self.graph))
        return self

    def mutilated(self, intervention: Mapping[str, Any]) -> "CausalModel":
        m = CausalModel()
        m.graph = self.graph.copy()
        m.nodes = dict(self.nodes)
        for var, val in intervention.items():
            for parent in list(m.graph.predecessors(var)):
                m.graph.remove_edge(parent, var)
            m.nodes[var] = CausalNode(var, cpd=CPD.point(var, val), values=[val])
        m._topo = list(nx.topological_sort(m.graph))
        return m

    # -- inferenza ---------------------------------------------------------- #
    def posterior(self, query: str, evidence: Mapping[str, Any] | None = None) -> dict[Any, float]:
        """P(query | evidence), esatta."""
        evidence = evidence or {}
        joint = self._joint_unnormalized(evidence)
        agg: dict[Any, float] = {}
        for assignment, prob in joint.items():
            agg[assignment[query]] = agg.get(assignment[query], 0.0) + prob
        total = sum(agg.values())
        if total == 0:
            raise ZeroDivisionError("Evidenza impossibile (probabilita' zero)")
        return {v: agg[v] / total for v in agg}

    def do(self, query: str, intervention: Mapping[str, Any],
           evidence: Mapping[str, Any] | None = None) -> dict[Any, float]:
        """P(query | do(intervention), evidence) sul modello mutilato."""
        return self.mutilated(intervention).posterior(query, evidence)

    def counterfactual(self, query: str, intervention: Mapping[str, Any],
                       evidence: Mapping[str, Any]) -> dict[Any, float]:
        """P(query_do(interv) | evidence). Abduzione -> Azione -> Predizione.

        Passo 1 Abduzione: calcola il posteriore congiunto P(V | evidence).
        Passo 2 Azione:    mutila il modello con l'intervento.
        Passo 3 Predizione: per ogni stato latente abdotto con peso>0, ricalcola
                            la distribuzione di `query` su tale stato e ne fa la
                            media pesata.
        """
        posterior_latent = self.posterior_joint(evidence)
        m = self.mutilated(intervention)
        results: dict[Any, float] = {}
        for assignment, w in posterior_latent.items():
            # Evidenza di predizione = soli valori latenti ESOGENI non-intervenuti
            # (l'evidenza pura da abduzione). Le variabili endogene osservate
            # sono gia' codificate nel peso `w`; quelle intervenute sono fissate
            # dall'intervento. Condizionare anche sugli endogeni dopo la
            # mutilazione provocherebbe contraddizioni (probabilita' zero).
            latent_evidence = {
                k: v
                for k, v in assignment.items()
                if k not in intervention and self.nodes[k].is_exogenous
            }
            dist = m.posterior(query, evidence=latent_evidence)
            for v, p in dist.items():
                results[v] = results.get(v, 0.0) + w * p
        return _normalize(results)

    def posterior_joint(self, evidence: Mapping[str, Any] | None = None) -> dict[Assignment, float]:
        """P(V | evidence) come mapping {assignment_dict: prob}."""
        evidence = evidence or {}
        joint = self._joint_unnormalized(evidence)
        return _normalize(joint)

    def _joint_unnormalized(self, evidence: Mapping[str, Any]) -> dict[dict, float]:
        result: dict[dict, float] = {}
        for assignment in self._enumerate(list(self._topo), evidence):
            prob = 1.0
            for var in self._topo:
                node = self.nodes[var]
                if node.cpd is None:
                    prob *= 1.0 / len(node.values) if node.values else 1.0
                    continue
                parent_vals = {p: assignment[p] for p in node.cpd.parents}
                prob *= node.cpd.prob(assignment[var], parent_vals)
            result[Assignment(assignment)] = prob
        return result

    def _enumerate(self, var_order: list[str], evidence: Mapping[str, Any]):
        if not var_order:
            yield {}
            return
        var, rest = var_order[0], var_order[1:]
        if var in evidence:
            for tail in self._enumerate(rest, evidence):
                yield {var: evidence[var], **tail}
        else:
            for val in self.nodes[var].values:
                for tail in self._enumerate(rest, evidence):
                    yield {var: val, **tail}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


class Assignment:
    """Assegnazione hashable che incapsula un dict {'var': valore}."""

    __slots__ = ("_data",)

    def __init__(self, data: Mapping[str, Any]):
        self._data = dict(data)

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __iter__(self):
        return iter(self._data.items())

    def items(self):
        return self._data.items()

    def __hash__(self) -> int:
        return hash(frozenset(self._data.items()))

    def __eq__(self, other) -> bool:
        return isinstance(other, Assignment) and self._data == other._data

    def __repr__(self) -> str:  # pragma: no cover
        return f"Assignment({self._data!r})"


def _normalize(d: dict[Any, float]) -> dict[Any, float]:
    total = sum(d.values())
    if total == 0:
        return {k: 0.0 for k in d}
    return {k: v / total for k, v in d.items()}


def _restrict(evidence: Mapping[str, Any], latent: Mapping[str, Any],
              exclude: Mapping[str, Any]) -> dict[str, Any]:
    """Blocca i nodi di `exclude` (intervenuti, hanno valore fissato) usando il
    valore latente osservato, evitando di sovrascrivere l'intervento."""
    out: dict[str, Any] = {}
    for k, v in latent.items():
        if k not in exclude:
            out[k] = v
    for k, v in evidence.items():
        if k not in exclude:
            out[k] = v
    return out


# --------------------------------------------------------------------------- #
# Esempio autonomo: pioggia / sprinkler / prato bagnato
# --------------------------------------------------------------------------- #


def sprinkler_model() -> CausalModel:
    m = CausalModel()
    m.add_variable(CausalNode("pioggia", values=[True, False]))
    m.add_variable(CausalNode("sprinkler", values=[True, False]))
    m.add_variable(
        CausalNode("bagnato", cpd=CPD(
            "bagnato",
            ["pioggia", "sprinkler"],
            {
                (True, True): {True: 0.99, False: 0.01},
                (True, False): {True: 0.95, False: 0.05},
                (False, True): {True: 0.90, False: 0.10},
                (False, False): {True: 0.0, False: 1.0},
            },
        )),
        parents=["pioggia", "sprinkler"],
    )
    return m


if __name__ == "__main__":
    m = sprinkler_model()
    print("P(bagnato) =", m.posterior("bagnato"))
    print("P(pioggia | bagnato=True) =", m.posterior("pioggia", {"bagnato": True}))
    print("P(bagnato | do(sprinkler=False)) =",
          m.do("bagnato", {"sprinkler": False}))
    print("Controfattuale: P(bagnato | do(pioggia=False), bagnato=True) =",
          m.counterfactual("bagnato", {"pioggia": False}, {"bagnato": True}))
