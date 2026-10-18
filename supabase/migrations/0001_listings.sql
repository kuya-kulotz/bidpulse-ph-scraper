create table listings (
  ropa_id       text primary key,
  batch_no      text,
  disposal_type text,
  prop_type     text not null,
  prop_group    text not null,
  occupancy     text not null,
  remarks       text,
  address       text,
  subdivision   text,
  city          text not null,
  city_id       text not null,
  province_id   text not null,
  province      text,
  region_id     text not null,
  region        text,
  lot_area      numeric,
  floor_area    numeric,
  min_price     numeric,
  lat           double precision,
  lng           double precision,
  bid_start     timestamptz,
  bid_end       timestamptz,
  opening_at    timestamptz,
  office_name   text,
  office_email  text,
  office_phone  text,
  first_seen_at timestamptz not null default now(),  -- never sent by the scraper, so upserts keep it
  last_seen_at  timestamptz not null,
  is_active     boolean not null default true
);
create index listings_active_city on listings (is_active, city_id);
create index listings_first_seen on listings (first_seen_at);

create table scrape_runs (
  id            bigint generated always as identity primary key,
  started_at    timestamptz not null,
  finished_at   timestamptz,
  status        text not null,
  error         text,
  cities_total  int,
  cities_ok     int,
  cities_failed int,
  listings      int,
  new_listings  int,
  deactivated   int
);

-- Public read-only; only the service key (scraper) writes.
alter table listings enable row level security;
alter table scrape_runs enable row level security;
create policy "public read" on listings for select using (true);
create policy "public read" on scrape_runs for select using (true);
