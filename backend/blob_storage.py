from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any, Final, Iterable
from uuid import UUID

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError


INPUT_PREFIX: Final[str] = "otdr/input"
OUTPUT_PREFIX: Final[str] = "otdr/output"
DEFAULT_MAX_DOWNLOAD_BYTES: Final[int] = 250 * 1024 * 1024
PRESIGNED_UPLOAD_LIFETIME_SECONDS: Final[int] = 15 * 60
PRESIGNED_DOWNLOAD_LIFETIME_SECONDS: Final[int] = 5 * 60
MULTIPART_UPLOAD_THRESHOLD_BYTES: Final[int] = 100 * 1024 * 1024
MULTIPART_PART_SIZE_BYTES: Final[int] = 16 * 1024 * 1024
SUPPORTED_INPUT_EXTENSIONS: Final[tuple[str, ...]] = (".sor", ".msor", ".trc")
_SAFE_FILENAME_RE: Final[re.Pattern[str]] = re.compile(r"[^A-Za-z0-9._-]+")
_MANAGED_INPUT_FILENAME_RE: Final[re.Pattern[str]] = re.compile(
    r"^\d{6}-[A-Za-z0-9._-]+\.(?:sor|msor|trc)$",
    re.IGNORECASE,
)
_MANAGED_PATH_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?P<prefix>otdr/(?:input|output))/"
    r"(?P<year>\d{4})/(?P<month>\d{2})/(?P<day>\d{2})/"
    r"(?P<job_id>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{12})/(?P<filename>[A-Za-z0-9._-]+)$"
)


@dataclass(frozen=True)
class StoredBlob:
    pathname: str
    url: str
    download_url: str
    content_type: str
    size: int | None = None


class BlobStorageError(RuntimeError):
    """Raised when an OTDR Blob storage operation cannot be completed safely."""


class BlobStorageConfigurationError(BlobStorageError):
    """Raised when the private Blob store is not configured."""


class BlobStorageNotFoundError(BlobStorageError):
    """Raised when a managed Blob object does not exist."""


class BlobStorageSizeError(BlobStorageError):
    """Raised when a managed Blob object exceeds an application size limit."""


class BlobStorageOperationError(BlobStorageError):
    """Raised when Cloudflare R2 rejects or cannot complete an operation."""


def _validated_job_id(job_id: str) -> str:
    try:
        return str(UUID(str(job_id)))
    except (ValueError, AttributeError, TypeError) as exc:
        raise BlobStorageError("job_id must be a valid UUID") from exc


def _safe_filename(filename: str) -> str:
    basename = PurePosixPath(str(filename).replace("\\", "/")).name
    sanitized = _SAFE_FILENAME_RE.sub("_", basename).strip("._")
    if not sanitized:
        raise BlobStorageError("filename is empty or invalid")
    return sanitized


def job_id_from_input_path(pathname: str) -> str:
    """Validate a canonical input Blob pathname and return its UUID job id."""
    match = _match_managed_path(pathname)
    if match.group("prefix") != INPUT_PREFIX or match.group("filename") != "batch.zip":
        raise BlobStorageError("input Blob pathname must point to a managed batch.zip")
    return match.group("job_id")


def job_id_from_input_file_path(pathname: str) -> str:
    """Validate one managed OTDR input pathname and return its UUID job id."""
    match = _match_managed_path(pathname)
    if (
        match.group("prefix") != INPUT_PREFIX
        or _MANAGED_INPUT_FILENAME_RE.fullmatch(match.group("filename")) is None
    ):
        raise BlobStorageError(
            "input Blob pathname must point to a managed OTDR file"
        )
    return match.group("job_id")


def job_id_from_output_path(pathname: str) -> str:
    """Validate one managed XLSX output pathname and return its UUID job id."""
    match = _match_managed_path(pathname)
    if (
        match.group("prefix") != OUTPUT_PREFIX
        or not match.group("filename").lower().endswith(".xlsx")
    ):
        raise BlobStorageError(
            "output Blob pathname must point to a managed XLSX file"
        )
    return match.group("job_id")


