"""CASCADE - Hook dati reali (dominio-agnostico).

Permette di infilare un dataset vero (CSV/telemetria/business) al posto dei
dati toy `[0.5, 0.3]`, e di consumarlo nei layer:

- `load_observations`    : legge CSV -> tensori numerici puliti.
- `auto_type`            : inferisce numerico/booleano da una colonna.
- hook->pipeline         : la funzione `build_task_stream` trasforma le righe
                           del dataset in `Task` pronti per `CascadePipeline`.

In questo modo il benchmark passa da "esempi inventati" a dati reali del tuo
dominio mantenendo l'interfaccia dei layer identica.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Optional

import numpy as np


class DataError(ValueError):
    pass


def infer_column_type(values: list[str]) -> str:
    """Inferisce il tipo di una colonna: 'bool' | 'int' | 'float' | 'str'."""
    if not values:
        return "str"
    cleaned = [v.strip() for v in values if v.strip() != ""]
    if not cleaned:
        return "str"
    unique = {v.lower() for v in cleaned}
    if unique <= {"true", "false", "1", "0", "yes", "no", "si", "no"}:
        return "bool"
    try:
        for v in cleaned:
            float(v)
        # se tutti interi -> int
        if all(float(v).is_integer() for v in cleaned):
            return "int"
        return "float"
    except ValueError:
        return "str"


def parse_value(value: str, kind: str) -> Any:
    value = value.strip()
    if kind == "bool":
        return value.lower() in {"true", "1", "yes", "si"}
    if kind == "int":
        return int(float(value))
    if kind == "float":
        return float(value)
    return value


@dataclass
class LoadedTable:
    """Rappresentazione in memoria di un file di dati reali."""
    columns: list[str]
    types: dict[str, str]
    rows: list[dict[str, Any]]
    numeric_matrix: Optional[np.ndarray] = None
    label_column: Optional[str] = None

    def to_numeric(self, label_column: Optional[str] = None) -> "LoadedTable":
        """Converte le colonne numeriche in matrice; separa l'etichetta."""
        num_cols = [c for c in self.columns
                    if self.types.get(c) in ("int", "float")]
        if label_column and label_column in num_cols:
            num_cols = [c for c in num_cols if c != label_column]
        matrix = np.array(
            [[self.rows[i][c] for c in num_cols] for i in range(len(self.rows))],
            dtype=np.float64,
        )
        self.numeric_matrix = matrix
        if label_column:
            self.label_array = np.array(
                [self.rows[i][label_column] for i in range(len(self.rows))]
            )
        self.label_column = label_column
        return self

    @property
    def n_rows(self) -> int:
        return len(self.rows)


def load_observations(path: str, label_column: Optional[str] = None,
                      delimiter: str = ",") -> LoadedTable:
    """Legge un CSV di dati reali e ne inferisce i tipi.

    Args:
        path: percorso del file (CSV/TSV per delimiter).
        label_column: nome della colonna da usare come target (opzionale).
        delimiter: separatore (',' o '\\t').
    """
    try:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.reader(f, delimiter=delimiter)
            header = next(reader)
            header = [h.strip() for h in header]
            rows_raw = [row for row in reader]
    except FileNotFoundError:
        raise DataError(f"File non trovato: {path}")

    if not header:
        raise DataError("CSV senza intestazione")

    n_cols = len(header)
    col_data: dict[str, list[str]] = {h: [] for h in header}
    for row in rows_raw:
        for i, h in enumerate(header):
            val = row[i] if i < len(row) else ""
            col_data[h].append(val)

    types = {h: infer_column_type(col_data[h]) for h in header}
    rows: list[dict[str, Any]] = []
    for r in range(len(rows_raw)):
        rows.append({
            h: parse_value(col_data[h][r], types[h]) for h in header
        })

    tbl = LoadedTable(columns=header, types=types, rows=rows)
    tbl.to_numeric(label_column)
    return tbl


def load_observations_in_memory(data: list[dict[str, Any]],
                                label_column: Optional[str] = None) -> LoadedTable:
    """Come load_observations ma da una lista di dict (utile in test/protogonio
    quando i dati arrivano gia' in memoria, es. da un'API)."""
    if not data:
        raise DataError("Nessun dato")
    header = list(data[0].keys())
    col_data: dict[str, list[str]] = {h: [] for h in header}
    for row in data:
        for h in header:
            col_data[h].append(str(row.get(h, "")))
    types = {h: infer_column_type(col_data[h]) for h in header}
    rows = [{h: parse_value(col_data[h][i], types[h]) for h in header}
            for i in range(len(data))]
    tbl = LoadedTable(columns=header, types=types, rows=rows)
    tbl.to_numeric(label_column)
    return tbl


def observations_to_tensors(tbl: LoadedTable) -> tuple[np.ndarray, np.ndarray | None]:
    """Estrae (X, y_or_None) dal dataset reale per l'uso nei layer ML."""
    if tbl.numeric_matrix is None:
        tbl.to_numeric(tbl.label_column)
    X = tbl.numeric_matrix
    y = getattr(tbl, "label_array", None)
    return X, y


def data_split(tbl: LoadedTable, train_frac: float = 0.7,
               seed: int = 0) -> tuple["LoadedTable", "LoadedTable"]:
    """Divide in train/test senza mescolare il resto dell'oggetto."""
    rng = np.random.default_rng(seed)
    idx = rng.permutation(tbl.n_rows)
    n_train = int(tbl.n_rows * train_frac)
    train_idx, test_idx = idx[:n_train], idx[n_train:]
    split = []
    for part_idx in (train_idx, test_idx):
        rows = [tbl.rows[i] for i in part_idx]
        t = LoadedTable(columns=tbl.columns, types=tbl.types, rows=rows)
        t.to_numeric(tbl.label_column)
        split.append(t)
    return split[0], split[1]
