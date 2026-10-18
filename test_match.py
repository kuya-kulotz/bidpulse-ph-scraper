import os

import pywebpush

import scrape
from scrape import matches, notify, push_payload

L = {"ropa_id": "1", "city_id": "042109000", "city": "CITY OF IMUS", "prop_group": "house",
     "occupancy": "Unoccupied", "min_price": 980000.0, "lot_area": 72.0, "floor_area": None}

assert matches(L, {})
assert matches(L, {"cities": ["042109000"], "groups": ["house", "lot"], "occupancy": ["Unoccupied"],
                   "priceMax": 1000000, "lotMin": 60})
assert not matches(L, {"cities": ["137601000"]})
assert not matches(L, {"occupancy": ["Occupied"]})
assert not matches(L, {"priceMax": 900000})
assert not matches(L, {"floorMin": 20})  # unknown floor area never satisfies a minimum
assert not matches({**L, "min_price": None}, {"priceMax": 1000000})

# Sale type, bidding status (relative to a fixed "now"), and exclude keywords.
from datetime import datetime, timezone
from scrape import bid_status
B = {**L, "disposal_type": "2nd Public Auction", "subdivision": "KASSEL RESIDENCES - PARANAQUE",
     "address": "Lot 1 Blk 2 KASSEL RESIDENCES, PARANAQUE",
     "bid_start": "2026-10-19T00:00:00+08:00", "bid_end": "2026-10-23T23:59:00+08:00"}
before, during, after = (datetime(2026, 10, d, 12, tzinfo=timezone.utc) for d in (17, 20, 25))
assert [bid_status(B, t) for t in (before, during, after)] == ["upcoming", "open", "closed"]
assert bid_status({**B, "bid_end": None}, during) is None
assert matches(B, {"disposal": ["2nd Public Auction"], "status": ["open"]}, during)
assert not matches(B, {"disposal": ["1st Public Auction"]}, during)
assert not matches(B, {"status": ["open", "upcoming"]}, after)
assert not matches(B, {"exclude": ["kassel residence"]}, during)       # case-insensitive, catches variants
assert matches({**B, "subdivision": "KASSEL CITY SUBDIVISION", "address": "Lot 3"}, {"exclude": ["Kassel Residence"]}, during)
assert matches(B, {"exclude": ["", "  "]}, during)                     # blank keywords ignored
assert matches(L, {"disposal": [], "status": [], "exclude": []})      # empty lists = no restriction

p = push_payload([L, {**L, "ropa_id": "2", "min_price": 1500000.0}])
assert p["title"] == "2 new matches for your alerts", p
assert p["body"] == "Unoccupied house & lot, Imus ₱980,000 + 1 more", p

# notify(): one push per matching device, dead subscriptions get deleted.
calls, sent_to = [], []
scrape.supabase = lambda method, path, body=None, prefer=None: (
    calls.append((method, path)) or
    ([{"token": "a", "push_subscription": {"endpoint": "https://push/a"}, "alerts": [{"filters": {"priceMax": 1000000}}]},
      {"token": "b", "push_subscription": {"endpoint": "https://push/b"}, "alerts": [{"filters": {"groups": ["condo"]}}]},
      {"token": "c", "push_subscription": {"endpoint": "https://push/c"}, "alerts": [{"filters": {}}]}]
     if method == "GET" else None))


class Gone:
    status_code = 410


def fake_webpush(sub, data, **kw):
    assert kw["vapid_claims"]["sub"].startswith("mailto:")
    if sub["endpoint"].endswith("/c"):
        raise pywebpush.WebPushException("gone", response=Gone())
    sent_to.append(sub["endpoint"])


pywebpush.webpush = fake_webpush
os.environ.update(VAPID_PRIVATE_KEY="x", VAPID_SUBJECT="mailto:test@example.com")
assert notify([L]) == 1 and sent_to == ["https://push/a"]
assert ("DELETE", "devices?token=eq.c") in calls
assert notify([]) == 0
print("ok")
