"""
Domain.com.au Competitor Agency Scraper
========================================
Writes results to Supabase via REST API.
No extra libraries needed -- uses Python stdlib urllib only.

Environment variables required (set as GitHub Actions secrets):
  SUPABASE_URL   e.g. https://abcdefgh.supabase.co
  SUPABASE_KEY   The service_role key (not anon) -- allows writes

Usage:
  python scraper.py                    # scrape all competitors
  python scraper.py --competitor nap   # single competitor
  python scraper.py --list             # list configured competitors
"""

import json
import re
import os
import sys
import argparse
import base64
from datetime import datetime, timezone
import urllib.request
import urllib.error
from pathlib import Path
import zoneinfo

# ---------------------------------------------------------------------------
# COMPETITORS
# Format: "short_key": ("full-slug", "Display Name")
# ---------------------------------------------------------------------------

COMPETITORS = {
    "propertynow": ("propertynow-10282",         "Property Now"),
    "buymyplace":  ("buymyplace-17238",           "buymyplace"),
    "fsbo":        ("forsalebyowner-20095",        "For Sale By Owner"),
    "sbho":        ("salebyhomeownercomau-31710",  "SaleByHomeOwner"),
    "nap":         ("noagentproperty-20869",       "No Agent Property"),
    "rentbetter":  ("rentbetter-27499",            "RentBetter"),
    "mta":         ("minustheagent-26625",         "Minus The Agent"),
}

# ---------------------------------------------------------------------------
# SETTINGS
# ---------------------------------------------------------------------------

MELBOURNE_TZ         = zoneinfo.ZoneInfo("Australia/Melbourne")
MAX_PAGINATION_PAGES = 10   # max extra GraphQL pages to fetch for anchor search

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-AU,en;q=0.9",
}

GRAPHQL_URL = "https://www.domain.com.au/graphql"

GRAPHQL_HEADERS = {
    "User-Agent":   HEADERS["User-Agent"],
    "Content-Type": "application/json",
    "Accept":       "application/json",
    "Origin":       "https://www.domain.com.au",
    "Referer":      "https://www.domain.com.au/",
}

# Confirmed via DevTools network capture on 22 Apr 2026
GRAPHQL_QUERY = """query agencyCurrentListings($agencyId: Int!, $page: Int!, $suburbId: String, $propertyType: AgencyApiPropertyType, $sortBy: AgentsearchListingsSortBy, $bedrooms: AgentsearchListingBedrooms) {
  agency(agencyId: $agencyId) {
    id
    agentsearchListingsByAgencyId(page: $page, pageSize: 6, listingStatuses: [SOLD, SALE, LEASE, LEASED], propertyType: $propertyType, sortBy: $sortBy, suburbId: $suburbId, bedrooms: $bedrooms) {
      soldListings { ...AgentListingsTab __typename }
      saleListings { ...AgentListingsTab __typename }
      leaseListings { ...AgentListingsTab __typename }
      leasedListings { ...AgentListingsTab __typename }
      __typename
    }
    __typename
  }
}
fragment AgentListingsTab on AgentsearchListingResults {
  total totalPages
  results { saleType listing { ...CurrentListingCard __typename } __typename }
  __typename
}
fragment CurrentListingCard on AgentsearchListing {
  id listingId listingSlug
  priceDetails { displayPrice __typename }
  bedrooms bathrooms
  soldInfo { soldDate soldPrice soldMethod __typename }
  __typename
}"""

# ---------------------------------------------------------------------------
# SUPABASE CLIENT  (pure stdlib, no supabase-py needed)
# ---------------------------------------------------------------------------

def get_supabase_config() -> tuple[str, str]:
    """Read SUPABASE_URL and SUPABASE_KEY from environment. Exits if missing."""
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_KEY", "")
    if not url or not key:
        print("ERROR: SUPABASE_URL and SUPABASE_KEY environment variables must be set.")
        print("  Local:          export SUPABASE_URL=... && export SUPABASE_KEY=...")
        print("  GitHub Actions: add them as repository secrets.")
        sys.exit(1)
    return url, key


