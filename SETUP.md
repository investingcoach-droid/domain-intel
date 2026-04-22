# Agency 360 — Setup Guide

This guide walks you through deploying the dashboard to
`domain-intel.agency360.com.au` step by step.

---

## What you're setting up

```
GitHub repo (domain-intel)
  ├── Stores all the code
  ├── Runs the scraper automatically every day at 5am
  └── Triggers Cloudflare Pages to rebuild the site

Supabase (new project)
  └── Stores all competitor data (the database)

Cloudflare Pages
  └── Hosts the dashboard at domain-intel.agency360.com.au
```

---

## STEP 1 — Create the Supabase project

1. Go to https://supabase.com and sign in
2. Click **New project**
3. Fill in:
   - **Name:** `domain-intel`
   - **Database password:** choose a strong password (save it somewhere)
   - **Region:** Sydney (ap-southeast-2)
4. Click **Create new project** — wait ~2 minutes for it to initialise
5. Once ready, click **SQL Editor** in the left sidebar
6. Copy the entire contents of `supabase_schema.sql` and paste it in
7. Click **Run** — you should see "Success"
8. Now go to **Project Settings → API** (left sidebar)
9. Note down these two values (you'll need them shortly):
   - **Project URL** (looks like `https://abcdefgh.supabase.co`)
   - **anon public** key (long string starting with `eyJ`)
   - **service_role** key (another long string — keep this secret!)

---

## STEP 2 — Create the GitHub repository

1. Go to https://github.com/investingcoach-droid
2. Click the **+** button → **New repository**
3. Fill in:
   - **Repository name:** `domain-intel`
   - **Visibility:** Private (recommended) or Public
   - Leave everything else as default
4. Click **Create repository**
5. You'll see a page with setup instructions — ignore them, just note the URL
   which will be `https://github.com/investingcoach-droid/domain-intel`

### Upload the files

The easiest way without using Terminal:

1. On the empty repository page, click **uploading an existing file**
2. Drag and drop ALL the files from the `domain-intel` folder:
   - `supabase_schema.sql`
   - `dashboard/index.html`
   - `scraper/scraper.py`
   - `.github/workflows/scrape.yml`
   
   **Important:** the folder structure must be preserved. GitHub will ask you
   to confirm — make sure you see the subfolders listed correctly.
3. Write a commit message like "Initial setup" and click **Commit changes**

---

## STEP 3 — Add secrets to GitHub

The scraper needs to connect to Supabase. You store the credentials as
"secrets" in GitHub — they are encrypted and never visible in the code.

1. Go to your repository: `github.com/investingcoach-droid/domain-intel`
2. Click **Settings** (top menu)
3. In the left sidebar, click **Secrets and variables → Actions**
4. Click **New repository secret** and add these two:

   | Name | Value |
   |------|-------|
   | `SUPABASE_URL` | The Project URL from Step 1 (e.g. `https://abcdefgh.supabase.co`) |
   | `SUPABASE_KEY` | The **service_role** key from Step 1 |

5. Click **Add secret** after each one

---

## STEP 4 — Run the scraper for the first time

1. In your GitHub repository, click **Actions** (top menu)
2. You'll see "Daily Competitor Scrape" in the list
3. Click it, then click **Run workflow → Run workflow**
4. Wait about 60 seconds — you'll see a green tick if it succeeded
5. Go to your Supabase project → **Table Editor** and check that
   `agency_stats` and `listing_snapshots` now have rows in them

---

## STEP 5 — Deploy to Cloudflare Pages

1. Go to https://dash.cloudflare.com and sign in
2. Click **Workers & Pages** in the left sidebar
3. Click **Create application → Pages → Connect to Git**
4. Authorise Cloudflare to access your GitHub account if asked
5. Select the `domain-intel` repository
6. Click **Begin setup**
7. Fill in the build settings:
   - **Project name:** `domain-intel`
   - **Production branch:** `main`
   - **Build command:** *(leave blank)*
   - **Build output directory:** `dashboard`
8. Click **Save and Deploy** — Cloudflare will deploy in ~30 seconds

### Add environment variables to Cloudflare

The dashboard needs to read from Supabase:

1. In Cloudflare Pages, click your `domain-intel` project
2. Go to **Settings → Environment variables**
3. Click **Add variable** for each:

   | Variable name | Value |
   |---------------|-------|
   | `SUPABASE_URL` | Your Supabase Project URL |
   | `SUPABASE_ANON_KEY` | The **anon public** key (NOT service_role) |

4. Click **Save**
5. Go to **Deployments** and click **Retry deployment** so it picks up the vars

---

## STEP 6 — Connect your domain

1. Still in your Cloudflare Pages project, go to **Custom domains**
2. Click **Set up a custom domain**
3. Enter: `domain-intel.agency360.com.au`
4. Cloudflare will automatically add the DNS record since agency360.com.au
   is already on Cloudflare
5. Click **Activate domain**
6. Wait 1–2 minutes — then visit https://domain-intel.agency360.com.au

---

## That's it!

Your dashboard is now live. Every day at 5am Melbourne time, GitHub Actions
will run the scraper, write results to Supabase, and your team can visit
https://domain-intel.agency360.com.au to see the latest data.

---

## Sharing with your team

The site is public by default. Just send them the URL:
**https://domain-intel.agency360.com.au**

If you want to password-protect it:
1. In Cloudflare Pages → Settings → **Access policy**
2. Enable Cloudflare Access and add your team's email addresses

---

## Troubleshooting

**Scraper failed (red X in GitHub Actions)**
→ Click on the failed run to see the error message
→ Most common cause: Supabase credentials wrong in Step 3

**Dashboard shows "Could not load data"**
→ Check the Cloudflare environment variables in Step 5
→ Make sure you used the `anon` key, not the `service_role` key

**Domain not working**
→ DNS can take up to 10 minutes to propagate
→ Check Cloudflare DNS tab to confirm the CNAME record was added
