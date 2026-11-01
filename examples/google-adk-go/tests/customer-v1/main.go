package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"time"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"google.golang.org/adk/agent"
	"google.golang.org/adk/agent/llmagent"
	"google.golang.org/adk/model/gemini"
	"google.golang.org/adk/runner"
	"google.golang.org/adk/session"
	"google.golang.org/adk/tool"
	"google.golang.org/adk/tool/functiontool"
	"google.golang.org/genai"
)

type StockRequest struct {
	SKU string `json:"sku"`
}
type StockResult struct {
	Available int `json:"available"`
}

func main() {
	if err := run(); err != nil {
		log.Fatal(err)
	}
}

func run() error {
	ctx := context.Background()
	exporter, err := otlptracehttp.New(ctx, otlptracehttp.WithTimeout(5*time.Second))
	if err != nil {
		return err
	}
	provider := sdktrace.NewTracerProvider(sdktrace.WithBatcher(exporter))
	otel.SetTracerProvider(provider)
	defer func() {
		// Do not reuse a cancelled request context when flushing completed spans.
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		if err := provider.Shutdown(shutdownCtx); err != nil {
			log.Printf("Trace shutdown: %v", err)
		}
	}()

	stock, err := functiontool.New(functiontool.Config{
		Name: "get_stock", Description: "Get available inventory for a product SKU.",
	}, func(_ agent.ToolContext, request StockRequest) (StockResult, error) {
		inventory := map[string]int{"NOTEBOOK-A5": 24}
		return StockResult{Available: inventory[request.SKU]}, nil
	})
	if err != nil {
		return err
	}
	llm, err := gemini.NewModel(ctx, os.Getenv("GOOGLE_MODEL"), &genai.ClientConfig{
		Backend: genai.BackendGeminiAPI, APIKey: os.Getenv("GOOGLE_API_KEY"),
	})
	if err != nil {
		return err
	}
	assistant, err := llmagent.New(llmagent.Config{
		Name: "inventory_assistant", Model: llm,
		Instruction: "Use get_stock to answer inventory questions.",
		Tools:       []tool.Tool{stock},
	})
	if err != nil {
		return err
	}
	sessions := session.InMemoryService()
	const appName, userID, sessionID = "inventory", "demo-user", "inventory-session-1"
	if _, err = sessions.Create(ctx, &session.CreateRequest{
		AppName: appName, UserID: userID, SessionID: sessionID,
	}); err != nil {
		return err
	}
	r, err := runner.New(runner.Config{AppName: appName, Agent: assistant, SessionService: sessions})
	if err != nil {
		return err
	}
	for event, err := range r.Run(ctx, userID, sessionID,
		genai.NewContentFromText("How many NOTEBOOK-A5 notebooks are available?", genai.RoleUser),
		agent.RunConfig{}) {
		if err != nil {
			return err
		}
		if event.Content != nil {
			for _, part := range event.Content.Parts {
				if part.Text != "" {
					fmt.Println(part.Text)
				}
			}
		}
	}
	return nil
}
