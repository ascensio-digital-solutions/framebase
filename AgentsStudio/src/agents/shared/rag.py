"""Vertex AI RAG Engine retrieval tools for Agents Studio.

Subclasses ADK's ``VertexAiRagRetrieval`` so regional RAG corpora in ``us-west1``
work alongside Python function tools when the planning model runs on the ``global``
Vertex AI endpoint (e.g. ``gemini-4-argon`` and ``gemini-3.5-flash``).
"""

from __future__ import annotations

import asyncio
import json
import os
import urllib.request
from typing import Any

import google.auth
import google.auth.transport.requests
from google.adk.tools.retrieval.base_retrieval_tool import BaseRetrievalTool
from google.adk.tools.retrieval.vertex_ai_rag_retrieval import VertexAiRagRetrieval

HAIR_SYSTEM_RAG_CORPUS = os.environ.get(
    "HAIR_SYSTEM_RAG_CORPUS",
    "projects/the-hair-concierge-2026/locations/us-west1/ragCorpora/4611686018427387904",
)

MARKETING_BRAND_RAG_CORPUS = os.environ.get(
    "MARKETING_BRAND_RAG_CORPUS",
    "projects/the-hair-concierge-2026/locations/us-west1/ragCorpora/2305843009213693952",
)


def retrieve_rag_sync(
    corpus: str,
    query: str,
    similarity_top_k: int = 5,
    vector_distance_threshold: float | None = None,
) -> list[dict[str, Any]]:
    """Synchronously query a regional Vertex AI RAG corpus via ``:retrieveContexts``."""
    parts = corpus.split("/")
    project = (
        parts[1]
        if len(parts) >= 4 and parts[0] == "projects"
        else os.environ.get("GOOGLE_CLOUD_PROJECT", "the-hair-concierge-2026")
    )
    location = (
        parts[3]
        if len(parts) >= 4 and parts[2] == "locations"
        else "us-west1"
    )

    creds, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    creds.refresh(google.auth.transport.requests.Request())
    url = (
        f"https://{location}-aiplatform.googleapis.com/v1beta1/"
        f"projects/{project}/locations/{location}:retrieveContexts"
    )
    store_cfg: dict[str, Any] = {"rag_resources": [{"rag_corpus": corpus}]}
    if vector_distance_threshold is not None:
        store_cfg["vector_distance_threshold"] = vector_distance_threshold
    payload = {
        "vertex_rag_store": store_cfg,
        "query": {"text": query, "similarity_top_k": similarity_top_k},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {creds.token}",
            "X-Goog-User-Project": project,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    contexts = data.get("contexts", {}).get("contexts", [])
    return [
        {
            "source_uri": c.get("sourceUri", ""),
            "text": c.get("text", ""),
            "distance": c.get("distance"),
        }
        for c in contexts
        if c.get("text")
    ]


class RegionalVertexAiRagRetrieval(VertexAiRagRetrieval):
    """VertexAiRagRetrieval that exposes a standard function tool declaration
    and queries the corpus's regional ``:retrieveContexts`` endpoint directly.
    """

    async def process_llm_request(self, *, tool_context: Any, llm_request: Any) -> None:
        await BaseRetrievalTool.process_llm_request(
            self, tool_context=tool_context, llm_request=llm_request
        )

    async def run_async(self, *, args: dict[str, Any], tool_context: Any) -> Any:
        query = args.get("query", "")
        if not isinstance(query, str) or not query.strip():
            return {"status": "error", "message": "A non-empty string 'query' is required."}

        project, location = self._project_and_location()
        corpus = None
        if self.vertex_rag_store.rag_corpora:
            corpus = self.vertex_rag_store.rag_corpora[0]
        elif self.vertex_rag_store.rag_resources:
            corpus = self.vertex_rag_store.rag_resources[0].rag_corpus

        if not corpus or not project or not location:
            return {"status": "error", "message": "RAG corpus, project, or location not configured."}

        top_k = self.vertex_rag_store.similarity_top_k or 5
        threshold = self.vertex_rag_store.vector_distance_threshold

        try:
            results = await asyncio.to_thread(
                retrieve_rag_sync,
                corpus,
                query,
                top_k,
                threshold,
            )
            return {
                "status": "retrieved",
                "corpus": corpus,
                "query": query,
                "count": len(results),
                "contexts": results,
            }
        except Exception as exc:
            return {
                "status": "error",
                "corpus": corpus,
                "query": query,
                "error": str(exc),
            }


def create_hair_system_rag_tool(similarity_top_k: int = 5) -> RegionalVertexAiRagRetrieval:
    """Create the Tier-1 Hair System Knowledge RAG retrieval tool."""
    return RegionalVertexAiRagRetrieval(
        name="retrieve_hair_system_knowledge",
        description=(
            "Retrieve Tier 1 approved Hair Solutions Co. hair system specifications, "
            "product facts (stock bases, thicknesses, densities, lifespans), "
            "Approved Claims compliance rules, the hair system bible, and Media Workshop taxonomy."
        ),
        rag_resources=[{"rag_corpus": HAIR_SYSTEM_RAG_CORPUS}],
        similarity_top_k=similarity_top_k,
    )


def create_marketing_brand_rag_tool(similarity_top_k: int = 5) -> RegionalVertexAiRagRetrieval:
    """Create the Tier-1 Marketing & Brand RAG retrieval tool."""
    return RegionalVertexAiRagRetrieval(
        name="retrieve_marketing_brand",
        description=(
            "Retrieve Tier 1 approved Hair Solutions Co. Atelier Zero design system "
            "(ascensio-digital-solutions/brand-design-system), tokens, brand voice, "
            "composition rules, email/social/shopify platform contracts, Approved Claims, "
            "Approved Support Facts, Storefront Facts, product facts, Krea collage handoff, "
            "and 2026 rebrand launch campaign strategy."
        ),
        rag_resources=[{"rag_corpus": MARKETING_BRAND_RAG_CORPUS}],
        similarity_top_k=similarity_top_k,
    )
