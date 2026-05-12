# scripts/

Utility scripts for database management and local development.

---

## seed_istanbul.py

Populates the database with ~500,000 synthetic cellular signal measurements
covering Istanbul's 6 central districts for 3 Turkish operators.

### When to use

Run this once on a fresh database (or after a `DROP TABLE` reset) to get
realistic heatmap coverage across Şişli, Beşiktaş, Beyoğlu, Fatih, Kadıköy,
and Üsküdar. Do **not** run repeatedly against a live database — it will
keep appending rows.

### Prerequisites

- PostgreSQL is running and migrations have been applied (`alembic upgrade head`)
- `DATABASE_URL` is set in `.env` or in the environment
- Project dependencies installed (`.venv` activated, or run inside Docker)

### Usage

**Local virtualenv** (run from project root):

```bash
python scripts/seed_istanbul.py
```

**Docker Compose** (recommended for production-like setup):

```bash
docker-compose exec app python scripts/seed_istanbul.py
```

### What gets inserted

| Parameter       | Value                                        |
|-----------------|----------------------------------------------|
| Total rows      | 500,000                                      |
| Districts       | Şişli, Beşiktaş, Beyoğlu, Fatih, Kadıköy, Üsküdar |
| Operators       | 28601 (Turkcell), 28602 (Vodafone TR), 28603 (Türk Telekom) |
| Technology mix  | LTE 70%, NR 25%, WCDMA 5%                    |
| Time window     | Uniform random over last 7 days              |
| Signal (normal) | RSRP –85 to –110 dBm, RSRQ –8 to –14 dB, SINR 5–25 dB |
| Signal (weak 5%)| RSRP –110 to –120 dBm, RSRQ –14 to –18 dB, SINR 0–5 dB |
| Batch size      | 10,000 rows per commit                       |
| Estimated time  | ~2–3 minutes                                 |

### After the script finishes

Rows are stored as `is_cleaned=False`. You must trigger the aggregation
pipeline to compute H3 hexagon scores and populate the heatmap:

```bash
curl -X POST http://localhost:8000/api/v1/pipeline/run \
     -H "Content-Type: application/json" \
     -d '{"hours_back": 168}'
```

Expected response:
```json
{"cleaned": 500000, "rejected": 0, "cells_upserted": 1234}
```

Then open the frontend map — all 6 districts should show heatmap coverage
for all 3 operators.

### Tuning

Edit the constants at the top of `seed_istanbul.py`:

| Constant              | Default     | Purpose                          |
|-----------------------|-------------|----------------------------------|
| `TOTAL_MEASUREMENTS`  | `500_000`   | Total rows to insert             |
| `BATCH_SIZE`          | `10_000`    | Rows per DB commit               |
| `DAYS_BACK`           | `7`         | Timestamp spread window (days)   |
| `DISTRICTS`           | 6 districts | Bounding boxes — add/remove freely |
| `OPERATORS`           | 3 operators | MCC+MNC strings                  |
| `_TECH_WEIGHTS`       | 70/25/5     | Technology distribution          |
