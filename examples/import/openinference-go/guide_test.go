package openinference_test

import (
	"bytes"
	"compress/gzip"
	"context"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
	"testing"
	"time"

	instrumentation "github.com/Arize-ai/openinference/go/openinference-instrumentation"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"go.opentelemetry.io/otel/trace"
	collector "go.opentelemetry.io/proto/otlp/collector/trace/v1"
	common "go.opentelemetry.io/proto/otlp/common/v1"
	tracepb "go.opentelemetry.io/proto/otlp/trace/v1"
	"google.golang.org/protobuf/proto"
)

const guidePath = "../../../src/pages/docs/integrations/import/openinference.mdx"

type exportBatch struct {
	spans []*tracepb.Span
	wire  []byte
}

type receiver struct {
	server *httptest.Server
	spans  chan exportBatch
}

// Decode the real exporter's wire payload, not an in-memory SDK substitute.
func newReceiver(t *testing.T, encoding string) *receiver {
	t.Helper()
	r := &receiver{spans: make(chan exportBatch, 10)}
	r.server = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		if req.Method != http.MethodPost || req.URL.Path != "/tracer/v1/traces" {
			t.Errorf("unexpected request: %s %s", req.Method, req.URL.Path)
		}
		for k, want := range map[string]string{
			"X-Api-Key": "synthetic-api-key", "X-Secret-Key": "synthetic-secret-key",
			"Content-Type": "application/x-protobuf", "Content-Encoding": encoding,
		} {
			if got := req.Header.Get(k); got != want {
				t.Errorf("header %s: got %q, want %q", k, got, want)
			}
		}
		var body io.Reader = req.Body
		if encoding == "gzip" {
			z, err := gzip.NewReader(body)
			if err != nil {
				t.Error(err)
				w.WriteHeader(http.StatusBadRequest)
				return
			}
			defer z.Close()
			body = z
		}
		data, err := io.ReadAll(body)
		var export collector.ExportTraceServiceRequest
		if err != nil {
			t.Error(err)
			w.WriteHeader(http.StatusBadRequest)
			return
		}
		if err := proto.Unmarshal(data, &export); err != nil {
			t.Error(err)
			w.WriteHeader(http.StatusBadRequest)
			return
		}
		var spans []*tracepb.Span
		for _, rs := range export.ResourceSpans {
			attrs := attributes(rs.Resource.Attributes)
			for k, want := range map[string]string{
				"project_name": "my-openinference-project", "project_type": "observe", "service.name": "go-shop",
			} {
				if got := attrs[k].GetStringValue(); got != want {
					t.Errorf("resource %s: got %q, want %q", k, got, want)
				}
			}
			for _, scope := range rs.ScopeSpans {
				spans = append(spans, scope.Spans...)
			}
		}
		r.spans <- exportBatch{spans: spans, wire: data}
		w.Header().Set("Content-Type", "application/x-protobuf")
		w.WriteHeader(http.StatusOK) // Empty protobuf ExportTraceServiceResponse.
	}))
	t.Cleanup(r.server.Close)
	return r
}

func attributes(kvs []*common.KeyValue) map[string]*common.AnyValue {
	result := make(map[string]*common.AnyValue, len(kvs))
	for _, kv := range kvs {
		result[kv.Key] = kv.Value
	}
	return result
}

func (r *receiver) collect(t *testing.T, want int) map[string]*tracepb.Span {
	t.Helper()
	result := make(map[string]*tracepb.Span)
	count := 0
	timer := time.NewTimer(10 * time.Second)
	defer timer.Stop()
	for count < want {
		select {
		case batch := <-r.spans:
			checkProductionConversion(t, batch)
			for _, span := range batch.spans {
				count++
				if _, exists := result[span.Name]; exists {
					t.Fatalf("duplicate span %q", span.Name)
				}
				result[span.Name] = span
			}
		case <-timer.C:
			t.Fatalf("received %d spans, want %d", count, want)
		}
	}
	if count != want {
		t.Fatalf("received %d spans, want %d", count, want)
	}
	select {
	case extra := <-r.spans:
		t.Fatalf("unexpected additional export: %d spans", len(extra.spans))
	default:
	}
	return result
}

