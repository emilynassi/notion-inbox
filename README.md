# notion-inbox

A personal capture → triage pipeline. Drop items into a web form from anywhere; a scheduled Claude agent runs every morning, classifies each item, and files it into the right Notion database automatically.

## How it works

```
Capture form (Vercel, password protected)
        ↓
Next.js server action → Notion API
        ↓
Notes* database (Status: Inbox)  ← staging area for everything
        ↓
Scheduled Claude agent (CCR, daily at 9am ET)
        ↓
Classifies each inbox item by title + URL
        ↓
Files into: Tasks*, Recipes, Books*, Concert Tracker, Resources*, Notes* (Draft)
Archives the original staging note
```

**Example:** You find a recipe → open the capture form → type "Chicken Wrap Recipe" and paste the URL → by 9am the next morning it's already in your Recipes database.

---

## Triage routing

| Type | Destination | Signal |
|---|---|---|
| Recipe | Recipes | Recipe site URL or dish/recipe in title |
| Book | Books* | Book title, "read X", "book by Y" |
| Concert | Concert Tracker | Artist + venue, ticketing URL |
| Task | Tasks* | Action verbs: buy, call, fix, submit, email… |
| Article | Resources* (Article) | News/blog URL or article headline |
| Video | Resources* (Video) | YouTube, Vimeo, TikTok |
| Podcast | Resources* (Podcast) | Podcast URL or episode mention |
| Website | Resources* (Website) | Any other URL |
| Note/Idea | Notes* → Draft | No URL, open-ended thought |

After filing, the staging note is archived (not deleted) — fully reversible.

---

## Repo layout

```
notion-inbox/
├── capture/                    ← Next.js app, deployed to Vercel
│   ├── proxy.ts                ← auth middleware (cookie-based password check)
│   ├── app/
│   │   ├── page.tsx            ← capture form (title + optional URL)
│   │   ├── login/page.tsx      ← password login
│   │   └── actions/
│   │       ├── auth.ts         ← login server action (sets 30-day cookie)
│   │       └── capture.ts      ← writes to Notes* via Notion API
│   └── .env.local.example
│
├── notion_inbox/               ← Python triage CLI
│   ├── cli.py                  ← entry point: reads inbox, classifies, routes, archives
│   ├── notion_client.py        ← Notion SDK wrapper (all DB read/write/archive ops)
│   ├── triage.py               ← Claude classification logic
│   └── routers/
│
├── tests/
│   └── test_triage.py
│
├── pyproject.toml              ← CLI deps + `notion-triage` script
├── .env.example                ← required env vars for the CLI
└── CONTEXT.md                  ← full architecture + Notion schema reference
```

---

## Capture app (`capture/`)

Next.js 16 App Router, TypeScript, Tailwind. Deployed to Vercel — auto-deploys on push to `main`.

**Env vars** (set in Vercel dashboard + `capture/.env.local` for local dev):

```
CAPTURE_PASSWORD=          # shared password for the form
NOTION_TOKEN=              # Notion integration token
NOTION_NOTES_DB_ID=        # Notes* database ID
```

---

## Triage CLI (`notion_inbox/`)

A Python package for running triage locally or testing changes. The scheduled agent handles production; this is for manual runs and development.

**Setup:**

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
# fill in .env with your tokens and DB IDs
```

**Run:**

```bash
notion-triage
```

Reads all Notes with Status = Inbox, classifies each one with Claude, files it, and archives the original.

**Env vars** (`.env`):

```
NOTION_TOKEN=
ANTHROPIC_API_KEY=         # only needed for local CLI use
NOTION_NOTES_DB_ID=
NOTION_TASKS_DB_ID=
NOTION_RESOURCES_DB_ID=
NOTION_BOOKS_DB_ID=
NOTION_RECIPES_DB_ID=
NOTION_CONCERTS_DB_ID=
```

---

## Scheduled agent

Triage runs automatically via a Claude Code Remote (CCR) routine — no local machine or cron job needed.

- **Schedule:** daily at 9am ET
- **Model:** claude-sonnet-4-6
- **No `ANTHROPIC_API_KEY` required** — the CCR agent IS Claude; it classifies natively
- Routine config + DB IDs are embedded in the routine prompt at claude.ai/code/routines

To trigger manually, ask Claude: *"run my triage routine"*

---

## Notion databases

The integration (named **Inbox Triage**) has full workspace access via the Emily's Second Brain top-level page. It writes to: Notes*, Tasks*, Resources*, Books*, Recipes, Concert Tracker.

Full schema reference and database IDs are in [CONTEXT.md](CONTEXT.md).
