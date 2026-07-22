from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Final
from uuid import UUID

import httpx
from vercel.blob import BlobClient
from vercel.blob.errors import BlobError, BlobNotFoundError


INPUT_PREFIX: Final[str] = "otdr/input"
OUTPUT_PREFIX: Final[str] = "otdr/output"
DEFAULT_MAX_DOWNLOAD_BYTES: Final[int] = 250 * 1024 * 1024
_SAFE_FILENAME_RE: Final[re.Pattern[str]] = re.compile(r"[^A-Za-z0-9._-]+")
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
    """Raised when Vercel Blob rejects or cannot complete an operation."""


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
    """Small, isolated adapter for the project's private Vercel Blob store."""

    def __init__(self, token: str | None = None) -> None:
        resolved_token = token or os.environ.get("BLOB_READ_WRITE_TOKEN")
        if not resolved_token:
            raise BlobStorageConfigurationError(
                "BLOB_READ_WRITE_TOKEN is not configured"
            )
        self._client = BlobClient(token=resolved_token)

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
        try:
            result = self._client.put(
                pathname,
                content,
                access="private",
                content_type=content_type,
                overwrite=overwrite,
                multipart=len(content) > 100 * 1024 * 1024,
            )
        except (BlobError, httpx.HTTPError) as exc:
            raise BlobStorageOperationError("private Blob upload failed") from exc
        return StoredBlob(
            pathname=result.pathname,
            url=result.url,
            download_url=result.download_url,
            content_type=result.content_type,
            size=len(content),
        )

    def metadata(self, pathname: str) -> StoredBlob:
        self._validate_managed_path(pathname)
        try:
            result = self._client.head(pathname)
        except BlobNotFoundError as exc:
            raise BlobStorageNotFoundError("Blob was not found") from exc
        except (BlobError, httpx.HTTPError) as exc:
            raise BlobStorageOperationError("private Blob metadata lookup failed") from exc
        return StoredBlob(
            pathname=result.pathname,
            url=result.url,
            download_url=result.download_url,
            content_type=result.content_type,
            size=result.size,
        )

    def download_bytes(
        self,
        pathname: str,
        *,
        max_bytes: int = DEFAULT_MAX_DOWNLOAD_BYTES,
    ) -> bytes:
        self._validate_managed_path(pathname)
        if max_bytes <= 0:
            raise BlobStorageError("max_bytes must be greater than zero")
        info = self.metadata(pathname)
        if info.size is not None and info.size > max_bytes:
            raise BlobStorageSizeError(
                f"Blob is too large to download ({info.size} > {max_bytes} bytes)"
            )
        try:
            result = self._client.get(pathname, access="private", use_cache=False)
        except BlobNotFoundError as exc:
            raise BlobStorageNotFoundError("Blob was not found") from exc
        except (BlobError, httpx.HTTPError) as exc:
            raise BlobStorageOperationError("private Blob download failed") from exc
        if result is None:
            raise BlobStorageNotFoundError("Blob was not found")
        if len(result.content) > max_bytes:
            raise BlobStorageSizeError(
                "Downloaded Blob exceeds the configured size limit"
            )
        return result.content

    def delete(self, pathname: str) -> None:
        self._validate_managed_path(pathname)
        try:
            self._client.delete(pathname)
        except BlobNotFoundError as exc:
            raise BlobStorageNotFoundError("Blob was not found") from exc
        except (BlobError, httpx.HTTPError) as exc:
            raise BlobStorageOperationError("private Blob deletion failed") from exc

    @staticmethod
    def _validate_managed_path(pathname: str) -> None:
        _match_managed_path(pathname)
