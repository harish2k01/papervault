import base64
import json
from dataclasses import dataclass
from datetime import datetime
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
from papervault_api.search.application.service import (
    SearchFilters,
    SearchRequest,
    SearchResult,
    build_highlights,
)
from papervault_api.search.domain.enums import SearchMode


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


class OpenSearchDocumentSearchIndex:
    def __init__(
        self,
        *,
        client: HttpOpenSearchClient,
        index_name: str,
    ) -> None:
        self._client = client
        self._index_name = index_name

    def search(
        self,
        request: SearchRequest,
        query_embedding: tuple[float, ...] | None,
    ) -> tuple[SearchResult, ...]:
        response = self._client.request(
            "POST",
            f"{self._index_name}/_search",
            opensearch_search_body(request, query_embedding),
        )
        if response.body is None:
            return ()
        return parse_search_response(response.body, request)


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


def build_search_query_index(settings: Settings) -> OpenSearchDocumentSearchIndex | None:
    if settings.search_query_backend != "opensearch" or not settings.search_index_enabled:
        return None

    client = HttpOpenSearchClient(
        base_url=settings.opensearch_url,
        username=settings.opensearch_username,
        password=settings.opensearch_password,
        timeout_seconds=settings.opensearch_timeout_seconds,
    )
    return OpenSearchDocumentSearchIndex(
        client=client,
        index_name=settings.opensearch_documents_index,
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


def opensearch_search_body(
    request: SearchRequest,
    query_embedding: tuple[float, ...] | None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "from": request.offset,
        "size": request.limit,
        "_source": [
            "document_id",
            "title",
            "original_filename",
            "document_type",
            "status",
            "summary",
            "created_at",
            "text",
        ],
        "query": opensearch_query(request, query_embedding),
        "highlight": {
            "number_of_fragments": 3,
            "fragment_size": 160,
            "fields": {
                "title": {},
                "original_filename": {},
                "summary": {},
                "text": {},
            },
        },
        "sort": [{"_score": "desc"}, {"created_at": "desc"}],
    }
    if not request.query:
        body["sort"] = [{"created_at": "desc"}]
    return body


def opensearch_query(
    request: SearchRequest,
    query_embedding: tuple[float, ...] | None,
) -> dict[str, Any]:
    filters = opensearch_filters(request.owner_id, request.filters)
    if not request.query:
        return {"bool": {"filter": filters}}

    keyword_query = opensearch_keyword_query(request.query)
    semantic_query = (
        opensearch_semantic_query(query_embedding) if query_embedding is not None else None
    )

    if request.mode is SearchMode.KEYWORD or semantic_query is None:
        return {"bool": {"filter": filters, "must": [keyword_query]}}

    if request.mode is SearchMode.SEMANTIC:
        return {
            "script_score": {
                "query": {"bool": {"filter": [*filters, {"exists": {"field": "embedding"}}]}},
                "script": semantic_query["script_score"]["script"],
            },
        }

    return {
        "bool": {
            "filter": filters,
            "should": [
                keyword_query,
                semantic_query,
            ],
            "minimum_should_match": 1,
        },
    }


def opensearch_filters(owner_id: UUID, filters: SearchFilters) -> list[dict[str, Any]]:
    clauses: list[dict[str, Any]] = [{"term": {"owner_id": str(owner_id)}}]
    if filters.document_type:
        clauses.append({"term": {"document_type": filters.document_type}})
    if filters.issuer:
        clauses.append(case_insensitive_term_filter("issuer", filters.issuer))
    if filters.organization:
        clauses.append(case_insensitive_term_filter("organization", filters.organization))
    if filters.tag:
        clauses.append({"term": {"tags": filters.tag}})
    date_range: dict[str, str] = {}
    if filters.date_from:
        date_range["gte"] = filters.date_from.isoformat()
    if filters.date_to:
        date_range["lte"] = filters.date_to.isoformat()
    if date_range:
        clauses.append({"range": {"document_date": date_range}})
    return clauses


def case_insensitive_term_filter(field: str, value: str) -> dict[str, Any]:
    return {"term": {field: {"value": value, "case_insensitive": True}}}


def opensearch_keyword_query(query: str) -> dict[str, Any]:
    return {
        "multi_match": {
            "query": query,
            "fields": [
                "title^4",
                "original_filename^2",
                "issuer^2",
                "organization^2",
                "summary^2",
                "text",
                "keywords^2",
                "suggested_tags^2",
            ],
            "type": "best_fields",
            "operator": "or",
        },
    }


def opensearch_semantic_query(query_embedding: tuple[float, ...]) -> dict[str, Any]:
    return {
        "script_score": {
            "query": {"exists": {"field": "embedding"}},
            "script": {
                "source": "knn_score",
                "lang": "knn",
                "params": {
                    "field": "embedding",
                    "query_value": list(query_embedding),
                    "space_type": "cosinesimil",
                },
            },
        },
    }


def parse_search_response(
    response_body: dict[str, Any],
    request: SearchRequest,
) -> tuple[SearchResult, ...]:
    hits = response_body.get("hits")
    if not isinstance(hits, dict):
        raise OpenSearchError("OpenSearch search response is missing hits")
    raw_hits = hits.get("hits")
    if not isinstance(raw_hits, list):
        raise OpenSearchError("OpenSearch search response hits must be a list")

    results: list[SearchResult] = []
    for raw_hit in raw_hits:
        if not isinstance(raw_hit, dict):
            continue
        source = raw_hit.get("_source")
        if not isinstance(source, dict):
            continue
        results.append(search_result_from_hit(raw_hit, source, request))
    return tuple(results)


def search_result_from_hit(
    hit: dict[str, Any],
    source: dict[str, Any],
    request: SearchRequest,
) -> SearchResult:
    highlights = highlights_from_hit(hit)
    if not highlights:
        highlights = build_highlights(
            request.query,
            " ".join(
                str(value)
                for value in (
                    source.get("title"),
                    source.get("original_filename"),
                    source.get("summary"),
                    source.get("text"),
                )
                if value
            ),
        )

    return SearchResult(
        document_id=UUID(required_str(source, "document_id")),
        title=required_str(source, "title"),
        original_filename=required_str(source, "original_filename"),
        document_type=required_str(source, "document_type"),
        status=required_str(source, "status"),
        summary=optional_str(source.get("summary")),
        created_at=parse_opensearch_datetime(required_str(source, "created_at")),
        score=round(float(hit.get("_score") or 0), 6),
        highlights=highlights,
    )


def highlights_from_hit(hit: dict[str, Any]) -> tuple[str, ...]:
    highlight = hit.get("highlight")
    if not isinstance(highlight, dict):
        return ()

    values: list[str] = []
    for fragments in highlight.values():
        if not isinstance(fragments, list):
            continue
        values.extend(str(fragment) for fragment in fragments if fragment)
    return tuple(values[:3])


def required_str(source: dict[str, Any], field: str) -> str:
    value = source.get(field)
    if not isinstance(value, str) or not value:
        raise OpenSearchError(f"OpenSearch hit is missing required field: {field}")
    return value


def optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def parse_opensearch_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def decode_json_response(response_body: bytes) -> dict[str, Any] | None:
    if not response_body:
        return None
    decoded = json.loads(response_body.decode("utf-8"))
    if not isinstance(decoded, dict):
        raise OpenSearchError("OpenSearch response must be a JSON object")
    return decoded
