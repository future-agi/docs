import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';

const destination = process.argv[2];
if (!destination) throw new Error('Usage: node scripts/anthropic-go-snippet.mjs <output-directory>');
const page = readFileSync(new URL('../src/pages/docs/integrations/traceai/go/anthropic.mdx', import.meta.url), 'utf8');
const source = page.match(/```go\n([\s\S]*?)\n```/)?.[1];
const install = page.match(/```bash\n([\s\S]*?)\n```/)?.[1];
if (!source || !install) throw new Error('Missing Go example or install commands');
mkdirSync(destination, { recursive: true });
writeFileSync(path.join(destination, 'main.go'), `${source}\n`);
writeFileSync(path.join(destination, 'install.sh'), `set -eu\n${install}\n`);
