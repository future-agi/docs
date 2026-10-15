// Run one Pi Coding Agent SDK session and trace it in Future AGI.
//
//   node trace_session.mjs "<prompt>"
//
// Environment:
//   FI_API_KEY, FI_SECRET_KEY   Future AGI keys (sent as X-Api-Key / X-Secret-Key)
//   FI_PROJECT_NAME             Future AGI project (default: pi-sdk)
//   FI_BASE_URL                 collector base URL (default: https://api.futureagi.com)
//   FI_HIDE_INPUTS=false        opt in to prompts and tool arguments
//   FI_HIDE_OUTPUTS=false       opt in to answers and tool results
//   PI_CODING_AGENT_DIR         Pi agent dir with models.json / auth.json (default: ~/.pi/agent)
//   PI_PROVIDER, PI_MODEL       model to use (default: Pi's configured default)
//   PI_CWD                      project directory the agent works in (default: cwd)
import { ProjectType, register } from "@traceai/fi-core";
import { PiCodingAgentInstrumentation } from "@traceai/pi-coding-agent";
import { createAgentSession, ModelRuntime, SessionManager } from "@earendil-works/pi-coding-agent";

const prompt = process.argv[2] ?? "List the files in this folder and read README.md.";
const cwd = process.env.PI_CWD ?? process.cwd();

const tracerProvider = register({
  projectType: ProjectType.OBSERVE,
  projectName: process.env.FI_PROJECT_NAME ?? "pi-sdk",
});
const instrumentation = new PiCodingAgentInstrumentation({ tracerProvider });
const createTracedSession = instrumentation.wrapCreateAgentSession(createAgentSession);

const options = { cwd, sessionManager: SessionManager.inMemory(cwd), tools: ["read", "ls", "bash"] };
if (process.env.PI_PROVIDER && process.env.PI_MODEL) {
  const modelRuntime = await ModelRuntime.create();
  const model = modelRuntime.getModel(process.env.PI_PROVIDER, process.env.PI_MODEL);
  if (!model) throw new Error(`Pi does not know ${process.env.PI_PROVIDER}/${process.env.PI_MODEL}; add it to models.json`);
  Object.assign(options, { model, modelRuntime });
}

const { session } = await createTracedSession(options);
try {
  await session.prompt(prompt);
  console.log(session.getLastAssistantText());
  console.error(`pi session id: ${session.sessionId}`);
} finally {
  session.dispose();
  await tracerProvider.shutdown();
}
