#!/usr/bin/env python3
"""
Nano Banana 2.1 Studio CLI — Image Generation, Multi-Reference Fusion,
Conversational Editing, and Preference Memory for Google Antigravity.

Uses the Google GenAI Interactions API (`google-genai >= 2.30.1`) and loads
`GEMINI_API_KEY` from `/Users/vincent/.env`.
"""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import io
import json
import mimetypes
import os
from pathlib import Path
import re
import shutil
import sys
from typing import Any

from dotenv import load_dotenv
from google import genai
from PIL import Image

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV_PATH = Path("/Users/vincent/.env")
GEMINI_MD_PATH = WORKSPACE_ROOT / "GEMINI.md"
REFERENCES_DIR = WORKSPACE_ROOT / "references"
OUTPUTS_DIR = WORKSPACE_ROOT / "outputs"
GENERATED_DIR = OUTPUTS_DIR / "generated"
HISTORY_PATH = OUTPUTS_DIR / "history.jsonl"

MAX_REFERENCE_IMAGES = 14
SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".heic", ".heif"}

VALID_ASPECT_RATIOS = {
    "1:1", "4:5", "5:4", "3:4", "4:3", "9:16", "16:9",
    "2:3", "3:2", "21:9", "1:4", "4:1", "1:8", "8:1",
}


def load_environment(env_file: Path = DEFAULT_ENV_PATH) -> str:
    """Load GEMINI_API_KEY from /Users/vincent/.env or local .env."""
    if env_file.exists():
        load_dotenv(env_file, override=False)
    local_env = WORKSPACE_ROOT / ".env"
    if local_env.exists():
        load_dotenv(local_env, override=False)

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            f"GEMINI_API_KEY not found in environment or {env_file}. "
            "Add GEMINI_API_KEY=... to /Users/vincent/.env."
        )
    return api_key


def read_visual_preferences(gemini_md: Path = GEMINI_MD_PATH) -> str:
    """Extract the active preference block from GEMINI.md."""
    if not gemini_md.exists():
        return ""
    content = gemini_md.read_text(encoding="utf-8")
    match = re.search(
        r"<!-- PREFERENCES_START -->(.*?)<!-- PREFERENCES_END -->",
        content,
        flags=re.DOTALL,
    )
    if match:
        return match.group(1).strip()
    return ""


def encode_reference_image(path: Path) -> dict[str, str]:
    """Read and base64-encode a local reference image for the Interactions API."""
    if not path.exists():
        raise FileNotFoundError(f"Reference image not found: {path}")

    mime_type, _ = mimetypes.guess_type(str(path))
    # Convert unsupported or raw formats via Pillow into PNG if needed
    if mime_type not in {"image/png", "image/jpeg", "image/webp"}:
        with Image.open(path) as img:
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="PNG")
            image_bytes = buf.getvalue()
            mime_type = "image/png"
    else:
        image_bytes = path.read_bytes()

    return {
        "type": "image",
        "data": base64.b64encode(image_bytes).decode("utf-8"),
        "mime_type": mime_type,
    }


def collect_reference_paths(
    refs: list[str] | None, ref_dirs: list[str] | None
) -> list[Path]:
    """Resolve and validate up to 14 reference images."""
    collected: list[Path] = []
    seen: set[Path] = set()

    for r in refs or []:
        p = Path(r).expanduser().resolve()
        if p not in seen:
            collected.append(p)
            seen.add(p)

    for d in ref_dirs or []:
        dir_path = Path(d).expanduser().resolve()
        if not dir_path.is_dir():
            raise NotADirectoryError(f"Reference directory not found: {dir_path}")
        for child in sorted(dir_path.iterdir()):
            if child.is_file() and child.suffix.lower() in SUPPORTED_EXTENSIONS:
                resolved = child.resolve()
                if resolved not in seen:
                    collected.append(resolved)
                    seen.add(resolved)

    if len(collected) > MAX_REFERENCE_IMAGES:
        print(
            f"[warn] {len(collected)} references provided; truncating to Nano Banana 2.1 limit of {MAX_REFERENCE_IMAGES}.",
            file=sys.stderr,
        )
        collected = collected[:MAX_REFERENCE_IMAGES]

    return collected


