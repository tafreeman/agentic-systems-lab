#!/usr/bin/env node
// Sprint B #3 — Node half of the wire-format drift gate.
//
// Reads the committed JSON Schema that mirrors
// `agentic_v2.contracts.events.ExecutionEvent` and compiles it to
// `src/api/events.generated.ts`. CI regenerates + diffs to catch drift.
//
// Run it manually after editing the Python contract:
//     cd agentic-workflows-v2/ui
//     npm run generate:types
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { compile } from 'json-schema-to-typescript';

// Resolve relative to this file so invocation from other cwds still works.
const SCRIPT_DIR = new URL('.', import.meta.url).pathname;
// On Windows, pathname looks like `/C:/...` — strip the leading slash when
// the next character is a drive letter so `resolve` treats it as absolute.
const NORMALIZED_SCRIPT_DIR =
  process.platform === 'win32' && /^\/[A-Za-z]:/.test(SCRIPT_DIR)
    ? SCRIPT_DIR.slice(1)
    : SCRIPT_DIR;

const SCHEMA_PATH = resolve(
  NORMALIZED_SCRIPT_DIR,
  '..',
  '..',
  'tests',
  'schemas',
  'events.schema.json',
);
const OUT_PATH = resolve(
  NORMALIZED_SCRIPT_DIR,
  '..',
  'src',
  'api',
  'events.generated.ts',
);

const schema = JSON.parse(readFileSync(SCHEMA_PATH, 'utf8'));

// Pydantic stamps every property with a `title` (e.g. "Run Id"), which makes
// json-schema-to-typescript promote every primitive to its own exported alias
// (`RunId`, `RunId1`, ... `Type7`). That pollutes the module's export surface
// with dozens of meaningless names. Stripping property-level titles while
// keeping top-level $defs titles lets the compiler inline primitives and
// preserves the useful names (`WorkflowStartEvent`, `StepEndEvent`, ...).
//
// We only strip titles from leaf property schemas under `$defs.<Model>.properties`,
// never from the $def itself — that title becomes the TypeScript interface name.
for (const def of Object.values(schema.$defs ?? {})) {
  if (def && typeof def === 'object' && def.properties) {
    for (const prop of Object.values(def.properties)) {
      if (prop && typeof prop === 'object' && 'title' in prop) {
        delete prop.title;
      }
      // `items` for array-typed properties also carries a generated title.
      if (prop && typeof prop === 'object' && prop.items && typeof prop.items === 'object' && 'title' in prop.items) {
        delete prop.items.title;
      }
    }
  }
}

const HEADER = `/**
 * AUTO-GENERATED — DO NOT EDIT BY HAND
 *
 * Regenerate with: npm run generate:types (from agentic-workflows-v2/ui/)
 *
 * Source JSON Schema: agentic-workflows-v2/tests/schemas/events.schema.json
 * Origin Pydantic model: agentic_v2.contracts.events.ExecutionEvent
 *
 * CI fails the 'wire-format-drift' job if this file does not match a fresh
 * regeneration from the committed schema.
 */
`;

const ts = await compile(schema, 'ExecutionEvent', {
  bannerComment: '',
  additionalProperties: false,
  style: { singleQuote: true, semi: true },
});

writeFileSync(OUT_PATH, HEADER + ts, 'utf8');
console.log(`Wrote ${OUT_PATH}`);
