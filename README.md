# Agency 360 — Domain Intel
## Competitor Intelligence Dashboard

**Live URL:** https://domain-intel.agency360.com.au
**Last updated:** 23 Apr 2026

---

## What this project does

Scrapes 7 competitor agency profiles on Domain.com.au daily at 5am AEST and displays the data in a live dashboard. Tracks:

- Active For Sale, Sold, For Rent, Leased listing counts (12-month window)
- New For Sale listings added each day (delta tracking via anchor ID strategy)
- Historical trends and competitor comparisons

---

## Competitors tracked

| Key | Slug | Platform | Notes |
|-----|------|----------|-------|
| PN | propertynow-10282 | Property Now | Competitor |
| BMP | buymyplace-17238 | buymyplace | Competitor |
| FSBO | forsalebyowner-20095 | For Sale By Owner | Competitor |
| SBHO | salebyhomeownercomau-31710 | SaleByHomeOwner | Competitor |
| NAP | noagentproperty-20869 | No Agent Property | **Us** |
| RB | rentbetter-27499 | RentBetter | Competitor |
| MTA | minustheagent-26625 | Minus The Agent | Competitor |

---

## Architecture

```
n8n (5am AEST daily)
  └── 7 × HTTP Request → BrightData (rea_unlocker zone)
        └── Fetches domain.com.au agency pages
              └── Code node parses __NEXT_DATA__ JSON
                    ├── HTTP POST → Supabase agency_stats
                    └── HTTP POST → Supabase listing_snapshots

Supabase (database)
  ├── agency_stats        — daily stats per competitor
  └── listing_snapshots   — daily anchor + delta per competitor

Cloudflare Workers (hosting)
  └── domain-intel.agency360.com.au
        └── Serves dashboard/index.html
              └── Reads live data from Supabase on page load
```

---

## Files in this project

### `/dashboard/index.html`
The live dashboard — single HTML file, no build step.
- 4 pages: Overview, Trends, Compare, Leaderboard
- Reads from Supabase using the anon key (read-only, safe to expose)
- Supabase credentials hardcoded directly (anon key only)
- Deployed to Cloudflare Workers → domain-intel.agency360.com.au

### `/scraper/scraper.py`
Python scraper — alternative to n8n, runs from command line.
- Uses `SUPABASE_URL` and `SUPABASE_KEY` environment variables
- Includes full GraphQL pagination logic for anchor search (pages 2–10)
- Currently NOT used in production (n8n workflow is used instead)
- Kept as backup and for local testing

### `/.github/workflows/scrape.yml`
GitHub Actions workflow — NOT currently used (Domain.com.au blocks GitHub Actions IPs).
- Kept for reference
- Would need a proxy/residential IP to work

### `/supabase_schema.sql`
Run once in Supabase SQL Editor to create the tables.
Already executed — tables exist in production.

### `/domain-intel-n8n.json` (in outputs root)
The n8n workflow JSON — import this into n8n to recreate the workflow.
- 36 nodes total
- 7 hardcoded Fetch nodes (one per competitor)
- Uses BrightData `rea_unlocker` zone to bypass Cloudflare protection
- Credentials hardcoded (BrightData token + Supabase service_role key)

---

## Credentials (keep secure)

| Service | Credential | Notes |
|---------|-----------|-------|
| Supabase | Project URL: `https://mdrsxaounqbdtfwdowyn.supabase.co` | Safe to share |
| Supabase | anon key: `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...role:anon` | In dashboard HTML |
| Supabase | service_role key: `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...role:service_role` | In n8n + scraper only |
| BrightData | Bearer token: `487b0598-5eb1-47ef-9d30-30f0d3500840` | In n8n workflow |
| BrightData | Zone: `rea_unlocker` | Works for both REA and Domain.com.au |

---

## Database schema

### `agency_stats`
One row per competitor per daily scrape.
| Column | Description |
|--------|-------------|
| scraped_at | UTC timestamp |
| scraped_at_melb | Melbourne local time string |
| agency_slug | e.g. `propertynow-10282` |
| agency_name | Display name |
| for_sale | Active For Sale listings (12mo window) |
| sold_total | Sold transactions (12mo) |
| for_rent | Active For Rent listings (12mo) |
| leased | Completed leases (12mo) |

