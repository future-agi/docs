"""Run the exact Azure Java page example against loopback Azure and OTLP servers.

Requires JDK 17+, Maven, Gradle 8.14.3, openssl and opentelemetry-proto==1.38.0.
Only synthetic credentials are passed to the example. No vendor account is used.
"""
import argparse
import gzip
import json
import os
from pathlib import Path
import re
import shutil
import ssl
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from google.protobuf.json_format import MessageToDict
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

PAGE = Path(__file__).resolve().parents[1] / 'src/pages/docs/integrations/traceai/java/llm-providers.mdx'
INPUT = [{'role': 'user', 'content': 'What is the capital of France?'}]
OUTPUT = [{'role': 'assistant', 'content': 'Paris'}]
MODEL = 'gpt-4o-mini-2024-07-18'


def attributes(span):
    return {a['key']: next(iter(a['value'].values())) for a in span['attributes']}


def assert_capture(page, capture):
    spans = [span for export in capture['exports']
             for resource in export.get('resource_spans', [])
             for scope in resource.get('scope_spans', []) for span in scope.get('spans', [])]
    assert len(spans) == 1, f'Expected one semantic span, got {len(spans)}'
    span = spans[0]
    assert span['name'] == 'Azure OpenAI Chat Completion'
    assert span['status']['code'] == 'STATUS_CODE_OK'
    attrs = attributes(span)
    expected = {
        'gen_ai.provider.name': 'azure',
        'gen_ai.request.model': 'chat-deploy',
        'gen_ai.response.model': MODEL,
        'gen_ai.usage.input_tokens': '9',
        'gen_ai.usage.output_tokens': '3',
        'gen_ai.usage.total_tokens': '12',
        'gen_ai.input.messages': INPUT,
        'gen_ai.output.messages': OUTPUT,
        'output.value': 'Paris',
    }
    reference = page.split('### Azure OpenAI attributes\n')[1].split('\n### ')[0]
    documented = re.findall(r'^\| `([^`]+)` \|', reference, re.M)
    assert set(documented) == set(expected), f'Documented keys changed: {documented}'
    for key, value in expected.items():
        actual = json.loads(attrs[key]) if key.endswith('.messages') else attrs[key]
        assert actual == value, (key, actual, value)
    assert not any(key.startswith('llm.') for key in attrs)
    assert attrs['fi.span.kind'] == 'LLM'
    # Pin the released SDK's serialization limitation, not a mocked tracer.
    for key, class_name in [('fi.raw_input', 'ChatCompletionsOptions'), ('fi.raw_output', 'ChatCompletions')]:
        assert re.fullmatch(r'com\.azure\.ai\.openai\.models\.' + class_name + r'@[0-9a-f]+', attrs[key]), (key, attrs[key])
        try:
            json.loads(attrs[key])
        except json.JSONDecodeError:
            pass
        else:
            raise AssertionError(f'{key} is now JSON; revisit the versioned documentation')
    assert 'not full request/response JSON' in reference
    assert 'Do not rely on the raw fields for payload replay' in reference
    assert len(capture['requests']) == 1
    request = capture['requests'][0]
    assert request['path'].startswith('/openai/deployments/chat-deploy/chat/completions?api-version=')
    assert request['body']['messages'] == INPUT
    assert request['api_key'] == 'synthetic-azure'
    assert len(capture['export_headers']) == 1
    headers = capture['export_headers'][0]
    assert headers['x-api-key'] == 'synthetic-fi-api'
    assert headers['x-secret-key'] == 'synthetic-fi-secret'
    assert headers['content-type'].startswith('application/x-protobuf')


