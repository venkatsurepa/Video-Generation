from __future__ import annotations

from typing import TYPE_CHECKING

import boto3
import structlog

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

logger = structlog.get_logger()


class R2Client:
    """Cloudflare R2 storage client (S3-compatible via boto3)."""

    def __init__(
        self,
        account_id: str,
        access_key_id: str,
        secret_access_key: str,
    ) -> None:
        self._client: S3Client = boto3.client(
            "s3",
            endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
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
