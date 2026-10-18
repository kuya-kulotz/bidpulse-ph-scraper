"""BidPulse PH scraper: sweeps Pag-IBIG OPA listings city by city into Supabase.

Env:
  SUPABASE_URL, SUPABASE_SERVICE_KEY  - if unset, runs dry and writes out/listings.json
  CONTACT                             - email/URL put in the User-Agent
  MAX_MINUTES                         - stop cleanly after this (default 300)
  ONLY_CITIES                         - comma list of city-name substrings, for testing
"""
import base64
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent

# Local runs: read scraper/.env (KEY=value lines). Real env vars win, so CI secrets are untouched.
if (HERE / ".env").exists():
    for line in (HERE / ".env").read_text(encoding="utf-8").splitlines():
        k, sep, v = line.partition("=")
        if sep and not k.strip().startswith("#"):
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

BASE = "https://www.pagibigfundservices.com/OnlinePublicAuction/ListofProperties/"
UA = f"BidPulsePH/1.0 (unofficial listings alert tool; contact: {os.getenv('CONTACT', 'see repo README')})"
REQUIRED = ("ropa_id", "prop_type", "min_sellprice", "city_muni", "occupancy")
HONORIFIC = re.compile(r"\b(MR|MRS|MS|SPS|ATTY|DR|ENGR)\.?\s|\bOCCUPIED BY\b|\bHEIRS? OF\b", re.I)


class Abort(Exception):
    """Stop the whole run: source is blocking us or changed shape."""


def get_json(path, params):
    url = BASE + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (403, 429):
                raise Abort(f"HTTP {e.code} on {path}: source is blocking or rate-limiting us")
            err = e
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            err = e
        if attempt == 1:
            time.sleep(30)
    raise err


def polite_sleep():
    time.sleep(random.uniform(3, 5))


def load_locations():
    """region -> province -> city tree; falls back to the committed cache."""
    cache = HERE / "locations.json"
    loc = lambda grp, r="", p="": get_json("LoadLocations", {"grpid": grp, "regionid": r, "provinceid": p, "cityid": "", "brgyid": ""})
    try:
        cities = []
        for reg in loc(1):
            polite_sleep()
            for prov in loc(2, reg["result_column0"]):
                polite_sleep()
                for c in loc(3, reg["result_column0"], prov["result_column0"]):
                    cities.append({"region_id": reg["result_column0"], "region": reg["result_column1"].strip(),
                                   "province_id": prov["result_column0"], "province": prov["result_column1"].strip(),
                                   "city_id": c["result_column0"], "city": c["result_column1"].strip()})
        if not cities:
            raise ValueError("empty location tree")
        cache.write_text(json.dumps(cities, ensure_ascii=False, indent=1), encoding="utf-8")
        return cities
    except Abort:
        raise
    except Exception as e:
        print(f"location refresh failed ({e}); using cache", file=sys.stderr)
        return json.loads(cache.read_text(encoding="utf-8"))


def num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f or None  # source uses 0 for "not applicable"


def latlng(s):
    try:
        lat, lng = (float(x) for x in (s or "").split(","))
    except ValueError:
        return None, None
    return (lat, lng) if 4 <= lat <= 22 and 116 <= lng <= 127 else (None, None)  # PH bounding box


def pht(s):
    return f"{s}+08:00" if s else None  # source times are Philippine local time


def prop_group(t):
    t = (t or "").lower()
    if "parking" in t:
        return "parking"
    if "condo" in t:
        return "condo"
    if "lot only" in t or t == "lot":
        return "lot"
    if "town" in t:
        return "townhouse"
    if re.search(r"attached|detached|duplex|plex\b|\brow|\bhouse\b|bungalow", t):
        return "house"
    return "other"


def normalize(r, city, seen_at):
    missing = [k for k in REQUIRED if k not in r]
    if missing:
        raise Abort(f"listing schema changed, missing {missing}")
    remarks = (r.get("remarks") or "").strip() or None
    if remarks and HONORIFIC.search(remarks):
        print(f"remarks dropped (possible personal name) for {r['ropa_id']}", file=sys.stderr)
        remarks = None
    lat, lng = latlng(r.get("ins_remarks"))
    # Deliberately not kept: tct_cct_no / survey_no (can identify prior owners), internal flags.
    return {
        "ropa_id": r["ropa_id"],
        "batch_no": r.get("batch_no"),
        "disposal_type": r.get("disposal_type"),
        "prop_type": r["prop_type"],
        "prop_group": prop_group(r["prop_type"]),
        "occupancy": r["occupancy"],
        "remarks": remarks,
        "address": (r.get("prop_location") or "").strip(),
        "subdivision": (r.get("subdivision") or "").strip() or None,
        "city": city["city"],
        "city_id": city["city_id"],
        "province_id": city["province_id"],
        "province": city.get("province"),
        "region_id": city["region_id"],
        "region": city.get("region"),
        "lot_area": num(r.get("lot_area")),
        "floor_area": num(r.get("floor_area")),
        "min_price": num(r["min_sellprice"]),
        "lat": lat,
        "lng": lng,
        "bid_start": pht(r.get("start_datetime")),
        "bid_end": pht(r.get("end_datetime")),
        "opening_at": pht(r.get("opening_datetime")),
        "office_name": r.get("handling_hbc"),
        "office_email": r.get("email_hbc"),
        "office_phone": r.get("contact_hbc"),
        "last_seen_at": seen_at,
        "is_active": True,
    }