def _match_managed_path(pathname: str) -> re.Match[str]:
    if not isinstance(pathname, str) or pathname != pathname.strip():
        raise BlobStorageError("invalid Blob pathname")
    match = _MANAGED_PATH_RE.fullmatch(pathname)
    if match is None:
        raise BlobStorageError("invalid managed Blob pathname")
    try:
        datetime(
            int(match.group("year")),
            int(match.group("month")),
            int(match.group("day")),
            tzinfo=timezone.utc,
        )
    except ValueError as exc:
        raise BlobStorageError("invalid date in Blob pathname") from exc
    if _validated_job_id(match.group("job_id")) != match.group("job_id"):
        raise BlobStorageError("Blob pathname job id is not canonical")
    return match


def build_job_path(
    prefix: str,
    job_id: str,
    filename: str,
    *,
    created_at: datetime | None = None,
) -> str:
    if prefix not in {INPUT_PREFIX, OUTPUT_PREFIX}:
        raise BlobStorageError("unsupported Blob pathname prefix")
    moment = created_at or datetime.now(timezone.utc)
    safe_job_id = _validated_job_id(job_id)
    safe_filename = _safe_filename(filename)
    return (
        f"{prefix}/{moment:%Y/%m/%d}/{safe_job_id}/{safe_filename}"
    )


def build_input_path(job_id: str, *, created_at: datetime | None = None) -> str:
    return build_job_path(
        INPUT_PREFIX,
        job_id,
        "batch.zip",
        created_at=created_at,
    )


def build_input_file_path(
    job_id: str,
    index: int,
    filename: str,
    *,
    created_at: datetime | None = None,
) -> str:
    if index < 1:
        raise BlobStorageError("input file index must be greater than zero")
    safe_filename = _safe_filename(filename)
    extension = PurePosixPath(safe_filename).suffix.lower()
    if extension not in SUPPORTED_INPUT_EXTENSIONS:
        raise BlobStorageError("unsupported OTDR input extension")
    return build_job_path(
        INPUT_PREFIX,
        job_id,
        f"{index:06d}-{safe_filename}",
        created_at=created_at,
    )


def build_output_path(
    job_id: str,
    filename: str,
    *,
    created_at: datetime | None = None,
) -> str:
    return build_job_path(
        OUTPUT_PREFIX,
        job_id,
        filename,
        created_at=created_at,
    )


