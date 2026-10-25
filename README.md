# Constitutional Law notes (private)

A password-locked study site for the Constitutional Law course at MNLU Nagpur (Semester III, 2026-27):
the day-wise class notes (15 July – 7 October), the exam-ready notes (October lectures), every original
lecture file, a case finder with direct Indian Kanoon links, the text of the Articles covered, and practice tools.

**Keep this repository private.** The `source/` folder holds the original notes and lecture files unencrypted.

## How the privacy works

- `docs/` is the website. It is the only folder GitHub Pages publishes.
- Everything in `docs/data/` is encrypted (AES-256-GCM). The key is locked with your password
  (PBKDF2-SHA256, 310,000 rounds) in `docs/data/key.json`. Without the password the site shows only the lock screen.
- The site sets `noindex` and `robots.txt` blocks crawlers.

## Publishing with GitHub Pages

Settings → Pages → Source: **Deploy from a branch**, branch `main`, folder **`/docs`**.

GitHub Pages for a private repository needs GitHub Pro (free with the GitHub Student Developer Pack).
If you do not have it, create a second, public repository and copy only the `docs/` folder into it — the
content there is encrypted, so the notes stay unreadable without the password. Never make this repository public.

## Changing the password

Open the site → Settings → *Change the password*. It downloads a new `key.json`; upload it to
`docs/data/key.json` here. Nothing else changes.

## Rebuilding after you change the notes

Needs Python 3.10+, `pandoc`, and `pip install -r build/requirements.txt`.

```bash
python3 build/docx2json.py      # source/notes/COLA_Exam_Ready_Notes_Kanishk.docx -> content/exam_notes.json
python3 build/pdf2json.py       # source/notes/PreCL.pdf -> content/day_notes.json (+ diagrams)
python3 build/articles.py       # Constitution text -> content/articles.json
SITE_PASSWORD='your password' python3 build/build.py   # -> docs/data (encrypted)
```

Each build uses a fresh encryption key, so it needs the password every time.

| File | What it holds |
|---|---|
| `build/cases_master.py` | The case registry: names, decision years, holdings, topics |
| `build/ik_links.txt` | Indian Kanoon links, each found by searching Indian Kanoon and matching title and date |
| `build/corrections.py` | Errors found in the notes, with the correct position and sources |
| `build/extras.py` | Amendment timeline, problem frameworks, the lecture-file catalogue |

## Credits

Constitution text: [civictech-India/constitution-of-india](https://github.com/civictech-India/constitution-of-india),
checked and patched for later amendments (see `build/articles.py`). Judgments: [Indian Kanoon](https://indiankanoon.org).
Fonts: Literata and Mukta (SIL Open Font License). Search: [MiniSearch](https://github.com/lucaong/minisearch) (MIT).