### `listing_snapshots`
One row per competitor per listing type per daily scrape.
Currently stores 4 types (sale, sold, lease, leased) — **pending team decision to simplify to sale-only**.

| Column | Description |
|--------|-------------|
| agency_slug | Competitor slug |
| listing_type | 'sale', 'sold', 'lease', or 'leased' |
| total_count | Total listings of this type |
| page1_ids | JSON array of listing IDs from page 1 |
| anchor_id | Newest listing ID (used for next day delta) |
| new_since_yesterday | New For Sale listings since previous anchor |

---

## How the delta (new listings) tracking works

```
Day 1 (first run):
  Store page 1 listing IDs → anchor_id = newest ID
  new_since_yesterday = null

Day 2 (5am run):
  Fetch page 1 (6 listings, newest first)
  
  Is yesterday's anchor in page 1?
  YES → position = number of new listings today
  NO  → fetch page 2 via GraphQL API (domain.com.au/graphql)
        still not found? → page 3... up to page 10
        covers up to ~60 new listings before giving up (stores null)

GraphQL endpoint confirmed: domain.com.au/graphql
Operation: agencyCurrentListings
Variables: { agencyId: <int>, page: <int> }
```

---

## Historical data loaded

Data from spreadsheet loaded into `listing_snapshots` for Apr 15–22, 2026:

| Date | NAP | FSBO | BMP | PN | SBHO | MTA | RB |
|------|-----|------|-----|----|------|-----|----|
| Apr 15 | 1 | 0 | 2 | 7 | 4 | 4 | 1 |
| Apr 16 | 1 | 13 | 6 | 6 | 3 | 2 | 1 |
| Apr 17 | 0 | 7 | 1 | 5 | 0 | 0 | 1 |
| Apr 18 | 2 | 2 | 1 | 3 | 1 | 0 | 0 |
| Apr 19 | 1 | 11 | 3 | 2 | 3 | 0 | 0 |
| Apr 20 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Apr 21 | 1 | 5 | 5 | 6 | 3 | 1 | 1 |
| Apr 22 | 1 | null | 5 | 3 | 5 | 1 | 0 |

Apr 22 anchor IDs (used as starting point for future delta):
- NAP: `2020781432`
- FSBO: `2020782883`
- BMP: `2019557474`
- PN: `2020782461`
- SBHO: `2020780500`
- MTA: `2020775570`
- RB: `2020777055`

---

## Pending decisions (discuss with team)

### 1. Simplify listing_snapshots to For Sale only

**Current:** 4 rows per competitor per day (sale, sold, lease, leased) = 28 rows/day
**Proposed:** 1 row per competitor per day (sale only) = 7 rows/day

Rationale: We only calculate delta for For Sale. The other 3 types store anchors
we never use. The 4 summary stats (for_sale, sold, for_rent, leased) are already
captured in agency_stats — no need to duplicate in snapshots.

**Action needed:** Team approval → update n8n Prepare Snapshot Rows node + scraper.py

### 2. Add GraphQL pagination to n8n workflow (Option A)

**Current:** n8n workflow only checks page 1 (6 listings) for the anchor.
If more than 6 new listings appeared since yesterday, delta = null.

**Proposed:** Add GraphQL pagination nodes to n8n — fetch pages 2, 3... until
anchor is found, same logic as scraper.py already implements.

**Why it matters:** On busy days (FSBO had 13 new listings on Apr 16),
page 1 won't contain the anchor and delta will be null.

**GraphQL details already confirmed:**
- Endpoint: `https://www.domain.com.au/graphql`
- Method: POST via BrightData (same rea_unlocker zone)
- Operation: `agencyCurrentListings`
- Variables: `{ agencyId: <int>, page: <int> }`
- Full query string: documented in scraper.py

**Action needed:** Team approval → add pagination loop to n8n workflow

---

## n8n workflow — how to update

The workflow is in `domain-intel-n8n.json`. To make changes:
1. In n8n, open the Domain Intel workflow
2. Make changes manually OR
3. Delete and re-import the JSON after updating it

The workflow runs at **5am AEST daily** (19:00 UTC).
Manually trigger via: n8n → Domain Intel workflow → Execute workflow

---

## How to redeploy the dashboard

1. Edit `dashboard/index.html`
2. Go to dash.cloudflare.com → Workers & Pages → restless-scene-c71a
3. Click Create new deployment → Upload files
4. Upload the new index.html
5. Click Deploy
