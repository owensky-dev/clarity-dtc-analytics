from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_cro_prompt(analysis_context: dict[str, Any]) -> str:
    """Build a bounded Chinese CRO prompt from structured, non-PII evidence only."""
    return "\n".join(
        [
            "你是一名资深独立站用户行为分析师和 CRO 专家。",
            "仅根据以下结构化数据写中文周报；不允许虚构用户行为、录像内容或因果关系。",
            "每条结论必须区分：已观察到的事实、基于事实的推测、仍需验证的问题，并给出验证动作与证据可信度。",
            "优先关注高意向漏斗损失和可复现的 Clarity 筛选条件。",
            "输入数据：",
            json.dumps(analysis_context, ensure_ascii=False, indent=2),
        ]
    )


def generate_optional_narrative(analysis_context: dict[str, Any], settings: dict[str, str]) -> tuple[str | None, str]:
    """Return an optional OpenAI narrative; never block the deterministic report on failure."""
    if settings.get("LLM_MODE", "off").lower() != "openai":
        return None, "disabled"
    if not settings.get("OPENAI_API_KEY"):
        return None, "missing_api_key"
    try:
        from openai import OpenAI

        client = OpenAI(api_key=settings["OPENAI_API_KEY"])
        response = client.responses.create(
            model=settings.get("OPENAI_MODEL", "gpt-5-mini"),
            input=build_cro_prompt(analysis_context),
        )
        return response.output_text, "generated"
    except Exception as error:
        return None, f"failed: {type(error).__name__}"


def write_optional_narrative(
    analysis_context: dict[str, Any], settings: dict[str, str], output_path: Path
) -> str:
    """Write an opt-in narrative only when generation succeeds; leave deterministic files untouched otherwise."""
    narrative, status = generate_optional_narrative(analysis_context, settings)
    if narrative:
        output_path.write_text(narrative.rstrip() + "\n", encoding="utf-8")
    return status
