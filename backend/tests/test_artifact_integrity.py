"""Mutation tests: successful execution/self-reported pass cannot hide wrong joins."""

import csv
import json
from itertools import permutations

import pytest

from app.core.artifact_integrity import (
    ArtifactIntegrityError,
    validate_artifact_integrity,
)
from app.core.deliverable_contract import (
    ArtifactConsistencyValidationError,
    build_stage_contract,
    get_repair_execution_limit,
    validate_question_deliverables,
)


def write_csv(root, name, rows):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        csv.writer(stream).writerows(rows)


@pytest.fixture
def exports(tmp_path):
    # Nonordinal, zero-prefixed keys; matrix origin deliberately isn't row zero.
    write_csv(
        tmp_path,
        "cleaned/distance_matrix_m.csv",
        [
            ["编号", "001", "base", "007"],
            ["007", 6, 9, 0],
            ["001", 0, 4, 6],
            ["base", 4, 0, 9],
        ],
    )
    write_csv(
        tmp_path,
        "cleaned/geometry.csv",
        [
            ["entity", "水平距离_m"],
            ["007", 9],
            ["001", 4],
        ],
    )
    return {"artifacts": ["cleaned/geometry.csv", "cleaned/distance_matrix_m.csv"]}


def test_keyed_checks_ignore_row_order_and_preserve_zero_prefixes(tmp_path, exports):
    for rows in permutations([["001", 4], ["007", 9]]):
        write_csv(tmp_path, "cleaned/geometry.csv", [["entity", "水平距离_m"], *rows])
        checks = validate_artifact_integrity(tmp_path, exports)
        assert len(checks) == 1 and checks[0]["rows"] == 2


@pytest.mark.parametrize("values", [[0, 4], [4, 9], ["nan", 4], [float("inf"), 4]])
def test_shifted_or_nonfinite_exports_are_rejected(tmp_path, exports, values):
    write_csv(
        tmp_path,
        "cleaned/geometry.csv",
        [
            ["entity", "水平距离_m"],
            ["007", values[0]],
            ["001", values[1]],
        ],
    )
    with pytest.raises(ArtifactIntegrityError):
        validate_artifact_integrity(tmp_path, exports)


def test_duplicate_entity_is_not_silently_overwritten(tmp_path, exports):
    write_csv(
        tmp_path,
        "cleaned/geometry.csv",
        [
            ["entity", "水平距离_m"],
            ["007", 9],
            ["001", 4],
            ["001", 4],
        ],
    )
    with pytest.raises(ArtifactIntegrityError, match="重复"):
        validate_artifact_integrity(tmp_path, exports)


def test_ambiguous_reference_does_not_invent_origin_or_semantics(tmp_path, exports):
    write_csv(
        tmp_path,
        "cleaned/other_distance_matrix_m.csv",
        [
            ["编号", "001", "base", "007"],
            ["001", 0, 44, 66],
            ["base", 44, 0, 99],
            ["007", 66, 99, 0],
        ],
    )
    exports["artifacts"].append("cleaned/other_distance_matrix_m.csv")
    assert validate_artifact_integrity(tmp_path, exports) == ()


def relation_report():
    return {
        "artifact_relations": [
            {
                "kind": "keyed_column",
                "table": "values.csv",
                "key": "entity",
                "value": "length",
                "unit": "km",
                "reference": "source.csv",
                "reference_key": "id",
                "reference_value": "length",
                "reference_unit": "m",
            }
        ]
    }


def test_declared_cross_table_join_converts_units_and_ignores_positions(tmp_path):
    write_csv(tmp_path, "source.csv", [["id", "length"], ["001", 1250], ["007", 9000]])
    write_csv(tmp_path, "values.csv", [["entity", "length"], ["007", 9], ["001", 1.25]])
    assert validate_artifact_integrity(tmp_path, relation_report())[0]["rows"] == 2
    write_csv(tmp_path, "values.csv", [["entity", "length"], ["001", 9], ["007", 1.25]])
    report = relation_report()
    report["artifact_relations"][0]["tolerance"] = 1e20
    with pytest.raises(ArtifactIntegrityError, match="2/2"):
        validate_artifact_integrity(tmp_path, report)