def supabase_insert(table: str, rows: list[dict], url: str, key: str) -> None:
    """Insert one or more rows into a Supabase table via REST API."""
    endpoint = f"{url}/rest/v1/{table}"
    payload  = json.dumps(rows if len(rows) > 1 else rows[0]).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=payload,
        headers={
            "apikey":        key,
            "Authorization": f"Bearer {key}",
            "Content-Type":  "application/json",
            "Prefer":        "return=minimal",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status not in (200, 201):
                raise RuntimeError(f"Supabase insert failed: HTTP {resp.status}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Supabase insert error {e.code}: {body}") from e


def supabase_query(table: str, params: str, url: str, key: str) -> list[dict]:
    """
    Query rows from a Supabase table.
    params is a raw query string, e.g.
        'agency_slug=eq.propertynow-10282&listing_type=eq.sale&order=id.desc&limit=1'
    """
    endpoint = f"{url}/rest/v1/{table}?{params}"
    req = urllib.request.Request(
        endpoint,
        headers={
            "apikey":        key,
            "Authorization": f"Bearer {key}",
            "Accept":        "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Supabase query error {e.code}: {body}") from e


# ---------------------------------------------------------------------------
# FETCH -- Domain HTML page
# ---------------------------------------------------------------------------

def fetch_agency_page(slug: str) -> dict:
    """Fetch the agency HTML page and return parsed __NEXT_DATA__ JSON."""
    url = f"https://www.domain.com.au/real-estate-agencies/{slug}/"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} fetching {url}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network error fetching {url}: {e.reason}") from e

    match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        html, re.DOTALL,
    )
    if not match:
        raise RuntimeError(f"No __NEXT_DATA__ found for slug: {slug}")
    return json.loads(match.group(1))


# ---------------------------------------------------------------------------
# FETCH -- Domain GraphQL (pagination)
# ---------------------------------------------------------------------------

def fetch_graphql_page(agency_id: int, page: int) -> dict:
    """Fetch a paginated listings page via the Domain GraphQL API."""
    payload = json.dumps({
        "operationName": "agencyCurrentListings",
        "variables":     {"agencyId": agency_id, "page": page},
        "query":         GRAPHQL_QUERY,
    }).encode("utf-8")

    req = urllib.request.Request(
        GRAPHQL_URL, data=payload, headers=GRAPHQL_HEADERS, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"GraphQL HTTP {e.code} (agencyId={agency_id}, page={page})") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"GraphQL network error: {e.reason}") from e

    if "errors" in data:
        raise RuntimeError(f"GraphQL error: {data['errors'][0].get('message','unknown')}")

    listings = (
        data.get("data", {}).get("agency", {}).get("agentsearchListingsByAgencyId")
    )
    if listings is None:
        raise RuntimeError(f"Unexpected GraphQL response for agencyId={agency_id}")
    return listings


def extract_ids_from_graphql(listings: dict, listing_type: str) -> list[str]:
    """Extract ordered listing IDs from a GraphQL response dict."""
    cat_map = {
        "sale":   "saleListings",
        "sold":   "soldListings",
        "lease":  "leaseListings",
        "leased": "leasedListings",
    }
    cat = listings.get(cat_map[listing_type], {})
    return [
        r["listing"]["id"]
        for r in cat.get("results", [])
        if r.get("listing", {}).get("id")
    ]


# ---------------------------------------------------------------------------
# PARSE -- __NEXT_DATA__
# ---------------------------------------------------------------------------

