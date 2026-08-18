from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any
from urllib.parse import urlparse


DEFAULT_HISTORY_LIMIT = 100
DEFAULT_NOTIFICATION_LIMIT = 50
DEFAULT_HISTORY_TIMEOUT_SECONDS = 10
_VIETNAM_TIMEZONE = timezone(timedelta(hours=7))


class HistoryStorageError(RuntimeError):
    """Base error for export-history persistence."""


class HistoryStorageConfigurationError(HistoryStorageError):
    """Raised when the Supabase backend configuration is incomplete."""


class HistoryStorageOperationError(HistoryStorageError):
    """Raised when Supabase rejects or cannot complete an operation."""


def _configured_supabase() -> tuple[str, str]:
    url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    secret_key = os.environ.get("SUPABASE_SECRET_KEY", "").strip()
    missing = [
        name
        for name, value in (
            ("SUPABASE_URL", url),
            ("SUPABASE_SECRET_KEY", secret_key),
        )
        if not value
    ]
    if missing:
        raise HistoryStorageConfigurationError(
            "Missing Supabase history configuration: " + ", ".join(missing)
        )

    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.path not in ("", "/"):
        raise HistoryStorageConfigurationError(
            "SUPABASE_URL must be the HTTPS project URL without an API path"
        )
    return url, secret_key


def _create_supabase_client() -> Any:
    url, secret_key = _configured_supabase()
    try:
        from supabase import create_client
        from supabase.client import ClientOptions
    except ImportError as exc:
        raise HistoryStorageConfigurationError(
            "The supabase Python package is not installed"
        ) from exc

    try:
        return create_client(
            url,
            secret_key,
            options=ClientOptions(
                postgrest_client_timeout=DEFAULT_HISTORY_TIMEOUT_SECONDS,
                storage_client_timeout=DEFAULT_HISTORY_TIMEOUT_SECONDS,
                schema="public",
            ),
        )
    except Exception as exc:
        raise HistoryStorageConfigurationError(
            "Could not initialize the Supabase history client"
        ) from exc


def _response_rows(response: Any, operation: str) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if not isinstance(data, list) or any(not isinstance(row, dict) for row in data):
        raise HistoryStorageOperationError(
            f"Supabase returned an invalid response while {operation}"
        )
    return data


def _format_export_time(value: Any) -> str:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        if not text:
            return ""
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return text

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(_VIETNAM_TIMEZONE)
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


def _positive_limit(value: int, maximum: int) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("history limit must be an integer") from exc
    if normalized < 1:
        raise ValueError("history limit must be positive")
    return min(normalized, maximum)


class SupabaseHistoryStorage:
    def __init__(self, client: Any | None = None) -> None:
        self._client = client if client is not None else _create_supabase_client()

    def record_export(
        self,
        exporter_name: str,
        unit: str,
        route_name: str,
    ) -> None:
        payload = {
            "exporter_name": str(exporter_name),
            "unit": str(unit),
            "route_name": str(route_name),
        }
        try:
            (
                self._client.table("export_history")
                .insert(payload)
                .execute()
            )
        except Exception as exc:
            raise HistoryStorageOperationError(
                "Could not record export history in Supabase"
            ) from exc

    def list_history(self, limit: int = DEFAULT_HISTORY_LIMIT) -> list[dict[str, Any]]:
        query_limit = _positive_limit(limit, DEFAULT_HISTORY_LIMIT)
        try:
            response = (
                self._client.table("export_history")
                .select("id,exporter_name,unit,route_name,export_time")
                .order("id", desc=True)
                .limit(query_limit)
                .execute()
            )
        except Exception as exc:
            raise HistoryStorageOperationError(
                "Could not retrieve export history from Supabase"
            ) from exc

        rows = _response_rows(response, "loading export history")
        try:
            return [
                {
                    "id": int(row["id"]),
                    "exporter_name": str(row.get("exporter_name") or ""),
                    "unit": str(row.get("unit") or ""),
                    "route_name": str(row.get("route_name") or ""),
                    "export_time": _format_export_time(row.get("export_time")),
                }
                for row in rows
            ]
        except (KeyError, TypeError, ValueError) as exc:
            raise HistoryStorageOperationError(
                "Supabase export history contains an invalid record"
            ) from exc

    def list_notifications(
        self,
        limit: int = DEFAULT_NOTIFICATION_LIMIT,
    ) -> list[dict[str, Any]]:
        query_limit = _positive_limit(limit, DEFAULT_NOTIFICATION_LIMIT)
        try:
            response = (
                self._client.table("export_notifications")
                .select(
                    "id,exporter_name,unit,route_name,export_time,"
                    "monthly_export_count,month_name"
                )
                .order("id", desc=True)
                .limit(query_limit)
                .execute()
            )
        except Exception as exc:
            raise HistoryStorageOperationError(
                "Could not retrieve export notifications from Supabase"
            ) from exc

        rows = _response_rows(response, "loading export notifications")
        notifications: list[dict[str, Any]] = []
        try:
            for row in rows:
                notification_id = int(row["id"])
                exporter_name = str(row.get("exporter_name") or "")
                unit = str(row.get("unit") or "")
                route_name = str(row.get("route_name") or "")
                count = max(1, int(row.get("monthly_export_count") or 1))
                month_name = str(row.get("month_name") or "")
                message = (
                    f"Nhân sự {exporter_name} ({unit}) vừa xuất tuyến "
                    f"{route_name}. Tuyến này đã được xuất {count} lần "
                    f"trong tháng {month_name}."
                )
                notifications.append(
                    {
                        "id": notification_id,
                        "message": message,
                        "export_time": _format_export_time(row.get("export_time")),
                        "exporter_name": exporter_name,
                        "route_name": route_name,
                        "count": count,
                    }
                )
        except (KeyError, TypeError, ValueError) as exc:
            raise HistoryStorageOperationError(
                "Supabase export notifications contain an invalid record"
            ) from exc
        return notifications


@lru_cache(maxsize=1)
def get_history_storage() -> SupabaseHistoryStorage:
    return SupabaseHistoryStorage()


def reset_history_storage_cache() -> None:
    get_history_storage.cache_clear()
