from __future__ import annotations

import asyncio
import shutil
import time
from pathlib import Path
from typing import TYPE_CHECKING

import boto3
import structlog

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

logger = structlog.get_logger()


class R2Client:
    """Cloudflare R2 / S3-compatible storage client (works with MinIO locally)."""

    def __init__(
        self,
        account_id: str,
        access_key_id: str,
        secret_access_key: str,
        endpoint_url: str = "",
    ) -> None:
        resolved_endpoint = (
            endpoint_url if endpoint_url else f"https://{account_id}.r2.cloudflarestorage.com"
        )
        self._client: S3Client = boto3.client(
            "s3",
            endpoint_url=resolved_endpoint,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name="auto",
        )

    def upload_file(
        self,
        bucket: str,
        key: str,
        file_path: str,
        content_type: str,
    ) -> str:
        """Upload a file to R2. Returns the object key."""
        self._client.upload_file(
            Filename=file_path,
            Bucket=bucket,
            Key=key,
            ExtraArgs={"ContentType": content_type},
        )
        logger.info("r2_upload_complete", bucket=bucket, key=key)
        return key

    def download_file(self, bucket: str, key: str, destination: str) -> str:
        """Download a file from R2 to a local path. Returns the destination path."""
        self._client.download_file(Bucket=bucket, Key=key, Filename=destination)
        logger.info("r2_download_complete", bucket=bucket, key=key, destination=destination)
        return destination

    def generate_presigned_url(
        self,
        bucket: str,
        key: str,
        expires_in: int = 3600,
    ) -> str:
        """Generate a presigned URL for temporary access."""
        url: str = self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires_in,
        )
        return url

    def delete_file(self, bucket: str, key: str) -> None:
        """Delete an object from R2."""
        self._client.delete_object(Bucket=bucket, Key=key)
        logger.info("r2_delete_complete", bucket=bucket, key=key)

    def file_exists(self, bucket: str, key: str) -> bool:
        """Check if an object exists in R2."""
        try:
            self._client.head_object(Bucket=bucket, Key=key)
        except self._client.exceptions.ClientError:
            return False
        return True

    # ------------------------------------------------------------------
    # Resilience helpers
    # ------------------------------------------------------------------

    _FALLBACK_DIR = Path("/tmp/crimemill/fallback")

    async def upload_file_resilient(
        self,
        bucket: str,
        key: str,
        file_path: str,
        content_type: str,
        max_attempts: int = 3,
        base_delay: float = 1.0,
    ) -> str:
        """Upload to R2 with retry and local filesystem fallback.

        Returns the R2 key on success, or a ``local://{path}`` URI if all
        retries fail.  Callers should treat ``local://`` URIs as degraded.
        """
        last_exc: Exception | None = None

        for attempt in range(max_attempts):
            try:
                return await asyncio.to_thread(
                    self.upload_file, bucket, key, file_path, content_type,
                )
            except Exception as exc:
                last_exc = exc
                if attempt < max_attempts - 1:
                    delay = base_delay * (2 ** attempt)
                    await logger.awarning(
                        "r2_upload_retry",
                        bucket=bucket,
                        key=key,
                        attempt=attempt + 1,
                        delay=round(delay, 2),
                        error=str(exc),
                    )
                    await asyncio.sleep(delay)

        # All retries exhausted — fall back to local storage
        fallback_path = self._FALLBACK_DIR / key
        fallback_path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(shutil.copy2, file_path, str(fallback_path))

        uri = f"local://{fallback_path}"
        await logger.aerror(
            "r2_upload_fallback",
            bucket=bucket,
            key=key,
            fallback_uri=uri,
            error=str(last_exc),
        )
        return uri

    async def health_check(self, bucket: str) -> dict[str, object]:
        """Quick R2 connectivity check via HeadBucket."""
        t0 = time.monotonic()
        try:
            await asyncio.to_thread(self._client.head_bucket, Bucket=bucket)
            return {
                "healthy": True,
                "latency_ms": int((time.monotonic() - t0) * 1000),
                "error": "",
            }
        except Exception as exc:
            return {
                "healthy": False,
                "latency_ms": int((time.monotonic() - t0) * 1000),
                "error": str(exc),
            }
