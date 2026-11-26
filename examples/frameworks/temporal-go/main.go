package main

import (
	"context"
	"errors"
	"fmt"
	"log"
	"os"
	"time"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"go.temporal.io/sdk/client"
	temporalotel "go.temporal.io/sdk/contrib/opentelemetry"
	"go.temporal.io/sdk/interceptor"
	"go.temporal.io/sdk/worker"
	"go.temporal.io/sdk/workflow"
)

const queue = "futureagi-example"

func provider(ctx context.Context, endpoint, apiKey, secretKey, project string) (*sdktrace.TracerProvider, error) {
	if endpoint == "" || apiKey == "" || secretKey == "" || project == "" {
		return nil, errors.New("FI_TRACES_URL, FI_API_KEY, FI_SECRET_KEY and FI_PROJECT_NAME are required")
	}
	exporter, err := otlptracehttp.New(ctx, otlptracehttp.WithEndpointURL(endpoint), otlptracehttp.WithHeaders(map[string]string{
		"X-Api-Key": apiKey, "X-Secret-Key": secretKey,
	}))
	if err != nil {
		return nil, err
	}
	return sdktrace.NewTracerProvider(
		sdktrace.WithResource(resource.NewWithAttributes("", attribute.String("project_name", project), attribute.String("project_type", "observe"), attribute.String("service.name", "temporal-go-example"))),
		sdktrace.WithBatcher(exporter),
	), nil
}

// Workflow code is deterministic. Put network calls and their instrumentation in activities.
func GreetingWorkflow(ctx workflow.Context, name string) (string, error) {
	ctx = workflow.WithActivityOptions(ctx, workflow.ActivityOptions{StartToCloseTimeout: time.Minute})
	var result string
	err := workflow.ExecuteActivity(ctx, GreetingActivity, name).Get(ctx, &result)
	return result, err
}

func GreetingActivity(ctx context.Context, name string) (string, error) {
	// Replace this activity's body with your model/tool call and its Go instrumentor.
	return "Hello, " + name, nil
}

func run(ctx context.Context, mode, name string, p *sdktrace.TracerProvider) error {
	tracing, err := temporalotel.NewTracingInterceptor(temporalotel.TracerOptions{Tracer: p.Tracer("temporal-sdk-go")})
	if err != nil {
		return err
	}
	c, err := client.Dial(client.Options{
		HostPort:     os.Getenv("TEMPORAL_ADDRESS"),
		Interceptors: []interceptor.ClientInterceptor{tracing},
	})
	if err != nil {
		return err
	}
	defer c.Close()
	if mode == "worker" {
		w := worker.New(c, queue, worker.Options{})
		w.RegisterWorkflow(GreetingWorkflow)
		w.RegisterActivity(GreetingActivity)
		return w.Run(worker.InterruptCh())
	}
	if mode != "starter" {
		return fmt.Errorf("mode must be worker or starter")
	}
	execution, err := c.ExecuteWorkflow(ctx, client.StartWorkflowOptions{
		ID: fmt.Sprintf("greeting-%d", time.Now().UnixNano()), TaskQueue: queue,
	}, GreetingWorkflow, name)
	if err != nil {
		return err
	}
	var result string
	if err := execution.Get(ctx, &result); err != nil {
		return err
	}
	fmt.Println(result)
	return nil
}

func main() {
	if err := execute(); err != nil {
		log.Fatal(err)
	}
}

func execute() error {
	ctx := context.Background()
	endpoint := os.Getenv("FI_TRACES_URL")
	if endpoint == "" {
		endpoint = "https://api.futureagi.com/tracer/v1/traces"
	}
	p, err := provider(ctx, endpoint, os.Getenv("FI_API_KEY"), os.Getenv("FI_SECRET_KEY"), os.Getenv("FI_PROJECT_NAME"))
	if err != nil {
		return err
	}
	defer func() {
		flushCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		if err := p.Shutdown(flushCtx); err != nil {
			log.Printf("tracing shutdown: %v", err)
		}
	}()
	mode := "starter"
	if len(os.Args) > 1 {
		mode = os.Args[1]
	}
	name := "Ada"
	if len(os.Args) > 2 {
		name = os.Args[2]
	}
	return run(ctx, mode, name, p)
}
