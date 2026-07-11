from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

if TYPE_CHECKING:
    from papervault_api.core.config import Settings


class ModelProviderError(RuntimeError):
    pass


class ModelClient(Protocol):
    provider: str
    chat_model: str
    embedding_model: str

    def complete(self, *, system: str, user: str) -> str:
        raise NotImplementedError

    def embed(self, text: str) -> tuple[float, ...]:
        raise NotImplementedError

    def health(self) -> tuple[bool, str]:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class JsonHttpResponse:
    status_code: int
    body: dict[str, Any]


class JsonHttpClient:
    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/") + "/"
        self._timeout_seconds = timeout_seconds
        self._headers = headers or {}

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> JsonHttpResponse:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Accept": "application/json", **self._headers}
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = Request(
            urljoin(self._base_url, path.lstrip("/")),
            data=data,
            method=method,
            headers=headers,
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ModelProviderError("Model provider returned a non-object response")
                return JsonHttpResponse(status_code=response.status, body=payload)
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise ModelProviderError(f"Model provider HTTP {exc.code}: {detail}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            detail = getattr(exc, "reason", str(exc))
            raise ModelProviderError(f"Model provider request failed: {detail}") from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ModelProviderError("Model provider returned invalid JSON") from exc


class OllamaModelClient:
    provider = "ollama"

    def __init__(
        self,
        *,
        base_url: str,
        chat_model: str,
        embedding_model: str,
        timeout_seconds: float,
        http_client: JsonHttpClient | None = None,
    ) -> None:
        self.chat_model = chat_model
        self.embedding_model = embedding_model
        self._http = http_client or JsonHttpClient(
            base_url=base_url,
            timeout_seconds=timeout_seconds,
        )

    def complete(self, *, system: str, user: str) -> str:
        response = self._http.request(
            "POST",
            "/api/chat",
            {
                "model": self.chat_model,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
        message = response.body.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise ModelProviderError("Ollama response is missing message content")
        content = message["content"]
        assert isinstance(content, str)
        return content

    def embed(self, text: str) -> tuple[float, ...]:
        response = self._http.request(
            "POST",
            "/api/embed",
            {"model": self.embedding_model, "input": text},
        )
        embeddings = response.body.get("embeddings")
        if (
            not isinstance(embeddings, list)
            or not embeddings
            or not isinstance(embeddings[0], list)
        ):
            raise ModelProviderError("Ollama response is missing embeddings")
        return numeric_vector(embeddings[0])

    def health(self) -> tuple[bool, str]:
        try:
            self._http.request("GET", "/api/tags")
        except ModelProviderError as exc:
            return False, str(exc)
        return True, "Ollama is reachable"


class OpenAICompatibleModelClient:
    provider = "openai_compatible"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        chat_model: str,
        embedding_model: str,
        timeout_seconds: float,
        http_client: JsonHttpClient | None = None,
    ) -> None:
        self.chat_model = chat_model
        self.embedding_model = embedding_model
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._http = http_client or JsonHttpClient(
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            headers=headers,
        )

    def complete(self, *, system: str, user: str) -> str:
        response = self._http.request(
            "POST",
            "/chat/completions",
            {
                "model": self.chat_model,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
        choices = response.body.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ModelProviderError("OpenAI-compatible response is missing choices")
        first = choices[0]
        message = first.get("message") if isinstance(first, dict) else None
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise ModelProviderError("OpenAI-compatible response is missing message content")
        content = message["content"]
        assert isinstance(content, str)
        return content

    def embed(self, text: str) -> tuple[float, ...]:
        response = self._http.request(
            "POST",
            "/embeddings",
            {"model": self.embedding_model, "input": text},
        )
        data = response.body.get("data")
        if not isinstance(data, list) or not data:
            raise ModelProviderError("OpenAI-compatible response is missing embedding data")
        first = data[0]
        embedding = first.get("embedding") if isinstance(first, dict) else None
        if not isinstance(embedding, list):
            raise ModelProviderError("OpenAI-compatible response is missing an embedding")
        return numeric_vector(embedding)

    def health(self) -> tuple[bool, str]:
        try:
            self._http.request("GET", "/models")
        except ModelProviderError as exc:
            return False, str(exc)
        return True, "OpenAI-compatible endpoint is reachable"


def numeric_vector(values: list[Any]) -> tuple[float, ...]:
    try:
        vector = tuple(float(value) for value in values)
    except (TypeError, ValueError) as exc:
        raise ModelProviderError("Embedding contains non-numeric values") from exc
    if not vector:
        raise ModelProviderError("Embedding vector is empty")
    return vector


def parse_json_object(content: str) -> dict[str, Any]:
    normalized = content.strip()
    if normalized.startswith("```"):
        normalized = normalized.removeprefix("```json").removeprefix("```")
        normalized = normalized.removesuffix("```").strip()
    try:
        payload = json.loads(normalized)
    except json.JSONDecodeError as exc:
        raise ModelProviderError("Model response is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ModelProviderError("Model response must be a JSON object")
    return payload


def build_model_client(
    provider: str,
    settings: Settings,
    *,
    timeout_seconds: float | None = None,
) -> ModelClient:
    timeout = timeout_seconds or settings.model_provider_timeout_seconds
    if provider == "ollama":
        return OllamaModelClient(
            base_url=settings.ollama_base_url,
            chat_model=settings.ollama_chat_model,
            embedding_model=settings.ollama_embedding_model,
            timeout_seconds=timeout,
        )
    if provider == "openai_compatible":
        return OpenAICompatibleModelClient(
            base_url=settings.openai_compatible_base_url,
            api_key=settings.openai_compatible_api_key,
            chat_model=settings.openai_compatible_chat_model,
            embedding_model=settings.openai_compatible_embedding_model,
            timeout_seconds=timeout,
        )
    raise ValueError(f"Unsupported model provider: {provider}")
