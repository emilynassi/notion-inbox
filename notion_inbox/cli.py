"""notion-triage: read the Notes* inbox, classify each item, file it, archive."""

import sys
from dotenv import load_dotenv

from notion_inbox import notion_client as nc
from notion_inbox.triage import classify_item


# ---------------------------------------------------------------------------
# Router — maps classification → create call
# ---------------------------------------------------------------------------

def _file_item(classification: dict, url: str | None) -> str:
    """Create the item in the right database. Return a human-readable summary."""
    category = classification.get("category", "note")
    name = classification.get("name", "(untitled)")

    # Prefer URL from classification (Claude may clean it up); fall back to
    # the raw URL extracted from the page body.
    effective_url = classification.get("url") or url

    if category == "recipe":
        nc.create_recipe(
            name=name,
            url=effective_url,
            tags=classification.get("tags", []),
        )
        return f"Recipes → {name}"

    elif category == "task":
        nc.create_task(
            name=name,
            description=classification.get("description", ""),
            priority=classification.get("priority", "Med."),
        )
        return f"Tasks* → {name}"

    elif category == "book":
        nc.create_book(
            name=name,
            author=classification.get("author", ""),
        )
        return f"Books* → {name}"

    elif category == "concert":
        nc.create_concert(
            artist=name,
            venue=classification.get("venue", ""),
            location=classification.get("location", ""),
            notes=classification.get("notes", ""),
        )
        return f"Concert Tracker → {name}"

    elif category in ("article", "video", "podcast", "website"):
        type_map = {
            "article": "Article",
            "video": "Video",
            "podcast": "Podcast",
            "website": "Website",
        }
        nc.create_resource(
            name=name,
            url=effective_url,
            resource_type=type_map[category],
            description=classification.get("description", ""),
        )
        return f"Resources* ({type_map[category]}) → {name}"

    elif category == "note":
        # Keep in Notes* but promote out of Inbox
        return None  # handled separately by caller — needs page_id

    else:
        # Unknown category — default to Resources* / Website
        nc.create_resource(
            name=name,
            url=effective_url,
            resource_type="Website",
        )
        return f"Resources* (Website) → {name}"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    load_dotenv()

    items = nc.get_inbox_items()
    if not items:
        print("Inbox is empty — nothing to do.")
        return

    print(f"Found {len(items)} item(s) in inbox.\n")

    errors: list[tuple[str, Exception]] = []

    for item in items:
        page_id = item["id"]
        title = nc.extract_title(item)
        url = item.get("_url")

        label = f"  {title!r}"
        if url:
            label += f"  [{url}]"
        print(f"{label}")
        print(f"    Classifying…", end=" ", flush=True)

        try:
            classification = classify_item(title, url)
            category = classification.get("category", "note")
            print(f"→ {category}", end="  ", flush=True)

            if category == "note":
                # Stay in Notes*, just promote to Draft
                note_type = classification.get("note_type", "Idea")
                nc.update_note_to_draft(page_id, note_type)
                print(f"✓  Notes* (Draft / {note_type})")
            else:
                destination = _file_item(classification, url)
                nc.archive_note(page_id)
                print(f"✓  {destination}")

        except Exception as exc:
            print(f"✗  error: {exc}")
            errors.append((title, exc))

    print()
    if errors:
        print(f"{len(errors)} item(s) failed:")
        for title, exc in errors:
            print(f"  • {title!r}: {exc}")
        sys.exit(1)
    else:
        print("All items filed successfully.")


if __name__ == "__main__":
    main()
