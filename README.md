# LEGO Part Cross-Reference API

Returns equivalent LEGO part numbers across major LEGO-related sites, using [Brick Architect](https://brickarchitect.com) as the authoritative source.

Supported sources include Brick Architect, LEGO Pick a Brick, BrickLink, Rebrickable, Brickset, and LDraw.

## Setup

Requires Python 3.10+.

```bash
cd lego-part-xref
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Or install as a package (creates a `part-xref` command):

```bash
pip install .
```

Optional: copy `.env.example` to `.env` and adjust settings.

```bash
cp .env.example .env
```

## Install on another Mac (e.g. Mac Mini)

Build a tarball on your dev machine:

```bash
./scripts/build-package.sh
```

Copy to the target Mac and install:

```bash
scp dist/lego-part-xref-1.0.0.tar.gz your-mac-mini:~/
ssh your-mac-mini
tar -xzf lego-part-xref-1.0.0.tar.gz
cd lego-part-xref-1.0.0
./install/install.sh --service
```

The installer:

- Creates a virtual environment and installs the app under `~/lego-part-xref` (override with `--dir PATH`)
- Copies `.env.example` to `.env` if `.env` is missing (edit PostgreSQL and other settings before relying on it)
- Runs the PostgreSQL schema migration when reachable
- With `--service`, registers a launchd user agent so the API starts at login

Useful options:

```bash
./install/install.sh --dir /opt/lego-part-xref --service   # custom location + auto-start
./install/install.sh --no-migrate                            # skip DB migration
./install/uninstall.sh --remove-files                        # stop service and remove install dir
```

Service logs: `~/Library/Logs/lego-part-xref/`

## Run

With the virtual environment activated:

```bash
source .venv/bin/activate   # if not already active
python3 run_part_xref.py
```

On macOS with Homebrew Python, you must use a virtual environment — do not run `pip install` against the system Python.

The server starts on port **8035** by default (configurable via `PART_XREF_PORT`, clamped to 8030–8039).

- Web UI: [http://localhost:8035/](http://localhost:8035/)
- OpenAPI docs: [http://localhost:8035/docs](http://localhost:8035/docs)

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PART_XREF_PORT` | `8035` | HTTP port (clamped to 8030–8039) |
| `PART_XREF_CACHE_ENABLED` | `1` | Enable SQLite cache (`1`, `true`, or `yes`) |
| `PART_XREF_CACHE_TTL` | `86400` | Cache entry lifetime in seconds (24 hours) |
| `PART_XREF_CACHE_DB` | `part_xref/data/part_xref_cache.db` | Path to the SQLite cache database |
| `PART_XREF_REQUEST_TIMEOUT` | `15` | Timeout in seconds for Brick Architect requests |
| `PART_XREF_USER_AGENT` | `LegoHub-PartXRef/1.0 (...)` | User-Agent header sent to Brick Architect |
| `BRICK_ARCHITECT_BASE_URL` | `https://brickarchitect.com/parts` | Base URL for part pages |
| `PART_XREF_LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, etc.) |

## API

### Look up a part number

```
GET /api/lego/part-number/{part_number}
```

**Example**

```bash
curl -s http://localhost:8035/api/lego/part-number/3001 | python3 -m json.tool
```

**Success (200)**

```json
{
  "part_number": "3001",
  "brick_architect_part_number": "3001",
  "alternative_part_numbers": {
    "brick_architect": "3001",
    "lego_pick_a_brick": "3001",
    "bricklink": "3001",
    "rebrickable": "3001",
    "brickset": "3001",
    "ldraw": "3001.dat"
  },
  "error": null
}
```

**Part not found (200)** — returns an `error` field with an empty `alternative_part_numbers` object:

```json
{
  "part_number": "999999999",
  "brick_architect_part_number": null,
  "alternative_part_numbers": {},
  "error": "Part number not found."
}
```

**Invalid input (400)** — e.g. whitespace-only part number:

```json
{
  "detail": {
    "part_number": "   ",
    "brick_architect_part_number": null,
    "alternative_part_numbers": {},
    "error": "Invalid part number."
  }
}
```

Upstream failures (timeouts, network errors) also return **200** with an `error` message and no alternatives.
