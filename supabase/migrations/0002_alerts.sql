-- Anonymous devices and their alert filters. No accounts: a device is identified by a
-- random secret token generated in the browser. The anon role can only touch these
-- tables through the functions below, and only for the token it knows.

create table devices (
  token             uuid primary key,
  push_subscription jsonb not null,
  created_at        timestamptz not null default now(),
  last_push_at      timestamptz
);

create table alerts (
  id           bigint generated always as identity primary key,
  device_token uuid not null references devices on delete cascade,
  name         text not null,
  filters      jsonb not null,  -- same shape as the app's Filters type
  created_at   timestamptz not null default now()
);
create index alerts_device on alerts (device_token);

alter table devices enable row level security;  -- no policies: no direct anon access
alter table alerts enable row level security;

alter table scrape_runs add column pushes_sent int;

create function save_device(p_token uuid, p_subscription jsonb) returns void
language plpgsql security definer set search_path = public as $$
begin
  if jsonb_typeof(p_subscription) <> 'object'
     or coalesce(p_subscription->>'endpoint', '') not like 'https://%'
     or jsonb_typeof(p_subscription->'keys') <> 'object'
     or length(p_subscription::text) > 2000 then
    raise exception 'invalid push subscription';
  end if;
  insert into devices (token, push_subscription) values (p_token, p_subscription)
  on conflict (token) do update set push_subscription = excluded.push_subscription;
end $$;

-- Replaces all of a device's alerts.
create function save_alerts(p_token uuid, p_alerts jsonb) returns void
language plpgsql security definer set search_path = public as $$
begin
  if not exists (select 1 from devices where token = p_token) then
    raise exception 'unknown device';
  end if;
  if jsonb_typeof(p_alerts) <> 'array' or jsonb_array_length(p_alerts) > 10 then
    raise exception 'alerts must be an array of at most 10';
  end if;
  if exists (select 1 from jsonb_array_elements(p_alerts) a
             where jsonb_typeof(a->'filters') <> 'object'
                or length(coalesce(a->>'name', '')) not between 1 and 60
                or length((a->'filters')::text) > 4000) then
    raise exception 'invalid alert';
  end if;
  delete from alerts where device_token = p_token;
  insert into alerts (device_token, name, filters)
  select p_token, a->>'name', a->'filters' from jsonb_array_elements(p_alerts) a;
end $$;

create function delete_device(p_token uuid) returns void
language sql security definer set search_path = public as $$
  delete from devices where token = p_token;
$$;

revoke execute on function save_device, save_alerts, delete_device from public;
grant execute on function save_device, save_alerts, delete_device to anon, authenticated;
