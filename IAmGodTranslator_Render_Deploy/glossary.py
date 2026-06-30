from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


HAN_RE = re.compile(r"[\u3400-\u9fff]")

CHEAPEST_MODEL = "gpt-4o-mini"
RECOMMENDED_MODEL = os.getenv("RECOMMENDED_MODEL", "gpt-4o")
DEFAULT_RETRY_COUNT = 1

MODEL_PRICING_USD_PER_MILLION = {
    "gpt-4o-mini": {
        "label": "GPT-4o mini",
        "input": 0.15,
        "output": 0.60,
    },
    "gpt-4o": {
        "label": "GPT-4o",
        "input": 2.50,
        "output": 10.00,
    },
}


@dataclass(frozen=True)
class TokenEstimate:
    input_tokens: int
    output_tokens: int


def estimate_text_tokens(text: str) -> int:
    han_chars = len(HAN_RE.findall(text))
    non_han = HAN_RE.sub("", text)
    non_han_tokens = math.ceil(len(non_han) / 4)
    return max(1, han_chars + non_han_tokens)


def estimate_chapter_tokens(prompt: str, chinese_text: str) -> TokenEstimate:
    input_tokens = estimate_text_tokens(prompt)
    source_tokens = estimate_text_tokens(chinese_text)
    output_tokens = max(600, math.ceil(source_tokens * 1.25))
    return TokenEstimate(input_tokens=input_tokens, output_tokens=output_tokens)


def chapter_cost(tokens: TokenEstimate, model: str) -> float:
    pricing = MODEL_PRICING_USD_PER_MILLION[model]
    input_cost = tokens.input_tokens / 1_000_000 * pricing["input"]
    output_cost = tokens.output_tokens / 1_000_000 * pricing["output"]
    return round(input_cost + output_cost, 6)


def build_cost_estimate(chapters: list[dict[str, Any]]) -> dict[str, Any]:
    cheapest_model = CHEAPEST_MODEL
    recommended_model = RECOMMENDED_MODEL

    if recommended_model not in MODEL_PRICING_USD_PER_MILLION:
        recommended_model = "gpt-4o"

    chapter_estimates = []

    for chapter in chapters:
        tokens = TokenEstimate(
            input_tokens=chapter["input_tokens"],
            output_tokens=chapter["output_tokens"],
        )
        cheapest_cost = chapter_cost(tokens, cheapest_model)
        recommended_cost = chapter_cost(tokens, recommended_model)

        chapter_estimates.append({
            "chapter": chapter["chapter"],
            "title": chapter["title"],
            "input_tokens": tokens.input_tokens,
            "output_tokens": tokens.output_tokens,
            "cheapest_model_cost": cheapest_cost,
            "recommended_model_cost": recommended_cost,
        })

    total_cheapest = round(sum(item["cheapest_model_cost"] for item in chapter_estimates), 6)
    total_recommended = round(sum(item["recommended_model_cost"] for item in chapter_estimates), 6)
    retry_multiplier = 1 + DEFAULT_RETRY_COUNT

    return {
        "currency": "USD",
        "pricing_unit": "per 1M tokens",
        "pricing": MODEL_PRICING_USD_PER_MILLION,
        "cheapest_model": cheapest_model,
        "recommended_model": recommended_model,
        "retry_count": DEFAULT_RETRY_COUNT,
        "retry_multiplier": retry_multiplier,
        "chapters": chapter_estimates,
        "totals": {
            "chapter_count": len(chapter_estimates),
            "input_tokens": sum(item["input_tokens"] for item in chapter_estimates),
            "output_tokens": sum(item["output_tokens"] for item in chapter_estimates),
            "cheapest_model_cost": total_cheapest,
            "recommended_model_cost": total_recommended,
            "cheapest_model_cost_with_retries": round(total_cheapest * retry_multiplier, 6),
            "recommended_model_cost_with_retries": round(total_recommended * retry_multiplier, 6),
        },
    }


def default_settings() -> dict[str, Any]:
    return {
        "max_total_budget": None,
        "max_cost_per_chapter": None,
        "stop_when_budget_reached": True,
        "test_chapter_only": True,
        "show_estimate_before_starting": True,
        "retry_failed_chapters": 1,
        "model": CHEAPEST_MODEL,
    }


def parse_budget(value: str | None) -> float | None:
    if value in {None, ""}:
        return None

    parsed = float(value)

    if parsed < 0:
        raise ValueError("Budget values cannot be negative.")

    return parsed


def write_estimate_report(job_dir: Path, estimate: dict[str, Any]) -> Path:
    output = job_dir / "Output"
    output.mkdir(parents=True, exist_ok=True)
    report = output / "cost_estimate_report.md"
    totals = estimate["totals"]
    lines = [
        "# Cost Estimate",
        "",
        f"Chapters: {totals['chapter_count']}",
        f"Input tokens: {totals['input_tokens']:,}",
        f"Output tokens: {totals['output_tokens']:,}",
        f"Cheapest model: {estimate['cheapest_model']}",
        f"Recommended model: {estimate['recommended_model']}",
        f"Estimated total cheapest: ${totals['cheapest_model_cost']:.6f}",
        f"Estimated total recommended: ${totals['recommended_model_cost']:.6f}",
        f"Estimated cheapest with retries: ${totals['cheapest_model_cost_with_retries']:.6f}",
        f"Estimated recommended with retries: ${totals['recommended_model_cost_with_retries']:.6f}",
        "",
        "| Chapter | Input Tokens | Output Tokens | Cheapest Cost | Recommended Cost |",
        "|---:|---:|---:|---:|---:|",
    ]

    for chapter in estimate["chapters"]:
        lines.append(
            f"| {chapter['chapter']} | {chapter['input_tokens']:,} | "
            f"{chapter['output_tokens']:,} | ${chapter['cheapest_model_cost']:.6f} | "
            f"${chapter['recommended_model_cost']:.6f} |"
        )

    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report
