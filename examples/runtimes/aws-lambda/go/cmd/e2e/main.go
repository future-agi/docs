// Runs the example handler in-process, the way the Lambda runtime does: one Init (cold start), then
// several invocations (warm), pointed at a real Future AGI through the FI_* environment.
//
//	go run ./cmd/e2e happy|failure|privacy|nokeys [marker]
//
// The context is a stand-in for the Lambda context (request id and remaining time). Nothing here
// calls AWS.
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/aws/aws-lambda-go/lambdacontext"

	"example.com/lambda-tracing/handler"
	"example.com/lambda-tracing/tracing"
)

func ctxFor(n int) (context.Context, context.CancelFunc) {
	c := lambdacontext.NewContext(context.Background(), &lambdacontext.LambdaContext{AwsRequestID: fmt.Sprintf("local-req-%04d", n)})
	return context.WithTimeout(c, 30*time.Second)
}

func must(b []byte, err error) json.RawMessage {
	if err != nil {
		panic(err)
	}
	return b
}

func main() {
	scenario, marker := "happy", "demo"
	if len(os.Args) > 1 {
		scenario = os.Args[1]
	}
	if len(os.Args) > 2 {
		marker = os.Args[2]
	}
	tracing.Init(nil, true) // cold start: the provider is built here, once

	var apigw map[string]any
	raw, _ := os.ReadFile("testdata/apigw_v2.json")
	_ = json.Unmarshal(raw, &apigw)
	apigw["body"] = fmt.Sprintf(`{"order_id": "A-100", "note": %q}`, marker)
	apigw["headers"].(map[string]any)["x-demo-header"] = marker // headers are never exported
	sqsRaw, _ := os.ReadFile("testdata/sqs.json")
	sqs := strings.Replace(string(sqsRaw), `{\"order_id\": \"A-200\", \"note\": \"fixture-note\"}`, fmt.Sprintf(`{\"order_id\": \"A-200\", \"note\": \"%s\"}`, marker), 1)
	direct := must(json.Marshal(map[string]string{"order_id": "A-300", "note": marker}))

	run := func(n int, ev json.RawMessage) {
		ctx, cancel := ctxFor(n)
		defer cancel()
		res, err := handler.Handle(ctx, ev)
		if err != nil {
			fmt.Printf("raised %T\n", err)
			return
		}
		fmt.Println("returned", res["status"])
	}
	switch scenario {
	case "happy", "privacy", "nokeys":
		run(1, must(json.Marshal(apigw)))
		run(2, direct)
		run(3, json.RawMessage(sqs))
	}
	switch scenario {
	case "failure", "privacy":
		run(9, must(json.Marshal(map[string]string{"order_id": "boom", "note": marker})))
		run(10, direct)
	}
	fmt.Println("providers_built", tracing.ProvidersBuilt.Load())
}
