// The real Lambda entry point. Built (not run) by the tests: running it needs the Lambda runtime.
package main

import (
	"github.com/aws/aws-lambda-go/lambda"

	"example.com/lambda-tracing/handler"
	"example.com/lambda-tracing/tracing"
)

func main() {
	tracing.Init(nil, true) // once per execution environment, outside the handler
	lambda.Start(handler.Handle)
}
