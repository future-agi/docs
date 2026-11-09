package openinference_test

import (
	"os"
	"regexp"
	"strings"
	"testing"

	tracepb "go.opentelemetry.io/proto/otlp/trace/v1"
)

func TestManualGoErrorGuidance(t *testing.T) {
	page, err := os.ReadFile(guidePath)
	if err != nil {
		t.Fatal(err)
	}
	mainBlock := regexp.MustCompile("(?s)```go\\n(package main\\n.*?)\\n```").FindSubmatch(page)
	errorBlock := regexp.MustCompile("(?s)### Record failed Go operations\\n.*?```go\\n(.*?)\\n```").FindSubmatch(page)
	if len(mainBlock) != 2 || len(errorBlock) != 2 {
		t.Fatal("guide must provide a runnable Go setup and explicit manual-error guidance")
	}
	for _, tc := range []struct {
		name       string
		nilError   bool
		recordOnly bool
		status     tracepb.Status_StatusCode
		message    string
		events     int
	}{
		{"record-error-and-status", false, false, tracepb.Status_STATUS_CODE_ERROR, "Order calculation failed", 1},
		{"no-error", true, false, tracepb.Status_STATUS_CODE_UNSET, "", 0},
		{"record-error-only", false, true, tracepb.Status_STATUS_CODE_UNSET, "", 1},
	} {
		t.Run(tc.name, func(t *testing.T) {
			snippet := string(errorBlock[1])
			imports := "\"context\"\n\"errors\""
			if tc.recordOnly {
				// Negative control: RecordError alone must not imply ERROR status.
				statusCall := regexp.MustCompile(`(?m)^\s*span\.SetStatus\(codes\.Error, "Order calculation failed"\)\s*$`)
				if len(statusCall.FindAllString(snippet, -1)) != 1 {
					t.Fatal("manual-error example must set a non-sensitive ERROR status")
				}
				snippet = statusCall.ReplaceAllString(snippet, "")
			} else {
				imports += "\n\"go.opentelemetry.io/otel/codes\""
			}
			// Execute the exact documented error block inside the documented setup.
			source := strings.Replace(string(mainBlock[1]), `"context"`, imports, 1)
			operation := "err = errors.New(\"Synthetic operation failure\")\n"
			if tc.nilError {
				operation += "err = nil\n"
			}
			operation += "span := tool\n" + snippet + "\n    tool.End()"
			if strings.Count(source, "    tool.End()") != 1 {
				t.Fatal("expected one tool span end in guide setup")
			}
			source = strings.Replace(source, "    tool.End()", operation, 1)
			spans := runGuide(t, source)
			checkTree(t, spans, map[string]string{"quote_order": "AGENT", "calculate_total": "TOOL"})
			if spans["quote_order"].GetStatus().GetCode() != tracepb.Status_STATUS_CODE_UNSET {
				t.Fatal("child error must not automatically change the parent status")
			}
			span := spans["calculate_total"]
			if span.GetStatus().GetCode() != tc.status || span.GetStatus().GetMessage() != tc.message {
				t.Fatalf("got status=%s message=%q; want %s %q", span.GetStatus().GetCode(), span.GetStatus().GetMessage(), tc.status, tc.message)
			}
			if len(span.Events) != tc.events {
				t.Fatalf("got %d events, want %d", len(span.Events), tc.events)
			}
			if tc.events > 0 {
				event := span.Events[0]
				if event.Name != "exception" || attributes(event.Attributes)["exception.message"].GetStringValue() != "Synthetic operation failure" {
					t.Fatalf("missing recorded exception: %v", event)
				}
			}
			t.Logf("status=%s status_message=%q exception_events=%d", span.GetStatus().GetCode(), span.GetStatus().GetMessage(), len(span.Events))
		})
	}
}
