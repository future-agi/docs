import assert from 'node:assert/strict';
import { describe, test } from 'node:test';

import {
  captureContentEnabled,
  contentOption,
  exporterHeaders,
  resourceAttributes,
  tracesUrl,
} from '../src/futureagi.ts';

describe('futureagi settings', () => {
  test('content capture is off unless FI_CAPTURE_CONTENT is truthy', () => {
    assert.equal(captureContentEnabled({}), false);
    assert.equal(captureContentEnabled({ FI_CAPTURE_CONTENT: '' }), false);
    assert.equal(captureContentEnabled({ FI_CAPTURE_CONTENT: '0' }), false);
    assert.equal(captureContentEnabled({ FI_CAPTURE_CONTENT: 'false' }), false);
    for (const v of ['1', 'true', 'TRUE', 'yes', 'on', ' 1 ']) assert.equal(captureContentEnabled({ FI_CAPTURE_CONTENT: v }), true, v);
  });

  test('default content option is `false`, which removes all Flue content', () => {
    assert.equal(contentOption({}), false);
  });

  test('the opt-in keeps content but drops stack traces', () => {
    const option = contentOption({ FI_CAPTURE_CONTENT: '1' });
    assert.ok(option && typeof option === 'object' && option.transform);
    const scope = (contentType: string) => ({ contentType, eventType: 'tool' }) as never;
    assert.equal(option.transform('at /Users/me/app/src/tool.ts:12', scope('exception_stacktrace')), undefined);
    assert.equal(option.transform('no station for Paris', scope('exception_message')), 'no station for Paris');
    assert.deepEqual(option.transform({ city: 'Paris' }, scope('tool_arguments')), { city: 'Paris' });
  });

  test('traces URL: hosted default, self-hosted origin, trailing slashes trimmed', () => {
    assert.equal(tracesUrl({}), 'https://api.futureagi.com/tracer/v1/traces');
    assert.equal(tracesUrl({ FI_BASE_URL: 'http://localhost:14338' }), 'http://localhost:14338/tracer/v1/traces');
    assert.equal(tracesUrl({ FI_BASE_URL: 'http://localhost:14338///' }), 'http://localhost:14338/tracer/v1/traces');
  });

  test('both auth headers are required', () => {
    assert.deepEqual(exporterHeaders({ FI_API_KEY: 'a', FI_SECRET_KEY: 'b' }), { 'X-Api-Key': 'a', 'X-Secret-Key': 'b' });
    assert.equal(exporterHeaders({ FI_API_KEY: 'a' }), null);
    assert.equal(exporterHeaders({ FI_SECRET_KEY: 'b' }), null);
    assert.equal(exporterHeaders({ FI_API_KEY: ' ', FI_SECRET_KEY: 'b' }), null);
  });

  test('project_name and project_type are resource attributes', () => {
    assert.deepEqual(resourceAttributes({ FI_PROJECT_NAME: 'my-flue-agent' }), {
      project_name: 'my-flue-agent',
      project_type: 'observe',
      'service.name': 'my-flue-agent',
    });
    assert.equal(resourceAttributes({}).project_name, 'flue-agent');
    assert.equal(resourceAttributes({ FI_PROJECT_NAME: 'p', OTEL_SERVICE_NAME: 'svc' })['service.name'], 'svc');
  });
});