def run(command, cwd, env, log):
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, timeout=600)
    log.write_text(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError(f'Command failed ({result.returncode}); see {log}')
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', required=True, type=Path)
    parser.add_argument('--page', type=Path, default=PAGE)
    parser.add_argument('--build-tool', choices=['maven', 'gradle', 'both'], default='both')
    args = parser.parse_args()
    work = args.work.resolve()
    evidence = work / 'evidence'
    source = work / 'project/src/main/java'
    source.mkdir(parents=True, exist_ok=True)
    evidence.mkdir(parents=True, exist_ok=True)
    project = source.parents[2]
    page = args.page.read_text()
    azure = page.split('## Azure OpenAI\n')[1].split('\n## ')[0]
    java = re.search(r'```java\n(.*?)```', azure, re.S)[1]
    imports = '\n'.join(line for line in java.splitlines() if line.startswith('import '))
    body = '\n'.join(line for line in java.splitlines() if not line.startswith('import '))
    (source / 'Example.java').write_text(imports + '\npublic class Example { public static void main(String[] args) {\n' + body + '\n}}\n')
    maven_deps = re.search(r'```xml Maven\n(.*?)```', azure, re.S)[1]
    gradle_deps = re.search(r'```groovy Gradle\n(.*?)```', azure, re.S)[1]
    (project / 'pom.xml').write_text('''<project xmlns="http://maven.apache.org/POM/4.0.0">
<modelVersion>4.0.0</modelVersion><groupId>test</groupId><artifactId>azure-docs</artifactId><version>1.0</version>
<properties><maven.compiler.release>17</maven.compiler.release></properties><dependencies>'''
        + maven_deps + '''</dependencies><build><plugins><plugin><groupId>org.apache.maven.plugins</groupId>
<artifactId>maven-compiler-plugin</artifactId><version>3.13.0</version></plugin></plugins></build></project>''')
    (project / 'settings.gradle').write_text("rootProject.name = 'azure-docs'\n")
    (project / 'build.gradle').write_text("plugins { id 'application' }\nrepositories { mavenCentral() }\ndependencies {\n"
        + gradle_deps + "}\napplication { mainClass = 'Example' }\n")
    env = {key: os.environ[key] for key in ['PATH', 'JAVA_HOME', 'HOME', 'TMPDIR'] if key in os.environ}
    assert env.get('JAVA_HOME'), 'Set JAVA_HOME to the JDK under test'
    run(['java', '-version'], project, env, evidence / 'java-version.log')
    tls_dir = work / 'tls'
    tls_dir.mkdir(exist_ok=True)
    key, cert, trust = [tls_dir / name for name in ['mock.key', 'mock.crt', 'truststore']]
    run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', str(key), '-out', str(cert),
         '-days', '1', '-subj', '/CN=localhost', '-addext', 'subjectAltName=DNS:localhost,IP:127.0.0.1'],
        project, env, evidence / 'certificate.log')
    shutil.copyfile(Path(env['JAVA_HOME']) / 'lib/security/cacerts', trust)
    run(['keytool', '-importcert', '-noprompt', '-alias', 'azure-docs-mock', '-file', str(cert),
         '-keystore', str(trust), '-storepass', 'changeit'], project, env, evidence / 'truststore.log')
    capture = {'exports': [], 'requests': [], 'export_headers': []}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            data = self.rfile.read(int(self.headers.get('Content-Length', '0')))
            if self.headers.get('Content-Encoding') == 'gzip':
                data = gzip.decompress(data)
            if self.path == '/tracer/v1/traces':
                decoded = MessageToDict(ExportTraceServiceRequest.FromString(data), preserving_proto_field_name=True)
                capture['exports'].append(decoded)
                capture['export_headers'].append({k.lower(): v for k, v in self.headers.items()})
                self.send_response(200)
                self.send_header('Content-Type', 'application/x-protobuf')
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            if not self.path.startswith('/openai/deployments/chat-deploy/chat/completions?'):
                self.send_error(404)
                return
            capture['requests'].append({'path': self.path, 'body': json.loads(data), 'api_key': self.headers.get('api-key')})
            response = json.dumps({
                'id': 'chatcmpl-synthetic', 'object': 'chat.completion', 'created': 1700000000, 'model': MODEL,
                'choices': [{'index': 0, 'message': OUTPUT[0], 'finish_reason': 'stop'}],
                'usage': {'prompt_tokens': 9, 'completion_tokens': 3, 'total_tokens': 12},
            }).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(response)))
            self.end_headers()
            self.wfile.write(response)

    otlp = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    azure_server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(cert, key)
    azure_server.socket = tls.wrap_socket(azure_server.socket, server_side=True)
    threads = [Thread(target=server.serve_forever, daemon=True) for server in [otlp, azure_server]]
    for thread in threads:
        thread.start()
    env.update({
        'FI_BASE_URL': f'http://127.0.0.1:{otlp.server_port}',
        'FI_API_KEY': 'synthetic-fi-api', 'FI_SECRET_KEY': 'synthetic-fi-secret', 'FI_PROJECT_NAME': 'azure-docs',
        'AZURE_OPENAI_ENDPOINT': f'https://localhost:{azure_server.server_port}',
        'AZURE_OPENAI_API_KEY': 'synthetic-azure', 'AZURE_OPENAI_DEPLOYMENT': 'chat-deploy',
        'JAVA_TOOL_OPTIONS': f'-Djavax.net.ssl.trustStore={trust} -Djavax.net.ssl.trustStorePassword=changeit',
    })
    tools = ['maven', 'gradle'] if args.build_tool == 'both' else [args.build_tool]
    try:
        for tool in tools:
            for values in capture.values():
                values.clear()
            if tool == 'maven':
                run(['mvn', '-B', '-ntp', 'package', 'dependency:build-classpath', '-Dmdep.outputFile=cp.txt'],
                    project, env, evidence / 'maven-build.log')
                classpath = str(project / 'target/classes') + os.pathsep + (project / 'cp.txt').read_text().strip()
                command = ['java', '-cp', classpath, 'Example']
            else:
                command = ['gradle', '--no-daemon', 'run']
            output = run(command, project, env, evidence / f'{tool}-run.log')
            (evidence / f'{tool}-capture.json').write_text(json.dumps(capture, indent=2) + '\n')
            assert 'Paris' in output
            assert_capture(page, capture)
            print(f'PASS {tool}: exact page example, captured OTLP keys/messages/usage, raw serialization limitation', flush=True)
    finally:
        for server in [otlp, azure_server]:
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(timeout=5)


if __name__ == '__main__':
    main()
