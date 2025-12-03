/**
 * Auto-generated API navigation from OpenAPI spec
 */

export interface ApiNavItem {
  title: string;
  href: string;
  method: string;
}

export interface ApiNavGroup {
  title: string;
  items: ApiNavItem[];
}

export const apiNavigation: ApiNavGroup[] = [
  {
    "title": "Health",
    "items": [
      {
        "title": "Health check",
        "href": "/docs/api/health/healthcheck",
        "method": "GET"
      }
    ]
  },
  {
    "title": "Scenarios",
    "items": [
      {
        "title": "Generate or create a scenario",
        "href": "/docs/api/scenarios/createscenario",
        "method": "POST"
      },
      {
        "title": "Add rows to a scenario using AI",
        "href": "/docs/api/scenarios/addscenariorowswithai",
        "method": "POST"
      },
      {
        "title": "Edit a scenario",
        "href": "/docs/api/scenarios/editscenario",
        "method": "PUT"
      },
      {
        "title": "Add empty rows to a scenario",
        "href": "/docs/api/scenarios/addemptyrowstodataset",
        "method": "POST"
      }
    ]
  },
  {
    "title": "Agent Definitions",
    "items": [
      {
        "title": "Create agent definition",
        "href": "/docs/api/agent-definitions/createagentdefinition",
        "method": "POST"
      }
    ]
  },
  {
    "title": "Agent Versions",
    "items": [
      {
        "title": "Create new version of agent",
        "href": "/docs/api/agent-versions/createagentversion",
        "method": "POST"
      }
    ]
  },
  {
    "title": "Run Tests",
    "items": [
      {
        "title": "Create a New Test Run",
        "href": "/docs/api/run-tests/createruntest",
        "method": "POST"
      },
      {
        "title": "Execute a test run",
        "href": "/docs/api/run-tests/executeruntest",
        "method": "POST"
      }
    ]
  },
  {
    "title": "Eval Groups",
    "items": [
      {
        "title": "List Evaluation Groups",
        "href": "/docs/api/eval-groups/listevalgroups",
        "method": "GET"
      },
      {
        "title": "Create Evaluation Group",
        "href": "/docs/api/eval-groups/createevalgroup",
        "method": "POST"
      },
      {
        "title": "Retrieve Evaluation Group",
        "href": "/docs/api/eval-groups/retrieveevalgroup",
        "method": "GET"
      },
      {
        "title": "Update Evaluation Group",
        "href": "/docs/api/eval-groups/updateevalgroup",
        "method": "PUT"
      },
      {
        "title": "Delete Evaluation Group",
        "href": "/docs/api/eval-groups/deleteevalgroup",
        "method": "DELETE"
      },
      {
        "title": "Edit Evaluation Group Members",
        "href": "/docs/api/eval-groups/editevallist",
        "method": "POST"
      },
      {
        "title": "Apply Evaluation Group",
        "href": "/docs/api/eval-groups/applyevalgroup",
        "method": "POST"
      }
    ]
  },
  {
    "title": "Eval Logs & Metrics",
    "items": [
      {
        "title": "Get Evaluation Log Details",
        "href": "/docs/api/eval-logs-metrics/getevallogdetails",
        "method": "GET"
      }
    ]
  },
  {
    "title": "Evals List",
    "items": [
      {
        "title": "Get Evals List",
        "href": "/docs/api/evals-list/getevalslist",
        "method": "GET"
      }
    ]
  }
];
