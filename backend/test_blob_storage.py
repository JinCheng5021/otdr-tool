from __future__ import annotations

from datetime import datetime, timezone
import os
import unittest
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError, EndpointConnectionError

from . import blob_storage
from .blob_storage import (
    BlobStorageConfigurationError,
    BlobStorageError,
    BlobStorageNotFoundError,
    BlobStorageOperationError,
    BlobStorageSizeError,
    PrivateBlobStorage,
    build_input_file_path,
    build_input_path,
    build_output_path,
    job_id_from_input_file_path,
    job_id_from_input_path,
    job_id_from_output_path,
)


UPLOAD_ID = "123e4567-e89b-12d3-a456-426614174000"
CREATED_AT = datetime(2026, 7, 22, tzinfo=timezone.utc)
INPUT_PATH = f"otdr/input/2026/07/22/{UPLOAD_ID}/batch.zip"
ACCOUNT_ID = "a" * 32
BUCKET = "otdr-tool-private"


class FakeStreamingBody:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.closed = False
        self.requested_size = None

    def read(self, size: int) -> bytes:
        self.requested_size = size
        return self.content[:size]

    def close(self) -> None:
        self.closed = True


def storage_with_client(client: Mock) -> PrivateBlobStorage:
    return PrivateBlobStorage(
        account_id=ACCOUNT_ID,
        access_key_id="access-key",
        secret_access_key="secret-key",
        bucket_name=BUCKET,
        client=client,
    )


def client_error(code: str, status: int, operation: str) -> ClientError:
    return ClientError(
        {
            "Error": {"Code": code, "Message": code},
            "ResponseMetadata": {"HTTPStatusCode": status},
        },
        operation,
    )


