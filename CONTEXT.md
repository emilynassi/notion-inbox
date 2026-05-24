# Notion Inbox — Project Context

## Goal

A personal capture → triage pipeline. Emily quickly drops items into a web form; a scheduled Claude agent runs daily to read her Notes inbox, classify each item, and file it into the right Notion database.

**Example flow:**
1. Emily finds a recipe she likes
2. She opens the capture form (hosted on Vercel), types "Chicken Wrap Recipe" + pastes the URL
3. Entry lands in Notes* database with Status: Inbox
4. Every morning at 9am ET, the scheduled Claude agent triages the inbox automatically
5. Claude reads every Note with Status = Inbox, classifies it, moves it to the right database (Tasks*, Recipes, Books*, Concert Tracker, Resources*), archives the staging note

---

## Architecture

```
Capture form (Vercel — password protected, accessible from anywhere)
        ↓
Next.js server action → Notion API
        ↓
Notes* database (Status: Inbox) ← staging area for all raw captures
        ↓
Scheduled Claude agent (CCR, runs daily at 9am ET via claude.ai/code/routines)
        ↓
Claude classifies each item natively (no separate Anthropic API key needed)
        ↓
Target databases: Tasks*, Recipes, Books*, Concert Tracker, Resources*, Notes* (Draft)
```

---

## Tech Stack

### Capture app (`capture/` — Next.js, deployed to Vercel)
- Next.js 16 App Router, TypeScript, Tailwind
- Password auth via cookie + `proxy.ts` (new Next.js convention, replaces `middleware.ts`)
- Server actions (not API routes) for login + capture
- `@notionhq/client` to write to Notion
- Env vars: `CAPTURE_PASSWORD`, `NOTION_TOKEN`, `NOTION_NOTES_DB_ID`

### Triage CLI (`notion_inbox/` — Python, installable locally)
- `anthropic` SDK — Claude classifies inbox items
- `notion-client` — reads Notes inbox, writes to target DBs
- Entry point: `notion-triage` (via pyproject.toml script)
- Env vars: `NOTION_TOKEN` + all six DB IDs + `ANTHROPIC_API_KEY` (see `.env`)
- **Note:** Daily triage now runs via the scheduled CCR agent (see below). The CLI exists for local/manual use.

### Scheduled triage agent (CCR — Claude Code Remote)
- Routine ID: `trig_01P92rMFocWNUgksCwBNB3nu`
- Manage at: https://claude.ai/code/routines/trig_01P92rMFocWNUgksCwBNB3nu
- Schedule: daily at 9am ET (`0 13 * * *` UTC)
- Model: claude-sonnet-4-6
- Repo: https://github.com/emilynassi/notion-inbox
- No `ANTHROPIC_API_KEY` needed — the CCR agent IS Claude, classifies natively
- Notion token + all DB IDs are embedded in the routine prompt
- To trigger manually: ask Claude "run my triage routine"

---

## Notion Workspace (Emily's Second Brain)

Integration name: **Inbox Triage**
Integration token: in `capture/.env.local` and `.env` as `NOTION_TOKEN`

**Important:** The integration must be connected to the *source* database pages directly — not to linked views or dashboard embeds. Linked views (e.g. "View of Notes*" inside the Inbox page) do NOT grant API access.

Integration has full workspace access via Emily's Second Brain top-level page — no per-database sharing needed.

| Database | REST API ID | MCP data source URL |
|---|---|---|
| Notes* | `4d696684ea54825da8f081d6c3878e37` | `collection://60996684-ea54-8215-9b68-07f86d6be68c` |
| Tasks* | `a5696684ea54829e975881a760956943` | `collection://e7596684-ea54-82cf-a13b-07cb43057832` |
| Resources* | `17696684ea54828cbb4201d6a0d64bd4` | `collection://ce496684-ea54-8249-ae78-871c548c50b7` |
| Projects* | `41896684ea54826f9b5181ef708163c6` | — |
| Books* | `d2e96684ea548313945a01616a9da7a2` | `collection://b5f96684-ea54-8376-8976-0723e20198ce` |
| Concert Tracker | `ae1aacda9675491d8f9006297bd703c0` | `collection://bfe6bd4b-ce68-4123-ad37-91ab1b54da29` |
| Recipes | `5e92b0fd2a4440bda68401c85a1f452e` | `collection://70a134c3-084d-4fc3-9ca8-e37c34d0f6e1` |
| Games Tracker | *(planned — not yet created)* | — |

**Note on MCP queries:** `notion-fetch` on a database ID returns schema only, not rows. To get actual entries, use `notion-search` with `data_source_url`, then `notion-fetch` each result page to read its properties. See the notion-query skill for full details.

### Notes* schema (capture target / staging)
- `Title` (title)
- `Status` (status): **Inbox** → Draft → Saved
- `Type` (select): Idea, Note, Meeting, Learning, Research
- `Archive` (checkbox)
- URL stored as a link in the **page body** (no URL property on Notes*)

### Tasks* schema
- `Task name` (title)
- `Status` (status): To do / Doing / Done
- `Priority` (select): High / Med. / Low
- `Description` (rich_text), `Due date` (date)

### Resources* schema
- `Title` (title)
- `Status` (status): Inbox / To review / Saved
- `Type` (select): Book / Video / Article / Podcast / Website / Document / Social media
- `Link` (url), `Description` (rich_text)

### Books* schema
- `Name` (title)
- `Status` (status): To read / Reading / Finished / Stopped
- `Author` (rich_text), `Pages` (number)