func checkTree(t *testing.T, spans map[string]*tracepb.Span, kinds map[string]string) {
	t.Helper()
	root := spans["quote_order"]
	if root == nil || len(root.ParentSpanId) != 0 || len(root.TraceId) != 16 || len(root.SpanId) != 8 {
		t.Fatal("missing or invalid root")
	}
	for name, kind := range kinds {
		span := spans[name]
		if span == nil {
			t.Fatalf("missing span %q", name)
		}
		attrs := attributes(span.Attributes)
		for k, want := range map[string]string{
			"openinference.span.kind": kind, "session.id": "order-123", "user.id": "shopper-42",
		} {
			if got := attrs[k].GetStringValue(); got != want {
				t.Errorf("%s %s: got %q, want %q", name, k, got, want)
			}
		}
		if name != "quote_order" && (!bytes.Equal(span.TraceId, root.TraceId) || !bytes.Equal(span.ParentSpanId, root.SpanId)) {
			t.Errorf("%s is not a child in the root trace", name)
		}
	}
}

func TestGuideInstallContract(t *testing.T) {
	page, err := os.ReadFile(guidePath)
	if err != nil {
		t.Fatal(err)
	}
	latest, err := os.ReadFile("latest.mod")
	if err != nil {
		t.Fatal(err)
	}
	for _, module := range []string{
		"github.com/Arize-ai/openinference/go/openinference-instrumentation",
		"go.opentelemetry.io/otel",
		"go.opentelemetry.io/otel/sdk",
		"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp",
	} {
		version := regexp.MustCompile(`(?m)^\s*` + regexp.QuoteMeta(module) + `\s+(v\S+)`).FindSubmatch(latest)
		if len(version) != 2 || !bytes.Contains(page, []byte(module+"@"+string(version[1]))) {
			t.Errorf("guide install must match the latest fixture for %s", module)
		}
	}
	if !bytes.Contains(page, []byte(`export FI_OTLP_ENDPOINT="https://api.futureagi.com/tracer/v1/traces"`)) {
		t.Error("guide must configure the full Cloud trace endpoint")
	}
}

func TestGuideExample(t *testing.T) {
	page, err := os.ReadFile(guidePath)
	if err != nil {
		t.Fatal(err)
	}
	blocks := regexp.MustCompile("(?s)```go\\n(package main\\n.*?)\\n```").FindAllSubmatch(page, -1)
	if len(blocks) != 1 {
		t.Fatalf("guide must provide one runnable Go setup; found %d Go snippets", len(blocks))
	}
	spans := runGuide(t, string(blocks[0][1]))
	checkTree(t, spans, map[string]string{"quote_order": "AGENT", "calculate_total": "TOOL"})
	for _, span := range spans {
		for _, kv := range span.Attributes {
			if strings.HasPrefix(kv.Key, "input.") || strings.HasPrefix(kv.Key, "output.") || strings.HasPrefix(kv.Key, "llm.") {
				t.Errorf("metadata-only guide unexpectedly records content: %s", kv.Key)
			}
		}
	}
}

func runGuide(t *testing.T, source string) map[string]*tracepb.Span {
	t.Helper()
	r := newReceiver(t, "")
	file := filepath.Join(t.TempDir(), "main.go")
	if err := os.WriteFile(file, []byte(source), 0600); err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	cmd := exec.CommandContext(ctx, "go", "run", file)
	for _, key := range []string{"PATH", "HOME", "GOCACHE", "GOMODCACHE", "GOTOOLCHAIN", "TMPDIR", "GOTMPDIR", "GOFLAGS"} {
		if value, ok := os.LookupEnv(key); ok {
			cmd.Env = append(cmd.Env, key+"="+value)
		}
	}
	cmd.Env = append(cmd.Env,
		"GOPROXY=off", "GOSUMDB=off", "GOWORK=off",
		"FI_OTLP_ENDPOINT="+r.server.URL+"/tracer/v1/traces",
		"FI_API_KEY=synthetic-api-key", "FI_SECRET_KEY=synthetic-secret-key",
		// Manual spans must not claim automatic redaction from these flags.
		"OPENINFERENCE_HIDE_INPUTS=true", "OPENINFERENCE_HIDE_OUTPUTS=true",
	)
	output, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("guide example failed: %v\n%s", err, output)
	}
	if strings.TrimSpace(string(output)) != "Order total: 30 USD" {
		t.Fatalf("unexpected example output %q", output)
	}
	return r.collect(t, 2)
}

