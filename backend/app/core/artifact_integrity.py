"""Read-only, keyed cross-artifact checks independent of generated solver code.

These checks establish consistency, not the correctness of the source model.
Relations are explicit except for an unambiguous distance-matrix projection.
"""

from __future__ import annotations

import csv
import math
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path


class ArtifactIntegrityError(ValueError):
    """A declared or unambiguous artifact relationship is inconsistent."""


@dataclass
class Table:
    name: str
    columns: list[str]
    rows: list[dict[str, str]]


def _read(root: Path, name: str) -> Table:
    path = (root / name).resolve()
    if (
        Path(name).is_absolute()
        or not path.is_relative_to(root.resolve())
        or path.suffix.lower() != ".csv"
    ):
        raise ArtifactIntegrityError(f"不允许的校验路径：{name}")
    try:
        if path.stat().st_size > 20_000_000:
            raise ArtifactIntegrityError(f"{name} 超过独立校验大小上限，需拆分校验表")
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            columns = reader.fieldnames or []
            if not columns or len(set(columns)) != len(columns):
                raise ArtifactIntegrityError(f"{name} 表头为空或重复")
            rows = []
            for row in reader:
                if None in row or None in row.values():
                    raise ArtifactIntegrityError(f"{name} 行列数量不一致")
                rows.append(row)
                if len(rows) > 100_000:
                    raise ArtifactIntegrityError(f"{name} 超过独立校验行数上限")
        if not rows:
            raise ArtifactIntegrityError(f"{name} 没有可校验数据行")
        return Table(name, columns, rows)
    except (OSError, UnicodeError, csv.Error) as exc:
        raise ArtifactIntegrityError(
            f"无法读取校验产物 {name}：{type(exc).__name__}"
        ) from exc


def _keyed(table: Table, column: str) -> dict[str, dict[str, str]]:
    if column not in table.columns:
        raise ArtifactIntegrityError(f"{table.name} 缺少实体编号列 {column}")
    result = {}
    for row in table.rows:
        key = row[column].strip()
        if not key or key in result:
            raise ArtifactIntegrityError(
                f"{table.name}.{column} 编号为空或重复：{key!r}"
            )
        result[key] = row
    return result


def _number(value, label: str) -> float:
    try:
        number = float(value)
    except (ValueError, TypeError) as exc:
        raise ArtifactIntegrityError(f"{label} 不是数值：{value!r}") from exc
    if isinstance(value, bool) or not math.isfinite(number):
        raise ArtifactIntegrityError(f"{label} 必须是有限数值")
    return number


def _unit_factor(unit: str) -> float:
    factors = {"m": 1.0, "km": 1000.0, "cm": 0.01, "mm": 0.001, "1": 1.0}
    if unit not in factors:
        raise ArtifactIntegrityError(
            f"不支持的比较单位 {unit!r}；请导出统一单位的校验列"
        )
    return factors[unit]


def _rounding_tolerance(
    actual: str, reference: str, scale_a: float, scale_b: float
) -> float:
    """Allow only the rounding implied by unequal exported decimal precision.

    Equally precise cells must match; a model-supplied tolerance is never used.
    This prevents a one-decimal projection of a six-decimal matrix from becoming
    a false scientific failure while still detecting shifted entity keys.
    """

    def resolution(value: str, scale: float) -> float:
        exponent = Decimal(value).as_tuple().exponent
        if not isinstance(exponent, int) or not -308 <= exponent <= 308:
            raise ArtifactIntegrityError("导出数值精度超出有限浮点校验范围")
        result = (10.0**exponent) * scale
        if not math.isfinite(result) or result <= 0:
            raise ArtifactIntegrityError("导出数值精度超出有限浮点校验范围")
        return result

    resolution_a = resolution(actual, scale_a)
    resolution_b = resolution(reference, scale_b)
    if math.isclose(resolution_a, resolution_b, rel_tol=1e-12, abs_tol=0):
        return 1e-9
    return max(resolution_a, resolution_b) / 2 + 1e-9