def parse_agency_data(next_data: dict, slug: str) -> dict:
    """Extract stats and page-1 listings from __NEXT_DATA__ Apollo state."""
    page_props = next_data.get("props", {}).get("pageProps", {})
    apollo     = page_props.get("__APOLLO_STATE__", {})
    agency_id  = page_props.get("agencyId")

    if not agency_id:
        raise RuntimeError(f"No agencyId in page data for: {slug}")

    agency_b64 = base64.b64encode(f"Agency:{agency_id}".encode()).decode()
    agency     = apollo.get(f"Agency:{agency_b64}")
    if not agency:
        raise RuntimeError(f"Agency key not found in Apollo state for: {slug}")

    agency_name = agency.get("name", slug).strip()

    stats = apollo.get(f"AgencyStatistics:{agency_id}-agency-statistics", {})
    summary = {
        "agency_name": agency_name,
        "agency_id":   agency_id,
        "for_sale":    stats.get("forSale"),
        "sold_total":  stats.get("soldTotal"),
        "for_rent":    stats.get("forRent"),
        "leased":      stats.get("leased"),
    }

    listings_key = next(
        (k for k in agency if k.startswith("agentsearchListingsByAgencyId(")), None
    )
    listings_data = {}
    if listings_key:
        raw = agency[listings_key]
        for cat_key, ltype in [
            ("saleListings",   "sale"),
            ("soldListings",   "sold"),
            ("leaseListings",  "lease"),
            ("leasedListings", "leased"),
        ]:
            cat = raw.get(cat_key, {})
            ids = [
                r["listing"]["__ref"].split(":")[-1]
                for r in cat.get("results", [])
                if r.get("listing", {}).get("__ref")
            ]
            listings_data[ltype] = {
                "total":       cat.get("total", 0),
                "total_pages": cat.get("totalPages", 0),
                "page1_ids":   ids,
                "anchor_id":   ids[0] if ids else None,
            }

    return {"summary": summary, "listings": listings_data}


# ---------------------------------------------------------------------------
# DELTA CALCULATION
# ---------------------------------------------------------------------------

def calculate_delta(
    agency_slug:       str,
    agency_id:         int,
    current_page1_ids: list[str],
    sb_url:            str,
    sb_key:            str,
    verbose:           bool = True,
) -> tuple[int | None, str | None]:
    """
    Return (delta, flag) using dual-anchor strategy.

    - Queries yesterday's anchor_id (A) and anchor_id_2 (B) from Supabase
    - Searches pages 1-MAX_PAGINATION_PAGES for A first, then B
    - Position of found anchor = number of new listings
    - Returns (delta, None) on success
    - Returns (None, 'overflow') if neither anchor found
    - Returns (None, None) on first run
    """
    rows = supabase_query(
        "listing_snapshots",
        f"agency_slug=eq.{agency_slug}&listing_type=eq.sale"
        f"&order=id.desc&limit=1&select=anchor_id,anchor_id_2",
        sb_url, sb_key,
    )
    if not rows or not rows[0].get("anchor_id"):
        return None, None   # first run

    anchor1 = rows[0].get("anchor_id")
    anchor2 = rows[0].get("anchor_id_2")

    def search_anchor(anchor: str) -> int | None:
        """Search for anchor across pages 1-MAX_PAGINATION_PAGES. Returns position or None."""
        if not anchor:
            return None
        # Check page 1 (already fetched)
        if anchor in current_page1_ids:
            return current_page1_ids.index(anchor)
        # Paginate via GraphQL
        accumulated = list(current_page1_ids)
        for page in range(2, MAX_PAGINATION_PAGES + 2):
            try:
                gql      = fetch_graphql_page(agency_id, page)
                page_ids = extract_ids_from_graphql(gql, "sale")
            except RuntimeError as e:
                if verbose:
                    print(f"      GraphQL error page {page}: {e}")
                return None
            if not page_ids:
                return None
            if anchor in page_ids:
                pos = page_ids.index(anchor)
                total = len(accumulated) + pos
                if verbose:
                    print(f"      Found anchor {anchor} on page {page} pos {pos} → delta={total}")
                return total
            accumulated.extend(page_ids)
        return None

    # Try anchor1 first
    if verbose:
        print(f"      Searching for anchor1={anchor1}")
    delta = search_anchor(anchor1)
    if delta is not None:
        return delta, None

    # Try anchor2
    if anchor2:
        if verbose:
            print(f"      anchor1 not found, trying anchor2={anchor2}")
        delta = search_anchor(anchor2)
        if delta is not None:
            return delta, None

    if verbose:
        print(f"      Neither anchor found in {MAX_PAGINATION_PAGES} pages → overflow")
    return None, "overflow"
            if verbose:
                print(f"      GraphQL error on page {page}: {e}")
            return None

        page_ids = extract_ids_from_graphql(gql, listing_type)

        if not page_ids:
            if verbose:
                print(f"      No results on page {page}, anchor may have expired.")
            return None

        if prev_anchor in page_ids:
            pos       = page_ids.index(prev_anchor)
            total_new = len(accumulated) + pos
            if verbose:
                print(f"      Found anchor on page {page} pos {pos}. Total new: {total_new}")
            return total_new

        accumulated.extend(page_ids)
        if verbose:
            print(f"      Page {page}: not found yet ({len(accumulated)} IDs checked)")



