create table if not exists public.export_history (
    id bigint generated always as identity primary key,
    exporter_name text not null,
    unit text not null,
    route_name text not null,
    export_time timestamptz not null default now()
);

create index if not exists export_history_time_idx
    on public.export_history (export_time desc);

create index if not exists export_history_route_time_idx
    on public.export_history (route_name, export_time);

alter table public.export_history enable row level security;

revoke all on public.export_history from anon, authenticated;
grant select, insert on public.export_history to service_role;
grant usage, select on sequence public.export_history_id_seq to service_role;

create or replace view public.export_notifications
with (security_invoker = true) as
select
    id,
    exporter_name,
    unit,
    route_name,
    export_time,
    count(*) over (
        partition by
            route_name,
            date_trunc(
                'month',
                export_time at time zone 'Asia/Ho_Chi_Minh'
            )
    )::bigint as monthly_export_count,
    to_char(
        export_time at time zone 'Asia/Ho_Chi_Minh',
        'MM'
    ) as month_name
from public.export_history;

revoke all on public.export_notifications from anon, authenticated;
grant select on public.export_notifications to service_role;

create table if not exists public.route_dashboard_snapshots (
    id bigint generated always as identity primary key,
    region text not null check (region in ('B-N', 'TBB', 'DBB')),
    route_key text not null,
    route_name text not null,
    measurement_month date not null,
    worst_event_loss_db double precision,
    worst_event_position_km double precision,
    utilization_percent double precision,
    dkd_core_percent double precision,
    dkd_required_percent double precision,
    assessment text check (assessment is null or assessment in ('Đạt', 'Không đạt')),
    source_file text not null,
    source_sheet text not null,
    source_format text not null default 'unknown',
    source_sha256 text not null,
    warnings jsonb not null default '[]'::jsonb,
    imported_at timestamptz not null default now(),
    unique (region, route_key, measurement_month, source_sha256, source_sheet)
);

create index if not exists route_dashboard_region_route_month_idx
    on public.route_dashboard_snapshots (region, route_key, measurement_month desc);

alter table public.route_dashboard_snapshots enable row level security;

revoke all on public.route_dashboard_snapshots from anon, authenticated;
grant select, insert, update on public.route_dashboard_snapshots to service_role;
grant usage, select on sequence public.route_dashboard_snapshots_id_seq to service_role;
