package main

import (
	"context"
	"errors"
	"fmt"
	"os"
	"sync"

	lc "github.com/future-agi/traceAI/go/langchaingo"
	"github.com/tmc/langchaingo/chains"
	"github.com/tmc/langchaingo/embeddings"
	"github.com/tmc/langchaingo/llms/openai"
	"github.com/tmc/langchaingo/prompts"
)

func run() (err error) {
	ctx := context.Background()
	tp, err := provider(ctx)
	if err != nil {
		return err
	}
	defer func() { err = errors.Join(err, tp.Shutdown(ctx)) }()
	modelID := os.Getenv("OPENAI_MODEL")
	if modelID == "" {
		return errors.New("set OPENAI_MODEL")
	}
	h := lc.NewHandler(lc.WithTracerProvider(tp), lc.WithModel(modelID))
	opts := []openai.Option{openai.WithCallback(h), openai.WithModel(modelID)}
	if url := os.Getenv("OPENAI_BASE_URL"); url != "" {
		opts = append(opts, openai.WithBaseURL(url))
	}
	embedModel := os.Getenv("OPENAI_EMBEDDING_MODEL")
	if embedModel != "" {
		opts = append(opts, openai.WithEmbeddingModel(embedModel))
	}
	model, err := openai.New(opts...)
	if err != nil {
		return err
	}
	if embedModel != "" {
		inner, err := embeddings.NewEmbedder(model)
		if err != nil {
			return err
		}
		vector, err := h.WrapEmbedder(inner).EmbedQuery(ctx, "drying a rain shell")
		if err != nil {
			return err
		}
		fmt.Println("Query dimensions:", len(vector))
	}
	var wg sync.WaitGroup
	results := make(chan error, 2)
	for _, item := range []string{"rain shell", "trail pack"} {
		wg.Add(1)
		go func() {
			defer wg.Done()
			runCtx := lc.ContextWithRun(ctx)
			defer h.EndRun(runCtx)
			prompt := prompts.NewPromptTemplate("Give one care tip for a Ridgeline {item}.", []string{"item"})
			chain := chains.NewLLMChain(model, prompt, chains.WithCallback(h))
			answer, err := chains.Run(runCtx, chain, item)
			if err == nil {
				fmt.Println(answer)
			}
			results <- err
		}()
	}
	wg.Wait()
	close(results)
	for result := range results {
		err = errors.Join(err, result)
	}
	return err
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
