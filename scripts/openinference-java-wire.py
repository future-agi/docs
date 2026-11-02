"""Execute the Java documentation with released Maven jars and a loopback receiver.

Prepare downloads first; run the checks in an outbound-network-denied sandbox.
Requires Python's opentelemetry-proto==1.38.0, Maven and JDK 17 or 21.
"""
import argparse
import gzip
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from google.protobuf.json_format import MessageToDict
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

CONFORMANCE = '''package example;
import com.arize.instrumentation.annotation.*;
import com.arize.semconv.trace.SemanticConventions.OpenInferenceSpanKind;
public class ConformanceService {
    @Agent(name = "test-agent")
    public String run() {
        chain("input-sentinel");
        return broken();
    }
    @Chain(name = "test-chain")
    public String chain(String prompt) {
        retrieve(prompt);
        return model(prompt, "excluded-sentinel");
    }
    @Span(kind = OpenInferenceSpanKind.RETRIEVER, name = "test-retriever")
    public String retrieve(String query) { return "retrieved-sentinel"; }
    @LLM(name = "test-model")
    public String model(String prompt, @ExcludeFromSpan String credential) {
        return "output-sentinel";
    }
    @Tool(name = "test-error")
    public String broken() { throw new IllegalStateException("error-sentinel"); }
}
'''
CALL = '''new ConformanceService().run();'''


def command(args, env, log, cwd):
    result = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, timeout=180)
    log.write_text(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}); see {log}")


