# NAP Business Intel — Project Handover

## What This Does

Scrapes 5 competitor agency profiles on **CommercialRealEstate.com.au** daily at 5:10am AEST. Tracks:
- Active Business for Sale listing counts per competitor
- **New Business listings added each day** (delta tracking via dual-anchor strategy)

**Dashboard:** https://domain-intel.agency360.com.au (Business tab)

---

## Tech Stack

| Layer | Tool | Purpose |
|-------|------|---------|
| Scraping | n8n (self-hosted on Hostinger) | Daily 5:10am AEST automation |
| Proxy (HTML) | BrightData `cre_unlocker` zone | Bypasses CRE Cloudflare protection |
| Proxy (API) | Cloudflare Worker `cre-proxy` | Forwards GraphQL calls (BrightData blocks API endpoints) |
| Database | Supabase (PostgreSQL) | Same project as RS — new tables |
| Frontend | Single HTML file | Updated `index.html` with Business tab |
| Hosting | Cloudflare Workers | Same worker as RS |

---

## Credentials

| Service | Value |
|---------|-------|
| Supabase URL | `https://mdrsxaounqbdtfwdowyn.supabase.co` |
| Supabase anon key | `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1kcnN4YW91bnFiZHRmd2Rvd3luIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY4Mzg4NjIsImV4cCI6MjA5MjQxNDg2Mn0.iK0JQMkiyPlqdpG812ydh9qa1XWArn1Ecn_1ltefKqs` |
| BrightData Bearer token | `487b0598-5eb1-47ef-9d30-30f0d3500840` |
| BrightData Zone | `cre_unlocker` |
| Cloudflare Worker (proxy) | `https://cre-proxy.stan-7a2.workers.dev/` |
| n8n URL | `https://n8n.srv1480405.hstgr.cloud` |
| Dashboard | `domain-intel.agency360.com.au` |

---

## Competitors Tracked

| Key | Slug | Name |
|-----|------|------|
| NAB | `no-agent-property--20869` | No Agent Business (**us**) |
| DB | `direct-business-pty-ltd-34935` | Direct Business |
| FSBO | `for-sale-by-owner-20095` | For Sale By Owner |
| Bonza | `bonza-business-franchise-sales-30533` | Bonza Business & Franchise Sales |
| NI | `network-infinity-31749` | Network Infinity |

CRE agency page format:
`https://www.commercialrealestate.com.au/real-estate-agents/{slug}`

---

## Database Schema (Supabase)

### Table: `cre_agency_stats`
```sql
CREATE TABLE cre_agency_stats (
  id                BIGSERIAL PRIMARY KEY,
  scraped_at        TIMESTAMPTZ,
  scraped_at_melb   TEXT,
  agency_slug       TEXT,
  agency_name       TEXT,
  business_for_sale INTEGER
);
```

### Table: `cre_listing_snapshots`
```sql
CREATE TABLE cre_listing_snapshots (
  id                   BIGSERIAL PRIMARY KEY,
  scraped_at           TIMESTAMPTZ,
  scraped_at_melb      TEXT,
  agency_slug          TEXT,
  total_count          INTEGER,
  total_pages          INTEGER,
  page1_ids            TEXT,
  anchor_id            TEXT,
  anchor_id_2          TEXT,
  new_since_yesterday  INTEGER,
  delta_flag           TEXT
);
```

RLS policies required (run in Supabase SQL Editor):
```sql
ALTER TABLE cre_agency_stats ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow anon insert" ON cre_agency_stats FOR INSERT TO anon WITH CHECK (true);
CREATE POLICY "Allow anon select" ON cre_agency_stats FOR SELECT TO anon USING (true);

ALTER TABLE cre_listing_snapshots ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow anon insert" ON cre_listing_snapshots FOR INSERT TO anon WITH CHECK (true);
CREATE POLICY "Allow anon select" ON cre_listing_snapshots FOR SELECT TO anon USING (true);
```

---

## How CRE Scraping Works

### Page Structure
CRE is a Next.js app. Stats are in `__NEXT_DATA__`:
```
nextData.props.pageProps.data.searchAgencies.pagedSearchResults[0]
  → listingStatsTabs[searchType=0].totalListingsCount  (business count)
  → listingStatsTabs[searchType=0].totalPages
  → firstPageListingsInProfile[].adID  (listing IDs — business-only agencies only)
```

### Agency Types
Two types of agencies require different handling:

| Type | Agencies | Page 1 IDs Source |
|------|----------|-------------------|
| **Business-only** | Direct Business, Bonza, Network Infinity | `firstPageListingsInProfile` in `__NEXT_DATA__` |
| **Mixed** (commercial + business) | NAB, FSBO | Cloudflare Worker GraphQL call |

### Cloudflare Worker (API Proxy)
BrightData's unlocker zone fetches HTML pages fine but blocks API endpoint calls.
The Worker at `cre-proxy.stan-7a2.workers.dev` proxies GraphQL calls to CRE:

