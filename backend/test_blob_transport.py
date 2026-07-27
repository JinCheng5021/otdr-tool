from __future__ import annotations

import json
import inspect
import os
import unittest
from unittest.mock import patch

from fastapi.responses import Response

os.environ.setdefault("VERCEL", "1")

from . import app_trace
from .blob_storage import StoredBlob


UPLOAD_ID = "123e4567-e89b-12d3-a456-426614174000"
INPUT_PATH = f"otdr/input/2026/07/22/{UPLOAD_ID}/000001-trace.sor"
INPUT_BYTES = b"SOR-DATA"
INPUT_MANIFEST = json.dumps(
    [
        {
            "original_name": "trace.sor",
            "pathname": INPUT_PATH,
            "size": len(INPUT_BYTES),
        }
    ]
)

CONVERT_OPTIONS = {
    "threshold_db": 0.11,
    "section_threshold_db": "0.22",
    "duration_threshold_s": "13",
    "deviation_m": 7.0,
    "expected_route_km": "42.5",
    "jumper_excluded_m": 1.0,
    "graph_reach_tolerance_km": 0.030,
    "event_shortfall_tolerance_km": 0.500,
    "overlength_tolerance_km": 0.500,
    "segment_start_km": "1.2",
    "segment_end_km": "9.8",
    "section_export_scope": "selected_range",
    "section_merge_tolerance_m": 99.0,
    "section_min_length_km": 0.01,
    "section_event_source": "all",
    "section_boundary_priority": "event",
    "section_allow_split": "true",
    "section_match_tolerance_m": 88.0,
    "section_measurement_mode": "fit",
    "orl_pass_threshold_db": 27.0,
    "orl_source_mode": "auto",
    "orl_missing_policy": "reference",
    "orl_allow_lower_bound": "true",
    "orl_lower_bound_status": "Unknown",
    "orl_physical_mode": "disabled",
    "output_mode": "fastreporter",
    "exporter_name": "Tester",
    "unit": "QA",
    "route_name": "Route 01",
    "stv_total_core": "24",
    "stv_used_core": "12",
}

#ABCD
class FakeBlobStorage:
    instances: list["FakeBlobStorage"] = []

    def __init__(self) -> None:
        self.upload_call = None
        self.deleted_paths = []
        self.closed = False
        self.__class__.instances.append(self)

    def __enter__(self) -> "FakeBlobStorage":
        return self

    def __exit__(self, *args: object) -> None:
        self.closed = True

    def download_bytes(
        self,
        pathname: str,
        *,
        max_bytes: int,
        expected_size: int,
    ) -> bytes:
        if pathname != INPUT_PATH:
            raise AssertionError(f"unexpected input path: {pathname}")
        if max_bytes != len(INPUT_BYTES) or expected_size != len(INPUT_BYTES):
            raise AssertionError("manifest size was not enforced")
        return INPUT_BYTES

    def upload_bytes(
        self,
        pathname: str,
        content: bytes,
        *,
        content_type: str,
        overwrite: bool,
    ) -> StoredBlob:
        self.upload_call = (pathname, content, content_type, overwrite)
        return StoredBlob(
            pathname=pathname,
            url="https://private.example/output",
            download_url="https://private.example/output?download=1",
            content_type=content_type,
            size=len(content),
        )

    def metadata(self, pathname: str) -> StoredBlob:
        if self.upload_call is None or pathname != self.upload_call[0]:
            raise AssertionError(f"unexpected metadata path: {pathname}")
        return StoredBlob(
            pathname=pathname,
            url="https://private.example/output",
            download_url="https://private.example/output?download=1",
            content_type=app_trace.XLSX_CONTENT_TYPE,
            size=len(self.upload_call[1]),
        )

    def delete(self, pathname: str) -> None:
        self.deleted_paths.append(pathname)


class ConvertFromBlobTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        FakeBlobStorage.instances.clear()

    async def test_transport_passes_the_exact_existing_parameters_to_convert(self) -> None:
        captured = {}

        def fake_build(payload, **kwargs):
            captured.update(kwargs)
            self.assertEqual(list(payload), [("trace.sor", INPUT_BYTES)])
            return Response(
                content=b"XLSX-DATA",
                media_type=app_trace.XLSX_CONTENT_TYPE,
                headers={
                    "Content-Disposition": 'attachment; filename="FastReporter_test.xlsx"'
                },
            )

        with (
            patch.object(app_trace, "PrivateBlobStorage", FakeBlobStorage),
            patch.object(
                app_trace,
                "_build_export_response",
                side_effect=fake_build,
            ) as build_mock,
            patch.object(app_trace, "_record_export_history") as history_mock,
        ):
            response = await app_trace.convert_from_blob(
                upload_id=UPLOAD_ID,
                input_manifest=INPUT_MANIFEST,
                **CONVERT_OPTIONS,
            )

        build_mock.assert_called_once()
        expected_build_options = {
            key: value
            for key, value in CONVERT_OPTIONS.items()
            if key not in {"exporter_name", "unit", "route_name"}
        }
        self.assertEqual(captured, expected_build_options)
        history_mock.assert_called_once_with("Tester", "QA", "Route 01")

        storage = FakeBlobStorage.instances[0]
        self.assertTrue(storage.closed)
        self.assertIsNotNone(storage.upload_call)
        output_path, content, content_type, overwrite = storage.upload_call
        self.assertIn(f"/{UPLOAD_ID}/FastReporter_test.xlsx", output_path)
        self.assertEqual(content, b"XLSX-DATA")
        self.assertEqual(content_type, app_trace.XLSX_CONTENT_TYPE)
        self.assertFalse(overwrite)
        self.assertEqual(storage.deleted_paths, [INPUT_PATH])

        payload = json.loads(response.body)
        self.assertEqual(payload["upload_id"], UPLOAD_ID)
        self.assertEqual(payload["status"], "succeeded")
        self.assertEqual(payload["filename"], "FastReporter_test.xlsx")
        self.assertEqual(payload["output_pathname"], output_path)

    async def test_converter_value_error_is_not_reclassified_as_uuid_error(self) -> None:
        def failing_build(payload, **kwargs):
            raise ValueError("converter failure")

        with (
            patch.object(app_trace, "PrivateBlobStorage", FakeBlobStorage),
            patch.object(app_trace, "_build_export_response", side_effect=failing_build),
        ):
            with self.assertRaisesRegex(ValueError, "converter failure"):
                await app_trace.convert_from_blob(
                    upload_id=UPLOAD_ID,
                    input_manifest=INPUT_MANIFEST,
                    **CONVERT_OPTIONS,
                )

    async def test_mismatched_path_is_rejected_before_blob_access(self) -> None:
        other_id = "123e4567-e89b-12d3-a456-426614174001"
        with patch.object(app_trace, "PrivateBlobStorage", FakeBlobStorage):
            with self.assertRaises(app_trace.HTTPException) as raised:
                await app_trace.convert_from_blob(
                    upload_id=other_id,
                    input_manifest=INPUT_MANIFEST,
                    **CONVERT_OPTIONS,
                )

        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(FakeBlobStorage.instances, [])

    async def test_mixed_supported_types_are_rejected_before_blob_access(self) -> None:
        mixed_manifest = json.dumps(
            [
                {
                    "original_name": "trace.sor",
                    "pathname": INPUT_PATH,
                    "size": len(INPUT_BYTES),
                },
                {
                    "original_name": "trace.msor",
                    "pathname": (
                        f"otdr/input/2026/07/22/{UPLOAD_ID}/"
                        "000002-trace.msor"
                    ),
                    "size": 10,
                },
            ]
        )
        with patch.object(app_trace, "PrivateBlobStorage", FakeBlobStorage):
            with self.assertRaises(app_trace.HTTPException) as raised:
                await app_trace.convert_from_blob(
                    upload_id=UPLOAD_ID,
                    input_manifest=mixed_manifest,
                    **CONVERT_OPTIONS,
                )

        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(FakeBlobStorage.instances, [])


class FakeJsonRequest:
    def __init__(self, body) -> None:
        self.body = body

    async def json(self):
        return self.body


class BlobInputSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_session_selects_one_type_and_ignores_other_files(self) -> None:
        response = await app_trace.create_blob_input(
            FakeJsonRequest(
                {
                    "files": [
                        {"name": "document.pdf", "size": 100},
                        {"name": "trace.msor", "size": 200},
                        {"name": "trace.sor", "size": 300},
                    ]
                }
            )
        )
        payload = json.loads(response.body)

        self.assertEqual(payload["selected_extension"], ".sor")
        self.assertEqual(payload["ignored_count"], 2)
        self.assertEqual(len(payload["files"]), 1)
        self.assertEqual(payload["files"][0]["original_name"], "trace.sor")
        self.assertEqual(payload["files"][0]["size"], 300)
        self.assertTrue(payload["files"][0]["pathname"].endswith("000001-trace.sor"))


class ConvertContractTests(unittest.TestCase):
    def test_blob_endpoint_has_the_same_business_parameter_contract(self) -> None:
        original = inspect.signature(app_trace.convert).parameters
        from_blob = inspect.signature(app_trace.convert_from_blob).parameters
        original_names = [name for name in original if name != "files"]
        from_blob_names = [
            name
            for name in from_blob
            if name not in {"upload_id", "input_manifest", "input_pathname"}
        ]
        self.assertEqual(from_blob_names, original_names)

        for name in original_names:
            with self.subTest(parameter=name):
                self.assertEqual(from_blob[name].annotation, original[name].annotation)
                self.assertEqual(
                    from_blob[name].default.default,
                    original[name].default.default,
                )


if __name__ == "__main__":
    unittest.main()
