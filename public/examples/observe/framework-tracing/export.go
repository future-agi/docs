package main

import (
	"context"
	"errors"
	"os"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
)

func provider(ctx context.Context) (*sdktrace.TracerProvider, error) {
	key, secret := os.Getenv("FI_API_KEY"), os.Getenv("FI_SECRET_KEY")
	if key == "" || secret == "" {
		return nil, errors.New("set FI_API_KEY and FI_SECRET_KEY")
	}
	endpoint := os.Getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
	if endpoint == "" {
		endpoint = "https://api.futureagi.com/tracer/v1/traces"
	}
	exp, err := otlptracehttp.New(ctx, otlptracehttp.WithEndpointURL(endpoint),
		otlptracehttp.WithCompression(otlptracehttp.NoCompression),
		otlptracehttp.WithHeaders(map[string]string{"X-Api-Key": key, "X-Secret-Key": secret}))
	if err != nil {
		return nil, err
	}
	return sdktrace.NewTracerProvider(sdktrace.WithBatcher(exp), sdktrace.WithResource(resource.NewSchemaless(
		attribute.String("project_name", "ridgeline-framework-tracing"), attribute.String("project_type", "observe"),
	))), nil
}