def fetch_city(c):
    data = get_json("Load_SearchListProperties_COPA", {
        "flag": 1, "region": c["region_id"], "province": c["province_id"], "city_muni": c["city"],
        "prop_type": "", "range_from": "", "range_to": "", "lot_from": "", "lot_to": "",
        "floor_from": "", "floor_to": "", "occupancy": ""})
    if not isinstance(data, dict) or not isinstance(data.get("data"), list):
        raise Abort(f"listing response shape changed for {c['city']}: {str(data)[:200]}")
    return data["data"]


def supabase(method, path, body=None, prefer=None):
    url, key = os.environ["SUPABASE_URL"].rstrip("/"), os.environ["SUPABASE_SERVICE_KEY"]
    headers = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        headers["Prefer"] = prefer
    req = urllib.request.Request(f"{url}/rest/v1/{path}", method=method, headers=headers,
                                 data=json.dumps(body).encode() if body is not None else None)
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
        return json.loads(raw) if raw else None


def save(listings, run, complete, failed_city_ids):
    for i in range(0, len(listings), 500):
        supabase("POST", "listings?on_conflict=ropa_id", listings[i:i + 500],
                 "resolution=merge-duplicates,return=minimal")
    since = urllib.parse.quote(run["started_at"])
    new = set()  # first seen, or moved to a new batch / sale type (listed_at is reset by a DB trigger)
    for off in range(0, 10**6, 1000):  # PostgREST caps responses at 1000 rows
        page = supabase("GET", f"listings?select=ropa_id&listed_at=gte.{since}&order=ropa_id&limit=1000&offset={off}")
        new.update(r["ropa_id"] for r in page)
        if len(page) < 1000:
            break
    run["new_listings"] = len(new)
    if complete:  # only a full sweep can tell us a listing is gone
        q = f"listings?is_active=is.true&last_seen_at=lt.{since}"
        if failed_city_ids:
            q += f"&city_id=not.in.({','.join(failed_city_ids)})"
        gone = supabase("PATCH", q, {"is_active": False}, "return=representation")
        run["deactivated"] = len(gone or [])
    run["pushes_sent"] = notify([l for l in listings if l["ropa_id"] in new])
    supabase("POST", "scrape_runs", run, "return=minimal")


GROUP_LABEL = {"house": "House & Lot", "townhouse": "Townhouse", "condo": "Condo", "lot": "Lot",
               "parking": "Parking", "other": "Property"}


def bid_status(l, now):
    """'upcoming' | 'open' | 'closed' | None. Mirror of bidStatus() in app/src/filters.ts."""
    if not l.get("bid_start") or not l.get("bid_end"):
        return None
    if now < datetime.fromisoformat(l["bid_start"]):
        return "upcoming"
    return "open" if now <= datetime.fromisoformat(l["bid_end"]) else "closed"


def matches(l, f, now=None):
    """Mirror of matches() in app/src/filters.ts: keep the two in sync."""
    inf = float("inf")
    text = f"{l.get('subdivision') or ''} {l.get('address') or ''}".lower()
    return ((not f.get("cities") or l["city_id"] in f["cities"])
            and (not f.get("disposal") or l.get("disposal_type") in f["disposal"])
            and (not f.get("status") or bid_status(l, now or datetime.now(timezone.utc)) in f["status"])
            and not any(k.strip() and k.strip().lower() in text for k in f.get("exclude") or [])
            and (not f.get("groups") or l["prop_group"] in f["groups"])
            and (not f.get("occupancy") or l["occupancy"] in f["occupancy"])
            and (f.get("priceMin") is None or (l["min_price"] or 0) >= f["priceMin"])
            and (f.get("priceMax") is None or (l["min_price"] or inf) <= f["priceMax"])
            and (f.get("lotMin") is None or (l["lot_area"] or 0) >= f["lotMin"])
            and (f.get("floorMin") is None or (l["floor_area"] or 0) >= f["floorMin"]))


