package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"iter"
	"os"
	"sync"
	"time"

	"go.opentelemetry.io/contrib/processors/baggagecopy"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/baggage"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"go.opentelemetry.io/otel/trace"
	"google.golang.org/adk/agent"
	"google.golang.org/adk/agent/llmagent"
	"google.golang.org/adk/agent/workflowagents/sequentialagent"
	"google.golang.org/adk/model"
	"google.golang.org/adk/runner"
	"google.golang.org/adk/session"
	"google.golang.org/adk/tool"
	"google.golang.org/adk/tool/functiontool"
	"google.golang.org/genai"
)

const canary = "CANARY_PRIVATE_7f8916"

type fakeModel struct{ mode string }

func (m fakeModel) Name() string { return "gemini-test" }
func (m fakeModel) GenerateContent(ctx context.Context, req *model.LLMRequest, stream bool) iter.Seq2[*model.LLMResponse, error] {
	return func(yield func(*model.LLMResponse, error) bool) {
		if m.mode == "model-error" {
			yield(nil, errors.New(canary+" model failure"))
			return
		}
		if m.mode == "cancel" {
			<-ctx.Done()
			yield(nil, ctx.Err())
			return
		}
		if ctx.Err() != nil {
			yield(nil, ctx.Err())
			return
		}
		responseSeen := m.mode == "early"
		// Only examine the newest turn: previous session turns must not suppress tools.
		for i := len(req.Contents) - 1; i >= 0; i-- {
			c := req.Contents[i]
			for _, p := range c.Parts {
				if p.FunctionResponse != nil {
					responseSeen = true
				}
			}
			if c.Role == "user" {
				break
			}
		}
		usage := &genai.GenerateContentResponseUsageMetadata{PromptTokenCount: 11, CandidatesTokenCount: 7, TotalTokenCount: 20, CachedContentTokenCount: 2, ThoughtsTokenCount: 2}
		if !responseSeen {
			yield(&model.LLMResponse{Content: &genai.Content{Role: "model", Parts: []*genai.Part{{FunctionCall: &genai.FunctionCall{ID: "call-synthetic", Name: "lookup", Args: map[string]any{"query": canary}}}}}, UsageMetadata: usage, FinishReason: genai.FinishReasonStop, ModelVersion: "gemini-test-001"}, nil)
			return
		}
		if stream {
			for _, s := range []string{"Settled ", canary} {
				if !yield(&model.LLMResponse{Content: genai.NewContentFromText(s, genai.RoleModel), Partial: true}, nil) {
					return
				}
			}
		}
		yield(&model.LLMResponse{Content: genai.NewContentFromText("Settled "+canary, genai.RoleModel), UsageMetadata: usage, FinishReason: genai.FinishReasonStop, TurnComplete: true, ModelVersion: "gemini-test-001"}, nil)
	}
}

type args struct {
	Query string `json:"query"`
}
type result struct {
	Value string `json:"value"`
}

func makeAgent(mode, name string) (agent.Agent, error) {
	t, err := functiontool.New(functiontool.Config{Name: "lookup", Description: canary + " tool description"}, func(ctx agent.ToolContext, a args) (result, error) {
		if mode == "tool-error" {
			return result{}, errors.New(canary + " tool failure")
		}
		if mode == "tool-cancel" {
			<-ctx.Done()
			return result{}, ctx.Err()
		}
		return result{Value: canary}, nil
	})
	if err != nil {
		return nil, err
	}
	return llmagent.New(llmagent.Config{Name: name, Description: canary + " agent description", Instruction: canary + " system", Model: fakeModel{mode}, Tools: []tool.Tool{t}})
}

