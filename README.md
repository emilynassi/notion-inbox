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

**Set up (on the Mac that has Bear):**

```bash
git clone git@github.com:emilynassi/notion-inbox.git && cd notion-inbox
bear_board/install.sh
```

The script:

1. checks for Bear 2 and Python 3.9+
2. has you choose a board password
3. starts the board at login (pass `--no-autostart` to skip)
4. shares the board over Tailscale, if Tailscale is installed and signed in

`--dry-run` shows what it would do without changing anything, and `--uninstall` stops the board and removes the login item.

There are no packages to install.

**Using it from other computers (Windows, Linux, a work laptop…):** the board reads Bear on your Mac, so it has to run there. To reach it from anywhere else:

1. Install [Tailscale](https://tailscale.com/download) on the Mac and on the other computer, and sign in to the same account on both.
2. Re-run `bear_board/install.sh` on the Mac. It prints the board's address, like `https://your-mac.tailnet-name.ts.net`.
3. Open that address on the other computer and sign in with the board password.

The Mac has to be awake. Only devices on your Tailscale account can reach the address. Clicking a card opens the note in Bear, so that part works only where Bear is installed.

**Run by hand:**

```bash
python3 bear_board/server.py --set-password   # once
python3 bear_board/server.py                  # http://127.0.0.1:8787
```

Settings (environment variables):
- `BEARCLI`: path to `bearcli`. Default `/Applications/Bear.app/Contents/MacOS/bearcli`.
- `BEAR_BOARD_PORT`: default `8787`.
- `BEAR_BOARD_HOSTS`: extra hostnames the board answers to, such as the Mac's Tailscale name.
- `BEAR_BOARD_CONFIG_DIR`: where the login config lives. Default `~/.config/bear-board`.

**Security:**
- **Password login on every page and request.** Only a salted scrypt hash of the password is stored, in `~/.config/bear-board/config.json` (readable only by you).
- **Sessions** last 30 days in a signed, HttpOnly, SameSite=Strict cookie (also Secure over Tailscale). Setting a new password signs out every device.
- **Wrong passwords are slowed down:** each failure takes a second, and after 10 failures in 10 minutes all logins pause until that window passes.
- **The server listens on 127.0.0.1 only.** Every request must name an allowed `Host`, which blocks DNS rebinding.
- **Changes need an `X-Bear-Board` header,** so other websites can't send them.
- **Checking a todo or changing tags doesn't change a note's modified date.**

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
