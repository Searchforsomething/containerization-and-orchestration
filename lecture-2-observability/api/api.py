import os
from flask import Flask, jsonify, request, Response, g
import json
import logging
import sys
import time
import uuid
from datetime import datetime, timezone

from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.instrumentation.flask import FlaskInstrumentor


app = Flask(__name__)

# Prometheus RED metrics
REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)

RESPONSE_TIME = Histogram(
    "http_request_duration_seconds",
    "Request duration in seconds",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.5, 1.0),
)


# OpenTelemetry
OTLP_ENDPOINT = os.getenv(
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "http://jaeger:4317",
)

resource = Resource.create({"service.name": "api-service"})
tracer_provider = TracerProvider(resource=resource)

try:
    otlp_exporter = OTLPSpanExporter(
        endpoint=OTLP_ENDPOINT,
        insecure=True,
    )
    tracer_provider.add_span_processor(
        BatchSpanProcessor(otlp_exporter)
    )
except Exception:
    logging.getLogger(__name__).exception(
        "Failed to initialize OTLP exporter"
    )

trace.set_tracer_provider(tracer_provider)
tracer = trace.get_tracer(__name__)
FlaskInstrumentor().instrument_app(app)



# Structured JSON logging
class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Additional structured fields supplied via logger.*(..., extra={...})
        for field in (
            "method",
            "endpoint",
            "status",
            "request_id",
            "trace_id",
            "duration_ms",
        ):
            value = getattr(record, field, None)
            if value is not None:
                log_entry[field] = value

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, ensure_ascii=False, default=str)


handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JsonFormatter())

logger = logging.getLogger("api")
logger.setLevel(logging.INFO)
logger.handlers.clear()
logger.addHandler(handler)
logger.propagate = False


def get_trace_id():
    span_context = trace.get_current_span().get_span_context()
    if span_context.is_valid:
        return format(span_context.trace_id, "032x")
    return None


@app.before_request
def before_request():
    g.start_time = time.perf_counter()
    g.request_id = str(uuid.uuid4())
    g.trace_id = get_trace_id()


@app.after_request
def after_request(response):
    duration = time.perf_counter() - g.start_time

    REQUESTS_TOTAL.labels(
        method=request.method,
        endpoint=request.path,
        status=str(response.status_code),
    ).inc()

    RESPONSE_TIME.observe(duration)

    logger.info(
        "request completed",
        extra={
            "method": request.method,
            "endpoint": request.path,
            "status": response.status_code,
            "request_id": g.request_id,
            "trace_id": get_trace_id(),
            "duration_ms": round(duration * 1000, 3),
        },
    )

    return response


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/fail", methods=["GET"])
def fail():
    try:
        with tracer.start_as_current_span("fail") as span:
            span.set_attribute("status", "error")
            raise RuntimeError("intentional error")
    except Exception:
        logger.exception(
            "request failed",
            extra={
                "method": request.method,
                "endpoint": request.path,
                "status": 500,
                "request_id": g.request_id,
                "trace_id": get_trace_id(),
            },
        )
        return jsonify({
            "error": "intentional error",
            "request_id": g.request_id,
            "trace_id": get_trace_id(),
        }), 500



@app.route("/slow", methods=["GET"])
def slow():
    with tracer.start_as_current_span("validate-request") as span:
        span.set_attribute("step", "validation")
        time.sleep(0.3)

    with tracer.start_as_current_span("load-user") as span:
        span.set_attribute("step", "database")
        time.sleep(0.7)

        with tracer.start_as_current_span("load-user-preferences") as child_span:
            child_span.set_attribute("step", "database")
            time.sleep(0.5)

    with tracer.start_as_current_span("calculate-recommendations") as span:
        span.set_attribute("step", "processing")
        time.sleep(1.0)

        with tracer.start_as_current_span("rank-recommendations") as child_span:
            child_span.set_attribute("step", "processing")
            time.sleep(0.4)

    with tracer.start_as_current_span("serialize-response") as span:
        span.set_attribute("step", "serialization")
        time.sleep(0.2)

    return jsonify({
        "status": "ok",
        "recommendations": ["item-1", "item-2", "item-3"],
    }), 200


@app.route("/load", methods=["GET"])
def load():
    # Generate sample requests through Flask's test client.
    # This is suitable for a small demo, not production load testing.
    with app.test_client() as client:
        for _ in range(100):
            client.get("/health")

    return jsonify({"status": "ok", "requests": 100}), 200


@app.route("/metrics", methods=["GET"])
def metrics():
    return Response(
        generate_latest(),
        mimetype=CONTENT_TYPE_LATEST,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, use_reloader=False)
