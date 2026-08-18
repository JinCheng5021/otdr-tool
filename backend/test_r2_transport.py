from __future__ import annotations

import io
import json
import inspect
import os
import unittest
from unittest.mock import patch

from fastapi.responses import Response

os.environ.setdefault("VERCEL", "1")
os.environ.setdefault("R2_SECRET_ACCESS_KEY", "test-r2-session-secret")

from . import app_trace
from .r2_storage import StoredBlob


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
OUTPUT_PATH = f"otdr/output/2026/07/22/{UPLOAD_ID}/FastReporter_test.xlsx"

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
    "output_mode": "fastreporter",
    "exporter_name": "Tester",
    "unit": "QA",
    "route_name": "Route 01",
    "stv_total_core": "24",
    "stv_used_core": "12",
}

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


class FakeR2SigningStorage:
    instances: list["FakeR2SigningStorage"] = []

    def __init__(self) -> None:
        self.aborted = []
        self.completed = []
        self.__class__.instances.append(self)

    def __enter__(self) -> "FakeR2SigningStorage":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def create_presigned_upload_url(
        self,
        pathname: str,
        *,
        content_type: str,
        expected_size: int,
    ) -> str:
        return f"https://account.r2.cloudflarestorage.com/{pathname}?single=1"

    def create_multipart_upload(
        self,
        pathname: str,
        *,
        content_type: str,
        expected_size: int,
    ) -> str:
        return "multipart-id"

    def create_presigned_part_url(
        self,
        pathname: str,
        multipart_upload_id: str,
        part_number: int,
        part_size: int,
    ) -> str:
        return (
            f"https://account.r2.cloudflarestorage.com/{pathname}"
            f"?partNumber={part_number}"
        )

    def complete_multipart_upload(
        self,
        pathname: str,
        multipart_upload_id: str,
        parts: list[dict],
    ) -> StoredBlob:
        self.completed.append((pathname, multipart_upload_id, parts))
        return StoredBlob(
            pathname=pathname,
            url=f"r2://bucket/{pathname}",
            download_url=f"r2://bucket/{pathname}",
            content_type="application/octet-stream",
            size=(
                app_trace.MULTIPART_UPLOAD_THRESHOLD_BYTES + 1
                if len(parts) > 1
                else len(INPUT_BYTES)
            ),
        )

    def abort_multipart_upload(
        self,
        pathname: str,
        multipart_upload_id: str,
    ) -> None:
        self.aborted.append((pathname, multipart_upload_id))

    def metadata(self, pathname: str) -> StoredBlob:
        return StoredBlob(
            pathname=pathname,
            url=f"r2://bucket/{pathname}",
            download_url=f"r2://bucket/{pathname}",
            content_type="application/octet-stream",
            size=len(INPUT_BYTES),
        )

    def create_presigned_download_url(self, pathname: str) -> str:
        return f"https://account.r2.cloudflarestorage.com/{pathname}?get=1"


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
        self.assertTrue(payload["upload_authorization"])
        self.assertGreater(payload["authorization_valid_until"], 0)


