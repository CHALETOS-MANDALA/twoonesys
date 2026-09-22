"""Test dell'hook dati reali."""

import numpy as np
import pytest

from cascade.data_loader import (
    DataError,
    infer_column_type,
    load_observations,
    load_observations_in_memory,
    parse_value,
    data_split,
)


def test_infer_types():
    assert infer_column_type(["1", "0", "1"]) == "bool"
    assert infer_column_type(["1", "2", "3"]) == "int"
    assert infer_column_type(["1.5", "2.0", "3.3"]) == "float"
    assert infer_column_type(["a", "b", "a"]) == "str"


def test_parse_value():
    assert parse_value("si", "bool") is True
    assert parse_value("0", "bool") is False
    assert parse_value("42", "int") == 42
    assert parse_value("3.14", "float") == 3.14


def test_load_in_memory_numeric():
    data = [
        {"pos": "0.5", "vel": "0.1", "label": "1"},
        {"pos": "-0.2", "vel": "0.3", "label": "0"},
        {"pos": "0.0", "vel": "0.0", "label": "1"},
    ]
    tbl = load_observations_in_memory(data, label_column="label")
    assert tbl.n_rows == 3
    assert tbl.numeric_matrix.shape == (3, 2)  # pos, vel (label esclusa)
    assert list(tbl.label_array) == [1, 0, 1]


def test_label_excluded_from_matrix():
    data = [{"a": "1", "b": "2", "target": "0"},
            {"a": "3", "b": "4", "target": "1"}]
    tbl = load_observations_in_memory(data, label_column="target")
    assert tbl.numeric_matrix.shape == (2, 2)
    assert tbl.numeric_matrix[0, 0] == 1.0


def test_split_preserves_total():
    data = [{"x": str(i), "y": str(i)} for i in range(100)]
    tbl = load_observations_in_memory(data)
    train, test = data_split(tbl, train_frac=0.7, seed=0)
    assert train.n_rows + test.n_rows == 100
    assert train.n_rows == 70


def test_missing_file_raises():
    with pytest.raises(DataError):
        load_observations("file_inesistente.csv")


def test_empty_data_raises():
    with pytest.raises(DataError):
        load_observations_in_memory([])
