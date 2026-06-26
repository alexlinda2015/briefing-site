# Auckland Industrial Property Dashboard

A live, automatically-refreshed dashboard of **Auckland industrial property for
lease**, aggregated from six commercial agencies. Rebuilt every day at **7:00 am
New Zealand time** by GitHub Actions — no PC, server, or manual step required.

- **Live page:** `auckland-industrial.html` (served by GitHub Pages once enabled —
  e.g. `https://<user>.github.io/<repo>/auckland-industrial.html`).
- **Open locally:** just open `auckland-industrial.html` in a browser; the data
  is embedded in the file.

## Sources

| Agency | Search |
|--------|--------|
| Bayleys | industrial / workplace, Auckland |
| Colliers | For Lease · Industrial · Auckland |
| JLL | lease warehouse, Auckland |
| CBRE | industrial & logistics for lease, Auckland |
| James Kirkpatrick (JKGL) | Auckland warehouse vacancies |
| Commercial Realty | lease · industrial · Manukau City |

## What it shows

Each listing displays: **address, suburb, grade, net lettable area (m²), asking
rent, date listed, days on market, property attributes, owner/agency**, and a
**click-through link** to the original listing. The table is searchable,
filterable by agency/suburb, and sortable.

- **Days on market** uses the agency's published listing date when available;
  otherwise it counts from the date this tracker *first observed* the listing
  (persisted in `data/seen.json`), so the figure accrues over time for sources
  that don't publish a date.
- **Owner** shows the landlord only where an agency publishes it — most listings
  expose only the marketing agency, which is shown as the coloured chip.

## How it works

```
scraper/scrape.py   # headless-browser scrape of all six sources → data/listings.json + data/seen.json
scraper/render.py   # data/listings.json → auckland-industrial.html (self-contained)
.github/workflows/auckland-industrial.yml   # daily 7am NZ cron → scrape, render, commit
```

The scraper uses a real headless Chromium (Playwright), so JavaScript-rendered
sites work. Extraction is layered — embedded JSON-LD → site selectors →
heuristic card parsing — and **each source is isolated**: if one site is
unreachable or blocks the run, it is shown as `blocked`/`0` on the dashboard and
the others still update. Raw page HTML from each run is uploaded as a CI
artifact (`source-html-*`) for parser tuning.

### Important: anti-bot reality

The large agencies (Colliers, JLL, CBRE, Bayleys) sit behind bot-protection that
can intermittently block automated access from datacenter IPs, including GitHub's
runners. When that happens the affected source shows as **blocked** and a banner
appears on the page; coverage from the remaining sources continues. The CI debug
artifacts make it straightforward to adjust the per-source selectors in
`scraper/sources.py` / `scraper/parse.py` if a site changes its markup.

## Schedule & timezone

GitHub cron is UTC-only and can't follow daylight saving, so the workflow fires
at both **18:00 UTC** (7am NZDT, summer) and **19:00 UTC** (7am NZST, winter); a
guard step lets only the trigger that lands on NZ 07:00 proceed — exactly once
per day, year-round.

**Scheduled runs only fire from the default branch.** After merging to `main`,
use the **Actions → Auckland industrial dashboard → Run workflow** button to
trigger an immediate build (works from any branch) and confirm it end-to-end.

## Enabling the live page (one-time)

Repo **Settings → Pages → Build and deployment → Source: Deploy from a branch →
`main` / root**. The dashboard is then live at the GitHub Pages URL above.

## Local development

```bash
pip install -r scraper/requirements.txt
python -m playwright install chromium
python scraper/scrape.py     # needs open internet to the six sites
python scraper/render.py     # rebuilds auckland-industrial.html
```

`python scraper/render.py` alone (no network) rebuilds the page from the last
saved `data/listings.json`.
