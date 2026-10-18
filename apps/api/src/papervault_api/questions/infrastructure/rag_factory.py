import hashlib

from papervault_api.core.config import Settings
from papervault_api.core.model_clients import JsonHttpClient, ModelClient, OllamaModelClient
from papervault_api.questions.infrastructure.local_inference import (
    LayoutParser,
    PrivateInference,
    SemanticModels,
)


def semantic_models(settings: Settings) -> SemanticModels:
    return SemanticModels(
        PrivateInference(settings.rag_embeddings_url),
        PrivateInference(settings.rag_reranker_url),
        model=settings.rag_embedding_model,
        revision=settings.rag_embedding_revision,
        dimensions=settings.rag_dimensions,
        reranker_model=settings.rag_reranker_model,
        reranker_revision=settings.rag_reranker_revision,
    )


def pipeline_id(settings: Settings) -> str:
    identity = (
        f"structured-v1:{LayoutParser.identity}:{settings.rag_embedding_model}:"
        f"{settings.rag_embedding_revision}:{settings.rag_dimensions}"
    )
    return hashlib.sha256(identity.encode()).hexdigest()


def analysis_client(settings: Settings) -> ModelClient:
    settings.validate_private_inference_url(settings.ollama_base_url)
    if settings.rag_chat_model:
        if not settings.rag_chat_digest:
            raise ValueError("Candidate analysis requires a pinned model digest")
        settings = settings.model_copy(
            update={
                "ollama_chat_model": settings.rag_chat_model,
                "ollama_expected_digest": settings.rag_chat_digest,
            }
        )
    return OllamaModelClient(
        base_url=settings.ollama_base_url,
        chat_model=settings.ollama_chat_model,
        embedding_model=settings.ollama_embedding_model,
        timeout_seconds=settings.model_provider_timeout_seconds,
        context_tokens=settings.ollama_context_tokens,
        max_output_tokens=settings.ollama_max_output_tokens,
        expected_digest=settings.ollama_expected_digest,
        http_client=JsonHttpClient(
            base_url=settings.ollama_base_url,
            timeout_seconds=settings.model_provider_timeout_seconds,
            private_only=True,
        ),
    )
