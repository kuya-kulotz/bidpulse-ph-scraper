# BidPulse PH — scraper

Collects public Pag-IBIG Online Public Auction listings so the BidPulse PH app can filter them and send alerts.

**Unofficial and independent.** This project is not affiliated with, authorized by, or endorsed by Pag-IBIG Fund.

How it behaves:
- One request at a time, with 3–5 s between requests.
- The User-Agent identifies the bot and gives a contact.
- No bypassing of any access control.
- Title and survey numbers are dropped and never stored.

To request changes or removal, open an issue or contact the address set in `CONTACT`.

## Run locally (dry run, no database)

```bash
python test_scrape.py
ONLY_CITIES="LAS PI,IMUS" python scrape.py   # writes out/listings.json and status/last_run.json
```

Python 3.12 or newer. Scraping uses only the standard library. Sending push notifications needs `pip install -r requirements.txt` (pywebpush).

`test_match.py` checks the alert matching. It must agree with `matches()` in `app/src/filters.ts`.

## Production setup

1. Create a Supabase project. In its SQL editor, run `supabase/migrations/0001_listings.sql`, then `0002_alerts.sql`.
2. Generate push keys: `npx web-push generate-vapid-keys`.
   - The **public** key goes to the app as `VITE_VAPID_PUBLIC_KEY`.
   - The **private** key goes here as a secret.
3. In this GitHub repo:
   - Add **Secrets** `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` and `VAPID_PRIVATE_KEY`.
   - Add **Variables** `CONTACT` (e.g. an email address) and `VAPID_SUBJECT` (`mailto:you@example.com`).
4. Go to Actions → scrape → **Run workflow**. Put a city in "only_cities" for a quick first test, then run it with that field blank.

The workflow runs on Tue, Thu and Sat at 02:00 PHT. If the site blocks the scraper (HTTP 403/429), changes its data shape, or fails 3 times in a row, the run aborts and fails, and GitHub emails you.
