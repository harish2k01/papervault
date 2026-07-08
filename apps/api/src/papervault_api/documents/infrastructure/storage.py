import asyncio
from pathlib import Path
from typing import Any

import boto3  # type: ignore[import-untyped]

from papervault_api.documents.application.storage import ObjectStorage, StoredObject


class S3ObjectStorage(ObjectStorage):
    def __init__(
        self,
        *,
        endpoint_url: str,
        access_key_id: str,
        secret_access_key: str,
        region: str,
    ) -> None:
        self._client: Any = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=region,
        )

    async def put_file(
        self,
        *,
        source_path: Path,
        bucket: str,
        key: str,
        content_type: str,
        metadata: dict[str, str],
    ) -> StoredObject:
        response = await asyncio.to_thread(
            self._put_object,
            source_path,
            bucket,
            key,
            content_type,
            metadata,
        )
        return StoredObject(
            bucket=bucket,
            key=key,
            version_id=response.get("VersionId"),
        )

    async def download_to_file(self, *, bucket: str, key: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(self._client.download_file, bucket, key, str(destination))

    async def delete_file(self, *, bucket: str, key: str) -> None:
        await asyncio.to_thread(self._client.delete_object, Bucket=bucket, Key=key)

    def _put_object(
        self,
        source_path: Path,
        bucket: str,
        key: str,
        content_type: str,
        metadata: dict[str, str],
    ) -> dict[str, Any]:
        with source_path.open("rb") as source_file:
            response: dict[str, Any] = self._client.put_object(
                Bucket=bucket,
                Key=key,
                Body=source_file,
                ContentType=content_type,
                Metadata=metadata,
            )
        return response
