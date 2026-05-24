"""Use Claude to classify an inbox item and extract structured metadata.

Claude returns a JSON object whose shape depends on the category:

  recipe   → {category, name, url, tags}
  task     → {category, name, description, priority}
  book     → {category, name, author}
  concert  → {category, name, venue, location, notes}
  article  → {category, name, url, description}
  video    → {category, name, url, description}
  podcast  → {category, name, url, description}
  website  → {category, name, url, description}
  note     → {category, name, note_type}

All fields except `category` and `name` are optional.
"""

import json
import os
import anthropic

SYSTEM_PROMPT = """You are a personal knowledge-management assistant.
Given the title and optional URL of an item captured to someone's inbox,
classify it and extract structured metadata.

Return ONLY a JSON object — no prose, no markdown fences.

Required fields in every response:
  category  – one of: recipe, task, book, concert, article, video,
                       podcast, website, note
  name      – cleaned-up title (fix typos, capitalise properly)

Additional fields by category (omit any you cannot confidently infer):
  recipe  → url (string), tags (array, pick from: Dessert Dinner Easy Lunch)
  task    → description (string), priority (one of: High Med. Low)
  book    → author (string)
  concert → venue (string), location (string), notes (string)
  article | video | podcast | website
          → url (string), description (one sentence)
  note    → note_type (one of: Idea Note Meeting Learning Research)

Classification rules:
- A URL pointing to a recipe site (e.g. AllRecipes, NYT Cooking, food blogs)
  → recipe
- "Read X", "book by Y", or an obvious book title → book
- "See [artist]", "concert", "[artist] at [venue]", ticket-booking URLs → concert
- YouTube / Vimeo / TikTok URLs → video
- Podcast URLs or "[podcast name] episode" → podcast
- Social media URLs (twitter/x, instagram, reddit, linkedin) → website
- Explicit action language ("buy", "call", "email", "fix", "submit") → task
- An open-ended thought, reflection, or meeting → note
- Anything else with a URL → website
- Anything else without a URL → note (note_type: Idea)"""

_client: anthropic.Anthropic | None = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    return _client


def classify_item(title: str, url: str | None) -> dict:
    """Return a classification dict for a single inbox item."""
    user_content = f"Title: {title}"
    if url:
        user_content += f"\nURL: {url}"

    message = get_client().messages.create(
        model="claude-opus-4-5",
        max_tokens=512,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    raw = message.content[0].text.strip()
    # Strip accidental markdown fences if the model includes them
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())
