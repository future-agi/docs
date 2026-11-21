package main

import (
	"context"
	"errors"
	"fmt"
	"os"

	"github.com/anthropics/anthropic-sdk-go"
	"github.com/anthropics/anthropic-sdk-go/option"
	a "github.com/future-agi/traceAI/go/anthropic"
	"go.opentelemetry.io/otel"
)

func run() (err error) {
	ctx := context.Background()
	tp, err := provider(ctx)
	if err != nil {
		return err
	}
	defer func() { err = errors.Join(err, tp.Shutdown(ctx)) }()
	otel.SetTracerProvider(tp)
	client := anthropic.NewClient(option.WithMiddleware(a.Middleware()))
	model := os.Getenv("ANTHROPIC_MODEL")
	if model == "" {
		return errors.New("set ANTHROPIC_MODEL")
	}
	stream := client.Messages.NewStreaming(ctx, anthropic.MessageNewParams{
		Model: anthropic.Model(model), MaxTokens: 100,
		Messages: []anthropic.MessageParam{anthropic.NewUserMessage(anthropic.NewTextBlock("Give one care tip for a Ridgeline rain shell."))},
	})
	defer stream.Close()
	var reply anthropic.Message
	for stream.Next() {
		if err := reply.Accumulate(stream.Current()); err != nil {
			return err
		}
	}
	if err := stream.Err(); err != nil {
		return err
	}
	fmt.Println("Output tokens:", reply.Usage.OutputTokens)
	return nil
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
