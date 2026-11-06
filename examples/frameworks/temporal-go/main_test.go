package main

import (
	"context"
	"encoding/hex"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	collectortrace "go.opentelemetry.io/proto/otlp/collector/trace/v1"
	temporalotel "go.temporal.io/sdk/contrib/opentelemetry"
	"go.temporal.io/sdk/interceptor"
	"go.temporal.io/sdk/testsuite"
	"go.temporal.io/sdk/worker"
	"google.golang.org/protobuf/proto"
)

// Exercise the official interceptor and a local OTLP/HTTP receiver; no Temporal server or real credentials.
func TestWorkflowExport(t *testing.T) {
	received := make(chan *collectortrace.ExportTraceServiceRequest, 8)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/tracer/v1/traces" || r.Header.Get("X-Api-Key") != "synthetic-key" || r.Header.Get("X-Secret-Key") != "synthetic-secret" {
			http.Error(w, "wrong OTLP route or headers", http.StatusBadRequest)
			return
		}
		body, err := io.ReadAll(r.Body)
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		msg := new(collectortrace.ExportTraceServiceRequest)
		if err := proto.Unmarshal(body, msg); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		received <- msg
		w.Header().Set("Content-Type", "application/x-protobuf")
		body, _ = proto.Marshal(&collectortrace.ExportTraceServiceResponse{})
		_, _ = w.Write(body)
	}))
	defer server.Close()
	p, err := provider(context.Background(), server.URL+"/tracer/v1/traces", "synthetic-key", "synthetic-secret", "temporal-go-test")
	if err != nil {
		t.Fatal(err)
	}
	tracing, err := temporalotel.NewTracingInterceptor(temporalotel.TracerOptions{Tracer: p.Tracer("temporal-sdk-go")})
	if err != nil {
		t.Fatal(err)
	}
	var suite testsuite.WorkflowTestSuite
	env := suite.NewTestWorkflowEnvironment()
	env.RegisterWorkflow(GreetingWorkflow)
	env.RegisterActivity(GreetingActivity)
	env.SetWorkerOptions(worker.Options{Interceptors: []interceptor.WorkerInterceptor{tracing}})
	env.ExecuteWorkflow(GreetingWorkflow, "Ada")
	if err := env.GetWorkflowError(); err != nil {
		t.Fatal(err)
	}
	var result string
	if err := env.GetWorkflowResult(&result); err != nil || result != "Hello, Ada" {
		t.Fatalf("result %q: %v", result, err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := p.Shutdown(ctx); err != nil {
		t.Fatal(err)
	}
	var spans []string
	var traceIDs = map[string]string{}
	var spanIDs = map[string]string{}
	var parentIDs = map[string]string{}
	for {
		select {
		case req := <-received:
			for _, rs := range req.ResourceSpans {
				attrs := rs.Resource.GetAttributes()
				hasProject := false
				for _, a := range attrs {
					if a.Key == "project_name" && a.Value.GetStringValue() == "temporal-go-test" {
						hasProject = true
					}
				}
				if !hasProject {
					t.Fatal("project_name missing from OTLP resource")
				}
				for _, ss := range rs.ScopeSpans {
					for _, span := range ss.Spans {
						spans = append(spans, span.Name)
						traceIDs[span.Name] = hex.EncodeToString(span.TraceId)
						spanIDs[span.Name] = hex.EncodeToString(span.SpanId)
						parentIDs[span.Name] = hex.EncodeToString(span.ParentSpanId)
						if len(span.TraceId) != 16 {
							t.Fatalf("invalid trace id: %s", span.Name)
						}
					}
				}
			}
		default:
			if !strings.Contains(strings.Join(spans, ","), "RunWorkflow:GreetingWorkflow") || !strings.Contains(strings.Join(spans, ","), "RunActivity:GreetingActivity") {
				t.Fatalf("missing Temporal workflow/activity spans: %v", spans)
			}
			if len(spans) != 3 {
				t.Fatalf("unexpected duplicate or missing spans: %v", spans)
			}
			if traceIDs["RunWorkflow:GreetingWorkflow"] != traceIDs["RunActivity:GreetingActivity"] || parentIDs["StartActivity:GreetingActivity"] != spanIDs["RunWorkflow:GreetingWorkflow"] || parentIDs["RunActivity:GreetingActivity"] != spanIDs["StartActivity:GreetingActivity"] {
				t.Fatalf("activity is not child of workflow: traceIDs=%v spanIDs=%v parentIDs=%v", traceIDs, spanIDs, parentIDs)
			}
			return
		}
	}
}

func TestMissingConfiguration(t *testing.T) {
	if _, err := provider(context.Background(), "", "key", "secret", "project"); err == nil {
		t.Fatal("accepted empty OTLP endpoint")
	}
	if _, err := provider(context.Background(), "http://localhost/tracer/v1/traces", "", "secret", "project"); err == nil {
		t.Fatal("accepted empty API key")
	}
}
