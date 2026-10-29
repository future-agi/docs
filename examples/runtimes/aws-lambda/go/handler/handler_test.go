// Lifecycle contract of the recipe. No network beyond 127.0.0.1, no AWS client, no credentials.
package handler

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/aws/aws-lambda-go/lambdacontext"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"go.opentelemetry.io/otel/sdk/trace/tracetest"
	coltrace "go.opentelemetry.io/proto/otlp/collector/trace/v1"
	"google.golang.org/protobuf/proto"

	"example.com/lambda-tracing/tracing"
)

// recordingExporter logs "export" events in order, so tests can see exports happen before returns.
type recordingExporter struct {
	mu  sync.Mutex
	log *[]string
	in  *tracetest.InMemoryExporter
}

func newRecorder(log *[]string) *recordingExporter {
	return &recordingExporter{log: log, in: tracetest.NewInMemoryExporter()}
}
func (r *recordingExporter) ExportSpans(ctx context.Context, s []sdktrace.ReadOnlySpan) error {
	r.mu.Lock()
	*r.log = append(*r.log, "export")
	r.mu.Unlock()
	return r.in.ExportSpans(ctx, s)
}
func (r *recordingExporter) Shutdown(ctx context.Context) error { return nil }

func setup(t *testing.T, env map[string]string) {
	t.Helper()
	for _, k := range []string{"FI_API_KEY", "FI_SECRET_KEY", "FI_BASE_URL", "FI_PROJECT_NAME", "AWS_LAMBDA_FUNCTION_NAME", "LAMBDA_TRACE_CAPTURE_CONTENT"} {
		t.Setenv(k, "")
	}
	for k, v := range env {
		t.Setenv(k, v)
	}
	tracing.ResetForTests()
	t.Cleanup(tracing.ResetForTests)
}

func lctx(remaining time.Duration) (context.Context, context.CancelFunc) {
	ctx := lambdacontext.NewContext(context.Background(), &lambdacontext.LambdaContext{AwsRequestID: "req-0001"})
	if remaining > 0 {
		return context.WithTimeout(ctx, remaining)
	}
	return ctx, func() {}
}

func fixture(t *testing.T, name string) json.RawMessage {
	b, err := os.ReadFile("../testdata/" + name)
	if err != nil {
		t.Fatal(err)
	}
	return b
}

func ev(orderID, note string) json.RawMessage {
	b, _ := json.Marshal(map[string]string{"order_id": orderID, "note": note})
	return b
}

func spanAttr(s tracetest.SpanStub, key string) string {
	for _, kv := range s.Attributes {
		if string(kv.Key) == key {
			return kv.Value.Emit()
		}
	}
	return ""
}

func dump(spans tracetest.SpanStubs) string {
	var sb strings.Builder
	for _, s := range spans {
		fmt.Fprintf(&sb, "%s %v %s ", s.Name, s.Attributes, s.Status.Description)
		for _, e := range s.Events {
			fmt.Fprintf(&sb, "%v ", e.Attributes)
		}
	}
	return sb.String()
}

func TestProviderBuiltOnceAcrossInvocations(t *testing.T) {
	setup(t, nil)
	var log []string
	tracing.Init(newRecorder(&log), false)
	for i := 0; i < 2; i++ {
		ctx, c := lctx(30 * time.Second)
		if _, err := Handle(ctx, ev("A-1", "")); err != nil {
			t.Fatal(err)
		}
		c()
	}
	if n := tracing.ProvidersBuilt.Load(); n != 1 {
		t.Fatalf("providers built = %d", n)
	}
}

func TestFlushBeforeReturnOnSuccessAndError(t *testing.T) {
	setup(t, nil)
	var log []string
	rec := newRecorder(&log)
	tracing.Init(rec, false)
	ctx, c := lctx(30 * time.Second)
	defer c()
	if _, err := Handle(ctx, ev("A-1", "")); err != nil {
		t.Fatal(err)
	}
	log = append(log, "returned")
	if _, err := Handle(ctx, ev("boom", "x")); err == nil {
		t.Fatal("expected error")
	}
	log = append(log, "raised")
	// the batch timer is one minute: exports can only come from the explicit flush
	if got := strings.Join(log, ","); got != "export,returned,export,raised" {
		t.Fatalf("order = %s", got)
	}
}

func TestWarmStartIsANewTraceAndErrorIsMarked(t *testing.T) {
	setup(t, nil)
	var log []string
	rec := newRecorder(&log)
	tracing.Init(rec, false)
	ctx, c := lctx(30 * time.Second)
	defer c()
	Handle(ctx, ev("A-1", ""))
	Handle(ctx, ev("A-2", ""))
	Handle(ctx, ev("boom", "SECRET-NOTE"))
	spans := rec.in.GetSpans()
	var roots tracetest.SpanStubs
	for _, s := range spans {
		if s.Name == "lambda.handler" {
			roots = append(roots, s)
		}
	}
	if len(spans) != 6 || len(roots) != 3 {
		t.Fatalf("spans=%d roots=%d (every span must be ended and exported)", len(spans), len(roots))
	}
	if roots[0].SpanContext.TraceID() == roots[1].SpanContext.TraceID() {
		t.Fatal("warm start reused the trace")
	}
	if spanAttr(roots[0], "faas.coldstart") != "true" || spanAttr(roots[1], "faas.coldstart") != "false" {
		t.Fatal("cold start flag")
	}
	if roots[2].Status.Code.String() != "Error" || roots[2].Status.Description == "" || strings.Contains(dump(spans), "SECRET-NOTE") {
		t.Fatalf("error span: %v", roots[2].Status)
	}
	if len(roots[2].Events) != 0 {
		t.Fatal("no exception event by default")
	}
}

