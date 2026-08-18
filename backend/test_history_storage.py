from __future__ import annotations

import json
import os
import unittest
from typing import Any
from unittest.mock import Mock, patch

from . import app_trace, history_storage
from .history_storage import (
    HistoryStorageConfigurationError,
    HistoryStorageOperationError,
    SupabaseHistoryStorage,
)


class FakeResponse:
    def __init__(self, data: Any) -> None:
        self.data = data


class FakeQuery:
    def __init__(self, client: "FakeClient", table_name: str) -> None:
        self.client = client
        self.table_name = table_name
        self.insert_payload: dict[str, Any] | None = None
        self.selected_columns: str | None = None
        self.ordering: tuple[str, bool] | None = None
        self.query_limit: int | None = None

    def insert(self, payload: dict[str, Any]) -> "FakeQuery":
        self.insert_payload = dict(payload)
        return self

    def select(self, columns: str) -> "FakeQuery":
        self.selected_columns = columns
        return self

    def order(self, column: str, *, desc: bool = False) -> "FakeQuery":
        self.ordering = (column, desc)
        return self

    def limit(self, value: int) -> "FakeQuery":
        self.query_limit = value
        return self

    def execute(self) -> FakeResponse:
        error = self.client.errors.get(self.table_name)
        if error is not None:
            raise error
        if self.insert_payload is not None:
            self.client.inserts.append((self.table_name, self.insert_payload))
            return FakeResponse([self.insert_payload])
        return FakeResponse(self.client.rows.get(self.table_name, []))


class FakeClient:
    def __init__(
        self,
        *,
        rows: dict[str, Any] | None = None,
        errors: dict[str, Exception] | None = None,
    ) -> None:
        self.rows = {} if rows is None else rows
        self.errors = {} if errors is None else errors
        self.inserts: list[tuple[str, dict[str, Any]]] = []
        self.queries: list[FakeQuery] = []

    def table(self, table_name: str) -> FakeQuery:
        query = FakeQuery(self, table_name)
        self.queries.append(query)
        return query


