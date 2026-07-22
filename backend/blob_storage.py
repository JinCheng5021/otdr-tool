from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Final
from uuid import UUID

from vercel.blob import BlobClient


INPUT_PREFIX: Final[str] = "otdr/input"
OUTPUT_PREFIX: Final[str] = "otdr/output"
DEFAULT_MAX_DOWNLOAD_BYTES: Final[int] = 250 * 1024 * 1024
_SAFE_FILENAME_RE: Final[re.Pattern[str]] = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class StoredBlob:
    pathname: str
    url: str
    download_url: str
    content_type: str
    size: int | None = None


class BlobStorageError(RuntimeError):
    """Raised when an OTDR Blob storage operation cannot be completed safely."""


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
            raise BlobStorageError("BLOB_READ_WRITE_TOKEN is not configured")
        self._client = BlobClient(token=resolved_token)

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
        result = self._client.put(
            pathname,
            content,
            access="private",
            content_type=content_type,
            overwrite=overwrite,
        )
        return StoredBlob(
            pathname=result.pathname,
            url=result.url,
            download_url=result.download_url,
            content_type=result.content_type,
            size=len(content),
        )

    def metadata(self, pathname: str) -> StoredBlob:
        self._validate_managed_path(pathname)
        result = self._client.head(pathname)
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
            raise BlobStorageError(
                f"Blob is too large to download ({info.size} > {max_bytes} bytes)"
            )
        result = self._client.get(pathname, access="private", use_cache=False)
        if result is None:
            raise BlobStorageError("Blob was not found")
        if len(result.content) > max_bytes:
            raise BlobStorageError("Downloaded Blob exceeds the configured size limit")
        return result.content

    def delete(self, pathname: str) -> None:
        self._validate_managed_path(pathname)
        self._client.delete(pathname)

    @staticmethod
    def _validate_managed_path(pathname: str) -> None:
        normalized = str(pathname).strip().lstrip("/")
        if normalized != pathname or ".." in PurePosixPath(normalized).parts:
            raise BlobStorageError("invalid Blob pathname")
        if not any(
            normalized.startswith(f"{prefix}/")
            for prefix in (INPUT_PREFIX, OUTPUT_PREFIX)
        ):
            raise BlobStorageError("Blob pathname is outside the managed namespace")