# ---------------------------------------------------------------------------
# MAIN SCRAPE
# ---------------------------------------------------------------------------

def scrape_agency(slug: str, sb_url: str, sb_key: str, verbose: bool = True) -> None:
    """Scrape one agency and write results to Supabase."""
    if verbose:
        print(f"\n{'─' * 54}")
        print(f"  Scraping: {slug}")

    next_data  = fetch_agency_page(slug)
    data       = parse_agency_data(next_data, slug)
    summary    = data["summary"]
    agency_id  = summary["agency_id"]

    now_utc  = datetime.now(timezone.utc).isoformat()
    now_melb = datetime.now(MELBOURNE_TZ).strftime("%Y-%m-%d %H:%M:%S")

    # Write stats row
    supabase_insert("agency_stats", [{
        "scraped_at":      now_utc,
        "scraped_at_melb": now_melb,
        "agency_slug":     slug,
        "agency_name":     summary["agency_name"],
        "for_sale":        summary["for_sale"],
        "sold_total":      summary["sold_total"],
        "for_rent":        summary["for_rent"],
        "leased":          summary["leased"],
    }], sb_url, sb_key)

    if verbose:
        print(f"  ✓ {summary['agency_name']}  (agencyId={agency_id})")
        print(
            f"    For Sale: {summary['for_sale']:>4}  |  Sold: {summary['sold_total']:>4}  "
            f"|  For Rent: {summary['for_rent']:>4}  |  Leased: {summary['leased']:>4}"
        )

    # Write listing snapshot — For Sale only, dual anchor strategy
    ldata  = data["listings"].get("sale", {})
    ids    = ldata.get("page1_ids", [])
    delta, flag = calculate_delta(slug, agency_id, ids, sb_url, sb_key, verbose=verbose)
    supabase_insert("listing_snapshots", [{
        "scraped_at":          now_utc,
        "scraped_at_melb":     now_melb,
        "agency_slug":         slug,
        "listing_type":        "sale",
        "total_count":         ldata.get("total", 0),
        "page1_ids":           json.dumps(ids),
        "anchor_id":           ids[0] if ids else None,
        "anchor_id_2":         ids[1] if len(ids) > 1 else None,
        "new_since_yesterday": delta,
        "delta_flag":          flag,
    }], sb_url, sb_key)
    if verbose:
        d_str = f"+{delta}" if delta is not None else f"null ({flag or 'first run'})"
        print(f"    [sale  ] total={ldata.get('total',0):5}  anchor={ids[0] if ids else None}  delta={d_str}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def resolve_slug(arg: str) -> str:
    if arg in COMPETITORS:
        return COMPETITORS[arg][0]
    if arg in {s for s, _ in COMPETITORS.values()}:
        return arg
    raise ValueError(f"Unknown competitor '{arg}'. Use --list to see options.")


def list_competitors() -> None:
    print(f"\n{'Key':<14} {'Slug':<36} Display Name")
    print("-" * 70)
    for key, (slug, name) in COMPETITORS.items():
        print(f"{key:<14} {slug:<36} {name}")


def main():
    parser = argparse.ArgumentParser(description="Domain.com.au competitor scraper")
    parser.add_argument("--competitor", metavar="KEY_OR_SLUG",
                        help="Scrape a single competitor")
    parser.add_argument("--list", action="store_true",
                        help="List all configured competitors")
    args = parser.parse_args()

    if args.list:
        list_competitors()
        return

    sb_url, sb_key = get_supabase_config()

    slugs = [resolve_slug(args.competitor)] if args.competitor \
        else [s for s, _ in COMPETITORS.values()]

    errors = 0
    for slug in slugs:
        try:
            scrape_agency(slug, sb_url, sb_key)
        except Exception as e:
            print(f"\n  ERROR -- {slug}: {e}")
            errors += 1

    print(f"\n{'─' * 54}")
    print(f"  Done. {len(slugs) - errors}/{len(slugs)} succeeded.")
    if errors:
        print(f"  {errors} error(s) above.")


if __name__ == "__main__":
    main()
