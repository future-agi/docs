// Package handler is an example Lambda handler: one invocation is one trace, flushed before the
// handler returns.
package handler

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"

	"github.com/aws/aws-lambda-go/lambdacontext"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"

	"example.com/lambda-tracing/tracing"
)

type event struct {
	Version        string            `json:"version"`
	Headers        map[string]string `json:"headers"`
	Body           string            `json:"body"`
	RequestContext json.RawMessage   `json:"requestContext"`
	Records        []struct {
		Body string `json:"body"`
	} `json:"Records"`
	OrderID string `json:"order_id"`
	Note    string `json:"note"`
}

func lookupOrder(ctx context.Context, orderID, note string) (map[string]any, error) {
	ctx, span := tracing.Tracer().Start(ctx, "lookup_order", trace.WithAttributes(
		attribute.String("fi.span.kind", "TOOL"), attribute.String("tool.name", "lookup_order")))
	defer span.End()
	capture := tracing.CaptureContent()
	if capture {
		span.SetAttributes(attribute.String("input.value", tracing.JSON(map[string]string{"order_id": orderID, "note": note})))
	}
	if orderID == "boom" {
		err := fmt.Errorf("order lookup failed: %s", note)
		fail(span, err, capture)
		return nil, err
	}
	res := map[string]any{"order_id": orderID, "status": "shipped", "note": note}
	if capture {
		span.SetAttributes(attribute.String("output.value", tracing.JSON(res)))
	}
	_ = ctx
	return res, nil
}

// fail marks the span as an error. The status carries the error type only, unless the operator
// opted in to content. No RecordError: it attaches a stack trace, which carries file paths.
func fail(span trace.Span, err error, capture bool) {
	typ := fmt.Sprintf("%T", errors.Unwrap(err))
	if errors.Unwrap(err) == nil {
		typ = fmt.Sprintf("%T", err)
	}
	span.SetAttributes(attribute.String("error.type", typ))
	if capture {
		span.SetStatus(codes.Error, err.Error())
		span.AddEvent("exception", trace.WithAttributes(attribute.String("exception.type", typ), attribute.String("exception.message", err.Error())))
	} else {
		span.SetStatus(codes.Error, typ)
	}
}

func invoke(ctx context.Context, raw json.RawMessage) (map[string]any, error) {
	var ev event
	_ = json.Unmarshal(raw, &ev)                             // an unparsable event is still an invocation
	ctx = tracing.ExtractParent(ctx, ev.Version, ev.Headers) // no-op unless API Gateway v2 / function URL

	trigger := "other"
	if ev.Version == "2.0" && len(ev.RequestContext) > 0 {
		trigger = "http"
	}
	attrs := []attribute.KeyValue{
		attribute.String("fi.span.kind", "CHAIN"),
		attribute.Bool("faas.coldstart", tracing.TakeColdStart()),
		attribute.String("faas.trigger", trigger),
	}
	if lc, ok := lambdacontext.FromContext(ctx); ok && lc.AwsRequestID != "" {
		attrs = append(attrs, attribute.String("faas.invocation_id", lc.AwsRequestID))
	}
	ctx, span := tracing.Tracer().Start(ctx, "lambda.handler", trace.WithSpanKind(trace.SpanKindServer), trace.WithAttributes(attrs...))
	defer span.End()
	capture := tracing.CaptureContent()
	if capture {
		span.SetAttributes(attribute.String("input.value", tracing.JSON(json.RawMessage(raw))))
	}

	body := ev.Body
	if len(ev.Records) > 0 {
		body = ev.Records[0].Body // SQS: first record
	}
	order := struct {
		OrderID string `json:"order_id"`
		Note    string `json:"note"`
	}{ev.OrderID, ev.Note}
	if body != "" {
		_ = json.Unmarshal([]byte(body), &order)
	}
	if order.OrderID == "" {
		order.OrderID = "unknown"
	}
	res, err := lookupOrder(ctx, order.OrderID, order.Note)
	if err != nil {
		fail(span, err, capture)
		return nil, err
	}
	if capture {
		span.SetAttributes(attribute.String("output.value", tracing.JSON(res)))
	}
	return res, nil
}

// Handle is the Lambda handler. Register it with lambda.Start(handler.Handle).
func Handle(ctx context.Context, raw json.RawMessage) (map[string]any, error) {
	// invoke has returned, so the root span has ended before the deferred flush runs: flush on the
	// success path and the error path, before the runtime freezes the environment.
	defer tracing.Flush(ctx)
	return invoke(ctx, raw)
}
