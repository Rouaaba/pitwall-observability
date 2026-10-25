"""OpenTelemetry instruments for the briefing command, exported through the
same Alloy/OTLP path as the replay pipeline, under a separate service
identity (pitwall-briefing) since it's a distinct process with its own
metric set."""

from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics import Meter, MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource


def build_briefing_meter_provider(otlp_endpoint: str) -> MeterProvider:
    resource = Resource.create({"service.name": "pitwall-briefing"})
    exporter = OTLPMetricExporter(endpoint=otlp_endpoint, insecure=True)
    # One-shot CLI process: export immediately on shutdown via the reader's
    # final flush, no need for a short periodic interval like the replay.
    reader = PeriodicExportingMetricReader(exporter, export_interval_millis=5000)
    return MeterProvider(resource=resource, metric_readers=[reader])


class PitwallBriefingMetrics:
    def __init__(self, meter: Meter) -> None:
        self._snapshot_generated_timestamp = meter.create_gauge(
            "pitwall_snapshot_generated_timestamp",
            description="Unix timestamp when a snapshot was last generated",
        )
        self._snapshot_duration_seconds = meter.create_gauge(
            "pitwall_snapshot_duration_seconds",
            unit="s",
            description="How long generating one snapshot took",
        )
        self._source_requests_total = meter.create_counter(
            "pitwall_source_requests_total",
            description="OpenF1 requests made while building a snapshot, by status code",
        )
        self._rate_limit_waits_total = meter.create_counter(
            "pitwall_rate_limit_waits_total",
            description="Times a request had to wait on the OpenF1 rate limiter",
        )
        self._snapshot_failures_total = meter.create_counter(
            "pitwall_snapshot_failures_total",
            description="Snapshot generation failures, by reason",
        )
        self._snapshot_last_success_timestamp = meter.create_gauge(
            "pitwall_snapshot_last_success_timestamp",
            description="Unix timestamp of the last snapshot generated without error",
        )

    def record_snapshot_generated(self, meeting_key: int, season: str, timestamp: float) -> None:
        attrs = {"meeting_key": str(meeting_key), "season": season}
        self._snapshot_generated_timestamp.set(timestamp, attrs)
        self._snapshot_last_success_timestamp.set(timestamp, {})

    def record_snapshot_duration(self, meeting_key: int, season: str, duration_s: float) -> None:
        self._snapshot_duration_seconds.set(
            duration_s, {"meeting_key": str(meeting_key), "season": season}
        )

    def record_source_request(self, status_code: int) -> None:
        self._source_requests_total.add(1, {"status_code": str(status_code)})

    def record_rate_limit_wait(self) -> None:
        self._rate_limit_waits_total.add(1, {})

    def record_snapshot_failure(self, reason: str) -> None:
        self._snapshot_failures_total.add(1, {"reason": reason})


def create_briefing_metrics(provider: MeterProvider) -> PitwallBriefingMetrics:
    metrics.set_meter_provider(provider)
    meter = provider.get_meter("pitwall.briefing")
    return PitwallBriefingMetrics(meter)
