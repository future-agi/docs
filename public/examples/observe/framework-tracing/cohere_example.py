import os

import cohere
from fi_instrumentation import TraceConfig, register
from fi_instrumentation.fi_types import ProjectType
from traceai_cohere import CohereInstrumentor

provider = register(project_type=ProjectType.OBSERVE, project_name="ridgeline-framework-tracing", verbose=False)
tracing = CohereInstrumentor()
tracing.instrument(tracer_provider=provider, config=TraceConfig(hide_inputs=True, hide_embedding_vectors=True))
try:
    client = cohere.Client(api_key=os.environ["COHERE_API_KEY"])
    reply = client.embed(model="embed-english-v3.0", input_type="search_document",
                         texts=["Air dry your Ridgeline rain shell."], embedding_types=["int8"])
    print("Vectors returned:", len(reply.embeddings.int8))
finally:
    tracing.uninstrument()
    provider.force_flush()
    provider.shutdown()
