"""Thin wrapper around the Notion SDK for inbox operations."""
import os
from notion_client import Client

_client: Client | None = None


def get_client() -> Client:
    global _client
    if _client is None:
        token = os.environ.get("NOTION_TOKEN")
        if not token:
            raise RuntimeError("NOTION_TOKEN is not set")
        _client = Client(auth=token)
    return _client


def list_unprocessed_inbox() -> list[dict]:
    """Return all inbox items where Status = Unprocessed."""
    db_id = os.environ["NOTION_INBOX_DB_ID"]
    response = get_client().databases.query(
        database_id=db_id,
        filter={"property": "Status", "status": {"equals": "Unprocessed"}},
    )
    return response["results"]


def mark_inbox_done(page_id: str) -> None:
    get_client().pages.update(
        page_id=page_id,
        properties={"Status": {"status": {"name": "Done"}}},
    )


def create_recipe(name: str, url: str, tags: list[str], notes: str) -> dict:
    db_id = os.environ["NOTION_RECIPES_DB_ID"]
    return get_client().pages.create(
        parent={"database_id": db_id},
        properties={
            "Name": {"title": [{"text": {"content": name}}]},
            "URL": {"url": url},
            "Tags": {"multi_select": [{"name": t} for t in tags]},
        },
        children=[
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"text": {"content": notes}}]},
            }
        ] if notes else [],
    )


def create_reading_item(name: str, url: str, item_type: str, tags: list[str]) -> dict:
    db_id = os.environ["NOTION_READING_LIST_DB_ID"]
    return get_client().pages.create(
        parent={"database_id": db_id},
        properties={
            "Title": {"title": [{"text": {"content": name}}]},
            "URL": {"url": url},
            "Type": {"select": {"name": item_type}},
            "Tags": {"multi_select": [{"name": t} for t in tags]},
        },
    )
