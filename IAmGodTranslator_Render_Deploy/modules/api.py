from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()

logger = logging.getLogger(__name__)
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def get_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set. Add it to .env or the hosting environment.")

    return OpenAI(api_key=api_key)


def translate(prompt: str, model: str | None = None) -> str:
    selected_model = model or os.getenv("OPENAI_MODEL", DEFAULT_MODEL)
    logger.info("Sending translation request to OpenAI model %s", selected_model)

    response = get_client().responses.create(
        model=selected_model,
        input=prompt,
    )

    return response.output_text.strip()