def attributes(values):
    return {a['key']: next(iter(a['value'].values())) for a in values}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--java-home', type=Path, required=True)
    parser.add_argument('--maven', default='mvn')
    parser.add_argument('--prepare', action='store_true')
    args = parser.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    java_home = args.java_home.resolve()
    env = {k: os.environ[k] for k in ['PATH', 'TMPDIR'] if k in os.environ}
    home = work / 'home'
    home.mkdir(exist_ok=True)
    env['HOME'] = str(home)
    env['JAVA_TOOL_OPTIONS'] = f'-Duser.home={home} -Djava.net.preferIPv4Stack=true'
    env['JAVA_HOME'] = str(java_home)
    env['PATH'] = str(java_home / 'bin') + os.pathsep + env.get('PATH', '')
    page = (Path(__file__).resolve().parents[1] / 'src/pages/docs/integrations/import/openinference.mdx').read_text()
    java_tab = page.split('<Tab title="Java">')[1].split('</Tab>')[0]
    pom = re.findall(r'```xml\n(.*?)\n```', java_tab, re.S)[0]
    sources = re.findall(r'```java\n(.*?)\n```', java_tab, re.S)
    assert len(sources) == 2
    # Also execute the launch command copied from the page, not a substitute launcher.
    launch = re.findall(r'```bash\n(.*?)\n```', java_tab, re.S)[-1]
    assert 'java -javaagent:target/dependency/byte-buddy-agent-1.14.12.jar' in launch
    launch_args = shlex.split(launch.split('\n', 1)[1].replace('\\\n', ''))
    configurations = [('floor', '0.1.1', '1.49.0'), ('current', '0.1.2', '1.67.0')]
    results = []
    for label, oi, otel in configurations:
        project = work / label
        source_dir = project / 'src/main/java/example'
        source_dir.mkdir(parents=True, exist_ok=True)
        (project / 'pom.xml').write_text(pom.replace('<openinference.version>0.1.2', f'<openinference.version>{oi}').replace('<otel.version>1.67.0', f'<otel.version>{otel}'))
        maven = [args.maven, '-q', '-f', str(project / 'pom.xml'), f'-Dmaven.repo.local={work / "m2"}']
        if args.prepare:
            (source_dir / 'Main.java').write_text(sources[0])
            (source_dir / 'GardenService.java').write_text(sources[1])
            command(maven + ['package', 'dependency:copy-dependencies'], env, project / 'prepare.log', project)
            continue
        for hidden in [True, False]:
            for compression in ['none', 'gzip']:
                for scenario in ['page', 'conformance']:
                    name = f'{label}-{hidden}-{compression}-{scenario}'
                    source = sources[0]
                    if not hidden:
                        source = source.replace('.hideInputs(true)', '.hideInputs(false)').replace('.hideOutputs(true)', '.hideOutputs(false)')
                    if compression == 'gzip':
                        source = source.replace('.setEndpoint(', '.setCompression("gzip")\n                .setEndpoint(', 1)
                    if scenario == 'conformance':
                        source = source.replace('System.out.println(new GardenService().plan("rooftop"));', CALL)
                        source = source.replace('} finally {', '} catch (IllegalStateException expected) {\n            if (!"error-sentinel".equals(expected.getMessage())) throw expected;\n        } finally {')
                    (source_dir / 'Main.java').write_text(source)
                    (source_dir / 'GardenService.java').write_text(sources[1])
                    (source_dir / 'ConformanceService.java').write_text(CONFORMANCE)
                    command(maven + ['-o', 'package'], env, work / f'{name}-build.log', project)
                    received = []
                    class Receiver(BaseHTTPRequestHandler):
                        def do_POST(self):
                            if self.headers.get('Transfer-Encoding') == 'chunked':
                                chunks = []
                                while True:
                                    size = int(self.rfile.readline().strip().split(b';')[0], 16)
                                    if not size:
                                        while self.rfile.readline() != b'\r\n':
                                            pass
                                        break
                                    chunks.append(self.rfile.read(size))
                                    assert self.rfile.read(2) == b'\r\n'
                                body = b''.join(chunks)
                            else:
                                body = self.rfile.read(int(self.headers['Content-Length']))
                            received.append((self.path, dict(self.headers), body))
                            self.send_response(200)
                            self.send_header('Content-Type', 'application/x-protobuf')
                            self.send_header('Content-Length', '0')
                            self.end_headers()

                        def log_message(self, *args):
                            pass
                    server = ThreadingHTTPServer(('127.0.0.1', 0), Receiver)
                    thread = Thread(target=server.serve_forever, daemon=True)
                    thread.start()
                    run_env = dict(env, FI_BASE_URL=f'http://127.0.0.1:{server.server_port}/tracer/', FI_API_KEY='synthetic-api', FI_SECRET_KEY='synthetic-secret')
                    try:
                        command(launch_args, run_env, work / f'{name}-run.log', project)
                    finally:
                        server.shutdown()
                        server.server_close()
                        thread.join()
                    assert len(received) == 1, (name, 'expected exactly one export', len(received))
                    path, headers, body = received[0]
                    headers = {k.lower(): v for k, v in headers.items()}
                    assert path == '/tracer/v1/traces', (name, path)
                    assert headers['x-api-key'] == 'synthetic-api'
                    assert headers['x-secret-key'] == 'synthetic-secret'
                    assert headers['content-type'] == 'application/x-protobuf'
                    assert headers.get('content-encoding', 'none') == compression
                    if compression == 'gzip':
                        body = gzip.decompress(body)
                    decoded = MessageToDict(ExportTraceServiceRequest.FromString(body), use_integers_for_enums=True)
                    (work / f'{name}.json').write_text(json.dumps(decoded, indent=2))
                    spans = []
                    for resource in decoded['resourceSpans']:
                        res = attributes(resource['resource']['attributes'])
                        assert res['project_name'] == 'my-openinference-java-project'
                        assert res['project_type'] == 'observe'
                        assert res['service.name'] == 'java-annotations'
                        spans += [s for scope in resource['scopeSpans'] for s in scope['spans']]
                    expected = {'garden-planner': 'AGENT', 'choose-plant': 'TOOL'} if scenario == 'page' else {'test-agent': 'AGENT', 'test-chain': 'CHAIN', 'test-retriever': 'RETRIEVER', 'test-model': 'LLM', 'test-error': 'TOOL'}
                    assert len(spans) == len(expected), (name, len(spans))
                    assert len({s['spanId'] for s in spans}) == len(spans)
                    assert len({s['traceId'] for s in spans}) == 1
                    by_name = {s['name']: s for s in spans}
                    assert set(by_name) == set(expected)
                    root = 'garden-planner' if scenario == 'page' else 'test-agent'
                    assert not by_name[root].get('parentSpanId')
                    for span in spans:
                        attrs = attributes(span['attributes'])
                        assert attrs['openinference.span.kind'] == expected[span['name']]
                        assert int(span['endTimeUnixNano']) >= int(span['startTimeUnixNano'])
                        if span['name'] != root:
                            parent = 'test-chain' if span['name'] in ['test-retriever', 'test-model'] else root
                            assert span['parentSpanId'] == by_name[parent]['spanId']
                        if hidden:
                            assert 'input.value' not in attrs and 'output.value' not in attrs
                        elif scenario == 'page':
                            assert attrs['input.value'] == 'rooftop'
                            assert 'rosemary' in attrs['output.value']
                        error = scenario == 'conformance' and span['name'] in ['test-agent', 'test-error']
                        assert span['status']['code'] == (2 if error else 1)
                        if error:
                            assert span['status']['message'] == 'error-sentinel'
                            event = next(e for e in span['events'] if e['name'] == 'exception')
                            assert attributes(event['attributes'])['exception.message'] == 'error-sentinel'
                    encoded = json.dumps(decoded)
                    assert 'excluded-sentinel' not in encoded
                    for sentinel in ['input-sentinel', 'output-sentinel', 'retrieved-sentinel']:
                        if scenario == 'conformance':
                            assert (sentinel in encoded) == (not hidden), (name, sentinel)
                    results.append({'case': name, 'spans': len(spans), 'passed': True})
                    print(f'PASS {name}: {len(spans)} unique, parented spans', flush=True)
    if not args.prepare:
        (work / 'results.json').write_text(json.dumps(results, indent=2))
        print(f'{len(results)} wire checks passed')


if __name__ == '__main__':
    main()
