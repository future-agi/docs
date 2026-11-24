package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"reflect"
	"strings"
	"testing"

	traceaigenai "github.com/future-agi/traceAI/go/genai"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"go.opentelemetry.io/otel/sdk/trace/tracetest"
	"google.golang.org/genai"
)

const (
	privatePrompt = "PRIVATE_PROMPT_970"
	privateAnswer = "PRIVATE_ANSWER_970"
	privateCity   = "PRIVATE_CITY_970"
	toolReply     = `{"candidates":[{"content":{"role":"model","parts":[{"functionCall":{"name":"get_weather","id":"call_1","args":{"city":"PRIVATE_CITY_970"}},"thoughtSignature":"c2ln"}]},"finishReason":"STOP","index":0}]}`
	answerReply   = `{"candidates":[{"content":{"role":"model","parts":[{"text":"PRIVATE_ANSWER_970"}]},"finishReason":"STOP","index":0}]}`
)

type roundTripFunc func(*http.Request) (*http.Response, error)

func (f roundTripFunc) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }

func response(r *http.Request, status int, contentType, body string) *http.Response {
	return &http.Response{
		StatusCode: status,
		Header:     http.Header{"Content-Type": []string{contentType}},
		Body:       io.NopCloser(strings.NewReader(body)),
		Request:    r,
	}
}

func privacyEnv(t *testing.T, inputText, outputText, allContent bool) {
	t.Helper()
	for _, name := range []string{
		"FI_HIDE_INPUTS", "FI_HIDE_OUTPUTS", "FI_HIDE_INPUT_TEXT", "FI_HIDE_OUTPUT_TEXT",
		"FI_HIDE_INPUT_MESSAGES", "FI_HIDE_OUTPUT_MESSAGES", "FI_HIDE_INPUT_IMAGES",
		"FI_HIDE_LLM_INVOCATION_PARAMETERS", "FI_HIDE_ERROR_DETAILS",
	} {
		t.Setenv(name, "")
	}
	t.Setenv("FI_HIDE_INPUT_TEXT", fmt.Sprint(inputText))
	t.Setenv("FI_HIDE_OUTPUT_TEXT", fmt.Sprint(outputText))
	t.Setenv("FI_HIDE_INPUTS", fmt.Sprint(allContent))
	t.Setenv("FI_HIDE_OUTPUTS", fmt.Sprint(allContent))
}

func recordingProvider(t *testing.T) (*sdktrace.TracerProvider, *tracetest.InMemoryExporter) {
	t.Helper()
	exporter := tracetest.NewInMemoryExporter()
	provider := sdktrace.NewTracerProvider(sdktrace.WithSyncer(exporter))
	t.Cleanup(func() {
		if err := provider.Shutdown(context.Background()); err != nil {
			t.Error(err)
		}
	})
	return provider, exporter
}

func attributes(span tracetest.SpanStub) map[string]string {
	attrs := make(map[string]string, len(span.Attributes))
	for _, kv := range span.Attributes {
		attrs[string(kv.Key)] = kv.Value.AsString()
	}
	return attrs
}

// Exercise the real application functions and released transport with synthetic
// Gemini responses. No external service or credential is needed.
func TestAgentAndToolSpansContainOnlyMetadata(t *testing.T) {
	for _, privacy := range []struct {
		name                  string
		inputText, outputText bool
		allContent            bool
	}{
		{name: "default"},
		{name: "input_text", inputText: true},
		{name: "output_text", outputText: true},
		{name: "both_text", inputText: true, outputText: true},
		{name: "inputs_and_outputs", allContent: true},
	} {
		for _, stream := range []bool{false, true} {
			t.Run(fmt.Sprintf("%s/stream=%t", privacy.name, stream), func(t *testing.T) {
				privacyEnv(t, privacy.inputText, privacy.outputText, privacy.allContent)
				tp, exporter := recordingProvider(t)
				var requests []string
				transport := roundTripFunc(func(r *http.Request) (*http.Response, error) {
					body, err := io.ReadAll(r.Body)
					_ = r.Body.Close()
					if err != nil {
						return nil, err
					}
					requests = append(requests, string(body))
					if len(requests) == 1 {
						return response(r, 200, "application/json", toolReply), nil
					}
					if len(requests) != 2 {
						return nil, fmt.Errorf("unexpected model call %d", len(requests))
					}
					if stream {
						return response(r, 200, "text/event-stream", "data: "+answerReply+"\n\n"), nil
					}
					return response(r, 200, "application/json", answerReply), nil
				})
				client, err := genai.NewClient(context.Background(), &genai.ClientConfig{
					APIKey:  "synthetic-gemini-key",
					Backend: genai.BackendGeminiAPI,
					HTTPClient: traceaigenai.WrapClient(&http.Client{Transport: transport},
						traceaigenai.WithTracerProvider(tp)),
				})
				if err != nil {
					t.Fatal(err)
				}
				ctx := traceaigenai.ContextWithSessionID(context.Background(), "session-970")
				ctx = traceaigenai.ContextWithUserID(ctx, "user-970")
				answer, err := runAgent(ctx, client, tp.Tracer("gemini-go-example"), "gemini-3.8-flash", privatePrompt, stream)
				if err != nil || answer != privateAnswer {
					t.Fatalf("answer = %q, error = %v", answer, err)
				}
				if len(requests) != 2 || !strings.Contains(requests[0], privatePrompt) ||
					!strings.Contains(requests[1], privateCity) || !strings.Contains(requests[1], "functionResponse") {
					t.Fatalf("privacy settings changed the application requests: %v", requests)
				}

				spans := exporter.GetSpans()
				if len(spans) != 4 {
					t.Fatalf("got %d spans, want agent, tool and two LLM spans", len(spans))
				}
				var agent tracetest.SpanStub
				custom := 0
				for _, span := range spans {
					var want map[string]string
					switch span.Name {
					case "weather-agent":
						agent = span
						want = map[string]string{
							traceaigenai.GenAISpanKind:      traceaigenai.SpanKindAgent,
							traceaigenai.GenAIOperationName: "invoke_agent",
							"gen_ai.agent.name":             "weather-agent",
							"session.id":                    "session-970",
							"user.id":                       "user-970",
						}
					case "execute_tool get_weather":
						want = map[string]string{
							traceaigenai.GenAISpanKind:      traceaigenai.SpanKindTool,
							traceaigenai.GenAIOperationName: "execute_tool",
							traceaigenai.GenAIToolName:      "get_weather",
							traceaigenai.GenAIToolCallID:    "call_1",
							"session.id":                    "session-970",
							"user.id":                       "user-970",
						}
					default:
						continue
					}
					custom++
					if got := attributes(span); !reflect.DeepEqual(got, want) {
						t.Errorf("%s attributes = %v, want only %v", span.Name, got, want)
					}
					if span.Status.Code != codes.Unset || span.Status.Description != "" || len(span.Events) != 0 {
						t.Errorf("%s unexpectedly carries status text or events", span.Name)
					}
				}
				if custom != 2 || !agent.SpanContext.IsValid() || agent.Parent.IsValid() {
					t.Fatal("missing custom spans or invalid root agent")
				}
				for _, span := range spans {
					if span.Name != "weather-agent" && (span.Parent.SpanID() != agent.SpanContext.SpanID() ||
						span.SpanContext.TraceID() != agent.SpanContext.TraceID()) {
						t.Errorf("%s is not a child of the agent", span.Name)
					}
				}

				encoded, err := json.Marshal(spans)
				if err != nil {
					t.Fatal(err)
				}
				for marker, hidden := range map[string]bool{
					privatePrompt: privacy.inputText || privacy.allContent,
					privateAnswer: privacy.outputText || privacy.allContent,
					privateCity:   privacy.allContent,
				} {
					if strings.Contains(string(encoded), marker) == hidden {
						t.Errorf("exported marker %s: hidden = %t", marker, hidden)
					}
				}
			})
		}
	}
}