func TestUnsetKeysDoNotFailAndExportNothing(t *testing.T) {
	srv, got, mu := collector(t, 200, 0)
	for name, env := range map[string]map[string]string{
		"no keys":       {"FI_BASE_URL": srv.URL},
		"only a key":    {"FI_BASE_URL": srv.URL, "FI_API_KEY": "only-one"},
		"only a secret": {"FI_BASE_URL": srv.URL, "FI_SECRET_KEY": "only-one"},
	} {
		t.Run(name, func(t *testing.T) {
			setup(t, env)
			ctx, c := lctx(30 * time.Second)
			defer c()
			res, err := Handle(ctx, ev("A-1", ""))
			if err != nil || res["status"] != "shipped" {
				t.Fatalf("%v %v", res, err)
			}
			mu.Lock()
			defer mu.Unlock()
			if len(*got) != 0 {
				t.Fatalf("exported %d requests without both keys", len(*got))
			}
		})
	}
}

type captured struct {
	path    string
	headers http.Header
	body    []byte
}

func collector(t *testing.T, status int, delay time.Duration) (*httptest.Server, *[]captured, *sync.Mutex) {
	var mu sync.Mutex
	var got []captured
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		b, _ := io.ReadAll(r.Body)
		mu.Lock()
		got = append(got, captured{r.URL.Path, r.Header.Clone(), b})
		mu.Unlock()
		time.Sleep(delay)
		w.WriteHeader(status)
	}))
	t.Cleanup(srv.Close)
	return srv, &got, &mu
}

func TestHeadersResourcePathAndNoGzip(t *testing.T) {
	srv, got, mu := collector(t, 200, 0)
	setup(t, map[string]string{"FI_API_KEY": "key-1", "FI_SECRET_KEY": "secret-1", "FI_BASE_URL": srv.URL, "FI_PROJECT_NAME": "lambda-test"})
	ctx, c := lctx(30 * time.Second)
	defer c()
	if _, err := Handle(ctx, ev("A-1", "")); err != nil {
		t.Fatal(err)
	}
	mu.Lock()
	defer mu.Unlock()
	if len(*got) != 1 {
		t.Fatalf("requests = %d", len(*got))
	}
	r := (*got)[0]
	if r.path != "/tracer/v1/traces" || r.headers.Get("X-Api-Key") != "key-1" || r.headers.Get("X-Secret-Key") != "secret-1" {
		t.Fatalf("path/headers: %s %v", r.path, r.headers)
	}
	if r.headers.Get("Content-Encoding") != "" {
		t.Fatal("body must not be compressed")
	}
	var req coltrace.ExportTraceServiceRequest
	if err := proto.Unmarshal(r.body, &req); err != nil {
		t.Fatal(err)
	}
	res := map[string]string{}
	for _, kv := range req.ResourceSpans[0].Resource.Attributes {
		res[kv.Key] = kv.Value.GetStringValue()
	}
	if res["project_name"] != "lambda-test" || res["project_type"] != "observe" {
		t.Fatalf("resource: %v", res)
	}
	if _, ok := res["faas.name"]; ok {
		t.Fatal("faas.name invented")
	}
	for k := range res {
		if strings.HasPrefix(k, "host.") || strings.HasPrefix(k, "process.") {
			t.Fatalf("resource leaks %s", k)
		}
	}
}

func TestEventBodyNotExportedByDefaultAndOptIn(t *testing.T) {
	setup(t, nil)
	var log []string
	rec := newRecorder(&log)
	tracing.Init(rec, false)
	ctx, c := lctx(30 * time.Second)
	defer c()
	Handle(ctx, fixtureWithNote(t, "BODY-MARKER"))
	if d := dump(rec.in.GetSpans()); strings.Contains(d, "BODY-MARKER") || strings.Contains(d, "input.value") {
		t.Fatalf("content exported by default: %s", d)
	}

	setup(t, map[string]string{"LAMBDA_TRACE_CAPTURE_CONTENT": "true"})
	rec = newRecorder(&log)
	tracing.Init(rec, false)
	Handle(ctx, ev("A-1", "OPT-IN-MARKER"))
	Handle(ctx, ev("boom", "OPT-IN-ERR"))
	d := dump(rec.in.GetSpans())
	if !strings.Contains(d, "OPT-IN-MARKER") || !strings.Contains(d, "OPT-IN-ERR") {
		t.Fatalf("opt-in did not export content: %s", d)
	}
	if strings.Contains(d, "goroutine") || strings.Contains(d, "/Users/") {
		t.Fatal("stack or path exported")
	}
}