type summary struct {
	Runs          int   `json:"runs"`
	Events        int   `json:"events"`
	Errors        int   `json:"errors"`
	ShutdownMS    int64 `json:"shutdown_ms"`
	ShutdownError bool  `json:"shutdown_error"`
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
func run() error {
	mode := "normal"
	if len(os.Args) > 1 {
		mode = os.Args[1]
	}
	ctx := context.Background()
	// Standard SDK only: no ADK automatic telemetry setup, no log exporter.
	exp, err := otlptracehttp.New(ctx, otlptracehttp.WithEndpointURL(os.Getenv("TEST_ENDPOINT")), otlptracehttp.WithHeaders(map[string]string{}), otlptracehttp.WithCompression(otlptracehttp.NoCompression), otlptracehttp.WithTimeout(time.Second), otlptracehttp.WithRetry(otlptracehttp.RetryConfig{Enabled: false}))
	if err != nil {
		return err
	}
	tp := sdktrace.NewTracerProvider(sdktrace.WithSpanProcessor(baggagecopy.NewSpanProcessor(func(m baggage.Member) bool { return m.Key() == "adk.session.id" })), sdktrace.WithBatcher(exp, sdktrace.WithBatchTimeout(50*time.Millisecond)), sdktrace.WithResource(resource.NewSchemaless(attribute.String("service.name", "adk-go-test"), attribute.String("private.resource", canary))))
	if os.Getenv("TEST_DISABLE_TELEMETRY") != "1" {
		otel.SetTracerProvider(tp)
	}
	a, err := makeAgent(mode, "assistant")
	if err != nil {
		return err
	}
	if mode == "nested" {
		b, e := makeAgent(mode, "second")
		if e != nil {
			return e
		}
		a, err = sequentialagent.New(sequentialagent.Config{AgentConfig: agent.Config{Name: "pipeline", Description: canary, SubAgents: []agent.Agent{a, b}}})
		if err != nil {
			return err
		}
	}
	if mode == "workflow" {
		a, err = makeWorkflow(a)
		if err != nil {
			return err
		}
	}
	sessions := session.InMemoryService()
	r, err := runner.New(runner.Config{AppName: "adk-go-test", Agent: a, SessionService: sessions})
	if err != nil {
		return err
	}
	for _, sid := range []string{"session-a", "session-b"} {
		if _, err = sessions.Create(ctx, &session.CreateRequest{AppName: "adk-go-test", UserID: "synthetic", SessionID: sid}); err != nil {
			return err
		}
	}
	out := summary{}
	var mu sync.Mutex
	invoke := func(sid string) {
		runctx := ctx
		var cancel context.CancelFunc
		if mode == "cancel" || mode == "tool-cancel" {
			runctx, cancel = context.WithTimeout(ctx, 30*time.Millisecond)
			defer cancel()
		}
		member, err := baggage.NewMember("adk.session.id", sid)
		if err != nil {
			panic(err)
		}
		private, err := baggage.NewMember("private", canary)
		if err != nil {
			panic(err)
		}
		bag, err := baggage.New(member, private)
		if err != nil {
			panic(err)
		}
		runctx = baggage.ContextWithBaggage(runctx, bag)
		if mode == "parent" {
			var outer, inner trace.Span
			runctx, outer = otel.Tracer(canary+" http-server", trace.WithInstrumentationVersion(canary), trace.WithSchemaURL(canary), trace.WithInstrumentationAttributes(attribute.String("private", canary))).Start(runctx, canary+" request", trace.WithAttributes(attribute.String("http.target", canary), attribute.String("gen_ai.tool.name", canary)), trace.WithLinks(trace.Link{SpanContext: trace.NewSpanContext(trace.SpanContextConfig{TraceID: trace.TraceID{1}, SpanID: trace.SpanID{1}}), Attributes: []attribute.KeyValue{attribute.String("private", canary)}}))
			defer outer.End()
			runctx, inner = otel.Tracer("application-request").Start(runctx, canary+" handler")
			defer inner.End()
			inner.SetStatus(codes.Error, canary)
			inner.RecordError(errors.New(canary), trace.WithStackTrace(true))
			// Ancestors end in a different export batch from their native children.
			defer func() {
				if err := tp.ForceFlush(context.Background()); err != nil {
					panic(err)
				}
			}()
		}
		cfg := agent.RunConfig{}
		if mode == "stream" || mode == "early" {
			cfg.StreamingMode = agent.StreamingModeSSE
		}
		events, errs := 0, 0
		for event, err := range r.Run(runctx, "synthetic", sid, genai.NewContentFromText(canary+" prompt", genai.RoleUser), cfg) {
			if err != nil {
				errs++
				break
			}
			if event != nil {
				events++
			}
			if mode == "early" {
				break
			}
		}
		mu.Lock()
		out.Runs++
		out.Events += events
		out.Errors += errs
		mu.Unlock()
	}
	if mode == "concurrent" {
		var wg sync.WaitGroup
		for _, sid := range []string{"session-a", "session-a", "session-b"} {
			wg.Add(1)
			go func(s string) { defer wg.Done(); invoke(s) }(sid)
		}
		wg.Wait()
	} else {
		invoke("session-a")
	}
	if mode == "privacy" || mode == "malformed" {
		fallback, err := baggage.NewMember("adk.session.id", "fallback-session")
		if err != nil {
			return err
		}
		bag, err := baggage.New(fallback)
		if err != nil {
			return err
		}
		privacyCtx := baggage.ContextWithBaggage(ctx, bag)
		_, s := tp.Tracer("gcp.vertex.agent").Start(privacyCtx, canary+" span name", trace.WithAttributes(attribute.String("gen_ai.operation.name", "invoke_agent"), attribute.String("gen_ai.conversation.id", "native-session"), attribute.String("session.id", "explicit-session"), attribute.String("gen_ai.agent.description", canary), attribute.String("input.value", canary), attribute.String("output.value", canary), attribute.String("gen_ai.input.messages", canary), attribute.String("gen_ai.tool.call.arguments", canary), attribute.String("unknown.future.attribute", canary)))
		s.SetStatus(codes.Error, canary)
		s.RecordError(errors.New(canary), trace.WithStackTrace(true))
		s.AddEvent(canary, trace.WithAttributes(attribute.String("alias", canary)))
		if mode == "malformed" {
			s.SetAttributes(attribute.String("test.force_error", "not-json"))
		}
		s.End()
	}
	if os.Getenv("TEST_DISABLE_TELEMETRY") != "1" && otel.GetTracerProvider() != tp {
		return errors.New("ADK replaced the application-owned provider")
	}
	// Native ADK must leave an existing application provider alive after a run.
	_, ownershipSpan := tp.Tracer("application-owner").Start(ctx, "still-owned")
	if !ownershipSpan.IsRecording() {
		return errors.New("ADK shut down the application provider")
	}
	ownershipSpan.End()
	start := time.Now()
	flushctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	out.ShutdownError = tp.Shutdown(flushctx) != nil
	out.ShutdownMS = time.Since(start).Milliseconds()
	return json.NewEncoder(os.Stdout).Encode(out)
}
