"""notion-games-enrich: enrich Games Tracker entries with NHL public API data.

For each past hockey game that can be matched to an NHL game ID:
  - Writes score, goal scorers, and three stars into the Notes field
    (skips if Notes already has content, unless --force)
  - Promotes Status from Upcoming → Missed for completed games
    (never touches Attended entries)

Usage:
    notion-games-enrich
    notion-games-enrich --dry-run
    notion-games-enrich --status-only
    notion-games-enrich --force          # overwrite existing Notes
"""

import argparse
import re
import sys
from datetime import date as Date
from dotenv import load_dotenv

from notion_inbox import notion_client as nc
from notion_inbox import nhl_client as nhl


def _prop_text(page: dict, prop_name: str, prop_type: str) -> str:
    items = page["properties"].get(prop_name, {}).get(prop_type, [])
    return "".join(t["plain_text"] for t in items).strip()


def _extract_date(page: dict) -> str | None:
    d = page["properties"].get("Date", {}).get("date")
    return d.get("start") if d else None


def _extract_status(page: dict) -> str | None:
    s = page["properties"].get("Status", {}).get("select")
    return s.get("name") if s else None


def _extract_teams(page: dict) -> tuple[str, str | None]:
    """Return (primary_team, opponent) parsed from title + Opponent field."""
    title = _prop_text(page, "Team/Event", "title")
    opponent = _prop_text(page, "Opponent", "rich_text")

    parts = re.split(r"\s+vs\.?\s+", title, maxsplit=1, flags=re.IGNORECASE)
    primary = parts[0].strip()
    other = parts[1].strip() if len(parts) > 1 else opponent
    return primary, other or None


def _is_hockey(page: dict) -> bool:
    sel = page["properties"].get("Sport", {}).get("select")
    return bool(sel and sel.get("name", "").lower() == "hockey")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enrich Games Tracker hockey entries with NHL API data."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would change without writing to Notion",
    )
    parser.add_argument(
        "--status-only", action="store_true",
        help="Only update Status (Upcoming → Missed); skip notes",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Overwrite Notes even when they already have content",
    )
    args = parser.parse_args()

    load_dotenv()

    print("Fetching games from Notion…")
    all_pages = nc.get_all_games()
    hockey = [p for p in all_pages if _is_hockey(p)]
    print(f"Found {len(hockey)} hockey game(s) out of {len(all_pages)} total.\n")

    today = str(Date.today())
    updated = skipped = failed = 0

    for page in hockey:
        page_id = page["id"]
        title = _prop_text(page, "Team/Event", "title")
        game_date = _extract_date(page)
        status = _extract_status(page)
        existing_notes = _prop_text(page, "Notes", "rich_text")

        label = f"  {title!r}  [{game_date or 'no date'}]"
        print(label, end="  ")

        if not game_date:
            print("→ skip (no date)")
            skipped += 1
            continue

        if game_date >= today:
            print("→ skip (future / today)")
            skipped += 1
            continue

        primary, opponent = _extract_teams(page)

        # Try primary team first; fall back to opponent as the lookup key
        schedule_game = nhl.find_game(game_date, primary, opponent)
        if schedule_game is None and opponent:
            schedule_game = nhl.find_game(game_date, opponent, primary)

        if schedule_game is None:
            print("→ no NHL match found")
            skipped += 1
            continue

        if schedule_game.get("gameState") not in nhl.FINAL_STATES:
            print(f"→ skip (state={schedule_game.get('gameState')})")
            skipped += 1
            continue

        # Decide what to update
        new_status: str | None = "Missed" if status == "Upcoming" else None

        new_notes: str | None = None
        if not args.status_only:
            if existing_notes and not args.force:
                pass  # already has notes; respect them
            else:
                try:
                    detail = nhl.get_game_detail(schedule_game["id"])
                    new_notes = nhl.format_game_notes(schedule_game, detail)
                except Exception as exc:
                    print(f"→ notes fetch failed: {exc}")
                    new_notes = None

        if new_status is None and new_notes is None:
            print("→ nothing to update")
            skipped += 1
            continue

        changes: list[str] = []
        if new_status:
            changes.append(f"status {status} → {new_status}")
        if new_notes:
            changes.append("notes ← NHL data")

        print(f"→ {', '.join(changes)}", end="  ")

        if args.dry_run:
            if new_notes:
                preview = new_notes.replace("\n", " | ")
                print(f"\n     {preview[:120]}", end="")
            print("  [DRY RUN]")
            updated += 1
            continue

        try:
            nc.update_game_enrichment(page_id, notes=new_notes, status=new_status)
            print("✓")
            updated += 1
        except Exception as exc:
            print(f"✗  {exc}")
            failed += 1

    print(f"\n{updated} updated  {skipped} skipped  {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