func fixtureWithNote(t *testing.T, note string) json.RawMessage {
	var m map[string]any
	if err := json.Unmarshal(fixture(t, "apigw_v2.json"), &m); err != nil {
		t.Fatal(err)
	}
	m["body"] = fmt.Sprintf(`{"order_id": "A-1", "note": %q}`, note)
	b, _ := json.Marshal(m)
	return b
}

func TestAPIGatewayV2TraceparentParentsTheRoot(t *testing.T) {
	setup(t, nil)
	var log []string
	rec := newRecorder(&log)
	tracing.Init(rec, false)
	ctx, c := lctx(30 * time.Second)
	defer c()
	Handle(ctx, fixture(t, "apigw_v2.json"))
	var root, tool tracetest.SpanStub
	for _, s := range rec.in.GetSpans() {
		if s.Name == "lambda.handler" {
			root = s
		} else {
			tool = s
		}
	}
	if root.SpanContext.TraceID().String() != "4bf92f3577b34da6a3ce929d0e0e4736" || root.Parent.SpanID().String() != "00f067aa0ba902b7" {
		t.Fatalf("root not parented: %s parent=%s", root.SpanContext.TraceID(), root.Parent.SpanID())
	}
	if tool.Parent.SpanID() != root.SpanContext.SpanID() {
		t.Fatal("tool span not under the root")
	}
}

func TestSQSAndV1EventsStartANewTrace(t *testing.T) {
	setup(t, nil)
	var log []string
	rec := newRecorder(&log)
	tracing.Init(rec, false)
	ctx, c := lctx(30 * time.Second)
	defer c()
	Handle(ctx, fixture(t, "sqs.json"))
	Handle(ctx, json.RawMessage(`{"headers":{"traceparent":"00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"}}`))
	bad := strings.Replace(string(fixture(t, "apigw_v2.json")), "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01", "not-a-traceparent", 1)
	Handle(ctx, json.RawMessage(bad))
	n := 0
	for _, s := range rec.in.GetSpans() {
		if s.Name != "lambda.handler" {
			continue
		}
		n++
		if s.Parent.IsValid() || s.SpanContext.TraceID().String() == "4bf92f3577b34da6a3ce929d0e0e4736" {
			t.Fatalf("unexpected parent on %v", s.Parent)
		}
	}
	if n != 3 {
		t.Fatalf("roots = %d", n)
	}
}

func TestExporterFailureNeverFailsTheInvocation(t *testing.T) {
	for name, url := range map[string]func() string{
		"503":         func() string { s, _, _ := collector(t, 503, 0); return s.URL },
		"unreachable": func() string { return "http://127.0.0.1:9" },
	} {
		t.Run(name, func(t *testing.T) {
			setup(t, map[string]string{"FI_API_KEY": "k", "FI_SECRET_KEY": "s", "FI_BASE_URL": url()})
			ctx, c := lctx(30 * time.Second)
			defer c()
			start := time.Now()
			res, err := Handle(ctx, ev("A-1", ""))
			if err != nil || res["status"] != "shipped" {
				t.Fatalf("%v %v", res, err)
			}
			if d := time.Since(start); d > 3500*time.Millisecond {
				t.Fatalf("handler held for %s", d)
			}
		})
	}
}

func TestFlushBudgetShorterThanRemainingTime(t *testing.T) {
	srv, _, _ := collector(t, 200, 5*time.Second) // a collector that answers too late
	setup(t, map[string]string{"FI_API_KEY": "k", "FI_SECRET_KEY": "s", "FI_BASE_URL": srv.URL})
	ctx, c := lctx(1 * time.Second) // 1 s left: 0.75 s budget
	defer c()
	start := time.Now()
	Handle(ctx, ev("A-1", ""))
	if d := time.Since(start); d > 1*time.Second {
		t.Fatalf("flush outlived the invocation: %s", d)
	}
}

func TestFlushSkippedWhenNoTimeLeft(t *testing.T) {
	setup(t, nil)
	var log []string
	tracing.Init(newRecorder(&log), false)
	ctx, c := lctx(100 * time.Millisecond)
	defer c()
	if res, err := Handle(ctx, ev("A-1", "")); err != nil || res["status"] != "shipped" {
		t.Fatal(err)
	}
	if len(log) != 0 {
		t.Fatalf("exported with no time left: %v", log)
	}
}

func TestCancelledContextStillAttemptsFlush(t *testing.T) {
	setup(t, nil)
	var log []string
	tracing.Init(newRecorder(&log), false)
	base, c := lctx(30 * time.Second)
	ctx, cancel := context.WithCancel(base)
	defer c()
	cancel() // the invocation context is already cancelled when the handler runs
	Handle(ctx, ev("A-1", ""))
	if len(log) != 1 {
		t.Fatalf("flush not attempted on a cancelled context: %v", log)
	}
}
