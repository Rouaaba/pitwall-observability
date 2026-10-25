"""CLI entrypoint: `python -m pipeline --season 2023 --race Qatar --session Race --speed 1`."""

import argparse
import logging
import os
import signal
import sys
from pathlib import Path

from dotenv import load_dotenv

from .clock import ReplayClock
from .driver_labels import load_driver_labels
from .engine import ReplayEngine
from .events import build_event_stream, get_race_start
from .logs import build_logger_provider, create_logs
from .metrics import build_meter_provider, create_metrics
from .race_labels import race_labels as build_race_labels
from .race_selector import RaceNotFoundError, resolve_session_key
from .traces import build_tracer_provider, create_traces

VERSION = "0.1.0"

# Matches what's actually cached under data/9221/sessions.json (2023 Qatar
# GP Race) rather than an assumed default.
DEFAULT_SEASON = "2023"
DEFAULT_RACE = "Qatar"
DEFAULT_SESSION = "Race"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay a cached race as live OTel telemetry.")
    parser.add_argument(
        "--season",
        default=os.environ.get("SEASON", DEFAULT_SEASON),
        help="Season year, e.g. 2023 (default: %(default)s)",
    )
    parser.add_argument(
        "--race",
        default=os.environ.get("RACE", DEFAULT_RACE),
        help="Race/circuit/country name, e.g. Qatar (default: %(default)s)",
    )
    parser.add_argument(
        "--session-type",
        default=os.environ.get("SESSION_TYPE", DEFAULT_SESSION),
        help="Session name, e.g. Race, Qualifying, 'Practice 1' (default: %(default)s)",
    )
    parser.add_argument(
        "--session-key",
        type=int,
        default=int(os.environ["SESSION_KEY"]) if "SESSION_KEY" in os.environ else None,
        help="Skip season/race/session lookup, use this cached session_key directly",
    )
    parser.add_argument(
        "--speed",
        type=int,
        choices=[1, 5, 10, 60],
        default=int(os.environ.get("SPEED", "1")),
    )
    parser.add_argument(
        "--otlp-endpoint",
        default=os.environ.get("OTLP_ENDPOINT", "localhost:4317"),
    )
    parser.add_argument(
        "--export-interval-seconds",
        type=float,
        default=float(os.environ.get("EXPORT_INTERVAL_SECONDS", "3")),
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(os.environ.get("DATA_DIR", "data")),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_dotenv()
    args = parse_args(argv)

    if args.session_key is not None:
        session_key = args.session_key
    else:
        try:
            session_key = resolve_session_key(
                args.data_dir, args.season, args.race, args.session_type
            )
        except RaceNotFoundError as exc:
            sys.exit(str(exc))

    session_dir = args.data_dir / str(session_key)
    if not session_dir.exists():
        sys.exit(f"No cached data for session_key={session_key} at {session_dir}")

    race_start = get_race_start(session_dir)
    driver_labels = load_driver_labels(session_dir)
    labels = build_race_labels(args.season, args.race, args.session_type)

    meter_provider = build_meter_provider(
        otlp_endpoint=args.otlp_endpoint,
        export_interval_seconds=args.export_interval_seconds,
        session_key=session_key,
    )
    metrics = create_metrics(meter_provider, labels)
    metrics.set_build_info(VERSION, session_key, args.speed)

    tracer_provider = build_tracer_provider(args.otlp_endpoint, session_key, labels)
    traces = create_traces(tracer_provider)

    logger_provider = build_logger_provider(args.otlp_endpoint, session_key, labels)
    logs = create_logs(logger_provider)

    clock = ReplayClock(race_start=race_start, speed=args.speed)
    engine = ReplayEngine(
        clock=clock, metrics=metrics, traces=traces, logs=logs, driver_labels=driver_labels
    )

    logging.info(
        "Replaying season=%s race=%s session=%s (session_key=%s) at %sx "
        "(race_start=%s, otlp_endpoint=%s)",
        labels["season"], labels["race"], labels["session"], session_key,
        args.speed, race_start, args.otlp_endpoint,
    )

    shutdown_done = False

    def shutdown_providers() -> None:
        nonlocal shutdown_done
        if shutdown_done:
            return
        shutdown_done = True
        logging.info("Shutting down, flushing telemetry...")
        meter_provider.shutdown()
        tracer_provider.shutdown()
        logger_provider.shutdown()

    def handle_signal(signum, frame):
        shutdown_providers()
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    try:
        engine.run(build_event_stream(session_dir))
    finally:
        shutdown_providers()

    logging.info("Replay complete.")


if __name__ == "__main__":
    main()
