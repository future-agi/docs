package main

import (
	"errors"

	"google.golang.org/adk/agent"
)

func makeWorkflow(agent.Agent) (agent.Agent, error) {
	return nil, errors.New("the graph workflow probe requires ADK v2")
}
