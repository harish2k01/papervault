"""Private inference clients. Never include provider bodies or input text in errors."""

import base64
import json
import math
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class InferenceUnavailable(RuntimeError):
    pass


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


class PrivateInference:
    def __init__(self, base_url: str, timeout: float = 120) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def request(self, path: str, payload: dict[str, Any] | None = None) -> Any:
        request = Request(
            self.base_url + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={"Content-Type": "application/json"},
        )
        try:
            with build_opener(ProxyHandler({}), NoRedirects()).open(
                request, timeout=self.timeout
            ) as response:
                return json.load(response)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError):
            # Even a validation error may echo the entire document. Suppress its cause too.
            raise InferenceUnavailable("Local inference request failed") from None


class SemanticModels:
    def __init__(
        self,
        embeddings: PrivateInference,
        reranker: PrivateInference,
        *,
        model: str,
        revision: str,
        dimensions: int,
        reranker_model: str,
        reranker_revision: str,
    ) -> None:
        self.embeddings = embeddings
        self.reranker = reranker
        self.model = model
        self.revision = revision
        self.dimensions = dimensions
        self.reranker_model = reranker_model
        self.reranker_revision = reranker_revision

    def verify(self, *, rerank: bool = False) -> None:
        client = self.reranker if rerank else self.embeddings
        model = self.reranker_model if rerank else self.model
        revision = self.reranker_revision if rerank else self.revision
        info = client.request("/info")
        if (
            not isinstance(info, dict)
            or info.get("model_id") != model
            or info.get("model_sha") != revision
        ):
            raise InferenceUnavailable(
                "Local model identity does not match the index configuration"
            )

    def embed(self, texts: list[str], *, query: bool = False) -> list[list[float]]:
        self.verify()
        # BGE's query instruction is model-specific, never prepended to document passages.
        inputs = [
            ("Represent this sentence for searching relevant passages: " + text)
            if query and self.model.startswith("BAAI/bge-small-en")
            else text
            for text in texts
        ]
        vectors = self.embeddings.request("/embed", {"inputs": inputs, "truncate": False})
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise InferenceUnavailable("Local embeddings returned an invalid batch")
        result: list[list[float]] = []
        for vector in vectors:
            if (
                not isinstance(vector, list)
                or len(vector) != self.dimensions
                or any(type(x) not in (int, float) or not math.isfinite(x) for x in vector)
            ):
                raise InferenceUnavailable("Local embeddings returned invalid dimensions or values")
            norm = math.sqrt(sum(x * x for x in vector))
            if norm == 0:
                raise InferenceUnavailable("Local embeddings returned an empty vector")
            result.append([float(x) / norm for x in vector])
        return result

    def rank(self, question: str, texts: list[str]) -> list[tuple[int, float]]:
        if not texts:
            return []
        self.verify(rerank=True)
        result = self.reranker.request(
            "/rerank", {"query": question, "texts": texts, "truncate": False, "raw_scores": False}
        )
        if not isinstance(result, list) or len(result) != len(texts):
            raise InferenceUnavailable("Local reranker returned an incomplete result")
        ranked: list[tuple[int, float]] = []
        for item in result:
            if not isinstance(item, dict):
                raise InferenceUnavailable("Local reranker returned an invalid result")
            index, score = item.get("index"), item.get("score")
            if (
                type(index) is not int
                or not 0 <= index < len(texts)
                or not isinstance(score, (int, float))
                or isinstance(score, bool)
                or not math.isfinite(score)
            ):
                raise InferenceUnavailable("Local reranker returned an invalid score")
            ranked.append((index, float(score)))
        if len({index for index, _ in ranked}) != len(texts):
            raise InferenceUnavailable("Local reranker returned duplicate indexes")
        return sorted(ranked, key=lambda pair: pair[1], reverse=True)


class LayoutParser:
    identity = "docling-serve1.37.0/docling2.138.0/core2.101.1-structured-v1"

    def __init__(self, client: PrivateInference) -> None:
        self.client = client

    def parse(self, content: bytes, content_type: str) -> dict[str, Any]:
        versions = self.client.request("/version")
        expected = {"docling-serve": "1.37.0", "docling": "2.138.0", "docling-core": "2.101.1"}
        if not isinstance(versions, dict) or any(
            versions.get(key) != value for key, value in expected.items()
        ):
            raise InferenceUnavailable(
                "Local parser version does not match the index configuration"
            )
        # A neutral filename also avoids leaking personal names through parser logs.
        filename = {
            "application/pdf": "document.pdf",
            "image/png": "document.png",
            "image/jpeg": "document.jpg",
        }.get(content_type)
        if filename is None:
            raise InferenceUnavailable("Unsupported structured document format")
        response = self.client.request(
            "/v1/convert/source",
            {
                "options": {
                    "to_formats": ["json"],
                    "image_export_mode": "placeholder",
                    "do_ocr": True,
                    "force_ocr": False,
                    "do_table_structure": True,
                    "table_mode": "accurate",
                    "include_images": False,
                    "include_page_images": False,
                    "abort_on_error": True,
                    "document_timeout": 1100,
                    "do_pdf_heading_hierarchy": True,
                },
                "sources": [
                    {
                        "kind": "file",
                        "base64_string": base64.b64encode(content).decode(),
                        "filename": filename,
                    }
                ],
            },
        )
        if not isinstance(response, dict) or response.get("status") != "success":
            raise InferenceUnavailable("Structured conversion did not complete successfully")
        document = response.get("document", {}).get("json_content")
        if not isinstance(document, dict):
            raise InferenceUnavailable("Structured conversion returned no document")
        return document
