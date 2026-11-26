// Test adapter for the production OTLP conversion entrypoint, not a copied mapper.
// Build from the pinned future-agi/fi-collector checkout (see crewai-docs.yml).
package main

import (
	"encoding/json"
	"os"

	"github.com/future-agi/future-agi/fi-collector/exporter/clickhouse25exporter"
	"go.opentelemetry.io/collector/pdata/ptrace"
)

func main() {
	encoder := json.NewEncoder(os.Stdout)
	for _, filename := range os.Args[1:] {
		data, err := os.ReadFile(filename)
		if err != nil {
			panic(err)
		}
		traces, err := (&ptrace.ProtoUnmarshaler{}).UnmarshalTraces(data)
		if err != nil {
			panic(err)
		}
		rows, err := clickhouse25exporter.Convert(traces)
		if err != nil {
			panic(err)
		}
		for _, row := range rows {
			if err := encoder.Encode(row); err != nil {
				panic(err)
			}
		}
	}
}
