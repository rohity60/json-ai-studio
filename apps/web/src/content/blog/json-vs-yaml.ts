import type { BlogPost } from '@/content/types';

export const post: BlogPost = {
  meta: {
    slug: 'json-vs-yaml',
    title: 'JSON vs YAML: Differences, Pitfalls and Which to Use for Config Files',
    description:
      'A side-by-side comparison of JSON and YAML: syntax, comments, data types, the Norway problem, anchors, and which tools expect which. Includes the same config in both formats and how to convert.',
    updatedAt: '2026-11-22',
    author: 'JSON AI Studio',
    tags: ['json vs yaml', 'yaml', 'config files', 'kubernetes', 'github actions'],
    readingTime: '7 min',
    aiSummary:
      'JSON uses braces, brackets and double quotes; YAML uses indentation and allows comments, unquoted strings, multi-line strings and anchors. YAML 1.2 is designed as a superset of JSON. JSON is stricter and safer to generate and parse, which suits APIs and machine-written files. YAML is easier to hand-edit, which suits Kubernetes, GitHub Actions, Docker Compose and CI. YAML pitfalls: indentation errors, implicit typing (NO, on, 1.10 and 012 can change type, especially with YAML 1.1 parsers), and unsafe loaders. Convert with yq.',
    relatedTemplates: ['kubernetes-deployment', 'github-actions-workflow', 'openapi-spec', 'package-json'],
    relatedBlogs: ['json-vs-jsonl', 'json-vs-toon', 'openapi-json-explained', 'json-schema-guide'],
    faq: [
      {
        q: 'Is YAML a superset of JSON?',
        a: 'YAML 1.2 was designed so that valid JSON is also valid YAML, and in practice almost any JSON file parses as YAML. YAML 1.1 parsers (still common) have small differences, so do not rely on it for edge cases.',
      },
      {
        q: 'Can JSON have comments?',
        a: 'Standard JSON cannot. Some tools accept "JSON with comments" (JSONC), such as VS Code settings and tsconfig.json, and JSON5 allows comments too, but a strict parser like JSON.parse rejects them.',
      },
      {
        q: 'What is the YAML Norway problem?',
        a: 'In YAML 1.1, unquoted values like NO, no, off and on are booleans, so a country code NO becomes false. YAML 1.2 only treats true/false as booleans, but many parsers still default to 1.1 rules. Quote any value that must stay a string.',
      },
      {
        q: 'Which is faster to parse?',
        a: 'JSON. Its grammar is tiny and every language ships a fast native parser. YAML parsers are much more complex. For config files the difference rarely matters; for high-volume data, use JSON.',
      },
    ],
  },
  body: `JSON and YAML can describe the same data. They differ in who they are written for: JSON for machines, YAML for people editing by hand.

## The same config in both

**JSON**

\`\`\`json
{
  "service": "checkout",
  "replicas": 3,
  "debug": false,
  "ports": [8080, 9090],
  "env": {
    "LOG_LEVEL": "info",
    "REGION": "eu-west-1"
  }
}
\`\`\`

**YAML**

\`\`\`yaml
# Checkout service
service: checkout
replicas: 3
debug: false
ports:
  - 8080
  - 9090
env:
  LOG_LEVEL: info
  REGION: eu-west-1
\`\`\`

## Comparison

| | JSON | YAML |
|---|---|---|
| Structure | Braces and brackets | Indentation (spaces only) |
| Comments | Not allowed | \`# comment\` |
| Strings | Always double-quoted | Usually unquoted |
| Multi-line strings | Escaped \`\\n\` | Block scalars \`\\|\` and \`>\` |
| Reuse | None | Anchors and aliases (\`&base\`, \`*base\`) |
| Multiple documents per file | No | Yes, separated by \`---\` |
| Type inference | Explicit | Implicit (can surprise you) |
| Parser complexity | Tiny, fast, everywhere | Large; behaviour varies by version |
| Typical use | APIs, package.json, generated files | Kubernetes, GitHub Actions, Compose, CI |

## Where YAML bites

**Implicit typing.** YAML guesses types from unquoted values. Depending on the parser's YAML version:

\`\`\`yaml
country: NO        # false in YAML 1.1 parsers (the "Norway problem")
version: 1.10      # the number 1.1, not the string "1.10"
zip: 012345        # may become an octal or decimal number
time: 12:30        # sexagesimal 750 in some YAML 1.1 parsers
\`\`\`

Quote anything that must stay a string: \`country: "NO"\`, \`version: "1.10"\`.

**Indentation.** A single misplaced space moves a key to a different parent, and tabs are not allowed at all. The file still parses; it just means something else.

**Unsafe loading.** Some YAML loaders can construct arbitrary objects (Python's \`yaml.load\` without a safe loader, for example). Always use the safe loader for untrusted input.

## Where JSON bites

- **No comments**, so explaining a setting means a separate README or a \`"_comment"\` key.
- **Trailing commas** and single quotes are syntax errors.
- **Noisy to hand-edit** in big files: every string quoted, every level closed.

## Which should you use?

- **The tool decides first.** Kubernetes accepts both, GitHub Actions only YAML, npm only JSON. Use what the ecosystem expects.
- **Generated or machine-read files** (API payloads, lockfiles, build output): JSON.
- **Hand-edited config with comments**: YAML, or JSONC if the tool supports it.
- **Validation**: both work with JSON Schema. Editors use it for YAML autocompletion too (see the [JSON Schema guide](/blog/json-schema-guide)).

## Converting with yq

\`\`\`bash
# YAML → JSON
yq -o=json '.' deployment.yaml > deployment.json

# JSON → YAML
yq -P '.' deployment.json > deployment.yaml
\`\`\`

This is mikefarah's Go \`yq\`. Converting YAML to JSON drops comments, and anchors are expanded into copies.

## Related comparisons

- [JSON vs JSONL](/blog/json-vs-jsonl) for logs and datasets.
- [JSON vs TOON](/blog/json-vs-toon) for prompts sent to LLMs.
`,
};
