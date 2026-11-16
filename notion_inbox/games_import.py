"""notion-games-import: bulk-load games into Games Tracker from a CSV.

Usage:
    notion-games-import games.csv
    notion-games-import games.csv --dry-run

CSV columns (header row required; all columns except `team_event` are optional):

    team_event   – e.g. "Rangers vs. Bruins"      [REQUIRED]
    sport        – Hockey / Baseball / Basketball / Football / Soccer
    status       – Upcoming / Attended / Missed    [default: Upcoming]
    opponent     – other team name
    venue        – stadium / arena name
    location     – city
    date         – YYYY-MM-DD
    notes        – free text

Column order doesn't matter. Extra columns are ignored.
Blank cells are skipped (field left empty in Notion).
"""

import argparse
import csv
import sys
from dotenv import load_dotenv

from notion_inbox import notion_client as nc

VALID_SPORTS   = {"Hockey", "Baseball", "Basketball", "Football", "Soccer"}
VALID_STATUSES = {"Upcoming", "Attended", "Missed"}


def _coerce_sport(raw: str) -> str:
    """Case-insensitive match against valid sport names."""
    cleaned = raw.strip().title()
    return cleaned if cleaned in VALID_SPORTS else ""


def _coerce_status(raw: str) -> str:
    cleaned = raw.strip().title()
    return cleaned if cleaned in VALID_STATUSES else "Upcoming"


def _load_rows(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [row for row in reader]


def _preview(row: dict, index: int) -> str:
    parts = [f"  [{index}] {row['team_event']!r}"]
    if row.get("sport"):
        parts.append(f"sport={row['sport']}")
    if row.get("status"):
        parts.append(f"status={row['status']}")
    if row.get("date"):
        parts.append(f"date={row['date']}")
    if row.get("venue"):
        parts.append(f"@ {row['venue']!r}")
    return "  ".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bulk-import games into Notion Games Tracker from a CSV."
    )
    parser.add_argument("csv_file", help="Path to the CSV file")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate the CSV but don't write anything to Notion",
    )
    args = parser.parse_args()

    load_dotenv()

    try:
        raw_rows = _load_rows(args.csv_file)
    except FileNotFoundError:
        print(f"Error: file not found: {args.csv_file}", file=sys.stderr)
        sys.exit(1)

    if not raw_rows:
        print("CSV is empty — nothing to import.")
        return

    # Normalise rows
    games: list[dict] = []
    errors: list[str] = []
    for i, row in enumerate(raw_rows, start=1):
        team_event = row.get("team_event", "").strip()
        if not team_event:
            errors.append(f"Row {i}: missing required field `team_event` — skipping")
            continue
        games.append({
            "team_event": team_event,
            "sport":      _coerce_sport(row.get("sport", "")),
            "status":     _coerce_status(row.get("status", "Upcoming")),
            "opponent":   row.get("opponent", "").strip(),
            "venue":      row.get("venue", "").strip(),
            "location":   row.get("location", "").strip(),
            "date":       row.get("date", "").strip(),
            "notes":      row.get("notes", "").strip(),
        })

    if errors:
        for msg in errors:
            print(f"⚠️  {msg}", file=sys.stderr)

    if not games:
        print("No valid rows to import.")
        sys.exit(1 if errors else 0)

    print(f"{'[DRY RUN] ' if args.dry_run else ''}Importing {len(games)} game(s)...\n")

    if args.dry_run:
        for i, game in enumerate(games, start=1):
            print(_preview(game, i))
        print(f"\nDry run complete — nothing written to Notion.")
        return

    successes, failures = 0, []
    for game in games:
        label = game["team_event"]
        print(f"  {label!r}…", end=" ", flush=True)
        try:
            nc.create_game(**game)
            print("✓")
            successes += 1
        except Exception as exc:
            print(f"✗  {exc}")
            failures.append((label, exc))

    print()
    print(f"{successes} game(s) imported successfully.")
    if failures:
        print(f"{len(failures)} failed:")
        for label, exc in failures:
            print(f"  • {label!r}: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