class R2SigningEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        FakeR2SigningStorage.instances.clear()

    def upload_request(self, size: int) -> FakeJsonRequest:
        upload_authorization, _valid_until = (
            app_trace._create_storage_upload_authorization(
                UPLOAD_ID,
                [{"pathname": INPUT_PATH, "size": size}],
            )
        )
        return FakeJsonRequest(
            {
                "pathname": INPUT_PATH,
                "upload_id": UPLOAD_ID,
                "size": size,
                "content_type": "application/octet-stream",
                "upload_authorization": upload_authorization,
            }
        )

    async def test_prepare_single_upload_preserves_path_size_and_headers(self) -> None:
        with patch.object(
            app_trace,
            "PrivateBlobStorage",
            FakeR2SigningStorage,
        ):
            response = await app_trace.prepare_storage_upload(
                self.upload_request(len(INPUT_BYTES))
            )

        payload = json.loads(response.body)
        self.assertEqual(payload["mode"], "single")
        self.assertEqual(payload["pathname"], INPUT_PATH)
        self.assertEqual(payload["size"], len(INPUT_BYTES))
        self.assertEqual(
            payload["required_headers"],
            {
                "Content-Type": "application/octet-stream",
                "If-None-Match": "*",
            },
        )

    async def test_prepare_large_upload_returns_complete_ordered_part_plan(self) -> None:
        size = app_trace.MULTIPART_UPLOAD_THRESHOLD_BYTES + 1
        with patch.object(
            app_trace,
            "PrivateBlobStorage",
            FakeR2SigningStorage,
        ):
            response = await app_trace.prepare_storage_upload(
                self.upload_request(size)
            )

        payload = json.loads(response.body)
        self.assertEqual(payload["mode"], "multipart")
        self.assertEqual(payload["multipart_upload_id"], "multipart-id")
        self.assertEqual(
            [part["part_number"] for part in payload["parts"]],
            list(range(1, len(payload["parts"]) + 1)),
        )
        self.assertEqual(sum(part["size"] for part in payload["parts"]), size)

    async def test_multipart_part_url_is_signed_just_in_time(self) -> None:
        size = app_trace.MULTIPART_UPLOAD_THRESHOLD_BYTES + 1
        request = self.upload_request(size)
        request.body.update(
            {
                "multipart_upload_id": "multipart-id",
                "part_number": 1,
                "part_size": app_trace.MULTIPART_PART_SIZE_BYTES,
            }
        )
        with patch.object(
            app_trace,
            "PrivateBlobStorage",
            FakeR2SigningStorage,
        ):
            response = await app_trace.create_storage_multipart_part_url(
                request
            )

        payload = json.loads(response.body)
        self.assertEqual(payload["part_number"], 1)
        self.assertEqual(payload["part_size"], app_trace.MULTIPART_PART_SIZE_BYTES)
        self.assertIn("partNumber=1", payload["upload_url"])

    async def test_signing_rejects_a_descriptor_not_in_the_session_token(self) -> None:
        request = self.upload_request(len(INPUT_BYTES))
        request.body["size"] = len(INPUT_BYTES) + 1
        with patch.object(
            app_trace,
            "PrivateBlobStorage",
            FakeR2SigningStorage,
        ):
            with self.assertRaises(app_trace.HTTPException) as raised:
                await app_trace.prepare_storage_upload(request)

        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(FakeR2SigningStorage.instances, [])

    async def test_complete_multipart_requires_all_ordered_parts(self) -> None:
        size = app_trace.MULTIPART_UPLOAD_THRESHOLD_BYTES + 1
        part_count = (
            size + app_trace.MULTIPART_PART_SIZE_BYTES - 1
        ) // app_trace.MULTIPART_PART_SIZE_BYTES
        request = self.upload_request(size)
        request.body.update(
            {
                "multipart_upload_id": "multipart-id",
                "parts": [
                    {"part_number": number, "etag": f'"etag-{number}"'}
                    for number in range(1, part_count + 1)
                ],
            }
        )
        with patch.object(
            app_trace,
            "PrivateBlobStorage",
            FakeR2SigningStorage,
        ):
            response = await app_trace.complete_storage_multipart(request)

        payload = json.loads(response.body)
        self.assertEqual(payload["pathname"], INPUT_PATH)
        self.assertEqual(payload["size"], size)
        self.assertEqual(
            len(FakeR2SigningStorage.instances[0].completed[0][2]),
            part_count,
        )

    async def test_download_url_accepts_only_managed_xlsx_output(self) -> None:
        with patch.object(
            app_trace,
            "PrivateBlobStorage",
            FakeR2SigningStorage,
        ):
            response = await app_trace.create_storage_download_url(
                FakeJsonRequest({"pathname": OUTPUT_PATH})
            )
        payload = json.loads(response.body)
        self.assertIn("r2.cloudflarestorage.com", payload["download_url"])

        with self.assertRaises(app_trace.HTTPException) as raised:
            await app_trace.create_storage_download_url(
                FakeJsonRequest({"pathname": INPUT_PATH})
            )
        self.assertEqual(raised.exception.status_code, 400)


class ConvertContractTests(unittest.TestCase):
    def test_normal_scope_discards_stale_range_values(self) -> None:
        options = {
            **CONVERT_OPTIONS,
            "section_export_scope": "all",
            "segment_start_km": "9.8",
            "segment_end_km": "1.2",
        }
        build_options = {
            key: value
            for key, value in options.items()
            if key not in {"exporter_name", "unit", "route_name"}
        }

        with patch.object(
            app_trace,
            "build_workbook_from_uploads",
            return_value=io.BytesIO(b"XLSX-DATA"),
        ) as workbook_mock:
            response = app_trace._build_export_response(
                [("trace.sor", INPUT_BYTES)],
                **build_options,
            )

        self.assertEqual(response.body, b"XLSX-DATA")
        workbook_options = workbook_mock.call_args.kwargs
        self.assertEqual(workbook_options["section_export_scope"], "all")
        self.assertIsNone(workbook_options["segment_start_km"])
        self.assertIsNone(workbook_options["segment_end_km"])

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

    def test_orl_threshold_parameters_are_removed_from_all_export_contracts(self) -> None:
        removed = {
            "orl_pass_threshold_db",
            "orl_source_mode",
            "orl_missing_policy",
            "orl_allow_lower_bound",
            "orl_lower_bound_status",
            "orl_physical_mode",
        }
        contracts = (
            inspect.signature(app_trace.convert).parameters,
            inspect.signature(app_trace.convert_from_blob).parameters,
            inspect.signature(app_trace.build_workbook_from_uploads).parameters,
        )
        for contract in contracts:
            self.assertTrue(removed.isdisjoint(contract))


if __name__ == "__main__":
    unittest.main()
