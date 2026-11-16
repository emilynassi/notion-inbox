"""Thin wrapper around the Notion SDK for inbox triage operations.

Databases and their IDs (set via env vars):
  NOTION_NOTES_DB_ID     – Notes* (staging inbox)
  NOTION_TASKS_DB_ID     – Tasks*
  NOTION_RESOURCES_DB_ID – Resources*
  NOTION_BOOKS_DB_ID     – Books*
  NOTION_RECIPES_DB_ID   – Recipes
  NOTION_CONCERTS_DB_ID  – Concert Tracker
  NOTION_GAMES_DB_ID     – Games Tracker
"""

import os
import re
from notion_client import Client

_client: Client | None = None
_URL_RE = re.compile(r"https?://\S+")


# ---------------------------------------------------------------------------
# Client bootstrap
# ---------------------------------------------------------------------------

def get_client() -> Client:
    global _client
    if _client is None:
        token = os.environ.get("NOTION_TOKEN")
        if not token:
            raise RuntimeError("NOTION_TOKEN is not set")
        _client = Client(auth=token)
    return _client


# ---------------------------------------------------------------------------
# Reading the inbox
# ---------------------------------------------------------------------------

def get_inbox_items() -> list[dict]:
    """Return all Notes* pages with Status = Inbox.

    Each page dict gets an extra ``_url`` key with the first URL found in
    the page body (or None), since Notes* stores URLs in the body, not a
    property.
    """
    db_id = os.environ["NOTION_NOTES_DB_ID"]
    response = get_client().databases.query(
        database_id=db_id,
        filter={"property": "Status", "status": {"equals": "Inbox"}},
    )
    pages = response["results"]
    for page in pages:
        page["_url"] = _extract_url_from_body(page["id"])
    return pages


def _extract_url_from_body(page_id: str) -> str | None:
    """Fetch block children and return the first URL found in any rich-text."""
    try:
        resp = get_client().blocks.children.list(block_id=page_id)
        for block in resp.get("results", []):
            block_type = block.get("type", "")
            rich_text = block.get(block_type, {}).get("rich_text", [])
            for rt in rich_text:
                # href is set when Notion recognised it as a link
                if rt.get("href"):
                    return rt["href"]
                # fall back: scan plain text for a URL pattern
                m = _URL_RE.search(rt.get("plain_text", ""))
                if m:
                    return m.group(0)
    except Exception:
        pass
    return None


def extract_title(page: dict) -> str:
    """Pull plain-text title from a Notes* page dict."""
    props = page.get("properties", {})
    title_prop = props.get("Title") or props.get("Name") or {}
    rich_text = title_prop.get("title", [])
    return "".join(t["plain_text"] for t in rich_text).strip()


# ---------------------------------------------------------------------------
# Mutating the staging note
# ---------------------------------------------------------------------------

def archive_note(page_id: str) -> None:
    """Archive the staging note so it disappears from all active views."""
    get_client().pages.update(page_id=page_id, archived=True)


def update_note_to_draft(page_id: str, note_type: str = "Idea") -> None:
    """Keep the item in Notes* but promote it from Inbox → Draft and set Type."""
    valid_types = {"Idea", "Note", "Meeting", "Learning", "Research"}
    props: dict = {"Status": {"status": {"name": "Draft"}}}
    if note_type in valid_types:
        props["Type"] = {"select": {"name": note_type}}
    get_client().pages.update(page_id=page_id, properties=props)


# ---------------------------------------------------------------------------
# Creating items in target databases
# ---------------------------------------------------------------------------

def create_task(name: str, description: str = "", priority: str = "Med.") -> dict:
    """Create a task in Tasks* with Status = To do."""
    valid_priorities = {"High", "Med.", "Low"}
    if priority not in valid_priorities:
        priority = "Med."
    db_id = os.environ["NOTION_TASKS_DB_ID"]
    props: dict = {
        "Task name": {"title": [{"text": {"content": name}}]},
        "Status": {"status": {"name": "To do"}},
        "Priority": {"select": {"name": priority}},
    }
    if description:
        props["Description"] = {"rich_text": [{"text": {"content": description}}]}
    return get_client().pages.create(
        parent={"database_id": db_id},
        properties=props,
    )


def create_resource(
    name: str,
    url: str | None = None,
    resource_type: str = "Website",
    description: str = "",
) -> dict:
    """Create a resource in Resources* with Status = Inbox."""
    valid_types = {"Book", "Video", "Article", "Podcast", "Website", "Document", "Social media"}
    if resource_type not in valid_types:
        resource_type = "Website"
    db_id = os.environ["NOTION_RESOURCES_DB_ID"]
    props: dict = {
        "Title": {"title": [{"text": {"content": name}}]},
        "Status": {"status": {"name": "Inbox"}},
        "Type": {"select": {"name": resource_type}},
    }
    if url:
        props["Link"] = {"url": url}
    if description:
        props["Description"] = {"rich_text": [{"text": {"content": description}}]}
    return get_client().pages.create(
        parent={"database_id": db_id},
        properties=props,
    )


