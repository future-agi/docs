package main

import (
	"google.golang.org/adk/v2/agent"
	"google.golang.org/adk/v2/agent/workflowagent"
	"google.golang.org/adk/v2/workflow"
)

func makeWorkflow(a agent.Agent) (agent.Agent, error) {
	cfg := workflow.NodeConfig{}
	prepare := workflow.NewFunctionNode("prepare", func(ctx agent.Context, input string) (string, error) { return input, nil }, cfg)
	child, err := workflow.NewAgentNode(a, cfg)
	if err != nil {
		return nil, err
	}
	return workflowagent.New(workflowagent.Config{Name: "graph", Description: canary, Edges: workflow.Chain(workflow.Start, prepare, child)})
}
