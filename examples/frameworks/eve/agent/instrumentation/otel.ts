// Process-wide OpenTelemetry settings. Declare otel() once per agent.
// Future AGI files every span under the resource attribute `project_name`.
import { otel } from "eve/instrumentation/otel";

export default otel({
  resource: {
    project_name: process.env.FI_PROJECT_NAME ?? "eve-agent",
    project_type: "observe",
  },
});
