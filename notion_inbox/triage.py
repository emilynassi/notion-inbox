"""Use Claude to classify an inbox item and extract metadata."""
import json
import os
import anthropic

SYSTEM_PROMPT = """You are an assistant that classifies personal capture items and extracts structured metadata.

Given a title and optional URL from someone's personal inbox, return a JSON object with:
- category: one of "recipe", "article", "book", "task", "video", "other"
- name: cleaned-up title (fix typos, capitalize properly)
- tags: list of 1-3 relevant tags (lowercase, single words or short phrases)
- notes: one sentence describing the item, or empty string if nothing useful to say

Respond ONLY with valid JSON. No prose, no markdown fences."""

_client: anthropic.Anthropic | None = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    return _client


def classify_item(title: str, url: str | None) -> dict:
    """Return classification dict for a single inbox item."""
    user_content = f"Title: {title}"
    if url:
        user_content += f"\nURL: {url}"

    message = get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    raw = message.content[0].text.strip()
    return json.loads(raw)