def get_last_interaction_id() -> str | None:
    """Return the most recent interaction_id from outputs/history.jsonl."""
    if not HISTORY_PATH.exists():
        return None
    lines = [
        line.strip()
        for line in HISTORY_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    for raw in reversed(lines):
        try:
            record = json.loads(raw)
            if record.get("interaction_id"):
                return str(record["interaction_id"])
        except json.JSONDecodeError:
            continue
    return None


def slugify(text: str, max_len: int = 40) -> str:
    """Create a filesystem-safe slug from a prompt."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", text.lower()).strip("_")
    return slug[:max_len].strip("_") or "image"


def build_prompt_with_preferences(
    prompt: str, preferences: str, is_followup_edit: bool
) -> str:
    """Combine user prompt with active visual preferences from GEMINI.md."""
    if not preferences:
        return prompt
    if is_followup_edit:
        return (
            f"{prompt}\n\n"
            f"[Maintain Visual Preference Guidelines]\n{preferences}"
        )
    return (
        f"{prompt}\n\n"
        f"[Visual Style & Preference Guidelines]\n{preferences}"
    )


def cmd_generate(args: argparse.Namespace) -> int:
    """Generate or conversationally edit an image using Nano Banana 2.1."""
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)

    previous_id: str | None = args.previous_id
    if args.edit_last and not previous_id:
        previous_id = get_last_interaction_id()
        if not previous_id:
            print(
                "Error: --edit-last requested, but no previous generation was found in outputs/history.jsonl.",
                file=sys.stderr,
            )
            return 1

    preferences = "" if args.no_preferences else read_visual_preferences()
    final_prompt = build_prompt_with_preferences(
        args.prompt, preferences, is_followup_edit=bool(previous_id)
    )

    ref_paths = collect_reference_paths(args.ref, args.ref_dir)

    aspect_ratio = args.aspect_ratio
    if aspect_ratio not in VALID_ASPECT_RATIOS:
        print(
            f"Error: Unsupported aspect ratio '{aspect_ratio}'. Choose from: {sorted(VALID_ASPECT_RATIOS)}",
            file=sys.stderr,
        )
        return 1

    image_size = args.size.upper()
    if image_size not in {"1K", "2K", "4K"}:
        print(
            f"Error: Unsupported size '{args.size}'. Use 1K, 2K, or 4K.",
            file=sys.stderr,
        )
        return 1

    response_format: dict[str, Any] = {
        "type": "image",
        "mime_type": args.mime_type,
        "aspect_ratio": aspect_ratio,
        "image_size": image_size,
    }

    generation_config: dict[str, Any] = {}
    if args.thinking and args.model in {
        "gemini-nano-banana-2.1",
        "gemini-3.1-flash-lite-image",
    }:
        generation_config["thinking_level"] = args.thinking

    if args.dry_run:
        summary = {
            "model": args.model,
            "prompt": args.prompt,
            "preferences_applied": bool(preferences),
            "reference_images": [str(p) for p in ref_paths],
            "previous_interaction_id": previous_id,
            "response_format": response_format,
            "generation_config": generation_config or None,
            "google_search_grounding": bool(args.search),
        }
        print(json.dumps(summary, indent=2))
        return 0

    api_key = load_environment(Path(args.env_file))
    client = genai.Client(api_key=api_key)

    input_blocks: list[dict[str, Any]] = [{"type": "text", "text": final_prompt}]
    for ref_path in ref_paths:
        input_blocks.append(encode_reference_image(ref_path))

    create_kwargs: dict[str, Any] = {
        "model": args.model,
        "input": input_blocks if len(input_blocks) > 1 else final_prompt,
        "response_format": response_format,
    }
    if generation_config:
        create_kwargs["generation_config"] = generation_config
    if previous_id:
        create_kwargs["previous_interaction_id"] = previous_id
    if args.search:
        create_kwargs["tools"] = [{"type": "google_search"}]

    print(
        f"Generating with {args.model} "
        f"(size={image_size}, aspect={aspect_ratio}, refs={len(ref_paths)}"
        f"{f', previous_id={previous_id}' if previous_id else ''})..."
    )

    interaction = client.interactions.create(**create_kwargs)

    # Extract generated image (or iterate steps if interleaved)
    generated_image = interaction.output_image
    if not generated_image or not getattr(generated_image, "data", None):
        for step in getattr(interaction, "steps", []) or []:
            if getattr(step, "type", None) == "model_output":
                for block in getattr(step, "content", []) or []:
                    if getattr(block, "type", None) == "image" and getattr(block, "data", None):
                        generated_image = block

    if not generated_image or not getattr(generated_image, "data", None):
        print("Error: Model response did not contain an image.", file=sys.stderr)
        if getattr(interaction, "output_text", None):
            print(f"Model text output: {interaction.output_text}", file=sys.stderr)
        return 1

    ext = ".jpg" if args.mime_type == "image/jpeg" else ".png"
    timestamp = datetime.now(timezone.utc).astimezone().strftime("%Y%m%d_%H%M%S")
    if args.output:
        output_path = Path(args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        filename = f"{timestamp}_{slugify(args.prompt)}{ext}"
        output_path = GENERATED_DIR / filename

    image_bytes = base64.b64decode(generated_image.data)
    output_path.write_bytes(image_bytes)

    record = {
        "timestamp": datetime.now(timezone.utc).astimezone().isoformat(),
        "interaction_id": getattr(interaction, "id", None),
        "previous_interaction_id": previous_id,
        "model": args.model,
        "prompt": args.prompt,
        "preferences_applied": bool(preferences),
        "reference_images": [str(p) for p in ref_paths],
        "aspect_ratio": aspect_ratio,
        "image_size": image_size,
        "thinking_level": generation_config.get("thinking_level"),
        "output_path": str(output_path),
        "output_text": getattr(interaction, "output_text", None),
        "feedback": None,
    }

    # Write sidecar JSON and append to history.jsonl
    sidecar_path = output_path.with_suffix(".json")
    sidecar_path.write_text(json.dumps(record, indent=2), encoding="utf-8")

    with HISTORY_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    print(f"Saved image:      {output_path}")
    print(f"Saved metadata:   {sidecar_path}")
    print(f"Interaction ID:   {record['interaction_id']}")
    if record["output_text"]:
        print(f"Model notes:      {record['output_text']}")
    return 0


def cmd_learn(args: argparse.Namespace) -> int:
    """Persist a new preference rule or critique note into GEMINI.md and history.jsonl."""
    if not args.rule and not args.feedback:
        print("Error: Provide --rule and/or --feedback.", file=sys.stderr)
        return 1

    today = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")

    if GEMINI_MD_PATH.exists():
        content = GEMINI_MD_PATH.read_text(encoding="utf-8")
        if args.rule:
            rule_line = f"- {args.rule.strip()}\n<!-- PREFERENCES_END -->"
            content = content.replace("<!-- PREFERENCES_END -->", rule_line)
        log_text = args.rule or args.feedback
        log_line = f"- `{today}`: {log_text.strip()}\n<!-- LEARNED_LOG_END -->"
        content = content.replace("<!-- LEARNED_LOG_END -->", log_line)
        GEMINI_MD_PATH.write_text(content, encoding="utf-8")
        print(f"Updated preference memory in {GEMINI_MD_PATH}")

    if args.feedback and HISTORY_PATH.exists():
        lines = HISTORY_PATH.read_text(encoding="utf-8").splitlines()
        for idx in range(len(lines) - 1, -1, -1):
            if not lines[idx].strip():
                continue
            record = json.loads(lines[idx])
            if not args.interaction_id or record.get("interaction_id") == args.interaction_id:
                record["feedback"] = args.feedback
                lines[idx] = json.dumps(record)
                HISTORY_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
                print(
                    f"Recorded feedback on interaction {record.get('interaction_id')} in {HISTORY_PATH}"
                )
                break

    return 0


def cmd_history(args: argparse.Namespace) -> int:
    """Display recent generations from outputs/history.jsonl."""
    if not HISTORY_PATH.exists():
        print("No generation history yet (outputs/history.jsonl does not exist).")
        return 0

    lines = [
        json.loads(line)
        for line in HISTORY_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    for entry in lines[-args.limit :]:
        print(
            f"[{entry.get('timestamp')}] id={entry.get('interaction_id')} "
            f"model={entry.get('model')} ({entry.get('aspect_ratio')}, {entry.get('image_size')})\n"
            f"  output: {entry.get('output_path')}\n"
            f"  prompt: {entry.get('prompt')}"
        )
        if entry.get("feedback"):
            print(f"  feedback: {entry.get('feedback')}")
    return 0


def cmd_promote(args: argparse.Namespace) -> int:
    """Promote a generated image into references/{styles,characters,objects}/."""
    source_path: Path | None = None
    if args.file:
        source_path = Path(args.file).expanduser().resolve()
    elif HISTORY_PATH.exists():
        lines = [
            json.loads(line)
            for line in HISTORY_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if lines:
            source_path = Path(lines[-1]["output_path"])

    if not source_path or not source_path.exists():
        print("Error: Could not find source image to promote.", file=sys.stderr)
        return 1

    target_dir = REFERENCES_DIR / args.category
    target_dir.mkdir(parents=True, exist_ok=True)
    target_name = (
        f"{slugify(args.name, max_len=60)}{source_path.suffix}"
        if args.name
        else source_path.name
    )
    dest_path = target_dir / target_name
    shutil.copy2(source_path, dest_path)
    print(f"Promoted {source_path.name} -> {dest_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Nano Banana 2.1 Studio CLI — Image generation, references, and preference memory."
    )
    parser.add_argument(
        "--env-file",
        default=str(DEFAULT_ENV_PATH),
        help="Path to .env file containing GEMINI_API_KEY (default: /Users/vincent/.env)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # generate
    gen = subparsers.add_parser(
        "generate", help="Generate or conversationally edit an image"
    )
    gen.add_argument("-p", "--prompt", required=True, help="Text prompt or edit instruction")
    gen.add_argument(
        "-r",
        "--ref",
        action="append",
        help="Reference image path (repeatable, up to 14 images total)",
    )
    gen.add_argument(
        "--ref-dir",
        action="append",
        help="Directory of reference images to include (up to 14 images total)",
    )
    gen.add_argument(
        "-m",
        "--model",
        default="gemini-nano-banana-2.1",
        choices=[
            "gemini-nano-banana-2.1",
            "gemini-3-pro-image",
            "gemini-3.1-flash-lite-image",
        ],
        help="Gemini image model (default: gemini-nano-banana-2.1)",
    )
    gen.add_argument(
        "-a",
        "--aspect-ratio",
        default="4:5",
        help="Output aspect ratio (default: 4:5). E.g. 1:1, 4:5, 16:9, 9:16, 3:2",
    )
    gen.add_argument(
        "-s",
        "--size",
        default="2K",
        help="Output resolution: 1K, 2K, or 4K (default: 2K)",
    )
    gen.add_argument(
        "--mime-type",
        default="image/png",
        choices=["image/png", "image/jpeg"],
        help="Output image MIME type (default: image/png)",
    )
    gen.add_argument(
        "--thinking",
        default="medium",
        choices=["minimal", "medium", "high"],
        help="Thinking level for composition reasoning (default: medium)",
    )
    gen.add_argument(
        "--search",
        action="store_true",
        help="Enable Google Search grounding for real-time visual facts",
    )
    gen.add_argument(
        "--edit-last",
        action="store_true",
        help="Continue editing the most recent generation via previous_interaction_id",
    )
    gen.add_argument(
        "--previous-id",
        help="Continue editing a specific interaction_id via previous_interaction_id",
    )
    gen.add_argument(
        "--no-preferences",
        action="store_true",
        help="Do not inject the visual preference profile from GEMINI.md",
    )
    gen.add_argument("-o", "--output", help="Custom output file path")
    gen.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the resolved API payload summary without calling the API",
    )
    gen.set_defaults(func=cmd_generate)

    # learn
    learn = subparsers.add_parser(
        "learn", help="Save a permanent visual preference rule or critique to GEMINI.md"
    )
    learn.add_argument(
        "--rule",
        help="Permanent aesthetic rule to append to the Active Visual Taste section of GEMINI.md",
    )
    learn.add_argument(
        "--feedback",
        help="Critique note for the latest generation (saved to history.jsonl and GEMINI.md)",
    )
    learn.add_argument(
        "--interaction-id",
        help="Specific interaction_id to attach feedback to (defaults to latest)",
    )
    learn.set_defaults(func=cmd_learn)

    # history
    hist = subparsers.add_parser("history", help="Show recent image generations")
    hist.add_argument("-n", "--limit", type=int, default=10, help="Number of entries to show")
    hist.set_defaults(func=cmd_history)

    # promote
    prom = subparsers.add_parser(
        "promote", help="Promote a generated image into the references/ vault"
    )
    prom.add_argument(
        "--category",
        default="styles",
        choices=["characters", "objects", "styles"],
        help="Reference folder category (default: styles)",
    )
    prom.add_argument("--file", help="Path to image (defaults to latest generated image)")
    prom.add_argument("--name", help="New descriptive name for the reference")
    prom.set_defaults(func=cmd_promote)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

