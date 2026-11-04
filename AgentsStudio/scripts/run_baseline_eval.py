"""Run baseline evaluation on Hair System Expert and Marketing Director (`gemini-4-argon` + RAG + Reference Loader)."""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from google.adk.runners import InMemoryRunner
from google.genai import types

from src.agents.hair_system_expert.agent import hair_system_expert
from src.agents.marketing_director.agent import marketing_director

BANNED_WORDS = [
    "undetectable",
    "100% natural",
    "guaranteed",
    "perfect",
    "medical grade",
    "hypoallergenic",
    "dermatologist tested",
    "clinically tested",
    "safe for sensitive skin",
    "non-irritating",
    "onehead",
    "lordhair",
]


def check_no_banned_wording(text: str) -> tuple[bool, list[str]]:
    lower = text.lower()
    hits = [w for w in BANNED_WORDS if w in lower]
    return len(hits) == 0, hits


async def run_case(agent: Any, question: str, expected_tools: list[str]) -> dict[str, Any]:
    t0 = time.time()
    runner = InMemoryRunner(agent=agent, app_name=f"eval_{agent.name}")
    session = await runner.session_service.create_session(
        app_name=f"eval_{agent.name}", user_id="eval_user"
    )
    called_tools: list[str] = []
    tool_args: list[dict[str, Any]] = []
    tool_outputs: list[Any] = []
    text_parts: list[str] = []

    async def _consume() -> None:
        async for event in runner.run_async(
            user_id="eval_user",
            session_id=session.id,
            new_message=types.Content(role="user", parts=[types.Part.from_text(text=question)]),
        ):
            if event.content and event.content.parts:
                for p in event.content.parts:
                    if p.function_call:
                        called_tools.append(p.function_call.name)
                        tool_args.append(dict(p.function_call.args or {}))
                    if p.function_response:
                        tool_outputs.append(p.function_response.response)
                    if p.text:
                        text_parts.append(p.text)

    try:
        await asyncio.wait_for(_consume(), timeout=60.0)
    except asyncio.TimeoutError:
        text_parts.append("[TIMEOUT]")

    full_text = "\n".join(text_parts).strip()
    clean_ok, banned_hits = check_no_banned_wording(full_text)

    if not expected_tools:
        # Expect refusal (no generation tool called)
        gen_tools = {
            "generate_hair_system_image",
            "generate_hair_system_video",
            "generate_marble_head",
            "generate_editorial_collage",
            "generate_social_asset",
            "generate_campaign_visual",
        }
        tool_match = len(set(called_tools) & gen_tools) == 0
    else:
        tool_match = any(t in called_tools for t in expected_tools)

    return {
        "question": question,
        "expected_tools": expected_tools,
        "called_tools": called_tools,
        "tool_args": tool_args,
        "tool_match": tool_match,
        "no_banned_wording": clean_ok,
        "banned_hits": banned_hits,
        "passed": tool_match and clean_ok,
        "latency_s": round(time.time() - t0, 2),
        "response_preview": full_text[:300],
    }


async def main() -> None:
    hs_sample = [
        ("Show me a man with a #3 dark brown hair system, body wave, exposed hairline", ["generate_hair_system_image"]),
        ("Generate a before and after transformation for a 45-year-old man, Norwood 5", []),
        ("What hair system base should I get if I swim every day?", ["recommend_base_type"]),
        ("Calculate the right density for a 52-year-old man, Norwood 4", ["calculate_density"]),
        ("What color code matches dark brown hair with 30% grey at the temples?", ["match_hair_color"]),
        ("Look up reference swatches in the R2 manifest for french-lace base material", ["lookup_reference_swatches"]),
        ("What are the stock hair system models and their base thicknesses in Product Facts?", ["retrieve_hair_system_knowledge"]),
    ]

    mk_sample = [
        ("Show me Miles with a textured crop in gallery lighting", ["generate_marble_head"]),
        ("Create editorial collage No.01 featuring a man in his 40s with medium brown wavy hair", ["generate_editorial_collage"]),
        ("Write an email subject line, preheader, and body paragraph introducing the Nano Skin 0.03mm hair system for first-time buyers (Daniel avatar)", ["write_marketing_copy", "transfer_to_agent", "retrieve_marketing_brand"]),
        ("Write website hero-split section copy (eyebrow, H1 with one italic phrase, lead paragraph, and primary CTA label) for the Hair Solutions Co. homepage", ["write_marketing_copy", "transfer_to_agent", "retrieve_marketing_brand"]),
        ("Look up the Atelier Zero email layout and surface adjacency rules", ["get_brand_spec", "retrieve_marketing_brand"]),
        ("Retrieve the official storefront facts and email footer address from the marketing-brand knowledge base", ["retrieve_marketing_brand"]),
    ]

    print("Running Hair System Expert baseline eval (7 representative cases across all tools)...")
    hs_results = []
    for q, exp in hs_sample:
        res = await run_case(hair_system_expert, q, exp)
        hs_results.append(res)
        print(f"  [{'PASS' if res['passed'] else 'FAIL'}] {q[:65]} -> tools={res['called_tools']} ({res['latency_s']}s)")

    print("\nRunning Marketing Director baseline eval (6 representative cases across all tools)...")
    mk_results = []
    for q, exp in mk_sample:
        res = await run_case(marketing_director, q, exp)
        mk_results.append(res)
        print(f"  [{'PASS' if res['passed'] else 'FAIL'}] {q[:65]} -> tools={res['called_tools']} ({res['latency_s']}s)")

    summary = {
        "date": "2026-11-04",
        "project": "the-hair-concierge-2026",
        "planner_model": "gemini-4-argon",
        "copywriter_model": "gemini-3.5-flash",
        "image_model": "gemini-3.1-flash-image",
        "rag_corpora": {
            "hair_system_knowledge": "projects/the-hair-concierge-2026/locations/us-west1/ragCorpora/4611686018427387904",
            "marketing_brand": "projects/the-hair-concierge-2026/locations/us-west1/ragCorpora/2305843009213693952",
        },
        "hair_system_expert": {
            "total": len(hs_results),
            "passed": sum(1 for r in hs_results if r["passed"]),
            "tool_accuracy": round(sum(1 for r in hs_results if r["tool_match"]) / len(hs_results), 3),
            "compliance_rate": round(sum(1 for r in hs_results if r["no_banned_wording"]) / len(hs_results), 3),
            "cases": hs_results,
        },
        "marketing_director": {
            "total": len(mk_results),
            "passed": sum(1 for r in mk_results if r["passed"]),
            "tool_accuracy": round(sum(1 for r in mk_results if r["tool_match"]) / len(mk_results), 3),
            "compliance_rate": round(sum(1 for r in mk_results if r["no_banned_wording"]) / len(mk_results), 3),
            "cases": mk_results,
        },
    }

    out_path = ROOT / "docs" / "eval_baseline_2026-11-03.json"
    out_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved baseline report -> {out_path.relative_to(ROOT)}")
    print(
        f"Hair System Expert: {summary['hair_system_expert']['passed']}/{summary['hair_system_expert']['total']} passed | "
        f"Marketing Director: {summary['marketing_director']['passed']}/{summary['marketing_director']['total']} passed"
    )


if __name__ == "__main__":
    asyncio.run(main())
