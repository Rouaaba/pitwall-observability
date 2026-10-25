"""OpenTelemetry logger provider and log emitters for race control, pit stops,
stint changes and team radio.

Only service name and session are resource attributes (which Grafana Cloud's
OTLP-to-Loki translation promotes to labels); everything else (driver, flag,
lap number, compound, trace_id) stays on the log record's attributes so Loki
label cardinality stays low.
"""

from datetime import datetime

from opentelemetry._logs import SeverityNumber
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import Logger, LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.trace import NonRecordingSpan, SpanContext, set_span_in_context


def _to_ns(dt: datetime) -> int:
    return int(dt.timestamp() * 1_000_000_000)


def severity_for_race_control(flag: str | None, category: str | None) -> tuple[SeverityNumber, str]:
    """Maps a race control flag/category to an OTel severity. Pure function, no SDK objects."""
    if flag == "RED":
        return SeverityNumber.ERROR, "ERROR"
    if flag == "YELLOW" or category == "SafetyCar":
        return SeverityNumber.WARN, "WARN"
    return SeverityNumber.INFO, "INFO"


def build_logger_provider(
    otlp_endpoint: str, session_key: int, race_labels: dict[str, str]
) -> LoggerProvider:
    resource = Resource.create(
        {
            "service.name": "pitwall-replay",
            "pitwall.session_key": session_key,
            "pitwall.season": race_labels["season"],
            "pitwall.race": race_labels["race"],
            "pitwall.session": race_labels["session"],
        }
    )
    exporter = OTLPLogExporter(endpoint=otlp_endpoint, insecure=True)
    provider = LoggerProvider(resource=resource)
    provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
    return provider


class PitwallLogs:
    def __init__(self, logger: Logger) -> None:
        self._logger = logger

    def _context_for(self, trace_id: SpanContext | None):
        if trace_id is None:
            return None
        return set_span_in_context(NonRecordingSpan(trace_id))

    def log_race_control(
        self, attrs: dict, payload: dict, trace_context: SpanContext | None, emitted_at: datetime
    ) -> None:
        severity_number, severity_text = severity_for_race_control(
            payload.get("flag"), payload.get("category")
        )
        self._logger.emit(
            timestamp=_to_ns(emitted_at),
            severity_number=severity_number,
            severity_text=severity_text,
            body=payload.get("message", ""),
            attributes={
                **attrs,
                "flag": payload.get("flag"),
                "category": payload.get("category"),
                "lap_number": payload.get("lap_number"),
            },
            context=self._context_for(trace_context),
        )

    def log_pit_stop(
        self, attrs: dict, payload: dict, trace_context: SpanContext | None, emitted_at: datetime
    ) -> None:
        self._logger.emit(
            timestamp=_to_ns(emitted_at),
            severity_number=SeverityNumber.INFO,
            severity_text="INFO",
            body=f"Pit stop: {attrs.get('driver', payload.get('driver_number'))}",
            attributes={
                **attrs,
                "lap_number": payload.get("lap_number"),
                "pit_duration": payload.get("pit_duration"),
                "lane_duration": payload.get("lane_duration"),
            },
            context=self._context_for(trace_context),
        )

    def log_stint_start(self, attrs: dict, payload: dict, emitted_at: datetime) -> None:
        self._logger.emit(
            timestamp=_to_ns(emitted_at),
            severity_number=SeverityNumber.INFO,
            severity_text="INFO",
            body=f"Stint start: {attrs.get('driver')} on {payload.get('compound', 'UNKNOWN')}",
            attributes={
                **attrs,
                "compound": payload.get("compound"),
                "lap_start": payload.get("lap_start"),
                "lap_end": payload.get("lap_end"),
            },
        )

    def log_team_radio(
        self, attrs: dict, payload: dict, trace_context: SpanContext | None, emitted_at: datetime
    ) -> None:
        self._logger.emit(
            timestamp=_to_ns(emitted_at),
            severity_number=SeverityNumber.INFO,
            severity_text="INFO",
            body="Team radio",
            attributes={
                **attrs,
                "recording_url": payload.get("recording_url"),
            },
            context=self._context_for(trace_context),
        )


def create_logs(provider: LoggerProvider) -> PitwallLogs:
    logger = provider.get_logger("pitwall.replay")
    return PitwallLogs(logger)