class PrivateBlobStorage:
    """Isolated adapter for the project's private Cloudflare R2 bucket."""

    def __init__(
        self,
        *,
        account_id: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        bucket_name: str | None = None,
        client: Any | None = None,
    ) -> None:
        resolved_account_id = account_id or os.environ.get("R2_ACCOUNT_ID")
        resolved_access_key_id = access_key_id or os.environ.get(
            "R2_ACCESS_KEY_ID"
        )
        resolved_secret_access_key = secret_access_key or os.environ.get(
            "R2_SECRET_ACCESS_KEY"
        )
        resolved_bucket_name = bucket_name or os.environ.get("R2_BUCKET_NAME")

        missing = [
            name
            for name, value in (
                ("R2_ACCOUNT_ID", resolved_account_id),
                ("R2_ACCESS_KEY_ID", resolved_access_key_id),
                ("R2_SECRET_ACCESS_KEY", resolved_secret_access_key),
                ("R2_BUCKET_NAME", resolved_bucket_name),
            )
            if not value
        ]
        if missing:
            raise BlobStorageConfigurationError(
                f"Cloudflare R2 is not configured: missing {', '.join(missing)}"
            )
        if re.fullmatch(r"[0-9a-fA-F]{32}", resolved_account_id) is None:
            raise BlobStorageConfigurationError(
                "R2_ACCOUNT_ID must be a 32-character hexadecimal account id"
            )
        if (
            len(resolved_bucket_name) < 3
            or len(resolved_bucket_name) > 63
            or re.fullmatch(
                r"[a-z0-9][a-z0-9-]*[a-z0-9]", resolved_bucket_name
            )
            is None
        ):
            raise BlobStorageConfigurationError(
                "R2_BUCKET_NAME must be a valid lowercase R2 bucket name"
            )

        self._bucket = resolved_bucket_name
        self._endpoint_url = (
            f"https://{resolved_account_id}.r2.cloudflarestorage.com"
        )
        self._client = client or boto3.client(
            "s3",
            endpoint_url=self._endpoint_url,
            aws_access_key_id=resolved_access_key_id,
            aws_secret_access_key=resolved_secret_access_key,
            region_name="auto",
            config=Config(
                signature_version="s3v4",
                connect_timeout=10,
                read_timeout=180,
                max_pool_connections=4,
                retries={"max_attempts": 3, "mode": "standard"},
                s3={"addressing_style": "path"},
            ),
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "PrivateBlobStorage":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def upload_bytes(
        self,
        pathname: str,
        content: bytes,
        *,
        content_type: str,
        overwrite: bool = False,
    ) -> StoredBlob:
        self._validate_managed_path(pathname)
        if not isinstance(content, bytes):
            raise BlobStorageError("Blob content must be bytes")
        if len(content) > MULTIPART_UPLOAD_THRESHOLD_BYTES:
            return self._upload_bytes_multipart(
                pathname,
                content,
                content_type=content_type,
                overwrite=overwrite,
            )
        params: dict[str, Any] = {
            "Bucket": self._bucket,
            "Key": pathname,
            "Body": content,
            "ContentLength": len(content),
            "ContentType": content_type,
            "ContentDisposition": (
                f'attachment; filename="{PurePosixPath(pathname).name}"'
            ),
        }
        if not overwrite:
            params["IfNoneMatch"] = "*"
        try:
            self._client.put_object(**params)
        except (BotoCoreError, ClientError) as exc:
            raise BlobStorageOperationError("private R2 upload failed") from exc
        object_uri = self._object_uri(pathname)
        return StoredBlob(
            pathname=pathname,
            url=object_uri,
            download_url=object_uri,
            content_type=content_type,
            size=len(content),
        )

    def _upload_bytes_multipart(
        self,
        pathname: str,
        content: bytes,
        *,
        content_type: str,
        overwrite: bool,
    ) -> StoredBlob:
        multipart_upload_id: str | None = None
        completed = False
        try:
            multipart_upload_id = self.create_multipart_upload(
                pathname,
                content_type=content_type,
                expected_size=len(content),
                overwrite=overwrite,
            )
            completed_parts: list[dict[str, Any]] = []
            for part_number, start in enumerate(
                range(0, len(content), MULTIPART_PART_SIZE_BYTES),
                start=1,
            ):
                part = content[start:start + MULTIPART_PART_SIZE_BYTES]
                result = self._client.upload_part(
                    Bucket=self._bucket,
                    Key=pathname,
                    UploadId=multipart_upload_id,
                    PartNumber=part_number,
                    Body=part,
                    ContentLength=len(part),
                )
                etag = result.get("ETag")
                if not isinstance(etag, str) or not etag:
                    raise BlobStorageOperationError(
                        "R2 did not return an ETag for a multipart output part"
                    )
                completed_parts.append(
                    {"PartNumber": part_number, "ETag": etag}
                )
            stored = self.complete_multipart_upload(
                pathname,
                multipart_upload_id,
                completed_parts,
            )
            completed = True
            return stored
        except BlobStorageError:
            raise
        except (BotoCoreError, ClientError) as exc:
            raise BlobStorageOperationError(
                "private R2 multipart upload failed"
            ) from exc
        finally:
            if multipart_upload_id is not None and not completed:
                try:
                    self.abort_multipart_upload(pathname, multipart_upload_id)
                except BlobStorageError:
                    pass

    def metadata(self, pathname: str) -> StoredBlob:
        self._validate_managed_path(pathname)
        try:
            result = self._client.head_object(
                Bucket=self._bucket,
                Key=pathname,
            )
        except ClientError as exc:
            if self._is_not_found(exc):
                raise BlobStorageNotFoundError("R2 object was not found") from exc
            raise BlobStorageOperationError(
                "private R2 metadata lookup failed"
            ) from exc
        except BotoCoreError as exc:
            raise BlobStorageOperationError(
                "private R2 metadata lookup failed"
            ) from exc
        object_uri = self._object_uri(pathname)
        return StoredBlob(
            pathname=pathname,
            url=object_uri,
            download_url=object_uri,
            content_type=result.get("ContentType", "application/octet-stream"),
            size=result.get("ContentLength"),
        )

    def download_bytes(
        self,
        pathname: str,
        *,
        max_bytes: int = DEFAULT_MAX_DOWNLOAD_BYTES,
        expected_size: int | None = None,
    ) -> bytes:
        self._validate_managed_path(pathname)
        if max_bytes <= 0:
            raise BlobStorageError("max_bytes must be greater than zero")
        info = self.metadata(pathname)
        if info.size is not None and info.size > max_bytes:
            raise BlobStorageSizeError(
                f"Blob is too large to download ({info.size} > {max_bytes} bytes)"
            )
        if (
            expected_size is not None
            and info.size is not None
            and info.size != expected_size
        ):
            raise BlobStorageSizeError(
                f"Blob size does not match the upload manifest "
                f"({info.size} != {expected_size} bytes)"
            )
        try:
            result = self._client.get_object(
                Bucket=self._bucket,
                Key=pathname,
            )
            body = result.get("Body")
            if body is None:
                raise BlobStorageOperationError(
                    "private R2 download returned no response body"
                )
            try:
                content = body.read(max_bytes + 1)
            finally:
                body.close()
        except ClientError as exc:
            if self._is_not_found(exc):
                raise BlobStorageNotFoundError("R2 object was not found") from exc
            raise BlobStorageOperationError("private R2 download failed") from exc
        except BotoCoreError as exc:
            raise BlobStorageOperationError("private R2 download failed") from exc
        if len(content) > max_bytes:
            raise BlobStorageSizeError(
                "Downloaded R2 object exceeds the configured size limit"
            )
        if expected_size is not None and len(content) != expected_size:
            raise BlobStorageSizeError(
                f"Downloaded R2 object size does not match the upload manifest "
                f"({len(content)} != {expected_size} bytes)"
            )
        return content

    def delete(self, pathname: str) -> None:
        self._validate_managed_path(pathname)
        try:
            self._client.delete_object(Bucket=self._bucket, Key=pathname)
        except (BotoCoreError, ClientError) as exc:
            raise BlobStorageOperationError("private R2 deletion failed") from exc

    def create_presigned_upload_url(
        self,
        pathname: str,
        *,
        content_type: str,
        expected_size: int,
        expires_in: int = PRESIGNED_UPLOAD_LIFETIME_SECONDS,
    ) -> str:
        self._validate_managed_path(pathname)
        self._validate_presign_limits(expected_size, expires_in)
        try:
            return self._client.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": self._bucket,
                    "Key": pathname,
                    "ContentType": content_type,
                    "ContentLength": expected_size,
                    "IfNoneMatch": "*",
                },
                ExpiresIn=expires_in,
                HttpMethod="PUT",
            )
        except (BotoCoreError, ClientError) as exc:
            raise BlobStorageOperationError(
                "could not create the R2 upload URL"
            ) from exc

    def create_multipart_upload(
        self,
        pathname: str,
        *,
        content_type: str,
        expected_size: int,
        overwrite: bool = False,
    ) -> str:
        self._validate_managed_path(pathname)
        self._validate_presign_limits(expected_size, 1)
        try:
            if not overwrite:
                try:
                    self._client.head_object(Bucket=self._bucket, Key=pathname)
                except ClientError as exc:
                    if not self._is_not_found(exc):
                        raise
                else:
                    raise BlobStorageOperationError(
                        "an R2 object already exists at the managed pathname"
                    )
            result = self._client.create_multipart_upload(
                Bucket=self._bucket,
                Key=pathname,
                ContentType=content_type,
                ContentDisposition=(
                    f'attachment; filename="{PurePosixPath(pathname).name}"'
                ),
                Metadata={"expected-size": str(expected_size)},
            )
        except BlobStorageOperationError:
            raise
        except (BotoCoreError, ClientError) as exc:
            raise BlobStorageOperationError(
                "could not start the R2 multipart upload"
            ) from exc
        upload_id = result.get("UploadId")
        if not isinstance(upload_id, str) or not upload_id:
            raise BlobStorageOperationError(
                "R2 did not return a multipart upload id"
            )
        return upload_id

    def create_presigned_part_url(
        self,
        pathname: str,
        multipart_upload_id: str,
        part_number: int,
        part_size: int,
        *,
        expires_in: int = PRESIGNED_UPLOAD_LIFETIME_SECONDS,
    ) -> str:
        self._validate_managed_path(pathname)
        self._validate_multipart_upload_id(multipart_upload_id)
        if not 1 <= part_number <= 10_000:
            raise BlobStorageError("multipart part number is invalid")
        if part_size <= 0 or part_size > 5 * 1024 * 1024 * 1024:
            raise BlobStorageError("multipart part size is invalid")
        if not 1 <= expires_in <= 7 * 24 * 60 * 60:
            raise BlobStorageError("presigned URL lifetime is invalid")
        try:
            return self._client.generate_presigned_url(
                "upload_part",
                Params={
                    "Bucket": self._bucket,
                    "Key": pathname,
                    "UploadId": multipart_upload_id,
                    "PartNumber": part_number,
                    "ContentLength": part_size,
                },
                ExpiresIn=expires_in,
                HttpMethod="PUT",
            )
        except (BotoCoreError, ClientError) as exc:
            raise BlobStorageOperationError(
                "could not create an R2 multipart part URL"
            ) from exc

    def complete_multipart_upload(
        self,
        pathname: str,
        multipart_upload_id: str,
        parts: Iterable[dict[str, Any]],
    ) -> StoredBlob:
        self._validate_managed_path(pathname)
        self._validate_multipart_upload_id(multipart_upload_id)
        normalized_parts = list(parts)
        if not normalized_parts:
            raise BlobStorageError("multipart upload contains no parts")
        try:
            self._client.complete_multipart_upload(
                Bucket=self._bucket,
                Key=pathname,
                UploadId=multipart_upload_id,
                MultipartUpload={"Parts": normalized_parts},
            )
        except (BotoCoreError, ClientError) as exc:
            raise BlobStorageOperationError(
                "could not complete the R2 multipart upload"
            ) from exc
        return self.metadata(pathname)

    def abort_multipart_upload(
        self,
        pathname: str,
        multipart_upload_id: str,
    ) -> None:
        self._validate_managed_path(pathname)
        self._validate_multipart_upload_id(multipart_upload_id)
        try:
            self._client.abort_multipart_upload(
                Bucket=self._bucket,
                Key=pathname,
                UploadId=multipart_upload_id,
            )
        except (BotoCoreError, ClientError) as exc:
            raise BlobStorageOperationError(
                "could not abort the R2 multipart upload"
            ) from exc

    def create_presigned_download_url(
        self,
        pathname: str,
        *,
        expires_in: int = PRESIGNED_DOWNLOAD_LIFETIME_SECONDS,
    ) -> str:
        self._validate_managed_path(pathname)
        if not 1 <= expires_in <= 7 * 24 * 60 * 60:
            raise BlobStorageError("presigned URL lifetime is invalid")
        self.metadata(pathname)
        try:
            return self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": pathname},
                ExpiresIn=expires_in,
                HttpMethod="GET",
            )
        except (BotoCoreError, ClientError) as exc:
            raise BlobStorageOperationError(
                "could not create the R2 download URL"
            ) from exc

    def _object_uri(self, pathname: str) -> str:
        return f"r2://{self._bucket}/{pathname}"

    @staticmethod
    def _is_not_found(exc: ClientError) -> bool:
        response = getattr(exc, "response", {})
        code = str(response.get("Error", {}).get("Code", ""))
        status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        return code in {"404", "NoSuchKey", "NotFound"} or status == 404

    @staticmethod
    def _validate_presign_limits(expected_size: int, expires_in: int) -> None:
        if (
            not isinstance(expected_size, int)
            or isinstance(expected_size, bool)
            or not 0 < expected_size <= DEFAULT_MAX_DOWNLOAD_BYTES
        ):
            raise BlobStorageSizeError("R2 upload size is invalid")
        if not 1 <= expires_in <= 7 * 24 * 60 * 60:
            raise BlobStorageError("presigned URL lifetime is invalid")

    @staticmethod
    def _validate_multipart_upload_id(multipart_upload_id: str) -> None:
        if (
            not isinstance(multipart_upload_id, str)
            or not multipart_upload_id
            or len(multipart_upload_id) > 2048
            or any(ord(character) < 32 for character in multipart_upload_id)
        ):
            raise BlobStorageError("multipart upload id is invalid")

    @staticmethod
    def _validate_managed_path(pathname: str) -> None:
        _match_managed_path(pathname)