def push_payload(hits):
    top = min(hits, key=lambda l: l["min_price"] or float("inf"))
    city = top["city"].title().replace("City Of ", "")
    price = f"₱{top['min_price']:,.0f}" if top["min_price"] else ""
    desc = f"{top['occupancy']} {GROUP_LABEL[top['prop_group']].lower()}, {city} {price}".strip()
    more = f" + {len(hits) - 1} more" if len(hits) > 1 else ""
    n = len(hits)
    return {"title": f"{n} new match{'es' if n > 1 else ''} for your alerts", "body": desc + more, "url": "/#/alerts"}


def notify(new_rows):
    """One summarized push per device whose alerts match any new listing. Returns pushes sent."""
    if not new_rows:
        return 0
    from pywebpush import WebPushException, webpush  # only needed in production runs
    devices = supabase("GET", "devices?select=token,push_subscription,alerts(filters)")
    sent = 0
    for d in devices:
        hits = [l for l in new_rows if any(matches(l, a["filters"]) for a in d["alerts"])]
        if not hits:
            continue
        try:
            webpush(d["push_subscription"], json.dumps(push_payload(hits)), ttl=86400,
                    vapid_private_key=os.environ["VAPID_PRIVATE_KEY"],
                    vapid_claims={"sub": os.environ["VAPID_SUBJECT"]})  # fresh dict: webpush mutates it
            sent += 1
            supabase("PATCH", f"devices?token=eq.{d['token']}", {"last_push_at": datetime.now(timezone.utc).isoformat()})
        except WebPushException as e:
            if e.response is not None and e.response.status_code in (404, 410):  # unsubscribed / uninstalled
                supabase("DELETE", f"devices?token=eq.{d['token']}")
            else:
                print(f"push failed for a device: {e}", file=sys.stderr)
    return sent


def main():
    started = datetime.now(timezone.utc)
    deadline = time.monotonic() + 60 * float(os.getenv("MAX_MINUTES", "300"))
    run = {"started_at": started.isoformat(), "cities_total": 0, "cities_ok": 0, "cities_failed": 0,
           "listings": 0, "new_listings": None, "deactivated": None, "pushes_sent": None, "status": "running", "error": None}
    listings, failed, consecutive = {}, [], 0
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if os.getenv("SUPABASE_URL") and key.startswith("eyJ"):  # legacy JWT key: check its role before sweeping
        payload = key.split(".")[1]
        role = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))).get("role")
        if role != "service_role":
            sys.exit(f"SUPABASE_SERVICE_KEY has role '{role}'. Use the service_role key "
                     "(Supabase > Project Settings > API Keys), not the anon key.")
    try:
        cities = load_locations()
        only = [s.strip().upper() for s in os.getenv("ONLY_CITIES", "").split(",") if s.strip()]
        if only:
            cities = [c for c in cities if any(s in c["city"].upper() for s in only)]
        run["cities_total"] = len(cities)
        for i, c in enumerate(cities):
            if time.monotonic() > deadline:
                run["status"] = "partial: time budget reached"
                break
            if i:
                polite_sleep()
            try:
                for r in fetch_city(c):
                    listings[r["ropa_id"]] = normalize(r, c, run["started_at"])
                run["cities_ok"] += 1
                consecutive = 0
            except Abort:
                raise
            except Exception as e:
                failed.append(c["city_id"])
                consecutive += 1
                print(f"city failed: {c['city']} ({e})", file=sys.stderr)
                if consecutive >= 3:
                    raise Abort(f"3 consecutive failures, last: {e}")
        else:
            run["status"] = "ok"
    except Abort as e:
        run["status"], run["error"] = "aborted", str(e)
    run["cities_failed"] = len(failed)
    run["listings"] = len(listings)
    run["finished_at"] = datetime.now(timezone.utc).isoformat()

    rows = list(listings.values())
    if os.getenv("SUPABASE_URL"):
        # A city-filtered test run is never a full sweep, so it must not deactivate other cities.
        save(rows, run, run["status"] == "ok" and not os.getenv("ONLY_CITIES", "").strip(), failed)
    else:
        (HERE / "out").mkdir(exist_ok=True)
        (HERE / "out" / "listings.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    (HERE / "status").mkdir(exist_ok=True)
    (HERE / "status" / "last_run.json").write_text(json.dumps(run, indent=1), encoding="utf-8")
    print(json.dumps(run, indent=1))
    if run["status"] == "aborted":
        sys.exit(1)  # fails the workflow so GitHub emails the owner


if __name__ == "__main__":
    main()
