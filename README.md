# SnapFind

**Find any screenshot in seconds.** Upload screenshots, and SnapFind runs OCR on
them, auto-tags and categorises them, and makes every word inside instantly
searchable. Multi-user, server-rendered, and built to feel polished.

Google Photos × Notion × a file manager — focused on screenshots.

---

## Stack

| Layer        | Choice                                                            |
|--------------|-------------------------------------------------------------------|
| Backend      | Python · FastAPI                                                   |
| Templates    | Jinja2 (server-rendered) + HTMX (no SPA framework) + a little Alpine.js |
| Styling      | Tailwind CSS (Play CDN) — dark mode, responsive                   |
| Database     | PostgreSQL (SQLAlchemy 2.0) — SQLite fallback for a quick look    |
| OCR          | Tesseract via `pytesseract`, off-request in a thread pool         |
| Auth         | Session cookies + `passlib` (bcrypt), CSRF on all mutations       |

---

## Features

- **Auth & multi-user** — register / login / logout, profile & password settings.
  Every row is scoped by `user_id`; every single-record route funnels through one
  ownership check (`get_owned_*`) so no one can read another user's data by id.
- **Upload** — drag & drop, file picker, bulk upload, and clipboard paste (Ctrl+V).
  PNG / JPG / JPEG / WEBP.
- **Async OCR** — uploads return instantly; Tesseract runs in a `ThreadPoolExecutor`
  with live **Processing / Indexed / Failed** status badges (HTMX polling). Stuck
  jobs are re-enqueued on startup.
- **Duplicate detection** — perceptual image hashing, scoped per user; on a match
  you can *keep both*, *skip*, or *replace original*.
- **Instant search** — live, refresh-free (HTMX) full-text search over OCR text,
  with operators: `before:` `after:` `tag:` `collection:` `favorite:`.
- **Organisation** — auto-generated tags, auto-categorisation (School, Chats,
  Receipts, Code, Shopping, Photos, Miscellaneous), collections with drag-and-drop
  assignment, notes, favorites, and archive (hide without deleting).
- **Views** — responsive card grid, full-screen **viewer** with zoom/pan, a
  **timeline** grouped by Today / Yesterday / This Week / months, and a **dashboard**
  with storage, OCR completion, upload trends, and top categories (Chart.js).
- **Export** — current view as **ZIP** (images + metadata), **CSV**, or **JSON**.

---

## Quick start

### One command (Windows / PowerShell)

```powershell
cd C:\Users\jikok\snapfind
.\run.ps1
```

That's it. `run.ps1` creates the virtualenv, installs dependencies, writes a `.env`
(SQLite + a generated `SECRET_KEY`), seeds the demo account, and starts the app at
<http://localhost:8000>. Log in with **demo@snapfind.app / demo1234**.

- Skip demo data: `.\run.ps1 -NoSeed` · different port: `.\run.ps1 -Port 9000`
- If PowerShell blocks the script, run it once as:
  `powershell -ExecutionPolicy Bypass -File .\run.ps1`

### Or by hand

No `.env` and no database server required — it defaults to a local SQLite file.

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m seed.seed        # optional demo data: demo@snapfind.app / demo1234
uvicorn main:app --reload  # http://localhost:8000
```

Tables and the SQLite file are created automatically on first boot.

### Optional: real OCR (Tesseract)

The app runs fine without it — uploads just show a **Failed** badge and the demo seed
uses its bundled text manifest. To enable OCR on new uploads, install the native engine:

- **Windows:** [UB-Mannheim build](https://github.com/UB-Mannheim/tesseract/wiki), then
  add it to `PATH` or set `TESSERACT_CMD` in `.env` (e.g.
  `C:\Program Files\Tesseract-OCR\tesseract.exe`).
- **macOS:** `brew install tesseract` · **Debian/Ubuntu:** `sudo apt install tesseract-ocr`

### Optional: PostgreSQL (full multi-user deployment)

```powershell
docker compose up -d db
# then in .env:
# DATABASE_URL=postgresql+psycopg://snapfind:snapfind@localhost:5432/snapfind
```

---

## Search operators

| Example                       | Meaning                                  |
|-------------------------------|------------------------------------------|
| `invoice total`              | free text in OCR / filename / notes      |
| `tag:receipt`                | has the tag *receipt*                     |
| `collection:Projects`        | inside the *Projects* collection          |
| `favorite:yes`               | favorited only                            |
| `after:2026-01-01`           | uploaded on/after a date                  |
| `before:2026-06-01`          | uploaded before a date                    |

Operators combine: `tag:code after:2026-05-01 react`.

---

## Project structure

```
snapfind/
├── main.py            # FastAPI app: middleware, routers, startup
├── config.py          # settings (.env)
├── database.py        # engine, session, Base
├── auth.py            # passwords, sessions, CSRF, ownership helpers
├── templating.py      # Jinja env + shared nav/sidebar context
├── models/            # User, Screenshot, Collection, Tag, associations
├── routes/            # pages, auth, upload, screenshots, search, collections, tags, export
├── services/          # ocr, hashing, tagging, categorize, search, stats, export, processing
├── utils/             # search parser, time grouping, file storage, time helpers
├── templates/         # base/app shell, landing, grid, viewer, dashboard, timeline, auth, partials
├── static/            # app.css, app.js
├── uploads/           # per-user object storage (created at runtime, git-ignored)
├── seed/              # demo seed script, generated images, manifest
└── docker-compose.yml # PostgreSQL for the full multi-user deployment
```

### Where this is built to grow

OCR logic is isolated in `services/ocr.py` and dispatched through
`services/processing.py`, so moving from `BackgroundTasks`/thread pool to a real
queue (Celery/RQ) later is a localized change. Uploads are stored under per-user
prefixes (`uploads/<user_id>/…`) mirroring an S3/GCS layout. Full-text search uses
portable `ILIKE`; a Postgres `tsvector` + GIN index is the natural next step at scale.
