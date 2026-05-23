# Notion Inbox — Project Context

## Goal

A personal capture → triage pipeline. Emily quickly drops items into a web form; later she runs a local Claude-powered triage command that reads her Notes inbox, classifies each item, and files it into the right Notion database.

**Example flow:**
1. Emily finds a recipe she likes
2. She opens the capture form (hosted on Vercel), types "Chicken Wrap Recipe" + pastes the URL
3. Entry lands in Notes* database with Status: Inbox
4. Later, she runs `notion-triage` in the terminal
5. Claude reads every Note with Status = Inbox, classifies it, moves it to the right database (Tasks, Resources, etc.), updates the status

---

## Architecture

```
Capture form (Vercel — password protected, accessible from anywhere)
        ↓
Next.js server action → Notion API
        ↓
Notes* database (Status: Inbox) ← staging area for all raw captures
        ↓
notion-triage CLI (Python, run locally on demand)
        ↓
Claude (classifies each item, determines destination + metadata)
        ↓
Target databases: Tasks*, Notes* (status update), Resources*, Projects*
```

---

## Tech Stack

### Capture app (`capture/` — Next.js, deploy to Vercel)
- Next.js 16 App Router, TypeScript, Tailwind
- Password auth via cookie + `proxy.ts` (new Next.js convention, replaces `middleware.ts`)
- Server actions (not API routes) for login + capture
- `@notionhq/client` to write to Notion
- Env vars: `CAPTURE_PASSWORD`, `NOTION_TOKEN`, `NOTION_NOTES_DB_ID`

### Triage CLI (`notion_inbox/` — Python, run locally)
- `anthropic` SDK — Claude classifies inbox items
- `notion-client` — reads Notes inbox, writes to target DBs
- Entry point: `notion-triage` (via pyproject.toml script)
- Env vars: same `NOTION_TOKEN` + all four DB IDs

---

## Notion Workspace (Emily's Second Brain)

Integration name: **Inbox Triage**
Integration token: in `capture/.env.local` as `NOTION_TOKEN`

**Important:** The integration must be connected to the *source* database pages directly — not to linked views or dashboard embeds. Linked views (e.g. "View of Notes*" inside the Inbox page) do NOT grant API access.

Integration has full workspace access via Emily's Second Brain top-level page — no per-database sharing needed.

| Database | REST API ID |
|---|---|
| Notes* | `4d696684ea54825da8f081d6c3878e37` |
| Tasks* | `a5696684ea54829e975881a760956943` |
| Resources* | `17696684ea54828cbb4201d6a0d64bd4` |
| Projects* | `41896684ea54826f9b5181ef708163c6` |
| Books* | `d2e96684ea548313945a01616a9da7a2` |
| Concert Tracker | `ae1aacdа96754 91d8f9006297bd703c0` |
| Recipes | `5e92b0fd2a4440bda68401c85a1f452e` |

### Notes* schema (capture target)
- `Title` (title)
- `Status` (status): **Inbox** → Draft → Saved
- `Type` (select): Idea, Note, Meeting, Learning, Research
- URL stored as a link in the **page body** (no URL property on Notes)

### Tasks* schema
- `Task name` (title), `Status`: To do / Doing / Done
- `Priority`: High / Med. / Low, `Description` (text), `Due date`

### Resources* schema
- `Title`, `Status`: Inbox / To review / Saved
- `Type`: Book / Video / Article / Podcast / Website / Document / Social media
- `Link` (url), `Description` (text)

### Projects* schema
- `Name` (title), `Status`: Inbox / Planned / In progress / Done
- `Description` (text)

---

## Project Layout

```
notion-inbox/
├── CONTEXT.md                      ← this file
├── .gitignore
│
├── capture/                        ← Next.js app (deploy to Vercel)
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
│   ├── cli.py                      ← entry point: reads inbox, calls triage
│   ├── notion_client.py            ← Notion SDK wrapper (needs updating)
│   ├── triage.py                   ← Claude classification call
│   └── routers/
│       ├── __init__.py
│       ├── recipe.py
│       └── reading.py
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
8. [ ] **Triage CLI** — rewrite `notion_client.py` + `triage.py` + `cli.py` to use real schemas + all known databases
9. [ ] Install + test triage CLI end-to-end

---

## Triage CLI — What Claude Should Do

Read all Notes* with Status = Inbox. For each:
- If it belongs in **Resources*** (recipe, article, book, video, concert listing, etc.) → create in Resources*, set Type appropriately, delete or archive the Note
- If it belongs in **Tasks*** → create in Tasks* with Status: To do, delete/archive the Note  
- If it belongs in **Projects*** → create in Projects* with Status: Inbox, delete/archive the Note
- If it's genuinely a note/idea → update Status to Draft and set Type

Claude should infer category from title + URL. Unknown categories should default to Resources* Type: Website or Notes* Type: Idea.

---

## Key Decisions Made

- Capture goes to **Notes*** (Status: Inbox) as the staging area — it already has an Inbox status in Emily's existing schema
- No separate inbox database — zero changes to Emily's existing Notion setup
- Classification happens at **triage time** (local CLI), not at capture time — avoids needing Anthropic API key in the Vercel deployment
- Capture form is **password protected** (shared password, cookie-based, 30-day session)
- Next.js `middleware.ts` is now `proxy.ts` in Next.js 16
