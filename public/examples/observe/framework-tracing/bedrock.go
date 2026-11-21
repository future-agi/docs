package main

import (
	"context"
	"errors"
	"fmt"
	"os"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/bedrockruntime"
	"github.com/aws/aws-sdk-go-v2/service/bedrockruntime/types"
	b "github.com/future-agi/traceAI/go/bedrock"
)

func run() (err error) {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	tp, err := provider(ctx)
	if err != nil {
		return err
	}
	defer func() { err = errors.Join(err, tp.Shutdown(context.Background())) }()
	cfg, err := config.LoadDefaultConfig(ctx)
	if err != nil {
		return err
	}
	client := b.NewClient(bedrockruntime.NewFromConfig(cfg), b.WithTracerProvider(tp))
	ctx = b.ContextWithSessionID(ctx, "ridgeline-care")
	model := os.Getenv("BEDROCK_MODEL_ID")
	if model == "" {
		return errors.New("set BEDROCK_MODEL_ID")
	}
	messages := []types.Message{{Role: types.ConversationRoleUser, Content: []types.ContentBlock{
		&types.ContentBlockMemberText{Value: "Give one care tip for a Ridgeline rain shell."},
	}}}
	limits := &types.InferenceConfiguration{MaxTokens: aws.Int32(100)}
	_, err = client.Converse(ctx, &bedrockruntime.ConverseInput{ModelId: &model, Messages: messages, InferenceConfig: limits})
	if err != nil {
		return err
	}
	response, err := client.ConverseStream(ctx, &bedrockruntime.ConverseStreamInput{ModelId: &model, Messages: messages, InferenceConfig: limits})
	if err != nil {
		return err
	}
	stream := response.GetStream()
	defer stream.Close()
	for event := range stream.Events() {
		if d, ok := event.(*types.ConverseStreamOutputMemberContentBlockDelta); ok {
			if text, ok := d.Value.Delta.(*types.ContentBlockDeltaMemberText); ok {
				fmt.Print(text.Value)
			}
		}
	}
	fmt.Println()
	return stream.Err()
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
