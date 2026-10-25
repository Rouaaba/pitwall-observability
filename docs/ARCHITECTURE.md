# Architecture

## The use case

Pitwall is a race-weekend companion for the current Formula 1 season, built
and operated the way a production observability system would be. It has
three parts:

1. **Briefing** (not yet built): a pre-race view — what happened last time
   at this circuit, current form, things to watch for.
2. **Debrief** (not yet built): a post-race view — what the telemetry
   actually showed, built from the same signals the pipeline ingests live
   during the race.
3. **Pipeline**: the near-live ingestion path, operated like production —
   metrics, logs and traces flowing through Grafana Alloy to Grafana Cloud,
   with SLOs and alerting (SLOs/alerting not yet built).

The **rehearsal tool** sits alongside the pipeline, not inside Briefing or
Debrief: before each real Grand Prix weekend, it replays last year's race at
the *same circuit* through the exact same pipeline, at a configurable
speed. This is how the pipeline, its dashboards and its alerting get
exercised and validated before the real thing happens — the same reason a
production system gets a load test or a game-day drill before a big event.
The rehearsal tool is what was originally built as the "replay engine"
(`pipeline/`); it hasn't changed in kind, only in role — it's no longer the
whole project, it's one input into a bigger one.

## The four parts, and how they relate

```
                 ┌─────────────┐
 last year's  →  │  Rehearsal  │  →  ┐
 race (OpenF1)    │  (replay)   │     │
                 └─────────────┘     │
                                      ▼
                                 ┌─────────┐      ┌───────────────┐
 this weekend's  →  (future)    │Pipeline │  →   │ Grafana Alloy │  →  Grafana Cloud
 live race (OpenF1)             │(ingest) │      │  (collector)  │      (metrics/logs/traces,
                                 └─────────┘      └───────────────┘       dashboards, SLOs)
                                      ▲
                                      │
                      ┌───────────────┴───────────────┐
                      │                                │
                 Briefing (future)              Debrief (future)
             pre-race, reads cached            post-race, reads what
             historical context                the pipeline ingested
```

Both the rehearsal tool and the (future) live ingestion path feed the exact
same pipeline — same event model, same metric/log/span shapes, same
`season`/`race`/`session` labels — so a dashboard or alert validated during
rehearsal behaves identically during the real race. This is the whole point
of rehearsing: if it works for last year's Qatar GP at 10x speed, it will
work for this year's Qatar GP in real time.

## The label convention: `season`, `race`, `session`

Every `pitwall_*` metric carries exactly these three labels (see
`pipeline/race_labels.py` for the normalization and `pipeline/metrics.py`
for where they're attached):

| Label | Shape | Example |
|---|---|---|
| `season` | string year | `"2023"` |
| `race` | lowercase, spaces/punctuation → `_` | `"qatar"`, `"united_arab_emirates"` |
| `session` | short code | `"R"`, `"Q"`, `"S"`, `"SQ"`, `"FP1"`, `"FP2"`, `"FP3"` |

This is a deliberate, fixed contract: it's what every dashboard variable and
every alert rule filters on, whether the data behind it came from a
rehearsal run or (once built) the live pipeline. Metric *names* never
encode season/race/session — only labels do — so a dashboard built against
rehearsal data keeps working unmodified once pointed at live data.

Labels are attached as explicit per-call metric attributes, not as OTel
resource attributes, because Grafana Cloud's OTLP-to-Prometheus translation
mostly surfaces resource attributes as `target_info` rather than as labels
on every series. Resource attributes are still set (for logs/traces
parity), but metrics deliberately don't rely on them — see
`pipeline/metrics.py`'s `_with_race_labels`.

## Why the rate limit justifies "fetch once, then replay/process from cache"

OpenF1's free tier allows 3 requests/second and 30 requests/minute. A full
race session easily needs hundreds of requests (20 drivers × several
high-frequency endpoints, each paginated or driver-scoped — see
`pipeline/fetch_openf1.py`'s `PER_DRIVER_ENDPOINTS`). At 30 requests/minute,
fetching a session live, on every rehearsal run, would take many minutes
just in rate-limit waiting — and would burn through the shared budget if
anything else (a future Briefing/Debrief, a manual check) is also calling
OpenF1 at the same time.

This is why the pipeline is built around a **cache-once** design:

- `pipeline/openf1_client.py` is the single shared client every
  OpenF1-calling path uses (today: `fetch_openf1.py`; later: Briefing,
  Debrief). It owns rate limiting, retry/backoff, and a local response
  cache, so no caller needs to reimplement any of this.
- Session data is fetched **once**, into `data/<session_key>/`, and every
  rehearsal run after that replays from the local cache — zero OpenF1 calls
  per replay, regardless of how many times you rehearse or at what speed.
- The client's own lower-level response cache (keyed by endpoint + params,
  under `data/.http_cache/`) sits underneath that: it's what makes
  `fetch_openf1.py`'s per-session JSON files cheap to build and rebuild
  without hammering the API, and it's what a future Briefing/Debrief would
  share if they query OpenF1 with different parameter combinations than
  `fetch_openf1.py` does.

### Cache rules

The response cache enforces three rules, because a stale-but-wrong answer
is worse than no cache at all here:

1. **Never cache a `"latest"` query** (`meeting_key=latest`,
   `session_key=latest`). What "latest" means changes from one call to the
   next — caching it would silently answer a different question than the
   one being asked.
2. **Never cache an empty response.** During a live race weekend, an
   endpoint's data may simply not be published yet (e.g. `intervals` before
   the session starts). Caching `[]` would hide the real data once OpenF1
   actually publishes it.
3. **Cache permanently only once the session has ended**, and only a
   non-empty response. A session that hasn't happened yet (or is in
   progress) can still change; a session that's over is historical and
   final. Everything that isn't eligible for permanent caching gets a short
   (5-minute) TTL instead, so near-live polling eventually sees new data
   without needing to bypass the cache by hand.

### Observability hooks, without refactoring later

The client exposes `stats.rate_limit_waits_total`,
`stats.rate_limit_wait_seconds_total` and `stats.retries_total` on every
`OpenF1Client` instance. These aren't wired into `pitwall_*` metrics yet —
that's planned for a later phase (`pitwall_rate_limit_waits_total`) — but
the counters already exist and are updated on every request, so that phase
is a metrics-emission change only, not a client refactor.

## Known limitation: the rate limiter is per process

`RateLimiter` tracks tokens in-process. If two processes call OpenF1 at the
same time — say, a manual `fetch_openf1.py` run and a future live pipeline
process — each one enforces 3/s and 30/min **independently**, so together
they can exceed OpenF1's actual free-tier limit and get rate-limited (HTTP
429) by the server, which the client *will* retry through, but at the cost
of wasted requests and slower fetches for both processes.

For now: **run only one OpenF1-calling process at a time.** A shared,
cross-process rate limiter (e.g. backed by a local file lock or a small
coordinator process) would fix this properly, but isn't built yet — it's
only worth adding once there are actually multiple processes that need to
call OpenF1 concurrently (e.g. once Briefing/Debrief exist alongside a live
pipeline).
