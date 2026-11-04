"""Shared utilities for Agents Studio (Vertex AI RAG retrieval and R2/local reference loading)."""

from .rag import (
    HAIR_SYSTEM_RAG_CORPUS,
    MARKETING_BRAND_RAG_CORPUS,
    RegionalVertexAiRagRetrieval,
    create_hair_system_rag_tool,
    create_marketing_brand_rag_tool,
)
from .references import (
    lookup_manifest_references,
    select_hair_system_references,
    select_marketing_references,
)

__all__ = [
    "HAIR_SYSTEM_RAG_CORPUS",
    "MARKETING_BRAND_RAG_CORPUS",
    "RegionalVertexAiRagRetrieval",
    "create_hair_system_rag_tool",
    "create_marketing_brand_rag_tool",
    "lookup_manifest_references",
    "select_hair_system_references",
    "select_marketing_references",
]
