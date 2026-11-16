"""Offline eval for the inbox triage classifier.

Runs a set of representative + edge-case inbox items through `classify_item`
and checks the returned category / status / date against expectations.

Usage:
    ANTHROPIC_API_KEY=sk-ant-... python -m notion_inbox.eval_triage

Exit code is non-zero if any case fails, so it can gate CI.
Date-sensitive cases are evaluated relative to today, so they keep working
no matter when you run them.
"""

import datetime as _dt
import sys

from dotenv import load_dotenv

from notion_inbox.triage import classify_item


def _check(actual: dict, expect: dict) -> list[str]:
    """Return a list of mismatch strings (empty == pass)."""
    problems: list[str] = []
    for key, want in expect.items():
        got = actual.get(key)
        if callable(want):
            if not want(got):
                problems.append(f"{key}={got!r} failed predicate")
        elif got != want:
            problems.append(f"{key}: want {want!r}, got {got!r}")
    return problems


def main() -> None:
    load_dotenv()

    today = _dt.date.today()
    past = (today - _dt.timedelta(days=3)).isoformat()
    future = (today + _dt.timedelta(days=10)).isoformat()

    # Each case: (title, url, expected-fields)
    cases: list[tuple[str, str | None, dict]] = [
        # --- core routing ---
        ("Atomic Habits by James Clear", None,
         {"category": "book"}),
        ("Thai Marinated Steak Salad", "https://www.skinnytaste.com/thai-marinated-steak-salad/",
         {"category": "recipe"}),
        ("Email the accountant about Q2 taxes", None,
         {"category": "task"}),

        # --- book over-matching guard (was misclassifying tasks as books) ---
        ("Read Q3 revenue report", None,
         {"category": lambda c: c in ("task", "article", "website")}),
        ("Read the onboarding doc before Monday", None,
         {"category": lambda c: c in ("task", "article", "website")}),

        # --- social media now its own category mapping to "Social media" ---
        ("Funny thread about productivity", "https://x.com/someone/status/123",
         {"category": "social"}),

        # --- GAME: past attended, with date + status extraction ---
        (f"Went to the Rangers vs Bruins game on {past}", None,
         {"category": "game", "status": "Attended", "date": past}),
        ("Rangers vs Canadiens last night", None,
         {"category": "game", "status": "Attended",
          "date": (today - _dt.timedelta(days=1)).isoformat()}),

        # --- GAME: future plan -> Upcoming ---
        (f"Knicks game on {future}", None,
         {"category": "game", "status": "Upcoming", "date": future}),

        # --- CONCERT: missed ---
        (f"Missed Bon Iver at MSG on {past}", None,
         {"category": "concert", "status": "Missed", "date": past}),

        # --- CONCERT: upcoming with venue/location ---
        (f"Tickets for Phoebe Bridgers at Forest Hills Stadium {future}", None,
         {"category": "concert", "status": "Upcoming", "date": future}),

        # --- note fallback ---
        ("Random idea: a tool that summarizes my week", None,
         {"category": "note"}),
    ]

    passed = 0
    failed = 0
    for title, url, expect in cases:
        try:
            result = classify_item(title, url)
        except Exception as exc:  # noqa: BLE001
            print(f"✗ ERROR  {title!r}: {exc}")
            failed += 1
            continue

        problems = _check(result, expect)
        if problems:
            failed += 1
            print(f"✗ FAIL   {title!r}")
            for p in problems:
                print(f"           {p}")
            print(f"           full: {result}")
        else:
            passed += 1
            print(f"✓ pass   {title!r}  → {result.get('category')}")

    print(f"\n{passed} passed, {failed} failed ({passed + failed} total)")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
