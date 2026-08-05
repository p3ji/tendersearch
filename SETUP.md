# Setup, for people who don't use a terminal

The README assumes you are comfortable at a command line. This page does not. It is longer and
slower, and it gets you to the same place.

You will need about 30 minutes the first time. After that, daily use is two commands.

**A word on the two windows.** This tool lives in two different places, and mixing them up is
the single most common way to get stuck:

- A **terminal** — a plain text window where you type commands and press Enter. On Windows this
  is PowerShell. You use it for installing things and for the `canadabuys` commands.
- **Claude Code** — an AI assistant that runs *inside* that same terminal window. You use it for
  anything starting with a slash: `/profile`, `/rank`, `/apply`.

Every instruction below says which one you are in.

---

## 1. Install the three things you need

### Python

Go to [python.org/downloads](https://www.python.org/downloads/) and install Python 3.11 or
newer. **On the first screen of the installer, tick "Add Python to PATH"** before clicking
Install. If you miss that checkbox, later steps fail with "python is not recognized," and the
fix is to run the installer again and choose Modify.

### Git

Go to [git-scm.com/downloads](https://git-scm.com/downloads) and install it. Accept every
default.

### Claude Code

Follow the instructions at [claude.com/claude-code](https://claude.com/claude-code). You need
either a Claude subscription or an Anthropic API key. This tool cannot work without it — the
judgment half of the pipeline *is* Claude.

---

## 2. Open a terminal

Press the **Windows key**, type `powershell`, and press **Enter**.

A window opens with a blinking cursor and a line ending in `>`. This is your terminal. When
this guide says "type this and press Enter," it means here.

Check that Python arrived correctly:

```
python --version
```

You should see something like `Python 3.12.4`. If you instead see "not recognized," Python did
not get added to PATH — reinstall it and tick that box.

---

## 3. Download the tool

Still in the terminal. This copies the project onto your machine and moves you into it:

```
git clone https://github.com/p3ji/tendersearch.git
cd tendersearch
```

Where did it go? Into your user folder — usually `C:\Users\<you>\tendersearch`. You can open it
in File Explorer to look around, and you will need to later.

---

## 4. Set up the workspace

Three commands. Type each one, press Enter, and wait for the cursor to come back before typing
the next.

```
python -m venv .venv
```

This makes a private workspace inside the project folder so this tool's components stay separate
from anything else on your computer. It takes a few seconds and prints nothing.

```
.venv\Scripts\Activate.ps1
```

This switches your terminal into that workspace. You will see `(.venv)` appear at the start of
your prompt line — that is how you know it worked.

> **If you get a red error about "running scripts is disabled":** Windows blocks scripts by
> default. Type this, press Enter, then try the activate line again. It applies only to this
> window and undoes itself when you close it:
>
> ```
> Set-ExecutionPolicy -Scope Process RemoteSigned
> ```

```
pip install -e ".[dev]"
```

This downloads three small helper libraries and takes under a minute. A wall of text scrolls
past — that is normal. It should end with a line starting `Successfully installed`.

Now check that everything works:

```
pytest
```

You should see a row of dots and then a line ending in `passed`, with no failures. This runs
entirely on your machine and touches nothing on the internet. If anything fails, stop here and
open an [issue](https://github.com/p3ji/tendersearch/issues) — do not continue.

### The one thing to remember

**`(.venv)` has to be showing at the start of your prompt.** It disappears every time you close
the terminal. When you come back tomorrow, you need two lines before anything else works:

```
cd tendersearch
.venv\Scripts\Activate.ps1
```

If you ever get "canadabuys is not recognized," this is why, and those two lines are the fix.

---

## 5. Get the tender notices

Still in the terminal, with `(.venv)` showing:

```
canadabuys fetch --feed open
```

This downloads every open federal tender notice — around 900 of them — and takes a minute or
two. It prints a summary of how many were new. Running it again later only fetches what
changed, so it is safe to repeat as often as you like.

---

## 6. Start Claude Code

Still in the same terminal window:

```
claude
```

The prompt changes. **You are now in Claude Code**, and this is where every slash command goes.
You can type ordinary questions here too.

To leave Claude Code and get back to the plain terminal, type `/exit`.

---

## 7. Build a profile

In Claude Code, type:

```
/profile alex
```

Use a short lowercase nickname instead of `alex` — one word, no spaces.

The command will create a folder for that person's documents and pause. Open File Explorer,
navigate to `tendersearch\profiles\alex\evidence\`, and copy in anything describing their work:
resumes, CVs, capability statements, past proposals. PDF and Word are both fine. Then come back
and tell Claude they are ready.

It reads those and asks you questions — one at a time, roughly ten to fifteen of them. Expect
15–20 minutes. Answer honestly; "no" and "none yet" are real answers and never disqualify
anyone.

**The part that matters most.** Partway through, Claude proposes a list of keywords and asks
you to approve them. Do not rush this. Government buyers do not describe your work the way you
do — what you call "change management" gets advertised as "business transformation advisory
services." Those keywords decide which notices the tool can see *at all*. Roughly one notice in
eight carries no category code whatsoever and is findable only by keyword. A thin list here is
the difference between seeing an opportunity and never knowing it existed.

Repeat `/profile <name>` for each person in your group.

---

## 8. Check your settings

Open the file `config.yml` in the `tendersearch` folder. Right-click it in File Explorer, choose
**Open with**, and pick **Notepad**.

You will see four settings. The only one worth changing at the start is the first:

```
min_turnaround_days: 5
```

That means "ignore anything closing in fewer than 5 days, because I could not write a bid that
fast." If you need more lead time, change `5` to `10`.

**Editing rules:** change only what comes after the colon. Do not delete the colons, do not use
the Tab key, and keep everything lined up as you found it. Save with Ctrl+S.

---

## 9. Run it

Back in Claude Code:

```
/rank
```

This filters all ~900 notices down to the few dozen that plausibly fit you, then reads each one
against your profiles and scores it. It takes several minutes and uses a real portion of your
daily Claude allowance — think of it as costing about what a long conversation costs. Once a
day is the intended rhythm; there is no reason to run it more.

It produces a digest at `matches\<today's date>\digest.md`. Open it in Notepad, or just ask
Claude Code to summarize it for you.

**What you are reading.** The digest is not a list of things to bid on. It is mostly a list of
things *not* to bid on, and why — "you meet 6 of 8 mandatory requirements; nobody in your group
holds the required clearance." That is the point. A federal proposal costs weeks, and knowing
early that you cannot win one is worth more than a maybe.

---

## Your daily routine, once set up

Open PowerShell:

```
cd tendersearch
.venv\Scripts\Activate.ps1
claude
```

Then in Claude Code:

```
/scrape
/rank
```

You can also have this run automatically on a schedule — see [docs/scheduling.md](docs/scheduling.md).

---

## When something goes wrong

| What you see | What it means | What to do |
|---|---|---|
| `canadabuys is not recognized` | The workspace isn't switched on | Run `.venv\Scripts\Activate.ps1` — check for `(.venv)` in your prompt |
| `python is not recognized` | Python wasn't added to PATH | Reinstall Python, tick "Add Python to PATH" |
| `running scripts is disabled` | Windows script blocking | `Set-ExecutionPolicy -Scope Process RemoteSigned`, then retry |
| `no notices stored yet` | You haven't fetched anything | Run `canadabuys fetch --feed open` |
| `no usable profiles found` | No profile exists yet | Run `/profile <name>` in Claude Code |
| The digest is nearly empty | Usually keywords, or `min_turnaround_days` | Re-run `/profile` and widen the keywords; check `config.yml` |
| A slash command does nothing | You're in the terminal, not Claude Code | Type `claude` first |

You can also just describe the problem to Claude Code in plain English. It can read the error
and the project's own documentation.

---

## Two things to know about your data

**Your colleagues' resumes never leave your machine**, except insofar as Claude reads them to
build profiles. They are stored in `profiles/`, which is deliberately excluded from anything
that gets shared or published. Do not move them elsewhere in the project folder.

**Your bid drafts are the one thing you could lose.** They live in `bids/` and are not backed up
by anything. Everything else in the project can be regenerated by re-running commands; those
cannot. Copy that folder somewhere you trust — OneDrive, a network drive, anywhere.

[SECURITY.md](SECURITY.md) states this in full, plainly.
