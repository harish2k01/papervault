from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class StoredObject:
    bucket: str
    key: str
    version_id: str | None = None


class ObjectStorage(Protocol):
    async def put_file(
        self,
        *,
        source_path: Path,
        bucket: str,
        key: str,
        content_type: str,
        metadata: dict[str, str],
    ) -> StoredObject:
        raise NotImplementedError

    async def download_to_file(self, *, bucket: str, key: str, destination: Path) -> None:
        raise NotImplementedError

    async def delete_file(self, *, bucket: str, key: str) -> None:
        raise NotImplementedError
