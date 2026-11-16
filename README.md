# Bear board + capture

Two small tools around [Bear](https://bear.app) notes. Bear stays the only place notes live. These tools just make it easier to get things in and to see what's there.

```
Phone / anywhere                      Mac
────────────────                      ───
Capture form (capture/)               Bear Board (bear_board/)
  type a note, #tags, URL               card board over all your notes
        ↓                                 ↕  bearcli
  bear://x-callback-url/create          Bear
        ↓
  Bear on that device
```

> The original Notion inbox pipeline (capture form → Notion, daily Claude triage agent, Games Tracker) is preserved at the `notion-archive` tag: `git checkout notion-archive`.

---

## Bear Board (`bear_board/`)

A local web app that shows your Bear notes as a card board. It runs only on your Mac and reads and writes through Bear's command-line tool, `bearcli`.

**What it does:**

- Masonry board of cards with the newest notes across the top and pinned notes first, colored by tag
- Tag chips with sub-tags for filtering, full-text search (`/`), and a Todos view
- Link previews built from each page's title and image
- Light, dark, and system themes
- **＋ New note** (or press `N`): first-line `#tags` become the note's tags
- Drag a card onto a tag chip to add a tag, or click × on a tag to remove it
- Check off todos right on the cards
- Archive a note, or move it to Bear's trash. Never a permanent delete.
- Undo on every change

**Run:**

```bash
python3 bear_board/server.py      # http://127.0.0.1:8787
```

There are no dependencies to install. It needs Bear 2 with `bearcli` at `/Applications/Bear.app/Contents/MacOS/bearcli`; override that path with `BEARCLI=…` and the port with `BEAR_BOARD_PORT=…`.

**Security:** the server listens on 127.0.0.1 only. Requests that change notes need an `X-Bear-Board` header and a matching `Host`, so other websites can't send changes. Checking a todo or changing tags doesn't change a note's modified date.

---

## Capture form (`capture/`)

A one-page Next.js app for saving a note from your phone. When you press save, it opens a `bear://x-callback-url/create` link, so **Bear on that device creates the note**. Bear then sends you back to the form with a confirmation. Nothing is sent to or stored on a server, so there are no secrets or env vars.

- Tags on the first line become the note's tags: `pad thai #recipe` → a note called "pad thai" tagged `#recipe`.
- Tags further down stay in the text, and Bear picks them up as usual.
- Nested tags work, like `#travel/japan`.
- If the hand-off to Bear doesn't happen, the draft is still there next time you open the page.

**Run locally:**

```bash
cd capture && npm install && npm run dev   # http://localhost:3000
```

It deploys to Vercel and auto-deploys on push to `main`.
