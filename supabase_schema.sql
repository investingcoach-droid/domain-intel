-- ============================================================
-- Domain Intel — Supabase Schema
-- Run this once in the Supabase SQL Editor to create tables.
-- ============================================================

-- Daily summary stats per competitor
CREATE TABLE IF NOT EXISTS agency_stats (
    id              BIGSERIAL PRIMARY KEY,
    scraped_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    scraped_at_melb TEXT NOT NULL,
    agency_slug     TEXT NOT NULL,
    agency_name     TEXT,
    for_sale        INTEGER,
    sold_total      INTEGER,
    for_rent        INTEGER,
    leased          INTEGER
);

-- Daily listing snapshots + delta
CREATE TABLE IF NOT EXISTS listing_snapshots (
    id                  BIGSERIAL PRIMARY KEY,
    scraped_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    scraped_at_melb     TEXT NOT NULL,
    agency_slug         TEXT NOT NULL,
    listing_type        TEXT NOT NULL,   -- 'sale', 'sold', 'lease', 'leased'
    total_count         INTEGER,
    page1_ids           TEXT,            -- JSON array of listing IDs from page 1
    anchor_id           TEXT,            -- newest listing ID (used for delta)
    new_since_yesterday INTEGER          -- null on first run or overflow
);

-- Indexes for fast dashboard queries
CREATE INDEX IF NOT EXISTS idx_agency_stats_slug_scraped
    ON agency_stats (agency_slug, scraped_at DESC);

CREATE INDEX IF NOT EXISTS idx_listing_snapshots_slug_type_scraped
    ON listing_snapshots (agency_slug, listing_type, scraped_at DESC);

-- Read-only access for the dashboard (anon key)
-- The dashboard uses the anon key which is public — these policies
-- allow SELECT only, no inserts or deletes from the browser.
ALTER TABLE agency_stats     ENABLE ROW LEVEL SECURITY;
ALTER TABLE listing_snapshots ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow public read on agency_stats"
    ON agency_stats FOR SELECT USING (true);

CREATE POLICY "Allow public read on listing_snapshots"
    ON listing_snapshots FOR SELECT USING (true);
