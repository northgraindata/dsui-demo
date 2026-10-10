-- Parsing must preserve amounts, including currency symbols and thousands.
with money_samples(raw, expected) as (
    values ('$1,234.56', 1234.56), ('12.00 EUR', 12.0), ('1234,56', 1234.56),
           (' 42.10 ', 42.10), ('-3,50', -3.50), (null, null), ('', null)
), timestamp_samples(raw, expected) as (
    values ('2026-01-31T12:34:56Z', timestamp '2026-01-31 12:34:56'),
           ('31/01/2026 12:34', timestamp '2026-01-31 12:34:00'),
           ('2026-01-31T12:34:56.123456', timestamp '2026-01-31 12:34:56.123456'),
           ('1769817600', timestamp '2026-01-31 00:00:00'),
           ('2026-01-31', timestamp '2026-01-31 00:00:00')
)
select 'money' as parser, raw from money_samples
where {{ parse_money('raw') }} is distinct from expected
union all
select 'timestamp' as parser, raw from timestamp_samples
where {{ parse_timestamp('raw') }} is distinct from expected
