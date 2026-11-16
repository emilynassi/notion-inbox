"""Use Claude to classify an inbox item and extract structured metadata.

Claude returns a JSON object whose shape depends on the category:

  recipe   → {category, name, url, tags}
  task     → {category, name, description, priority}
  book     → {category, name, author}
  concert  → {category, name, venue, location, notes, date, status}
  game     → {category, name, opponent, venue, location, sport, notes, date, status}
  article  → {category, name, url, description}
  video    → {category, name, url, description}
  podcast  → {category, name, url, description}
  website  → {category, name, url, description}
  social   → {category, name, url, description}
  note     → {category, name, note_type}

All fields except `category` and `name` are optional.
"""

import datetime as _dt
import json
import os
import anthropic

SYSTEM_PROMPT = """You are a personal knowledge-management assistant.
Given the title and optional URL of an item captured to someone's inbox,
classify it and extract structured metadata.

The user's message includes "Today's date" — use it to resolve any relative
dates ("last night", "tonight", "this Saturday", "next Friday") into an
absolute ISO 8601 date (YYYY-MM-DD).

Return ONLY a JSON object — no prose, no markdown fences.

Required fields in every response:
  category  – one of: recipe, task, book, concert, game, article, video,
                       podcast, website, social, note
  name      – cleaned-up title (fix typos, capitalise properly)

Additional fields by category (omit any you cannot confidently infer):
  recipe  → url (string), tags (array, pick from: Dessert Dinner Easy Lunch)
  task    → description (string), priority (one of: High Med. Low)
  book    → author (string)
  concert → venue (string), location (string), notes (string),
            date (ISO 8601 YYYY-MM-DD),
            status (one of: Upcoming Attended Missed)
  game    → opponent (string), venue (string), location (string),
            sport (one of: Hockey Baseball Basketball Football Soccer),
            notes (string), date (ISO 8601 YYYY-MM-DD),
            status (one of: Upcoming Attended Missed)
  article | video | podcast | website | social
          → url (string), description (one sentence)
  note    → note_type (one of: Idea Note Meeting Learning Research)

Inferring date & status for concerts and games:
- If the item names or implies a specific date, set `date` (resolve relative
  dates against Today's date). Omit `date` if none can be inferred.
- Set `status` by comparing the event date to Today's date:
    * event is in the future (or worded as a plan: "going to", "tickets for",
      "see", "this Saturday") → "Upcoming"
    * event already happened and they were there ("went to", "saw", "last
      night", past date) → "Attended"
    * event already happened and they did NOT go ("missed", "couldn't make
      it") → "Missed"
- If you cannot tell, omit `status` (the system defaults to Upcoming).

Classification rules:
- A URL pointing to a recipe site (e.g. AllRecipes, NYT Cooking, food blogs)
  → recipe
- An obvious published book title, "book by Y", or "reading X" where X is a
  book → book. Do NOT classify as book when "read" refers to a work task,
  document, email, report, article, or PR (e.g. "Read Q3 report", "read the
  onboarding doc") — those are task or article/website.
- "See [artist]", "concert", "[artist] at [venue]", ticket-booking URLs → concert
- "[Team] vs [Team]", "[Team] game", "[sport] game", "[Team] at [stadium]",
  sports team names (Rangers, Mets, Knicks, Giants, Yankees, Nets, Jets, etc.) → game
- YouTube / Vimeo / TikTok URLs → video
- Podcast URLs or "[podcast name] episode" → podcast
- Social media URLs (twitter/x, instagram, reddit, linkedin) → social
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
    today = _dt.date.today().isoformat()
    user_content = f"Today's date: {today}\nTitle: {title}"
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