def create_book(name: str, author: str = "") -> dict:
    """Create a book in Books* with Status = To read."""
    db_id = os.environ["NOTION_BOOKS_DB_ID"]
    props: dict = {
        "Name": {"title": [{"text": {"content": name}}]},
        "Status": {"status": {"name": "To read"}},
    }
    if author:
        props["Author"] = {"rich_text": [{"text": {"content": author}}]}
    return get_client().pages.create(
        parent={"database_id": db_id},
        properties=props,
    )


def create_recipe(
    name: str,
    url: str | None = None,
    tags: list[str] | None = None,
) -> dict:
    """Create a recipe in Recipes.

    Valid tags: Dessert, Dinner, Easy, Lunch
    """
    valid_tags = {"Dessert", "Dinner", "Easy", "Lunch"}
    clean_tags = [t for t in (tags or []) if t in valid_tags]
    db_id = os.environ["NOTION_RECIPES_DB_ID"]
    props: dict = {
        "Name": {"title": [{"text": {"content": name}}]},
    }
    if url:
        props["Link"] = {"url": url}
    if clean_tags:
        props["Tags"] = {"multi_select": [{"name": t} for t in clean_tags]}
    return get_client().pages.create(
        parent={"database_id": db_id},
        properties=props,
    )


def create_concert(
    artist: str,
    venue: str = "",
    location: str = "",
    notes: str = "",
    status: str = "Upcoming",
    date: str = "",
) -> dict:
    """Create an entry in Concert Tracker.

    Valid statuses: Upcoming, Attended, Missed
    Date: ISO 8601 string, e.g. "2025-11-12"
    """
    valid_statuses = {"Upcoming", "Attended", "Missed"}
    if status not in valid_statuses:
        status = "Upcoming"
    db_id = os.environ["NOTION_CONCERTS_DB_ID"]
    props: dict = {
        "Artist/Band": {"title": [{"text": {"content": artist}}]},
        "Status": {"select": {"name": status}},
    }
    if venue:
        props["Venue"] = {"rich_text": [{"text": {"content": venue}}]}
    if location:
        props["Location"] = {"rich_text": [{"text": {"content": location}}]}
    if notes:
        props["Notes"] = {"rich_text": [{"text": {"content": notes}}]}
    if date:
        props["Date"] = {"date": {"start": date}}
    return get_client().pages.create(
        parent={"database_id": db_id},
        properties=props,
    )


def get_all_games() -> list[dict]:
    """Return every page in Games Tracker (handles pagination)."""
    db_id = os.environ["NOTION_GAMES_DB_ID"]
    pages: list[dict] = []
    cursor: str | None = None
    while True:
        resp = get_client().databases.query(
            database_id=db_id,
            **({"start_cursor": cursor} if cursor else {}),
        )
        pages.extend(resp["results"])
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
    return pages


def update_game_enrichment(
    page_id: str,
    notes: str | None = None,
    status: str | None = None,
) -> None:
    """Update Notes and/or Status on an existing Games Tracker page."""
    valid_statuses = {"Upcoming", "Attended", "Missed"}
    props: dict = {}
    if notes is not None:
        props["Notes"] = {"rich_text": [{"text": {"content": notes}}]}
    if status in valid_statuses:
        props["Status"] = {"select": {"name": status}}
    if props:
        get_client().pages.update(page_id=page_id, properties=props)


def create_game(
    team_event: str,
    opponent: str = "",
    venue: str = "",
    location: str = "",
    sport: str = "",
    status: str = "Upcoming",
    date: str = "",
    notes: str = "",
) -> dict:
    """Create an entry in Games Tracker.

    Valid sports: Hockey, Baseball, Basketball, Football, Soccer
    Valid statuses: Upcoming, Attended, Missed
    Date: ISO 8601 string, e.g. "2025-11-12"
    """
    valid_sports = {"Hockey", "Baseball", "Basketball", "Football", "Soccer"}
    valid_statuses = {"Upcoming", "Attended", "Missed"}
    if status not in valid_statuses:
        status = "Upcoming"
    db_id = os.environ["NOTION_GAMES_DB_ID"]
    props: dict = {
        "Team/Event": {"title": [{"text": {"content": team_event}}]},
        "Status": {"select": {"name": status}},
    }
    if sport in valid_sports:
        props["Sport"] = {"select": {"name": sport}}
    if opponent:
        props["Opponent"] = {"rich_text": [{"text": {"content": opponent}}]}
    if venue:
        props["Venue"] = {"rich_text": [{"text": {"content": venue}}]}
    if location:
        props["Location"] = {"rich_text": [{"text": {"content": location}}]}
    if date:
        props["Date"] = {"date": {"start": date}}
    if notes:
        props["Notes"] = {"rich_text": [{"text": {"content": notes}}]}
    return get_client().pages.create(
        parent={"database_id": db_id},
        properties=props,
    )
