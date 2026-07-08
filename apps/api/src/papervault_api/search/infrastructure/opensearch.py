import base64
import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin
from urllib.request import Request, urlopen
from uuid import UUID

from papervault_api.core.config import Settings
from papervault_api.search.application.indexing import (
    NullSearchDocumentIndex,
    SearchIndexDocument,
)


class OpenSearchError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class OpenSearchResponse:
    status_code: int
    body: dict[str, Any] | None = None


class HttpOpenSearchClient:
    def __init__(
        self,
        *,
        base_url: str,
        username: str | None,
        password: str | None,
        timeout_seconds: float,
    ) -> None:
        self._base_url = base_url.rstrip("/") + "/"
        self._username = username
        self._password = password
        self._timeout_seconds = timeout_seconds

    def exists(self, path: str) -> bool:
        try:
            self.request("HEAD", path)
        except OpenSearchError as exc:
            if "HTTP 404" in str(exc):
                return False
            raise
        return True

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        ignore_not_found: bool = False,
    ) -> OpenSearchResponse:
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = Request(
            urljoin(self._base_url, path.lstrip("/")),
            data=data,
            method=method,
            headers=self._headers(body is not None),
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                response_body = response.read()
                return OpenSearchResponse(
                    status_code=response.status,
                    body=decode_json_response(response_body),
                )
        except HTTPError as exc:
            if ignore_not_found and exc.code == 404:
                return OpenSearchResponse(status_code=404)
            detail = exc.read().decode("utf-8", errors="replace")
            raise OpenSearchError(f"OpenSearch HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise OpenSearchError(f"OpenSearch request failed: {exc.reason}") from exc

    def _headers(self, has_body: bool) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if has_body:
            headers["Content-Type"] = "application/json"
        if self._username and self._password:
            token = base64.b64encode(
                f"{self._username}:{self._password}".encode(),
            ).decode("ascii")
            headers["Authorization"] = f"Basic {token}"
        return headers


class OpenSearchDocumentIndex:
    def __init__(
        self,
        *,
        client: HttpOpenSearchClient,
        index_name: str,
        embedding_dimensions: int,
    ) -> None:
        self._client = client
        self._index_name = index_name
        self._embedding_dimensions = embedding_dimensions

    def ensure_index(self) -> None:
        if self._client.exists(self._index_name):
            return
        self._client.request("PUT", self._index_name, self._index_definition())

    def index_document(self, document: SearchIndexDocument) -> None:
        path = f"{self._index_name}/_doc/{quote(str(document.document_id), safe='')}"
        self._client.request("PUT", path, document_to_opensearch_body(document))

    def delete_document(self, document_id: UUID) -> None:
        path = f"{self._index_name}/_doc/{quote(str(document_id), safe='')}"
        self._client.request("DELETE", path, ignore_not_found=True)

    def _index_definition(self) -> dict[str, Any]:
        return {
            "settings": {
                "index": {
                    "knn": True,
                },
            },
            "mappings": {
                "dynamic": "false",
                "properties": {
                    "document_id": {"type": "keyword"},
                    "owner_id": {"type": "keyword"},
                    "title": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                    "original_filename": {"type": "text"},
                    "content_type": {"type": "keyword"},
                    "status": {"type": "keyword"},
                    "document_type": {"type": "keyword"},
                    "document_date": {"type": "date"},
                    "issuer": {"type": "keyword"},
                    "organization": {"type": "keyword"},
                    "summary": {"type": "text"},
                    "text": {"type": "text"},
                    "tags": {"type": "keyword"},
                    "metadata": {"type": "object", "enabled": True},
                    "keywords": {"type": "keyword"},
                    "suggested_tags": {"type": "keyword"},
                    "entities": {"type": "object", "enabled": True},
                    "embedding": {
                        "type": "knn_vector",
                        "dimension": self._embedding_dimensions,
                    },
                    "embedding_dimensions": {"type": "integer"},
                    "source_text_sha256": {"type": "keyword"},
                    "created_at": {"type": "date"},
                    "updated_at": {"type": "date"},
                },
            },
        }


def build_search_document_index(
    settings: Settings,
) -> OpenSearchDocumentIndex | NullSearchDocumentIndex:
    if not settings.search_index_enabled:
        return NullSearchDocumentIndex()

    client = HttpOpenSearchClient(
        base_url=settings.opensearch_url,
        username=settings.opensearch_username,
        password=settings.opensearch_password,
        timeout_seconds=settings.opensearch_timeout_seconds,
    )
    return OpenSearchDocumentIndex(
        client=client,
        index_name=settings.opensearch_documents_index,
        embedding_dimensions=settings.embedding_dimensions,
    )


def document_to_opensearch_body(document: SearchIndexDocument) -> dict[str, Any]:
    body: dict[str, Any] = {
        "document_id": str(document.document_id),
        "owner_id": str(document.owner_id),
        "title": document.title,
        "original_filename": document.original_filename,
        "content_type": document.content_type,
        "status": document.status,
        "document_type": document.document_type,
        "document_date": document.document_date.isoformat()
        if document.document_date is not None
        else None,
        "issuer": document.issuer,
        "organization": document.organization,
        "summary": document.summary,
        "text": document.text,
        "tags": list(document.tags),
        "metadata": document.metadata,
        "keywords": list(document.keywords),
        "suggested_tags": list(document.suggested_tags),
        "entities": list(document.entities),
        "embedding": list(document.embedding) if document.embedding is not None else None,
        "embedding_dimensions": document.embedding_dimensions,
        "source_text_sha256": document.source_text_sha256,
        "created_at": document.created_at.isoformat(),
        "updated_at": document.updated_at.isoformat(),
    }
    return {key: value for key, value in body.items() if value is not None}


def decode_json_response(response_body: bytes) -> dict[str, Any] | None:
    if not response_body:
        return None
    decoded = json.loads(response_body.decode("utf-8"))
    if not isinstance(decoded, dict):
        raise OpenSearchError("OpenSearch response must be a JSON object")
    return decoded
