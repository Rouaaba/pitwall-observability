# Operations

## Running the briefing on a schedule

`python -m pipeline.briefing --meeting latest` is a complete, idempotent,
one-shot command — safe to run on any schedule. Run it **every 30 minutes,
every day, in UTC**, not restricted to Friday-Sunday in any particular
local time zone: race weekends happen in every time zone, some first
sessions start Thursday or Friday in UTC, and the command is cheap outside
a race weekend anyway (almost every run just confirms "unchanged" and makes
no OpenF1 requests beyond resolving the current meeting, since finished
meetings are marked `final` and skipped).

```cron
*/30 * * * * cd /path/to/pitwall-observability && .venv/bin/python -m pipeline.briefing --meeting latest >> /var/log/pitwall-briefing.log 2>&1
```

Set `TZ=UTC` in the crontab (or the environment cron runs under) so the
`*/30 * * * *` schedule is interpreted in UTC regardless of the host's
local timezone.

This will move to a Kubernetes CronJob later; the command itself doesn't
change, only how it's invoked.

## Backfilling a season

```
.venv/bin/python -m pipeline.briefing --backfill --season 2025
```

Prints a request/time estimate and asks for confirmation before doing
anything (skip the prompt with `--yes`). Finished meetings are skipped
automatically on a second run, so an interrupted backfill can simply be
re-run — it resumes from wherever it left off, at whatever cost remains for
the meetings not yet marked `final`.

## Alerting

`pitwall_snapshot_last_success_timestamp` is the metric to alert on: page if
there's been no successful snapshot in the last 2 hours during a race
weekend (and expect this metric to simply stop moving between weekends,
when the scheduled run finds nothing to do — that's not failure, it's
"final" working as intended).

`pitwall_snapshot_failures_total`, labeled by `reason` (the Python
exception class name), is for diagnosing *why* generation failed once the
staleness alert above has fired.