### Recipes schema
- `Name` (title)
- `Link` (url)
- `Tags` (multi_select): Dessert / Dinner / Easy / Lunch

### Concert Tracker schema
- `Artist/Band` (title)
- `Status` (select): Upcoming / Attended / Missed
- `Venue` (rich_text), `Location` (rich_text), `Notes` (rich_text), `Date` (date)

### Projects* schema
- `Name` (title), `Status`: Inbox / Planned / In progress / Done
- `Description` (rich_text)

---

## notion-query Skill

A Claude Code skill for querying Emily's Second Brain live from any conversation.

**Skill file:** `~/.claude/skills/notion-query/SKILL.md`

**How to invoke:** Use `/notion-query` explicitly — natural language queries sometimes undertrigger.
```
/notion-query what's on my reading list?
/notion-query do I have any high priority tasks?
/notion-query what concerts have I been to?
```

**What it does:** Routes natural-language questions to the right Notion database, runs the two-step search → fetch pattern, and returns filtered results.

**Supported queries:** Books (to read / finished / reading), Tasks (by status, priority, urgency), Recipes (by name/tag), Concert Tracker (upcoming / attended / missed), Resources (by type/status), Notes (by type/status), Projects. Also handles past-tense / historical queries ("what books did I finish last year?").

**Planned:** Games Tracker — same schema as Concert Tracker. When created in Notion, add its database ID + data source URL here and in the skill file.

---

## Project Layout

```
notion-inbox/
├── CONTEXT.md                      ← this file
├── .env                            ← triage CLI env vars (gitignored)
├── .gitignore
│
├── capture/                        ← Next.js app (deployed to Vercel)
│   ├── proxy.ts                    ← auth middleware (cookie check)
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── globals.css
│   │   ├── page.tsx                ← capture form (title + URL)
│   │   ├── login/page.tsx          ← password login page
│   │   └── actions/
│   │       ├── auth.ts             ← login server action (sets cookie)
│   │       └── capture.ts          ← writes to Notes* DB via Notion API
│   ├── .env.local                  ← CAPTURE_PASSWORD, NOTION_TOKEN, NOTION_NOTES_DB_ID
│   └── .env.local.example
│
├── pyproject.toml                  ← triage CLI deps
├── notion_inbox/
│   ├── __init__.py
│   ├── cli.py                      ← entry point: reads inbox, classifies, routes, archives
│   ├── notion_client.py            ← Notion SDK wrapper (all DB create/read/archive ops)
│   ├── triage.py                   ← Claude classification (all 9 categories)
│   └── routers/
│       └── __init__.py
└── tests/
    └── test_triage.py
```

---

## Build Order

1. [x] Project scaffold
2. [x] Notion integration created (token obtained)
3. [x] Capture app built — freeform textarea + optional URL, password auth, writes to Notes* with Status: Inbox
4. [x] End-to-end capture tested locally (dev server)
5. [x] Deployed to Vercel → **https://capture-alpha-seven.vercel.app**
6. [x] GitHub repo → https://github.com/emilynassi/notion-inbox (connected to Vercel, auto-deploys on push)
7. [x] Notion integration granted full workspace access via Emily's Second Brain top-level page
8. [x] **Triage CLI** — rewrote `notion_client.py` + `triage.py` + `cli.py` from scratch against live Notion schemas; covers Tasks*, Resources*, Books*, Recipes, Concert Tracker, Notes* (Draft)
9. [x] **Scheduled agent** — CCR routine created, runs daily at 9am ET, tested and confirmed working
10. [ ] Add tests to `tests/test_triage.py`

---

## Triage Routing Logic

Read all Notes* with Status = Inbox. For each item, classify by title + URL:

| Category | Destination | Key signal |
|---|---|---|
| `recipe` | Recipes | Recipe site URL, dish/recipe in title |
| `book` | Books* | Book title, "read X", "book by Y" |
| `concert` | Concert Tracker | Artist + venue, "see [artist]", ticketing URL |
| `game` | Games Tracker *(planned)* | Sports team, game, stadium, ticketing URL |
| `task` | Tasks* | Action verbs: buy, call, fix, submit, email… |
| `article` | Resources* (Article) | News/blog URL or article-style headline |
| `video` | Resources* (Video) | YouTube, Vimeo, TikTok URL |
| `podcast` | Resources* (Podcast) | Podcast URL or episode mention |
| `website` | Resources* (Website) | Any other URL |
| `note` | Notes* → Draft | No URL, open-ended thought or idea |

Fallback: URL present → Resources* (Website). No URL → Notes* Draft (Type: Idea).

After filing, the staging note is **archived** (not deleted). Notes that stay as Notes* are promoted in-place (Status: Draft, Type set).

---

## Key Decisions Made

- Capture goes to **Notes*** (Status: Inbox) as the staging area — zero changes to Emily's existing Notion setup
- Classification happens at **triage time**, not capture time — no Anthropic API key needed in Vercel
- Triage runs as a **scheduled CCR agent** (not a local cron) — fires daily at 9am ET with no local machine required
- CCR agent classifies natively using its own Claude intelligence — no `ANTHROPIC_API_KEY` needed in the routine
- Staging notes are **archived** after filing (not deleted) — safe, reversible
- Concert Tracker ID in CONTEXT.md was garbled; correct ID confirmed via Notion MCP: `ae1aacda9675491d8f9006297bd703c0`
- Capture form is **password protected** (shared password, cookie-based, 30-day session)
- Next.js `middleware.ts` is now `proxy.ts` in Next.js 16
