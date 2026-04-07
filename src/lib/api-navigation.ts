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
        "title": "List scenarios",
        "href": "/docs/api/scenarios/listscenarios",
        "method": "GET"
      },
      {
        "title": "Get scenario details",
        "href": "/docs/api/scenarios/getscenario",
        "method": "GET"
      },
      {
        "title": "Generate or create a scenario",
        "href": "/docs/api/scenarios/createscenario",
        "method": "POST"
      },
      {
        "title": "Edit a scenario",
        "href": "/docs/api/scenarios/editscenario",
        "method": "PUT"
      },
      {
        "title": "Delete a scenario",
        "href": "/docs/api/scenarios/deletescenario",
        "method": "DELETE"
      },
      {
        "title": "Add rows to a scenario using AI",
        "href": "/docs/api/scenarios/addscenariorowswithai",
        "method": "POST"
      },
      {
        "title": "Add columns to a scenario",
        "href": "/docs/api/scenarios/addcolumns",
        "method": "POST"
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
        "title": "List agent definitions",
        "href": "/docs/api/agent-definitions/listagentdefinitions",
        "method": "GET"
      },
      {
        "title": "Create agent definition",
        "href": "/docs/api/agent-definitions/createagentdefinition",
        "method": "POST"
      },
      {
        "title": "Get agent definition details",
        "href": "/docs/api/agent-definitions/getagentdefinition",
        "method": "GET"
      },
      {
        "title": "Delete agent definitions",
        "href": "/docs/api/agent-definitions/deleteagentdefinitions",
        "method": "DELETE"
      },
      {
        "title": "Fetch assistant from provider",
        "href": "/docs/api/agent-definitions/fetchassistantfromprovider",
        "method": "POST"
      }
    ]
  },
  {
    "title": "Agent Versions",
    "items": [
      {
        "title": "List agent versions",
        "href": "/docs/api/agent-versions/listagentversions",
        "method": "GET"
      },
      {
        "title": "Create new version of agent",
        "href": "/docs/api/agent-versions/createagentversion",
        "method": "POST"
      },
      {
        "title": "Get agent version details",
        "href": "/docs/api/agent-versions/getagentversion",
        "method": "GET"
      },
      {
        "title": "Get call executions for version",
        "href": "/docs/api/agent-versions/getversioncallexecutions",
        "method": "GET"
      },
      {
        "title": "Get eval summary for version",
        "href": "/docs/api/agent-versions/getversionevalsummary",
        "method": "GET"
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
    "title": "Eval Tasks",
    "items": [
      { "title": "List Eval Tasks", "href": "/docs/api/eval-tasks/list-eval-tasks-filtered", "method": "GET" },
      { "title": "Create Eval Task", "href": "/docs/api/eval-tasks/create-eval-task", "method": "POST" },
      { "title": "Get Eval Task", "href": "/docs/api/eval-tasks/get-eval-task", "method": "GET" },
      { "title": "Update Eval Task", "href": "/docs/api/eval-tasks/update-eval-task", "method": "PATCH" },
      { "title": "Delete Eval Task", "href": "/docs/api/eval-tasks/delete-eval-task", "method": "DELETE" },
      { "title": "Bulk Delete Eval Tasks", "href": "/docs/api/eval-tasks/bulk-delete-eval-tasks", "method": "POST" },
      { "title": "Pause Eval Task", "href": "/docs/api/eval-tasks/pause-eval-task", "method": "POST" },
      { "title": "Unpause Eval Task", "href": "/docs/api/eval-tasks/unpause-eval-task", "method": "POST" }
    ]
  },
  {
    "title": "Custom Eval Configs",
    "items": [
      { "title": "List Custom Eval Configs", "href": "/docs/api/custom-eval-configs/list-configs-filtered", "method": "GET" },
      { "title": "Create Custom Eval Config", "href": "/docs/api/custom-eval-configs/create-custom-eval-config", "method": "POST" },
      { "title": "Get Custom Eval Config", "href": "/docs/api/custom-eval-configs/get-custom-eval-config", "method": "GET" },
      { "title": "Update Custom Eval Config", "href": "/docs/api/custom-eval-configs/update-custom-eval-config", "method": "PATCH" },
      { "title": "Delete Custom Eval Config", "href": "/docs/api/custom-eval-configs/delete-custom-eval-config", "method": "DELETE" },
      { "title": "Check Config Exists", "href": "/docs/api/custom-eval-configs/check-config-exists", "method": "POST" }
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
  },
  {
    "title": "Simulation Analytics",
    "items": [
      {
        "title": "Get Simulation Metrics",
        "href": "/docs/api/simulation-analytics/metrics",
        "method": "GET"
      },
      {
        "title": "Get Simulation Runs",
        "href": "/docs/api/simulation-analytics/runs",
        "method": "GET"
      },
      {
        "title": "Get Simulation Analytics",
        "href": "/docs/api/simulation-analytics/analytics",
        "method": "GET"
      }
    ]
  },
  {
    "title": "Datasets",
    "items": [
      { "title": "Create Dataset", "href": "/docs/api/datasets/create-dataset", "method": "POST" },
      { "title": "Upload Dataset from File", "href": "/docs/api/datasets/upload-dataset", "method": "POST" }
    ]
  },
  {
    "title": "Annotation Scores",
    "items": [
      { "title": "Create Score", "href": "/docs/api/annotations/scores/create-score", "method": "POST" },
      { "title": "Bulk Create Scores", "href": "/docs/api/annotations/scores/bulk-create-scores", "method": "POST" },
      { "title": "Get Scores for Source", "href": "/docs/api/annotations/scores/get-scores-for-source", "method": "GET" },
      { "title": "List Scores", "href": "/docs/api/annotations/scores/list-scores", "method": "GET" },
      { "title": "Delete Score", "href": "/docs/api/annotations/scores/delete-score", "method": "DELETE" }
    ]
  },
  {
    "title": "Annotation Labels",
    "items": [
      { "title": "Create Label", "href": "/docs/api/annotations/labels/create-label", "method": "POST" },
      { "title": "List Labels", "href": "/docs/api/annotations/labels/list-labels", "method": "GET" },
      { "title": "Get Label", "href": "/docs/api/annotations/labels/get-label", "method": "GET" },
      { "title": "Update Label", "href": "/docs/api/annotations/labels/update-label", "method": "PUT" },
      { "title": "Delete Label", "href": "/docs/api/annotations/labels/delete-label", "method": "DELETE" },
      { "title": "Restore Label", "href": "/docs/api/annotations/labels/restore-label", "method": "POST" }
    ]
  },
  {
    "title": "Annotation Queues",
    "items": [
      { "title": "Create Queue", "href": "/docs/api/annotations/queues/create-queue", "method": "POST" },
      { "title": "List Queues", "href": "/docs/api/annotations/queues/list-queues", "method": "GET" },
      { "title": "Get Queue", "href": "/docs/api/annotations/queues/get-queue", "method": "GET" },
      { "title": "Update Queue", "href": "/docs/api/annotations/queues/update-queue", "method": "PUT" },
      { "title": "Delete Queue", "href": "/docs/api/annotations/queues/delete-queue", "method": "DELETE" },
      { "title": "Update Status", "href": "/docs/api/annotations/queues/update-status", "method": "POST" },
      { "title": "Get Progress", "href": "/docs/api/annotations/queues/get-progress", "method": "GET" },
      { "title": "Get Analytics", "href": "/docs/api/annotations/queues/get-analytics", "method": "GET" },
      { "title": "Get Agreement", "href": "/docs/api/annotations/queues/get-agreement", "method": "GET" },
      { "title": "Export", "href": "/docs/api/annotations/queues/export", "method": "GET" },
      { "title": "Export to Dataset", "href": "/docs/api/annotations/queues/export-to-dataset", "method": "POST" },
      { "title": "Add Label to Queue", "href": "/docs/api/annotations/queues/add-label", "method": "POST" },
      { "title": "Remove Label", "href": "/docs/api/annotations/queues/remove-label", "method": "POST" },
      { "title": "Get or Create Default", "href": "/docs/api/annotations/queues/get-or-create-default", "method": "POST" },
      { "title": "Find Queues for Source", "href": "/docs/api/annotations/queues/find-queues-for-source", "method": "GET" }
    ]
  },
  {
    "title": "Queue Items",
    "items": [
      { "title": "List Items", "href": "/docs/api/annotations/items/list-items", "method": "GET" },
      { "title": "Add Items", "href": "/docs/api/annotations/items/add-items", "method": "POST" },
      { "title": "Bulk Remove Items", "href": "/docs/api/annotations/items/bulk-remove-items", "method": "POST" },
      { "title": "Get Annotate Detail", "href": "/docs/api/annotations/items/get-annotate-detail", "method": "GET" },
      { "title": "Get Next Item", "href": "/docs/api/annotations/items/get-next-item", "method": "GET" },
      { "title": "Submit Annotations", "href": "/docs/api/annotations/items/submit-annotations", "method": "POST" },
      { "title": "Complete Item", "href": "/docs/api/annotations/items/complete-item", "method": "POST" },
      { "title": "Skip Item", "href": "/docs/api/annotations/items/skip-item", "method": "POST" },
      { "title": "Get Item Annotations", "href": "/docs/api/annotations/items/get-item-annotations", "method": "GET" },
      { "title": "Assign Items", "href": "/docs/api/annotations/items/assign-items", "method": "POST" },
      { "title": "Release Item", "href": "/docs/api/annotations/items/release-item", "method": "POST" }
    ]
  },
  {
    "title": "Bulk Annotation",
    "items": [
      { "title": "Bulk Annotate Spans", "href": "/docs/api/annotations/bulk/bulk-annotate-spans", "method": "POST" }
    ]
  }
];