@pytest.mark.parametrize(
    "defect", ["missing", "duplicate", "blank", "bad_unit", "escape", "bad_relation"]
)
def test_declared_relations_fail_closed(tmp_path, defect):
    write_csv(tmp_path, "source.csv", [["id", "length"], ["001", 1000]])
    rows = [["entity", "length"], ["001", 1]]
    if defect == "missing":
        rows[1][0] = "002"
    if defect == "duplicate":
        rows.append(["001", 1])
    if defect == "blank":
        rows[1][0] = ""
    write_csv(tmp_path, "values.csv", rows)
    report = relation_report()
    relation = report["artifact_relations"][0]
    if defect == "bad_unit":
        relation["unit"] = "seconds"
    if defect == "escape":
        relation["reference"] = "../source.csv"
    if defect == "bad_relation":
        relation["kind"] = "trust_model"
    with pytest.raises(ArtifactIntegrityError):
        validate_artifact_integrity(tmp_path, report)


@pytest.mark.parametrize("status", ["pass", "manual_review"])
def test_outer_gate_still_checks_numbers_when_schema_is_wrong(
    tmp_path, exports, status
):
    write_csv(
        tmp_path,
        "cleaned/geometry.csv",
        [
            ["entity", "水平距离_m"],
            ["007", 4],
            ["001", 0],
        ],
    )
    report = {**exports, "status": status, "problem_type": "mechanism_data_hybrid"}
    (tmp_path / "eda_quality_report.json").write_text(
        json.dumps(report), encoding="utf-8"
    )
    contract = build_stage_contract("eda")
    with pytest.raises(ArtifactConsistencyValidationError, match="2/2") as failure:
        validate_question_deliverables(tmp_path, contract)
    assert "problem_type" in str(failure.value)
    assert get_repair_execution_limit(tmp_path, contract, failure.value) == 4


def test_empty_coverage_is_not_claimed_as_a_numerical_check(tmp_path):
    assert validate_artifact_integrity(tmp_path, {"artifacts": []}) == ()


def test_missing_output_rows_require_explicit_subset_contract(tmp_path):
    write_csv(tmp_path, "source.csv", [["id", "length"], ["001", 1000], ["007", 9000]])
    write_csv(tmp_path, "values.csv", [["entity", "length"], ["001", 1]])
    report = relation_report()
    with pytest.raises(ArtifactIntegrityError, match="覆盖不完整"):
        validate_artifact_integrity(tmp_path, report)
    report["artifact_relations"][0]["coverage"] = "subset"
    assert validate_artifact_integrity(tmp_path, report)[0]["rows"] == 1


@pytest.mark.parametrize("actual,passes", [("1.2500", True), ("1.2501", False)])
def test_unit_conversion_respects_export_precision_but_not_wrong_values(
    tmp_path, actual, passes
):
    write_csv(tmp_path, "source.csv", [["id", "length"], ["001", "1250.04"]])
    write_csv(tmp_path, "values.csv", [["entity", "length"], ["001", actual]])
    if passes:
        assert validate_artifact_integrity(tmp_path, relation_report())[0]["rows"] == 1
    else:
        with pytest.raises(ArtifactIntegrityError):
            validate_artifact_integrity(tmp_path, relation_report())


@pytest.mark.parametrize("value", ["0e9999", "1e308"])
def test_numeric_overflow_cannot_turn_into_an_infinite_tolerance(tmp_path, value):
    write_csv(tmp_path, "source.csv", [["id", "length"], ["001", "1"]])
    write_csv(tmp_path, "values.csv", [["entity", "length"], ["001", value]])
    with pytest.raises(ArtifactIntegrityError):
        validate_artifact_integrity(tmp_path, relation_report())