func TestNativeContextAndLLMConformance(t *testing.T) {
	for _, encoding := range []string{"", "gzip"} {
		t.Run("protobuf/"+map[string]string{"": "plain", "gzip": "gzip"}[encoding], func(t *testing.T) {
			r := newReceiver(t, encoding)
			compression := otlptracehttp.NoCompression
			if encoding == "gzip" {
				compression = otlptracehttp.GzipCompression
			}
			exporter, err := otlptracehttp.New(context.Background(),
				otlptracehttp.WithEndpointURL(r.server.URL+"/tracer/v1/traces"),
				otlptracehttp.WithCompression(compression),
				otlptracehttp.WithHeaders(map[string]string{"X-Api-Key": "synthetic-api-key", "X-Secret-Key": "synthetic-secret-key"}),
			)
			if err != nil {
				t.Fatal(err)
			}
			provider := sdktrace.NewTracerProvider(sdktrace.WithBatcher(exporter), sdktrace.WithResource(resource.NewSchemaless(
				attribute.String("project_name", "my-openinference-project"),
				attribute.String("project_type", "observe"), attribute.String("service.name", "go-shop"),
			)))
			ctx := instrumentation.WithSession(context.Background(), "order-123")
			ctx = instrumentation.WithUser(ctx, "shopper-42")
			ctx = instrumentation.WithMetadata(ctx, `{"team":"example"}`)
			ctx = instrumentation.WithTags(ctx, "docs", "go")
			tracer := provider.Tracer("guide-conformance")
			ctx, root := tracer.Start(ctx, "quote_order", trace.WithAttributes(attribute.String("openinference.span.kind", "AGENT")))
			instrumentation.ApplyContextAttributes(ctx, root)
			_, tool := tracer.Start(ctx, "calculate_total", trace.WithAttributes(attribute.String("openinference.span.kind", "TOOL")))
			instrumentation.ApplyContextAttributes(ctx, tool)
			tool.End()
			// Synthetic manual LLM attributes exercise the wire contract, not a model call.
			_, llm := tracer.Start(ctx, "synthetic_completion", trace.WithAttributes(
				attribute.String("openinference.span.kind", "LLM"), attribute.String("llm.model_name", "synthetic-model"),
				attribute.Int("llm.token_count.prompt", 11), attribute.Int("llm.token_count.completion", 7),
				attribute.Int("llm.token_count.total", 18),
			))
			instrumentation.ApplyContextAttributes(ctx, llm)
			llm.End()
			root.End()
			shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
			defer cancel()
			if err := provider.Shutdown(shutdownCtx); err != nil {
				t.Fatal(err)
			}
			spans := r.collect(t, 3)
			checkTree(t, spans, map[string]string{"quote_order": "AGENT", "calculate_total": "TOOL", "synthetic_completion": "LLM"})
			attrs := attributes(spans["synthetic_completion"].Attributes)
			if attrs["llm.model_name"].GetStringValue() != "synthetic-model" || attrs["llm.token_count.prompt"].GetIntValue() != 11 || attrs["llm.token_count.completion"].GetIntValue() != 7 || attrs["llm.token_count.total"].GetIntValue() != 18 {
				t.Error("model/token attributes did not survive export")
			}
			for name, span := range spans {
				attrs := attributes(span.Attributes)
				if attrs["metadata"].GetStringValue() != `{"team":"example"}` || len(attrs["tag.tags"].GetArrayValue().GetValues()) != 2 {
					t.Errorf("context metadata/tags missing on %s", name)
				}
			}
			carrier := propagation.MapCarrier{}
			propagation.Baggage{}.Inject(ctx, carrier)
			if len(carrier) != 0 {
				t.Errorf("OpenInference context leaked into baggage: %v", carrier)
			}
		})
	}
}
