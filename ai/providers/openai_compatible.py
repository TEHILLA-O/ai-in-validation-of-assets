"""Optional language-model provider. It receives a prepared brief, never the calculation role."""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx


@dataclass
class OpenAICompatible:
    base_url: str
    api_key: str
    model: str

    def complete(self, system: str, user: str) -> str:
        response = httpx.post(
            self.base_url.rstrip("/") + "/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        return payload["choices"][0]["message"]["content"]


def configured_provider() -> OpenAICompatible | None:
    key = os.environ.get("VALUATIONLAB_LLM_API_KEY", "").strip()
    if not key:
        return None
    return OpenAICompatible(
        base_url=os.environ.get("VALUATIONLAB_LLM_BASE_URL", "https://api.openai.com/v1"),
        api_key=key,
        model=os.environ.get("VALUATIONLAB_LLM_MODEL", "gpt-4o-mini"),
    )


SYSTEM_PROMPT = (
    "You explain a valuation that the deterministic engine has already calculated. "
    "Quote only figures present in the brief. Do not invent market data, filings or formulas. "
    "Do not propose a number as if it had been calculated. "
    "State clearly that you cannot change model assumptions. "
    "Label your own comments as interpretation."
)
