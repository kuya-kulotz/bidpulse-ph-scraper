from scrape import Abort, latlng, normalize, prop_group

CITY = {"region_id": "130000000", "province_id": "137600000", "city_id": "137601000", "city": "CITY OF LAS PIÑAS"}
RAW = {  # trimmed real record, 2026-10-19
    "batch_no": "OPA1510116", "ropa_id": "815202502280056", "prop_type": "Condominium",
    "prop_location": "Unit 6 Flr. 9 EMMAUS VILLAGE, CITY OF LAS PIÑAS", "tct_cct_no": "C-2045",
    "survey_no": "CONDO UNIT", "lot_area": "0", "floor_area": "25", "min_sellprice": 473300,
    "remarks": "OCCUPIED - TITLE UNDER CONSOLIDATION", "city_muni": "CITY OF LAS PIÑAS",
    "ins_remarks": "14.421050,120.992408", "start_datetime": "2026-10-19T00:00:00",
    "end_datetime": "2026-10-23T23:59:00", "opening_datetime": "2026-10-26T09:00:00",
    "disposal_type": "1st Public Auction", "occupancy": "Occupied", "handling_hbc": "NCR HOUSING HUB",
}

row = normalize(RAW, CITY, "2026-10-19T00:00:00+00:00")
assert "tct_cct_no" not in row and "survey_no" not in row
assert row["lot_area"] is None and row["floor_area"] == 25 and row["min_price"] == 473300
assert (row["lat"], row["lng"]) == (14.42105, 120.992408)
assert row["bid_end"] == "2026-10-23T23:59:00+08:00"
assert row["prop_group"] == "condo" and row["remarks"].startswith("OCCUPIED")

assert normalize({**RAW, "remarks": "OCCUPIED BY MR. JUAN DELA CRUZ"}, CITY, "x")["remarks"] is None
assert latlng("") == (None, None) and latlng("0,0") == (None, None)
assert [prop_group(t) for t in ("Lot Only", "Town House", "Single Attached", "Duplex with Eaves",
        "Condominium Parking Slot", "Warehouse")] == ["lot", "townhouse", "house", "house", "parking", "other"]
try:
    normalize({"ropa_id": "1"}, CITY, "x")
    raise AssertionError("schema change not caught")
except Abort:
    pass
print("ok")
