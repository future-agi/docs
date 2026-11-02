package openinference_test

import (
	"bytes"
	"context"
	"encoding/hex"
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// INGESTION_CHECK is built from the production collector, not a copied mapper.
// The workflow sets it for both dependency versions. A local wire-only test may
// omit it; that skip is explicit. Authentication/project resolution need a real
// deployment and are deliberately outside this synthetic conversion contract.
func checkProductionConversion(t *testing.T, batch exportBatch) {
	t.Helper()
	t.Run("production-conversion", func(t *testing.T) {
		binary := os.Getenv("INGESTION_CHECK")
		if binary == "" {
			t.Skip("set INGESTION_CHECK to the compiled scripts/crewai-ingestion-check adapter")
		}
		filename := filepath.Join(t.TempDir(), "export.pb")
		if err := os.WriteFile(filename, batch.wire, 0600); err != nil {
			t.Fatal(err)
		}
		ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer cancel()
		output, err := exec.CommandContext(ctx, binary, filename).CombinedOutput()
		if err != nil {
			t.Fatalf("production conversion failed: %v\n%s", err, output)
		}
		lines := bytes.Split(bytes.TrimSpace(output), []byte("\n"))
		if len(lines) != len(batch.spans) {
			t.Fatalf("converted %d rows from %d spans", len(lines), len(batch.spans))
		}
		for i, line := range lines {
			var row map[string]any
			if err := json.Unmarshal(line, &row); err != nil {
				t.Fatal(err)
			}
			span := batch.spans[i]
			attrs := attributes(span.Attributes)
			for key, want := range map[string]any{
				"name":              span.Name,
				"id":                hex.EncodeToString(span.SpanId),
				"parent_span_id":    hex.EncodeToString(span.ParentSpanId),
				"service_name":      "go-shop",
				"observation_type":  strings.ToLower(attrs["openinference.span.kind"].GetStringValue()),
				"model":             attrs["llm.model_name"].GetStringValue(),
				"prompt_tokens":     float64(attrs["llm.token_count.prompt"].GetIntValue()),
				"completion_tokens": float64(attrs["llm.token_count.completion"].GetIntValue()),
				"total_tokens":      float64(attrs["llm.token_count.total"].GetIntValue()),
				"input":             "", "output": "",
			} {
				if got := row[key]; got != want {
					t.Errorf("%s %s: got %v, want %v", span.Name, key, got, want)
				}
			}
			traceID, ok := row["trace_id"].(string)
			if !ok || strings.ReplaceAll(traceID, "-", "") != hex.EncodeToString(span.TraceId) {
				t.Errorf("%s lost trace ID: %v", span.Name, row["trace_id"])
			}
			for group, expected := range map[string]map[string]string{
				"resource_attrs": {"project_name": "my-openinference-project", "project_type": "observe"},
				"attrs_string":   {"session.id": "order-123", "user.id": "shopper-42"},
			} {
				values, ok := row[group].(map[string]any)
				if !ok {
					t.Fatalf("missing converted %s", group)
				}
				for key, want := range expected {
					if got := values[key]; got != want {
						t.Errorf("%s %s.%s: got %v, want %v", span.Name, group, key, got, want)
					}
				}
			}
		}
	})
}