class SupabaseHistoryStorageTests(unittest.TestCase):
    def test_missing_configuration_names_every_required_variable(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(HistoryStorageConfigurationError) as context:
                history_storage._configured_supabase()

        message = str(context.exception)
        self.assertIn("SUPABASE_URL", message)
        self.assertIn("SUPABASE_SECRET_KEY", message)

    def test_configuration_rejects_non_project_urls(self) -> None:
        invalid_urls = (
            "http://example.supabase.co",
            "https://example.supabase.co/rest/v1",
            "not-a-url",
        )
        for url in invalid_urls:
            with self.subTest(url=url):
                with patch.dict(
                    os.environ,
                    {
                        "SUPABASE_URL": url,
                        "SUPABASE_SECRET_KEY": "test-secret",
                    },
                    clear=True,
                ):
                    with self.assertRaises(HistoryStorageConfigurationError):
                        history_storage._configured_supabase()

    def test_client_uses_bounded_postgrest_timeout(self) -> None:
        fake_client = object()
        with (
            patch.dict(
                os.environ,
                {
                    "SUPABASE_URL": "https://example.supabase.co",
                    "SUPABASE_SECRET_KEY": "test-secret",
                },
                clear=True,
            ),
            patch("supabase.create_client", return_value=fake_client) as create_mock,
        ):
            client = history_storage._create_supabase_client()

        self.assertIs(client, fake_client)
        options = create_mock.call_args.kwargs["options"]
        self.assertEqual(
            options.postgrest_client_timeout,
            history_storage.DEFAULT_HISTORY_TIMEOUT_SECONDS,
        )
        self.assertEqual(options.schema, "public")

    def test_record_export_inserts_only_existing_business_fields(self) -> None:
        client = FakeClient()
        storage = SupabaseHistoryStorage(client=client)

        storage.record_export("Nguyễn Văn A", "INF", "Tuyến 01")

        self.assertEqual(
            client.inserts,
            [
                (
                    "export_history",
                    {
                        "exporter_name": "Nguyễn Văn A",
                        "unit": "INF",
                        "route_name": "Tuyến 01",
                    },
                )
            ],
        )

    def test_list_history_preserves_contract_and_converts_to_vietnam_time(self) -> None:
        client = FakeClient(
            rows={
                "export_history": [
                    {
                        "id": 7,
                        "exporter_name": "Nguyễn Văn A",
                        "unit": "INF",
                        "route_name": "Tuyến 01",
                        "export_time": "2026-08-17T02:30:45+00:00",
                    }
                ]
            }
        )
        storage = SupabaseHistoryStorage(client=client)

        history = storage.list_history(limit=10)

        self.assertEqual(
            history,
            [
                {
                    "id": 7,
                    "exporter_name": "Nguyễn Văn A",
                    "unit": "INF",
                    "route_name": "Tuyến 01",
                    "export_time": "2026-08-17 09:30:45",
                }
            ],
        )
        query = client.queries[-1]
        self.assertEqual(query.ordering, ("id", True))
        self.assertEqual(query.query_limit, 10)

    def test_list_notifications_uses_view_count_and_existing_json_contract(self) -> None:
        client = FakeClient(
            rows={
                "export_notifications": [
                    {
                        "id": 8,
                        "exporter_name": "Nguyễn Văn B",
                        "unit": "QA",
                        "route_name": "Tuyến 02",
                        "export_time": "2026-08-17T03:00:00Z",
                        "monthly_export_count": 4,
                        "month_name": "08",
                    }
                ]
            }
        )
        storage = SupabaseHistoryStorage(client=client)

        notifications = storage.list_notifications()

        self.assertEqual(
            notifications,
            [
                {
                    "id": 8,
                    "message": (
                        "Nhân sự Nguyễn Văn B (QA) vừa xuất tuyến Tuyến 02. "
                        "Tuyến này đã được xuất 4 lần trong tháng 08."
                    ),
                    "export_time": "2026-08-17 10:00:00",
                    "exporter_name": "Nguyễn Văn B",
                    "route_name": "Tuyến 02",
                    "count": 4,
                }
            ],
        )

    def test_invalid_or_failed_supabase_responses_are_mapped(self) -> None:
        malformed = SupabaseHistoryStorage(
            client=FakeClient(rows={"export_history": None})
        )
        with self.assertRaises(HistoryStorageOperationError):
            malformed.list_history()

        failed = SupabaseHistoryStorage(
            client=FakeClient(
                errors={"export_notifications": RuntimeError("network unavailable")}
            )
        )
        with self.assertRaises(HistoryStorageOperationError):
            failed.list_notifications()


class HistoryEndpointTests(unittest.TestCase):
    @staticmethod
    def _json(response: Any) -> dict[str, Any]:
        return json.loads(response.body.decode("utf-8"))

    def test_history_endpoint_keeps_existing_success_shape(self) -> None:
        expected = [{"id": 1, "exporter_name": "A"}]
        storage = Mock()
        storage.list_history.return_value = expected
        with patch.object(app_trace, "get_history_storage", return_value=storage):
            response = app_trace.get_history()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self._json(response),
            {"status": "success", "data": expected},
        )

    def test_history_endpoint_reports_missing_server_configuration(self) -> None:
        storage = Mock()
        storage.list_history.side_effect = HistoryStorageConfigurationError(
            "missing"
        )
        with patch.object(app_trace, "get_history_storage", return_value=storage):
            response = app_trace.get_history()

        self.assertEqual(response.status_code, 503)
        self.assertEqual(self._json(response)["status"], "error")
        self.assertNotIn("missing", self._json(response)["detail"])

    def test_notification_endpoint_maps_supabase_operation_failure(self) -> None:
        storage = Mock()
        storage.list_notifications.side_effect = HistoryStorageOperationError(
            "network"
        )
        with patch.object(app_trace, "get_history_storage", return_value=storage):
            response = app_trace.get_notifications()

        self.assertEqual(response.status_code, 502)
        self.assertEqual(self._json(response)["status"], "error")
        self.assertNotIn("network", self._json(response)["detail"])

    def test_history_write_failure_does_not_break_report_completion(self) -> None:
        storage = Mock()
        storage.record_export.side_effect = HistoryStorageOperationError("network")
        with (
            patch.object(app_trace, "get_history_storage", return_value=storage),
            patch("builtins.print") as print_mock,
        ):
            app_trace._record_export_history("A", "B", "C")

        storage.record_export.assert_called_once_with("A", "B", "C")
        print_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
