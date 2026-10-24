"""CLI entrypoint: `python -m replay --session-key 9221 --speed 1`."""

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
from .traces import build_tracer_provider, create_traces

VERSION = "0.1.0"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay a cached race as live OTel telemetry.")
    parser.add_argument(
        "--session-key",
        type=int,
        default=int(os.environ.get("SESSION_KEY", "0")) or None,
        required="SESSION_KEY" not in os.environ,
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

    session_dir = args.data_dir / str(args.session_key)
    if not session_dir.exists():
        sys.exit(f"No cached data for session_key={args.session_key} at {session_dir}")

    race_start = get_race_start(session_dir)
    driver_labels = load_driver_labels(session_dir)

    meter_provider = build_meter_provider(
        otlp_endpoint=args.otlp_endpoint,
        export_interval_seconds=args.export_interval_seconds,
        session_key=args.session_key,
    )
    metrics = create_metrics(meter_provider)
    metrics.set_build_info(VERSION, args.session_key, args.speed)

    tracer_provider = build_tracer_provider(args.otlp_endpoint, args.session_key)
    traces = create_traces(tracer_provider)

    logger_provider = build_logger_provider(args.otlp_endpoint, args.session_key)
    logs = create_logs(logger_provider)

    clock = ReplayClock(race_start=race_start, speed=args.speed)
    engine = ReplayEngine(
        clock=clock, metrics=metrics, traces=traces, logs=logs, driver_labels=driver_labels
    )

    logging.info(
        "Replaying session_key=%s at %sx (race_start=%s, otlp_endpoint=%s)",
        args.session_key, args.speed, race_start, args.otlp_endpoint,
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
