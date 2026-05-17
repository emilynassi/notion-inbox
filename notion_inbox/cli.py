"""notion-triage: read the inbox, classify each item, file it, mark done."""
import sys
from dotenv import load_dotenv

from notion_inbox import notion_client as nc
from notion_inbox.triage import classify_item


def _extract_title(page: dict) -> str:
    props = page["properties"]
    title_prop = props.get("Name") or props.get("Title") or {}
    rich_text = title_prop.get("title", [])
    return "".join(t["plain_text"] for t in rich_text)


def _extract_url(page: dict) -> str | None:
    props = page["properties"]
    url_prop = props.get("URL", {})
    return url_prop.get("url")


def _file_item(classification: dict, url: str | None) -> str:
    category = classification.get("category", "other")
    name = classification["name"]
    tags = classification.get("tags", [])
    notes = classification.get("notes", "")

    if category == "recipe":
        nc.create_recipe(name, url or "", tags, notes)
        return f"Recipes → {name}"
    elif category in ("article", "video", "book"):
        nc.create_reading_item(name, url or "", category.capitalize(), tags)
        return f"Reading List ({category}) → {name}"
    else:
        return f"[skipped — category '{category}' has no router yet]"


def main() -> None:
    load_dotenv()

    items = nc.list_unprocessed_inbox()
    if not items:
        print("Inbox is empty. Nothing to do.")
        return

    print(f"Found {len(items)} unprocessed item(s).\n")

    errors = []
    for item in items:
        page_id = item["id"]
        title = _extract_title(item)
        url = _extract_url(item)

        print(f"  Processing: {title!r} …", end=" ", flush=True)
        try:
            classification = classify_item(title, url)
            destination = _file_item(classification, url)
            nc.mark_inbox_done(page_id)
            print(f"✓ {destination}")
        except Exception as exc:
            print(f"✗ error: {exc}")
            errors.append((title, exc))

    print()
    if errors:
        print(f"{len(errors)} item(s) failed — check above for details.")
        sys.exit(1)
    else:
        print("All items filed successfully.")


if __name__ == "__main__":
    main()
