-- listed_at: when the listing entered its current sale stage. Starts at first sighting and
-- resets when the property moves to a new batch or sale type (e.g. 1st -> 2nd auction ->
-- negotiated sale), so the app's NEW badge and push alerts treat a relisting as new.
alter table listings add column listed_at timestamptz;
update listings set listed_at = first_seen_at;
alter table listings alter column listed_at set not null, alter column listed_at set default now();
create index listings_listed_at on listings (listed_at);

-- Old data has trailing spaces in subdivision names.
update listings set subdivision = nullif(trim(subdivision), '');

create function listings_relisted() returns trigger
language plpgsql as $$
begin
  if new.batch_no is distinct from old.batch_no or new.disposal_type is distinct from old.disposal_type then
    new.listed_at := now();
  end if;
  return new;
end $$;

create trigger listings_relisted before update on listings
for each row execute function listings_relisted();
