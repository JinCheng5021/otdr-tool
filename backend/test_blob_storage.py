from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import httpx

from .blob_storage import (
    BlobStorageError,
    BlobStorageOperationError,
    BlobStorageSizeError,
    PrivateBlobStorage,
    build_input_file_path,
    build_input_path,
    build_output_path,
    job_id_from_input_file_path,
    job_id_from_input_path,
)


UPLOAD_ID = "123e4567-e89b-12d3-a456-426614174000"
CREATED_AT = datetime(2026, 7, 22, tzinfo=timezone.utc)
INPUT_PATH = f"otdr/input/2026/07/22/{UPLOAD_ID}/batch.zip"


class BlobPathTests(unittest.TestCase):
    def test_builders_create_canonical_managed_paths(self) -> None:
        self.assertEqual(
            build_input_path(UPLOAD_ID, created_at=CREATED_AT),
            INPUT_PATH,
        )
        self.assertEqual(
            build_output_path(
                UPLOAD_ID,
                "Fast Reporter 01.xlsx",
                created_at=CREATED_AT,
            ),
            f"otdr/output/2026/07/22/{UPLOAD_ID}/Fast_Reporter_01.xlsx",
        )
        self.assertEqual(job_id_from_input_path(INPUT_PATH), UPLOAD_ID)
        input_file_path = build_input_file_path(
            UPLOAD_ID,
            1,
            "Trace 01.SOR",
            created_at=CREATED_AT,
        )
        self.assertEqual(
            input_file_path,
            f"otdr/input/2026/07/22/{UPLOAD_ID}/000001-Trace_01.SOR",
        )
        self.assertEqual(
            job_id_from_input_file_path(input_file_path),
            UPLOAD_ID,
        )

    def test_input_parser_rejects_noncanonical_or_wrong_namespace_paths(self) -> None:
        invalid_paths = [
            f"otdr/output/2026/07/22/{UPLOAD_ID}/batch.zip",
            f"otdr/input/2026/02/30/{UPLOAD_ID}/batch.zip",
            f"otdr/input/2026/07/22/{UPLOAD_ID.upper()}/batch.zip",
            f"otdr/input/2026/07/22/{UPLOAD_ID}/other.zip",
            f"otdr/input/2026/07/22/{UPLOAD_ID}/../batch.zip",
        ]
        for pathname in invalid_paths:
            with self.subTest(pathname=pathname):
                with self.assertRaises(BlobStorageError):
                    job_id_from_input_path(pathname)


class PrivateBlobStorageTests(unittest.TestCase):
    @patch("backend.blob_storage.BlobClient")
    def test_download_checks_metadata_and_returns_exact_bytes(self, client_type) -> None:
        client = client_type.return_value
        client.head.return_value = SimpleNamespace(
            pathname=INPUT_PATH,
            url="https://private.example/input",
            download_url="https://private.example/input?download=1",
            content_type="application/zip",
            size=7,
        )
        client.get.return_value = SimpleNamespace(content=b"ZIPDATA")

        with PrivateBlobStorage(token="test-token") as storage:
            self.assertEqual(storage.download_bytes(INPUT_PATH, max_bytes=8), b"ZIPDATA")

        client.get.assert_called_once_with(
            INPUT_PATH,
            access="private",
            use_cache=False,
        )
        client.close.assert_called_once_with()

    @patch("backend.blob_storage.BlobClient")
    def test_download_rejects_content_that_does_not_match_manifest(
        self,
        client_type,
    ) -> None:
        client = client_type.return_value
        client.head.return_value = SimpleNamespace(
            pathname=INPUT_PATH,
            url="https://private.example/input",
            download_url="https://private.example/input?download=1",
            content_type="application/octet-stream",
            size=None,
        )
        client.get.return_value = SimpleNamespace(content=b"DATA")

        storage = PrivateBlobStorage(token="test-token")
        with self.assertRaises(BlobStorageSizeError):
            storage.download_bytes(
                INPUT_PATH,
                max_bytes=8,
                expected_size=5,
            )
        storage.close()

    @patch("backend.blob_storage.BlobClient")
    def test_download_stops_before_get_when_metadata_is_too_large(self, client_type) -> None:
        client = client_type.return_value
        client.head.return_value = SimpleNamespace(
            pathname=INPUT_PATH,
            url="https://private.example/input",
            download_url="https://private.example/input?download=1",
            content_type="application/zip",
            size=9,
        )

        storage = PrivateBlobStorage(token="test-token")
        with self.assertRaises(BlobStorageSizeError):
            storage.download_bytes(INPUT_PATH, max_bytes=8)
        storage.close()

        client.get.assert_not_called()

    @patch("backend.blob_storage.BlobClient")
    def test_upload_is_private_and_does_not_overwrite(self, client_type) -> None:
        output_path = f"otdr/output/2026/07/22/{UPLOAD_ID}/report.xlsx"
        client = client_type.return_value
        client.put.return_value = SimpleNamespace(
            pathname=output_path,
            url="https://private.example/output",
            download_url="https://private.example/output?download=1",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        storage = PrivateBlobStorage(token="test-token")
        stored = storage.upload_bytes(
            output_path,
            b"XLSX",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        storage.close()

        self.assertEqual(stored.pathname, output_path)
        self.assertEqual(stored.size, 4)
        client.put.assert_called_once_with(
            output_path,
            b"XLSX",
            access="private",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            overwrite=False,
            multipart=False,
        )

    @patch("backend.blob_storage.BlobClient")
    def test_sdk_transport_errors_are_mapped_to_blob_operation_errors(
        self,
        client_type,
    ) -> None:
        client = client_type.return_value
        client.head.side_effect = httpx.ReadTimeout("timed out")
        storage = PrivateBlobStorage(token="test-token")

        with self.assertRaises(BlobStorageOperationError):
            storage.download_bytes(INPUT_PATH)
        storage.close()


if __name__ == "__main__":
    unittest.main()