func TestAgentErrorKeepsStatusWithoutContent(t *testing.T) {
	privacyEnv(t, true, true, false)
	tp, exporter := recordingProvider(t)
	client, err := genai.NewClient(context.Background(), &genai.ClientConfig{
		APIKey:  "synthetic-gemini-key",
		Backend: genai.BackendGeminiAPI,
		HTTPClient: traceaigenai.WrapClient(&http.Client{Transport: roundTripFunc(func(r *http.Request) (*http.Response, error) {
			_ = r.Body.Close()
			return response(r, 400, "application/json",
				`{"error":{"code":400,"status":"INVALID_ARGUMENT","message":"PRIVATE_PROMPT_970"}}`), nil
		})}, traceaigenai.WithTracerProvider(tp)),
	})
	if err != nil {
		t.Fatal(err)
	}
	ctx := traceaigenai.ContextWithSessionID(context.Background(), "session-970")
	_, err = runAgent(ctx, client, tp.Tracer("gemini-go-example"), "gemini-3.8-flash", privatePrompt, false)
	if err == nil || !strings.Contains(err.Error(), privatePrompt) {
		t.Fatalf("application error was lost or changed: %v", err)
	}
	spans := exporter.GetSpans()
	if len(spans) != 2 {
		t.Fatalf("got %d spans, want agent and failed LLM", len(spans))
	}
	var foundAgent bool
	for _, span := range spans {
		if span.Name == "weather-agent" {
			foundAgent = true
			if span.Status.Code != codes.Error || span.Status.Description != "agent failed" ||
				attributes(span)["session.id"] != "session-970" {
				t.Errorf("agent lost error status or session metadata: %+v", span)
			}
		}
	}
	if !foundAgent {
		t.Fatal("missing agent span")
	}
	encoded, err := json.Marshal(spans)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(encoded), privatePrompt) {
		t.Fatal("prompt leaked through an error span")
	}
}

// Pin the documented v0.1.1 distinction: text-only switches do not redact
// arbitrary aggregate attributes passed to SetAttributes; full hiding does.
func TestSetAttributesAggregatePrivacyBoundary(t *testing.T) {
	for _, allContent := range []bool{false, true} {
		t.Run(fmt.Sprintf("all_content=%t", allContent), func(t *testing.T) {
			privacyEnv(t, true, true, allContent)
			tp, exporter := recordingProvider(t)
			_, span := tp.Tracer("privacy-boundary").Start(context.Background(), "aggregate-values")
			traceaigenai.TraceConfigFromEnv().SetAttributes(span,
				attribute.String(traceaigenai.InputValue, privatePrompt),
				attribute.String(traceaigenai.OutputValue, privateAnswer))
			span.End()
			spans := exporter.GetSpans()
			if len(spans) != 1 {
				t.Fatalf("got %d spans, want one", len(spans))
			}
			wantInput, wantOutput := privatePrompt, privateAnswer
			if allContent {
				wantInput, wantOutput = traceaigenai.RedactedValue, traceaigenai.RedactedValue
			}
			got := attributes(spans[0])
			if got[traceaigenai.InputValue] != wantInput || got[traceaigenai.OutputValue] != wantOutput {
				t.Fatalf("aggregate privacy behavior changed: %v", got)
			}
		})
	}
}
