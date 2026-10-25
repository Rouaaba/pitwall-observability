"""OpenTelemetry tracer provider and span-building helpers.

One completed lap becomes one trace: a root `lap` span with three back-to-back
`sector_N` child spans, and an optional `pit_stop` child span. Since a LAP
event fires only once the lap is already complete, spans are created and
ended immediately with explicit historical start/end times rather than held
open across the lap.
"""

from datetime import datetime

from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import Tracer, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import NonRecordingSpan, Span, SpanContext, set_span_in_context


def _to_ns(dt: datetime) -> int:
    return int(dt.timestamp() * 1_000_000_000)


def build_tracer_provider(
    otlp_endpoint: str, session_key: int, race_labels: dict[str, str]
) -> TracerProvider:
    resource = Resource.create(
        {
            "service.name": "pitwall-replay",
            "pitwall.session_key": session_key,
            "pitwall.season": race_labels["season"],
            "pitwall.race": race_labels["race"],
            "pitwall.session": race_labels["session"],
        }
    )
    exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    return provider


class PitwallTraces:
    def __init__(self, tracer: Tracer) -> None:
        self._tracer = tracer

    def start_lap_span(
        self, attrs: dict, lap_number: int, start_time: datetime, end_time: datetime
    ) -> Span:
        span = self._tracer.start_span(
            "lap",
            attributes={**attrs, "lap_number": lap_number},
            start_time=_to_ns(start_time),
        )
        span.end(end_time=_to_ns(end_time))
        return span

    def record_sector_span(
        self,
        parent_span: Span,
        attrs: dict,
        sector: int,
        start_time: datetime,
        end_time: datetime,
    ) -> None:
        context = set_span_in_context(parent_span)
        span = self._tracer.start_span(
            f"sector_{sector}",
            context=context,
            attributes={**attrs, "sector": sector},
            start_time=_to_ns(start_time),
        )
        span.end(end_time=_to_ns(end_time))

    def record_pit_stop_span(
        self,
        parent_span_context: SpanContext | None,
        attrs: dict,
        start_time: datetime,
        end_time: datetime,
    ) -> None:
        if parent_span_context is None:
            return
        context = set_span_in_context(NonRecordingSpan(parent_span_context))
        span = self._tracer.start_span(
            "pit_stop",
            context=context,
            attributes=attrs,
            start_time=_to_ns(start_time),
        )
        span.end(end_time=_to_ns(end_time))


def create_traces(provider: TracerProvider) -> PitwallTraces:
    tracer = provider.get_tracer("pitwall.replay")
    return PitwallTraces(tracer)