class BlobPathTests(unittest.TestCase):
    def test_builders_create_canonical_managed_paths(self) -> None:
        self.assertEqual(
            build_input_path(UPLOAD_ID, created_at=CREATED_AT),
            INPUT_PATH,
        )
        output_path = build_output_path(
            UPLOAD_ID,
            "Fast Reporter 01.xlsx",
            created_at=CREATED_AT,
        )
        self.assertEqual(
            output_path,
            f"otdr/output/2026/07/22/{UPLOAD_ID}/Fast_Reporter_01.xlsx",
        )
        self.assertEqual(job_id_from_output_path(output_path), UPLOAD_ID)
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
        self.assertEqual(job_id_from_input_file_path(input_file_path), UPLOAD_ID)

    def test_path_parsers_reject_noncanonical_or_wrong_namespace_paths(self) -> None:
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
    def test_missing_r2_configuration_lists_missing_variables(self) -> None:
        names = (
            "R2_ACCOUNT_ID",
            "R2_ACCESS_KEY_ID",
            "R2_SECRET_ACCESS_KEY",
            "R2_BUCKET_NAME",
        )
        previous = {name: os.environ.pop(name, None) for name in names}
        try:
            with self.assertRaises(BlobStorageConfigurationError) as raised:
                PrivateBlobStorage()
        finally:
            for name, value in previous.items():
                if value is not None:
                    os.environ[name] = value
        for name in names:
            self.assertIn(name, str(raised.exception))

    @patch("backend.blob_storage.boto3.client")
    def test_client_uses_the_cloudflare_r2_endpoint(self, client_factory) -> None:
        storage = PrivateBlobStorage(
            account_id=ACCOUNT_ID,
            access_key_id="access-key",
            secret_access_key="secret-key",
            bucket_name=BUCKET,
        )
        storage.close()

        _, kwargs = client_factory.call_args
        self.assertEqual(kwargs["endpoint_url"], f"https://{ACCOUNT_ID}.r2.cloudflarestorage.com")
        self.assertEqual(kwargs["region_name"], "auto")
        self.assertEqual(kwargs["aws_access_key_id"], "access-key")
        self.assertEqual(kwargs["aws_secret_access_key"], "secret-key")

    def test_download_checks_metadata_and_returns_exact_bytes(self) -> None:
        client = Mock()
        body = FakeStreamingBody(b"ZIPDATA")
        client.head_object.return_value = {
            "ContentLength": 7,
            "ContentType": "application/zip",
        }
        client.get_object.return_value = {"Body": body}

        with storage_with_client(client) as storage:
            self.assertEqual(storage.download_bytes(INPUT_PATH, max_bytes=8), b"ZIPDATA")

        client.head_object.assert_called_once_with(Bucket=BUCKET, Key=INPUT_PATH)
        client.get_object.assert_called_once_with(Bucket=BUCKET, Key=INPUT_PATH)
        self.assertEqual(body.requested_size, 9)
        self.assertTrue(body.closed)
        client.close.assert_called_once_with()

    def test_download_rejects_manifest_size_before_get(self) -> None:
        client = Mock()
        client.head_object.return_value = {
            "ContentLength": 4,
            "ContentType": "application/octet-stream",
        }
        storage = storage_with_client(client)

        with self.assertRaises(BlobStorageSizeError):
            storage.download_bytes(INPUT_PATH, max_bytes=8, expected_size=5)

        client.get_object.assert_not_called()

    def test_download_stops_before_get_when_metadata_is_too_large(self) -> None:
        client = Mock()
        client.head_object.return_value = {
            "ContentLength": 9,
            "ContentType": "application/zip",
        }
        storage = storage_with_client(client)

        with self.assertRaises(BlobStorageSizeError):
            storage.download_bytes(INPUT_PATH, max_bytes=8)

        client.get_object.assert_not_called()

    def test_upload_is_private_conditional_and_sets_download_filename(self) -> None:
        output_path = f"otdr/output/2026/07/22/{UPLOAD_ID}/report.xlsx"
        client = Mock()
        storage = storage_with_client(client)
        stored = storage.upload_bytes(
            output_path,
            b"XLSX",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        self.assertEqual(stored.pathname, output_path)
        self.assertEqual(stored.size, 4)
        client.put_object.assert_called_once_with(
            Bucket=BUCKET,
            Key=output_path,
            Body=b"XLSX",
            ContentLength=4,
            ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ContentDisposition='attachment; filename="report.xlsx"',
            IfNoneMatch="*",
        )

    def test_large_output_uses_managed_multipart_upload(self) -> None:
        output_path = f"otdr/output/2026/07/22/{UPLOAD_ID}/report.xlsx"
        content = b"0123456789"
        client = Mock()
        client.head_object.side_effect = [
            client_error("NoSuchKey", 404, "HeadObject"),
            {
                "ContentLength": len(content),
                "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            },
        ]
        client.create_multipart_upload.return_value = {"UploadId": "output-id"}
        client.upload_part.side_effect = [
            {"ETag": '"part-1"'},
            {"ETag": '"part-2"'},
            {"ETag": '"part-3"'},
        ]
        storage = storage_with_client(client)

        with (
            patch.object(blob_storage, "MULTIPART_UPLOAD_THRESHOLD_BYTES", 4),
            patch.object(blob_storage, "MULTIPART_PART_SIZE_BYTES", 4),
        ):
            stored = storage.upload_bytes(
                output_path,
                content,
                content_type=(
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                ),
            )

        self.assertEqual(stored.size, len(content))
        self.assertEqual(client.upload_part.call_count, 3)
        client.complete_multipart_upload.assert_called_once()
        client.put_object.assert_not_called()
        client.abort_multipart_upload.assert_not_called()

    def test_not_found_and_transport_errors_are_mapped(self) -> None:
        missing_client = Mock()
        missing_client.head_object.side_effect = client_error(
            "NoSuchKey", 404, "HeadObject"
        )
        with self.assertRaises(BlobStorageNotFoundError):
            storage_with_client(missing_client).metadata(INPUT_PATH)

        failing_client = Mock()
        failing_client.head_object.side_effect = EndpointConnectionError(
            endpoint_url="https://r2.example"
        )
        with self.assertRaises(BlobStorageOperationError):
            storage_with_client(failing_client).download_bytes(INPUT_PATH)

    def test_presigned_single_upload_is_bound_to_key_type_size_and_no_overwrite(self) -> None:
        client = Mock()
        client.generate_presigned_url.return_value = (
            f"https://{ACCOUNT_ID}.r2.cloudflarestorage.com/signed"
        )
        storage = storage_with_client(client)

        result = storage.create_presigned_upload_url(
            INPUT_PATH,
            content_type="application/octet-stream",
            expected_size=7,
        )

        self.assertIn("r2.cloudflarestorage.com", result)
        client.generate_presigned_url.assert_called_once_with(
            "put_object",
            Params={
                "Bucket": BUCKET,
                "Key": INPUT_PATH,
                "ContentType": "application/octet-stream",
                "ContentLength": 7,
                "IfNoneMatch": "*",
            },
            ExpiresIn=900,
            HttpMethod="PUT",
        )

    def test_multipart_start_part_complete_and_abort_use_the_exact_key(self) -> None:
        client = Mock()
        client.head_object.side_effect = [
            client_error("NoSuchKey", 404, "HeadObject"),
            {"ContentLength": 6, "ContentType": "application/octet-stream"},
        ]
        client.create_multipart_upload.return_value = {"UploadId": "multi-id"}
        client.generate_presigned_url.return_value = "https://r2.example/part"
        storage = storage_with_client(client)

        multipart_id = storage.create_multipart_upload(
            INPUT_PATH,
            content_type="application/octet-stream",
            expected_size=6,
        )
        self.assertEqual(multipart_id, "multi-id")
        storage.create_presigned_part_url(INPUT_PATH, multipart_id, 1, 6)
        stored = storage.complete_multipart_upload(
            INPUT_PATH,
            multipart_id,
            [{"PartNumber": 1, "ETag": '"etag"'}],
        )
        storage.abort_multipart_upload(INPUT_PATH, multipart_id)

        self.assertEqual(stored.size, 6)
        client.create_multipart_upload.assert_called_once_with(
            Bucket=BUCKET,
            Key=INPUT_PATH,
            ContentType="application/octet-stream",
            ContentDisposition='attachment; filename="batch.zip"',
            Metadata={"expected-size": "6"},
        )
        client.complete_multipart_upload.assert_called_once_with(
            Bucket=BUCKET,
            Key=INPUT_PATH,
            UploadId="multi-id",
            MultipartUpload={
                "Parts": [{"PartNumber": 1, "ETag": '"etag"'}]
            },
        )
        client.abort_multipart_upload.assert_called_once_with(
            Bucket=BUCKET,
            Key=INPUT_PATH,
            UploadId="multi-id",
        )


if __name__ == "__main__":
    unittest.main()