def _check(relation: dict, tables: dict[str, Table]) -> dict:
    kind = relation.get("kind")
    if kind not in {"matrix_lookup", "keyed_column"}:
        raise ArtifactIntegrityError(
            "artifact_relations.kind 必须为 matrix_lookup 或 keyed_column"
        )
    try:
        actual = tables[relation["table"]]
        reference = tables[relation["reference"]]
        value = relation["value"]
        actual_rows = _keyed(actual, relation["key"])
        reference_rows = _keyed(reference, relation["reference_key"])
        coverage = relation.get("coverage", "exact")
        if coverage not in {"exact", "subset"}:
            raise ArtifactIntegrityError("coverage 必须是 exact 或 subset")
        expected_keys = set(reference_rows)
        if kind == "matrix_lookup":
            expected_keys.discard(str(relation["anchor"]))
        if coverage == "exact" and set(actual_rows) != expected_keys:
            raise ArtifactIntegrityError(
                f"{actual.name} 实体编号覆盖不完整或多出编号；子集需显式声明 coverage=subset"
            )
        a_unit = relation.get("unit", "1")
        b_unit = relation.get("reference_unit", a_unit)
        if (a_unit == "1") != (b_unit == "1"):
            raise ArtifactIntegrityError("无量纲值不能与长度值直接比较")
        scale_a, scale_b = _unit_factor(a_unit), _unit_factor(b_unit)
        # These are copies/projections, not different physical approximations.
        differences = []
        for key, row in actual_rows.items():
            if kind == "matrix_lookup":
                anchor = str(relation["anchor"])
                expected = reference_rows[anchor][key]
            else:
                expected = reference_rows[key][relation["reference_value"]]
            a = _number(row[value], f"{actual.name}[{key}].{value}") * scale_a
            b = _number(expected, f"{reference.name}[{key}]") * scale_b
            if not math.isfinite(a) or not math.isfinite(b):
                raise ArtifactIntegrityError("单位换算后出现非有限数值")
            tolerance = _rounding_tolerance(row[value], expected, scale_a, scale_b)
            if not math.isclose(a, b, rel_tol=1e-9, abs_tol=tolerance):
                differences.append(
                    f"{key}: 导出={row[value]} {a_unit}, 参照={expected} {b_unit}"
                )
        if differences:
            raise ArtifactIntegrityError(
                f"实体编号一致性失败：{actual.name}.{value} 对照 {reference.name}，"
                f"{len(differences)}/{len(actual_rows)} 行不一致；"
                + "；".join(differences[:5])
                + "。修复生成源码的键映射并重新生成受影响产物，不能只改报告。"
            )
        return {
            "table": actual.name,
            "reference": reference.name,
            "rows": len(actual_rows),
            "kind": kind,
        }
    except (KeyError, TypeError) as exc:
        raise ArtifactIntegrityError(f"关系字段、实体编号或数值列缺失：{exc}") from exc


def _distance_unit(name: str) -> str | None:
    match = re.search(r"(?:distance|距离|dist).*?[_（(](km|m)(?:[）)]|$)", name, re.I)
    return match.group(1).lower() if match else None


def _infer(tables: dict[str, Table]) -> list[dict]:
    """Only infer a full N-1 entity projection with a unique remaining anchor.

    No positional indexing and no first-row/zero-distance anchor heuristics.
    Ambiguous semantic relationships must be declared explicitly by the solver.
    """
    matrices = []
    for table in tables.values():
        unit = _distance_unit(Path(table.name).stem)
        if not unit or "matrix" not in table.name.lower() or len(table.columns) < 3:
            continue
        keys = [row[table.columns[0]].strip() for row in table.rows]
        if len(keys) == len(set(keys)) and set(keys) == set(table.columns[1:]):
            matrices.append((table, unit, set(keys)))
    relations = []
    for table in tables.values():
        values = [(column, _distance_unit(column)) for column in table.columns]
        for value, unit in values:
            if unit is None:
                continue
            candidates = []
            for matrix, matrix_unit, ids in matrices:
                if (
                    matrix.name == table.name
                    or Path(matrix.name).parent != Path(table.name).parent
                ):
                    continue
                for key in table.columns:
                    actual_ids = {row[key].strip() for row in table.rows}
                    remaining = ids - actual_ids
                    if (
                        len(actual_ids) >= 2
                        and actual_ids < ids
                        and len(remaining) == 1
                    ):
                        candidates.append(
                            {
                                "kind": "matrix_lookup",
                                "table": table.name,
                                "key": key,
                                "value": value,
                                "unit": unit,
                                "reference": matrix.name,
                                "reference_key": matrix.columns[0],
                                "reference_unit": matrix_unit,
                                "anchor": next(iter(remaining)),
                            }
                        )
            if len(candidates) == 1:
                relations.extend(candidates)
    return relations


def validate_artifact_integrity(root: Path, report: dict) -> tuple[dict, ...]:
    """Validate declared CSV relations and discoverable distance projections.

    Only declared artifacts are scanned; original attachments and unrelated
    stages are never recursively scanned or modified. Empty result means no
    supported relationship was checked, never proof of numerical correctness.
    """
    relations = report.get("artifact_relations", [])
    if not isinstance(relations, list) or any(
        not isinstance(r, dict) for r in relations
    ):
        raise ArtifactIntegrityError("artifact_relations 必须为关系对象数组")
    if len(relations) > 100:
        raise ArtifactIntegrityError("单阶段最多声明 100 个产物关系")
    names = set()
    for relation in relations:
        for field in ("table", "reference"):
            name = relation.get(field)
            if not isinstance(name, str) or not name:
                raise ArtifactIntegrityError(f"artifact_relations 缺少路径 {field}")
            names.add(name)
    for name in (
        report.get("artifacts", []) if isinstance(report.get("artifacts"), list) else []
    ):
        if isinstance(name, str) and name.lower().endswith(".csv"):
            names.add(name)
    if len(names) > 100:
        raise ArtifactIntegrityError("单阶段独立校验最多读取 100 张 CSV 表")
    tables = {}
    cells = 0
    for name in sorted(names):
        table = _read(root, name)
        cells += len(table.columns) * len(table.rows)
        if cells > 1_000_000:
            raise ArtifactIntegrityError(
                "本阶段 CSV 超过独立校验总大小上限，请拆分校验表"
            )
        tables[name] = table
    discovered = _infer(tables)
    checks, errors = [], []
    for relation in relations + [r for r in discovered if r not in relations]:
        try:
            checks.append(_check(relation, tables))
        except ArtifactIntegrityError as exc:
            errors.append(str(exc))
    if errors:
        raise ArtifactIntegrityError("；".join(errors[:10]))
    return tuple(checks)
