-- Accounts, deduplicated and typed.
--
-- The generator writes roughly one percent of accounts twice, under a `-DUP`
-- identifier. Which row wins is a real modelling decision, so it is made here
-- and made explicitly rather than by whatever order the file happened to land in.

with source as (
    select * from {{ source('landing', 'accounts') }}
),

deduplicated as (
    select
        account_id,
        name,
        {{ normalize_status('plan') }}                     as plan,
        {{ parse_integer('seats') }}                      as seats,
        upper(trim(country))                              as country,
        {{ parse_timestamp('created_at') }}               as created_at,
        {{ normalize_status('status') }}                  as status,
        {{ parse_money('mrr') }}                          as mrr,
        {{ parse_timestamp('trial_ends_at') }}            as trial_ends_at,
        {{ parse_timestamp('churned_at') }}               as churned_at
    from source
    where account_id not like '%-DUP'
),

-- Prefer a row that actually carries the fields a later row is missing.
coalesced as (
    select
        account_id,
        any_value(name)         filter (where name is not null)         as name,
        any_value(plan)         filter (where plan is not null)         as plan,
        max(seats)                                                       as seats,
        any_value(country)      filter (where country is not null)      as country,
        min(created_at)                                                as created_at,
        any_value(status)       filter (where status is not null)       as status,
        max(mrr)                                                       as mrr,
        min(trial_ends_at)                                              as trial_ends_at,
        max(churned_at)                                                as churned_at
    from deduplicated
    group by account_id
)

select
    *,
    mrr > 0                                            as is_paying,
    date_diff('day', created_at, current_date)        as age_days,
    case
        when status = 'churned' or churned_at is not null then 'churned'
        when trial_ends_at is not null and trial_ends_at > current_timestamp then 'trialing'
        when mrr > 0 then 'active'
        else 'inactive'
    end                                                as lifecycle_status
from coalesced
