// Package tracing is the tracing lifecycle for an AWS Lambda function written in Go:
//
//	Init once (package init / main)  ->  one root span per invocation  ->  Flush before every return
//
// Copy it next to your handler. Nothing here calls AWS. Environment (set it on the function, keep
// the keys in Secrets Manager or an encrypted variable, never in the source):
//
//	FI_API_KEY, FI_SECRET_KEY   both are required; if either is missing tracing is switched off
//	FI_BASE_URL                 default https://api.futureagi.com   (self-hosted: your own URL)
//	FI_PROJECT_NAME             the Observe project (default: the function name)
//	LAMBDA_TRACE_CAPTURE_CONTENT=true   opt in to the event, result and error text on spans (off by default)
package tracing

import (
	"context"
	"encoding/json"
	"log"
	"os"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"go.opentelemetry.io/otel/trace"
)

const (
	FlushBudget  = 2 * time.Second        // proposed upper bound for one flush; a proposal, not a measurement
	FlushReserve = 250 * time.Millisecond // always leave this much of the remaining Lambda time unused
)

var (
	mu             sync.Mutex
	provider       *sdktrace.TracerProvider
	ProvidersBuilt atomic.Int32 // the tests assert this stays at 1 across invocations
	cold           atomic.Bool
)

func init() { cold.Store(true) }

// CaptureContent reports whether the operator opted in to event / result / error text on spans.
func CaptureContent() bool {
	return strings.EqualFold(os.Getenv("LAMBDA_TRACE_CAPTURE_CONTENT"), "true")
}

// Init builds the provider on the first call and returns it on later calls. Call it outside the
// handler. exporter may be nil: the OTLP/HTTP exporter is then built from the environment, or no
// exporter at all when a key is missing (the function still runs, nothing is exported).
func Init(exporter sdktrace.SpanExporter, setGlobal bool) *sdktrace.TracerProvider {
	mu.Lock()
	defer mu.Unlock()
	if provider != nil {
		return provider
	}
	ProvidersBuilt.Add(1)
	name := os.Getenv("FI_PROJECT_NAME")
	fn := os.Getenv("AWS_LAMBDA_FUNCTION_NAME")
	if name == "" {
		name = fn
	}
	if name == "" {
		name = "aws-lambda"
	}
	attrs := []attribute.KeyValue{
		attribute.String("project_name", name),
		attribute.String("project_type", "observe"),
		attribute.String("service.name", name),
	}
	if fn != "" { // only when the runtime provides it; never invented
		attrs = append(attrs, attribute.String("faas.name", fn))
	}
	opts := []sdktrace.TracerProviderOption{sdktrace.WithResource(resource.NewSchemaless(attrs...))}

	key, secret := os.Getenv("FI_API_KEY"), os.Getenv("FI_SECRET_KEY")
	if exporter == nil && key != "" && secret != "" {
		base := strings.TrimRight(os.Getenv("FI_BASE_URL"), "/")
		if base == "" {
			base = "https://api.futureagi.com"
		}
		exp, err := otlptracehttp.New(context.Background(),
			otlptracehttp.WithEndpointURL(base+"/tracer/v1/traces"),
			otlptracehttp.WithHeaders(map[string]string{"X-Api-Key": key, "X-Secret-Key": secret}),
			otlptracehttp.WithCompression(otlptracehttp.NoCompression), // Compatible with older self-hosted receivers
			otlptracehttp.WithTimeout(FlushBudget),                     // bounds the exporter's own retries
		)
		if err != nil {
			log.Printf("tracing off: exporter could not be built (%T)", err)
		} else {
			exporter = exp
		}
	} else if exporter == nil {
		log.Printf("FI_API_KEY / FI_SECRET_KEY not set: tracing is off, spans are not exported")
	}
	if exporter != nil {
		// Batcher + an explicit ForceFlush before return. Never wait for its timer: the
		// environment is frozen after the handler returns.
		opts = append(opts, sdktrace.WithBatcher(exporter, sdktrace.WithBatchTimeout(time.Minute)))
	}
	provider = sdktrace.NewTracerProvider(opts...)
	if setGlobal {
		otel.SetTracerProvider(provider)
	}
	return provider
}

// ResetForTests drops the provider (and shuts it down).
func ResetForTests() {
	mu.Lock()
	defer mu.Unlock()
	if provider != nil {
		_ = provider.Shutdown(context.Background())
	}
	provider = nil
	ProvidersBuilt.Store(0)
	cold.Store(true)
}

func Tracer() trace.Tracer { return Init(nil, true).Tracer("lambda-handler") }

// TakeColdStart is true for the first invocation of this execution environment only.
func TakeColdStart() bool { return cold.Swap(false) }

// ExtractParent reads W3C traceparent from an API Gateway HTTP API (payload v2) or Lambda function
// URL event. Those event shapes lower-case header names. SQS, SNS, EventBridge, ALB, REST API
// (payload v1) and X-Ray-only carriers are NOT read: those invocations start a new trace.
func ExtractParent(ctx context.Context, version string, headers map[string]string) context.Context {
	tp := headers["traceparent"]
	if version != "2.0" || tp == "" {
		return ctx
	}
	return propagation.TraceContext{}.Extract(ctx, propagation.MapCarrier{"traceparent": tp})
}

// Flush exports pending spans. Call it (defer) at the end of every invocation, success or error.
// It never fails the invocation and never waits past the time Lambda has left (ctx deadline).
func Flush(ctx context.Context) bool {
	budget := FlushBudget
	if dl, ok := ctx.Deadline(); ok {
		if left := time.Until(dl) - FlushReserve; left < budget {
			budget = left
		}
	}
	if budget <= 0 {
		log.Printf("flush skipped: not enough invocation time left, spans of this invocation are lost")
		return false
	}
	// Detach from ctx cancellation (a cancelled invocation still gets its flush attempt) but keep the budget.
	fctx, cancel := context.WithTimeout(context.WithoutCancel(ctx), budget)
	defer cancel()
	if err := Init(nil, true).ForceFlush(fctx); err != nil {
		log.Printf("flush did not complete within %s (%T), spans of this invocation may be lost", budget, err)
		return false
	}
	return true
}

func JSON(v any) string {
	b, _ := json.Marshal(v)
	if len(b) > 4000 {
		b = b[:4000]
	}
	return string(b)
}
