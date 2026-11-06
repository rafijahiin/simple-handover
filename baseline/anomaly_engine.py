from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import IntEnum
from typing import Any, Callable, Iterable, Mapping, Sequence


class Severity(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

    @property
    def label(self) -> str:
        return self.name.lower()


@dataclass(frozen=True)
class Anomaly:
    rule_id: str
    severity: Severity
    message: str
    record_id: str | None = None
    enumerator: str | None = None
    row_number: int | None = None
    fields: tuple[str, ...] = ()
    observed: Any = None
    expected: Any = None
    action: str | None = None
    category: str = "data_quality"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["severity"] = self.severity.label
        return data


RecordRule = Callable[[Mapping[str, Any], int], Iterable[Anomaly]]
DatasetRule = Callable[[Sequence[Mapping[str, Any]]], Iterable[Anomaly]]


class AnomalyEngine:
    """
    Deterministic anomaly engine.

    The engine deliberately separates:
    1. record-level rules,
    2. dataset/enumerator-level rules,
    3. severity and recommended action.

    This makes the results explainable and auditable. An AI model may later
    review free text, but it should not replace these deterministic rules.
    """

    def __init__(
        self,
        *,
        record_id_key: str | None = None,
        enumerator_key: str | None = None,
    ) -> None:
        self.record_id_key = record_id_key
        self.enumerator_key = enumerator_key
        self._record_rules: list[RecordRule] = []
        self._dataset_rules: list[DatasetRule] = []

    def add_record_rule(self, rule: RecordRule) -> "AnomalyEngine":
        self._record_rules.append(rule)
        return self

    def add_dataset_rule(self, rule: DatasetRule) -> "AnomalyEngine":
        self._dataset_rules.append(rule)
        return self

    def scan(self, records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        anomalies: list[Anomaly] = []

        for index, record in enumerate(records, start=2):
            for rule in self._record_rules:
                anomalies.extend(rule(record, index))

        for rule in self._dataset_rules:
            anomalies.extend(rule(records))

        anomalies.sort(
            key=lambda a: (
                -int(a.severity),
                a.enumerator or "",
                a.row_number or 0,
                a.rule_id,
            )
        )

        severity_counts = Counter(a.severity.label for a in anomalies)
        category_counts = Counter(a.category for a in anomalies)
        rule_counts = Counter(a.rule_id for a in anomalies)

        by_record: dict[str, list[dict[str, Any]]] = defaultdict(list)
        by_enumerator: dict[str, Counter[str]] = defaultdict(Counter)

        for anomaly in anomalies:
            if anomaly.record_id:
                by_record[anomaly.record_id].append(anomaly.to_dict())
            if anomaly.enumerator:
                by_enumerator[anomaly.enumerator][anomaly.severity.label] += 1

        risk_score = sum(int(a.severity) for a in anomalies)
        max_possible = max(1, len(records) * 12)
        normalized_risk = min(100.0, round((risk_score / max_possible) * 100, 1))

        return {
            "records_scanned": len(records),
            "anomaly_count": len(anomalies),
            "risk_score": normalized_risk,
            "summary": {
                "by_severity": {
                    name: severity_counts.get(name, 0)
                    for name in ("critical", "high", "medium", "low")
                },
                "by_category": dict(category_counts.most_common()),
                "top_rules": dict(rule_counts.most_common(15)),
            },
            "enumerators": {
                name: {
                    severity: counts.get(severity, 0)
                    for severity in ("critical", "high", "medium", "low")
                }
                for name, counts in sorted(by_enumerator.items())
            },
            "record_flags": dict(by_record),
            "anomalies": [a.to_dict() for a in anomalies],
        }


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def normalized_text(value: Any) -> str:
    return clean_text(value).casefold()


def as_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = clean_text(value).replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def as_int(value: Any) -> int | None:
    number = as_number(value)
    if number is None:
        return None
    return int(number)


def as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    text = normalized_text(value)
    if text in {"1", "yes", "y", "true", "selected", "checked"}:
        return True
    if text in {"0", "no", "n", "false", "not selected", "unchecked", ""}:
        return False
    return None


def as_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    text = clean_text(value)
    if not text:
        return None
    candidates = (
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%m/%d/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
    )
    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        pass
    for fmt in candidates:
        try:
            return datetime.strptime(normalized, fmt)
        except ValueError:
            continue
    return None


def record_context(
    record: Mapping[str, Any],
    row_number: int | None,
    record_id_key: str | None,
    enumerator_key: str | None,
) -> dict[str, Any]:
    record_id = clean_text(record.get(record_id_key)) if record_id_key else ""
    enumerator = clean_text(record.get(enumerator_key)) if enumerator_key else ""
    return {
        "record_id": record_id or None,
        "enumerator": enumerator or None,
        "row_number": row_number,
    }
