from __future__ import annotations

from datetime import date
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from .dashboard_metrics import (
    DashboardSnapshot,
    canonical_route_key,
    display_route_name,
    fold_text,
    normalize_region,
)
from .history_storage import _create_supabase_client, _response_rows


DEFAULT_DASHBOARD_MONTHS = 6
MAX_DASHBOARD_MONTHS = 24


class DashboardStorageError(RuntimeError):
    """Base error for route-dashboard persistence."""


class DashboardStorageConfigurationError(DashboardStorageError):
    """Raised when neither local data nor Supabase can be initialized."""


class DashboardStorageOperationError(DashboardStorageError):
    """Raised when dashboard data cannot be read or written."""


class DashboardRouteNotFoundError(DashboardStorageOperationError):
    """Raised when no stored snapshot matches a route."""


def _month_start(value: object) -> date:
    try:
        return date.fromisoformat(str(value)[:10]).replace(day=1)
    except (TypeError, ValueError) as exc:
        raise DashboardStorageOperationError(
            "dashboard snapshot has an invalid measurement_month"
        ) from exc


def _shift_month(value: date, offset: int) -> date:
    ordinal = value.year * 12 + value.month - 1 + offset
    return date(ordinal // 12, ordinal % 12 + 1, 1)


def _validated_month_count(value: int) -> int:
    try:
        months = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("months must be an integer") from exc
    if months < 1 or months > MAX_DASHBOARD_MONTHS:
        raise ValueError(f"months must be between 1 and {MAX_DASHBOARD_MONTHS}")
    return months


def _optional_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise DashboardStorageOperationError(
            "dashboard snapshot contains an invalid numeric value"
        ) from exc


def _clean_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    assessment = row.get("assessment")
    if assessment not in (None, "Đạt", "Không đạt"):
        raise DashboardStorageOperationError(
            "dashboard snapshot contains an invalid assessment"
        )
    warnings = row.get("warnings") or []
    if not isinstance(warnings, list):
        warnings = []
    return {
        "region": normalize_region(row.get("region")),
        "route_key": str(row.get("route_key") or ""),
        "route_name": display_route_name(row.get("route_name")),
        "measurement_month": _month_start(row.get("measurement_month")).isoformat(),
        "worst_event_loss_db": _optional_float(row.get("worst_event_loss_db")),
        "worst_event_position_km": _optional_float(row.get("worst_event_position_km")),
        "utilization_percent": _optional_float(row.get("utilization_percent")),
        "dkd_core_percent": _optional_float(row.get("dkd_core_percent")),
        "dkd_required_percent": _optional_float(row.get("dkd_required_percent")),
        "assessment": assessment,
        "source_file": str(row.get("source_file") or ""),
        "source_sheet": str(row.get("source_sheet") or ""),
        "source_format": str(row.get("source_format") or "unknown"),
        "source_sha256": str(row.get("source_sha256") or ""),
        "warnings": [str(item) for item in warnings],
    }


def aggregate_route_series(
    rows: Iterable[dict[str, Any]],
    *,
    region: str,
    route_key: str,
    months: int = DEFAULT_DASHBOARD_MONTHS,
) -> dict[str, Any]:
    normalized_region = normalize_region(region)
    normalized_key = canonical_route_key(route_key) if "--" not in route_key else route_key
    count = _validated_month_count(months)
    cleaned = [
        _clean_snapshot(row)
        for row in rows
        if normalize_region(row.get("region")) == normalized_region
        and str(row.get("route_key") or "") == normalized_key
    ]
    if not cleaned:
        raise DashboardRouteNotFoundError("dashboard route was not found")

    anchor = max(_month_start(row["measurement_month"]) for row in cleaned)
    first = _shift_month(anchor, -(count - 1))
    route_name = sorted(
        cleaned,
        key=lambda row: (
            _month_start(row["measurement_month"]),
            bool(row.get("dkd_core_percent") is not None),
            row.get("source_file") or "",
            row.get("source_sheet") or "",
        ),
    )[-1]["route_name"]

    month_rows: list[dict[str, Any]] = []
    for offset in range(count):
        current = _shift_month(first, offset)
        candidates = [
            row for row in cleaned if _month_start(row["measurement_month"]) == current
        ]
        loss_candidates = [
            row for row in candidates if row["worst_event_loss_db"] is not None
        ]
        worst = max(
            loss_candidates,
            key=lambda row: (
                row["worst_event_loss_db"],
                -(row["worst_event_position_km"] or 0),
            ),
            default=None,
        )
        qd_candidates = [
            row
            for row in candidates
            if row["dkd_core_percent"] is not None or row["assessment"] is not None
        ]
        format_rank = {"stv": 3, "fast": 2, "raw_matrix": 1, "unknown": 0}
        qd = max(
            qd_candidates,
            key=lambda row: (
                format_rank.get(row["source_format"], 0),
                bool(row["dkd_required_percent"] is not None),
                row["source_file"],
                row["source_sheet"],
            ),
            default=None,
        )
        month_rows.append(
            {
                "month": current.strftime("%Y-%m"),
                "month_label": f"Tháng {current.month}",
                "worst_event_loss_db": worst["worst_event_loss_db"] if worst else None,
                "worst_event_position_km": worst["worst_event_position_km"] if worst else None,
                "utilization_percent": qd["utilization_percent"] if qd else None,
                "dkd_core_percent": qd["dkd_core_percent"] if qd else None,
                "dkd_required_percent": qd["dkd_required_percent"] if qd else None,
                "assessment": qd["assessment"] if qd else None,
                "loss_source": (
                    {"file": worst["source_file"], "sheet": worst["source_sheet"]}
                    if worst else None
                ),
                "qd_source": (
                    {"file": qd["source_file"], "sheet": qd["source_sheet"]}
                    if qd else None
                ),
            }
        )

    return {
        "region": normalized_region,
        "route_key": normalized_key,
        "route_name": route_name,
        "period_start": first.isoformat(),
        "period_end": anchor.isoformat(),
        "months": month_rows,
    }


class RouteDashboardStorage:
    def __init__(
        self,
        *,
        client: Any | None = None,
        local_data_file: str | Path | None = None,
    ) -> None:
        local_path = local_data_file or os.environ.get("DASHBOARD_LOCAL_DATA_FILE", "").strip()
        self._local_data_file = Path(local_path).resolve() if local_path else None
        self._client = None if self._local_data_file else (client or _create_supabase_client())

    def _local_rows(self) -> list[dict[str, Any]]:
        if self._local_data_file is None:
            raise DashboardStorageConfigurationError("local dashboard data is not configured")
        try:
            payload = json.loads(self._local_data_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DashboardStorageOperationError(
                "could not read local dashboard data"
            ) from exc
        rows = payload.get("snapshots") if isinstance(payload, dict) else payload
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise DashboardStorageOperationError("local dashboard data has an invalid shape")
        return rows

    def upsert_snapshots(self, snapshots: Iterable[DashboardSnapshot | dict[str, Any]]) -> int:
        payload = [
            _clean_snapshot(item.to_dict() if isinstance(item, DashboardSnapshot) else item)
            for item in snapshots
        ]
        if not payload:
            return 0
        if self._local_data_file is not None:
            raise DashboardStorageConfigurationError("local dashboard data is read-only")
        try:
            response = (
                self._client.table("route_dashboard_snapshots")
                .upsert(
                    payload,
                    on_conflict="region,route_key,measurement_month,source_sha256,source_sheet",
                )
                .execute()
            )
            _response_rows(response, "upserting dashboard snapshots")
        except Exception as exc:
            raise DashboardStorageOperationError(
                "could not upsert dashboard snapshots in Supabase"
            ) from exc
        return len(payload)

    def _rows_for_region(self, region: str) -> list[dict[str, Any]]:
        normalized_region = normalize_region(region)
        if self._local_data_file is not None:
            return [
                row for row in self._local_rows()
                if normalize_region(row.get("region")) == normalized_region
            ]
        try:
            response = (
                self._client.table("route_dashboard_snapshots")
                .select(
                    "region,route_key,route_name,measurement_month,"
                    "worst_event_loss_db,worst_event_position_km,"
                    "utilization_percent,dkd_core_percent,dkd_required_percent,"
                    "assessment,source_file,source_sheet,source_format,source_sha256,warnings"
                )
                .eq("region", normalized_region)
                .order("measurement_month", desc=False)
                .execute()
            )
            return _response_rows(response, "loading dashboard snapshots")
        except Exception as exc:
            raise DashboardStorageOperationError(
                "could not retrieve dashboard snapshots from Supabase"
            ) from exc

    def list_routes(self, region: str) -> list[dict[str, str]]:
        routes: dict[str, tuple[date, str]] = {}
        for raw in self._rows_for_region(region):
            row = _clean_snapshot(raw)
            key = row["route_key"]
            candidate = (_month_start(row["measurement_month"]), row["route_name"])
            if key and (key not in routes or candidate[0] >= routes[key][0]):
                routes[key] = candidate
        return [
            {"route_key": key, "route_name": value[1]}
            for key, value in sorted(routes.items(), key=lambda item: fold_text(item[1][1]))
        ]

    def route_series(
        self,
        region: str,
        route_key: str,
        months: int = DEFAULT_DASHBOARD_MONTHS,
    ) -> dict[str, Any]:
        return aggregate_route_series(
            self._rows_for_region(region),
            region=region,
            route_key=route_key,
            months=months,
        )

@lru_cache(maxsize=1)
def get_dashboard_storage() -> RouteDashboardStorage:
    try:
        return RouteDashboardStorage()
    except Exception as exc:
        if isinstance(exc, DashboardStorageError):
            raise
        raise DashboardStorageConfigurationError(
            "could not initialize dashboard storage"
        ) from exc


def reset_dashboard_storage_cache() -> None:
    get_dashboard_storage.cache_clear()