```
GET https://cre-proxy.stan-7a2.workers.dev/?agencyId=20869&pageNo=1
```

Returns business listing IDs for the given agency and page.

Worker source code is in `cre-proxy-worker.js` in this package.

### Delta Algorithm
Same dual-anchor strategy as RS (see RS handover doc). Searches up to 3 pages for yesterday's anchor IDs. Listing ID field is `adID` (vs `id` in Domain).

---

## n8n Workflow Architecture

**Two workflows — import Delta Calculator FIRST.**

### Main Workflow — "CRE Business Intel — Daily Competitor Scrape"
Runs at 5:10am AEST (19:10 UTC). 5 separate parallel pipelines, one per competitor.

**Business-only pipeline (Direct Business, Bonza, Network Infinity):**
```
{Agency} URL → Build HTML Body → Fetch HTML (BrightData)
  → Parse HTML → Get Anchors (Supabase)
    → Merge Anchors → Execute Delta → Prep Stats Row → Write Stats
                                    → Prep Snapshot Row → Write Snapshot
```

**Mixed agency pipeline (NAB, FSBO):**
```
{Agency} URL → Build HTML Body → Fetch HTML (BrightData)
  → Parse HTML → Build GQL Body → Fetch GQL P1 (Cloudflare Worker)
    → Parse GQL P1 → Get Anchors (Supabase)
      → Merge Anchors → Execute Delta → Prep Stats Row → Write Stats
                                      → Prep Snapshot Row → Write Snapshot
```

### Sub-workflow — "CRE Business Intel — Delta Calculator"
Same structure as RS Delta Calculator. Searches pages 1→2→3 via Cloudflare Worker.

**IMPORTANT:** After importing the Delta Calculator, copy its workflow ID and paste it into the **Execute Delta** node in the main workflow.

---

## Key Code Patterns

### BrightData HTML Fetch
```javascript
const bdBody = JSON.stringify({
  zone: 'cre_unlocker',
  url: 'https://www.commercialrealestate.com.au/real-estate-agents/' + agency_slug,
  method: 'GET',
  format: 'raw'
});
```

### Cloudflare Worker GQL Call
```javascript
const url = 'https://cre-proxy.stan-7a2.workers.dev/?agencyId=' + agency_id + '&pageNo=1';
// Plain GET — no proxy, no auth needed
```

### Parse GQL Response
```javascript
const raw = typeof d.data === 'string' ? JSON.parse(d.data) : d.data;
const results = raw?.data?.searchListings?.pagedSearchResults || [];
const page1Ids = results.map(r => String(r.adID || '')).filter(Boolean);
```

### Delta Calculator — Read Anchors in Check P2/P3
Always read anchors from `$('Check P1').first().json` — HTTP response overwrites input:
```javascript
const p1out = $('Check P1').first().json;
const anchor1 = String(p1out.anchor1 || '');
const anchor2 = String(p1out.anchor2 || '');
const acc = p1out.accumulated || 0; // P2
const acc = $('Check P2').first().json.accumulated || 0; // P3
```

---

## Dashboard

Single HTML file with **Residential / Business** section switcher in the topbar.
- Residential section: unchanged from RS setup
- Business section: Overview, Trends, Compare, Leaderboard pages
- Business data loads lazily on first click

**Deploy:** Cloudflare → Workers & Pages → restless-scene-c71a → Create new deployment → Upload `index.html`

---

## Files in This Package

| File | Description |
|------|-------------|
| `index.html` | Updated dashboard — upload to Cloudflare to deploy |
| `cre-delta-calculator.json` | Delta Calculator sub-workflow — import FIRST |
| `cre-main-workflow.json` | Main scraper workflow — import after Delta Calculator |
| `cre-proxy-worker.js` | Cloudflare Worker source code |
| `NAP-Business-Intel-Handover.md` | This file |

---

## Common Issues & Solutions

| Issue | Cause | Fix |
|-------|-------|-----|
| BrightData `bad_endpoint` on GQL calls | `cre_unlocker` blocks API endpoints | Use Cloudflare Worker for all GQL calls |
| `page1_ids` empty for NAB/FSBO | Mixed agency — business listings not in `__NEXT_DATA__` | Check Fetch GQL P1 is using Worker URL, not BrightData |
| Merge Anchors reads wrong agency data | `$('Merge IDs')` reference after removing that node | Update reference to `$('Parse HTML')` or `$('Parse GQL P1')` |
| `Always Output Data` needed on Get Anchors | Supabase returns empty array on first run | Enable in Settings tab of Get Anchors node |
| RLS blocking Supabase writes | Tables created without anon policies | Run the RLS SQL above |
| Overflow on second run | Anchor IDs not saved correctly on first run | Check `page1_ids` in snapshot — should have 6 IDs |
