import type { BlogPost } from '@/content/types';

export const post: BlogPost = {
  meta: {
    slug: 'mcp-json-guide',
    title: 'The .mcp.json Guide',
    description:
      'How .mcp.json wires Model Context Protocol servers into Claude Code, Cursor and Windsurf — stdio vs remote servers, passing secrets via environment variables, and scoping access safely.',
    updatedAt: '2026-11-21',
    author: 'JSON AI Studio',
    tags: ['mcp', 'model-context-protocol', 'ai', 'claude-code'],
    readingTime: '5 min',
    aiSummary:
      '.mcp.json declares the MCP servers an AI agent can use. Each entry is either a local stdio server (command + args + env) or a remote one (type http/sse + url + headers). It is the same format across Claude Code, Cursor and Windsurf. Reference secrets with ${ENV_VAR}, scope credentials to least privilege, and only add servers you trust — they can run code.',
    relatedTemplates: ['mcp-server-config'],
    relatedBlogs: ['claude-code-settings-guide', 'json-schema-guide'],
    faq: [
      {
        q: 'Is .mcp.json the same across tools?',
        a: 'The server definitions are nearly identical, but each tool reads a different file. Claude Code reads .mcp.json at the project root, Cursor reads .cursor/mcp.json, and VS Code reads .vscode/mcp.json, which uses a top-level "servers" key instead of "mcpServers". Windsurf keeps a global mcp_config.json and names the remote URL key serverUrl. Copy the entries across, but check each tool\'s path and key names.',
      },
      {
        q: 'stdio or http — which server type?',
        a: 'stdio (the default) launches a local process and talks over stdin/stdout — best for filesystem or CLI-backed tools. http (Streamable HTTP) connects to a hosted server by URL — best for SaaS tools like Sentry or Linear. sse is the older remote transport; use http for new servers.',
      },
    ],
  },
  body: `\`.mcp.json\` is how you hand an AI agent tools. Each entry under \`mcpServers\` is a server the agent can call — to read files, query a database, or hit an API — through the Model Context Protocol.

## Two kinds of server

**Local (stdio)** — the agent launches a process and talks over stdin/stdout:

\`\`\`json
"filesystem": {
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-filesystem", "./src"]
}
\`\`\`

**Remote (http)**: the agent connects to a hosted URL over Streamable HTTP. \`sse\` is the older remote transport; new servers should use \`http\`:

\`\`\`json
"sentry": {
  "type": "http",
  "url": "https://mcp.sentry.dev/mcp",
  "headers": { "Authorization": "Bearer \${SENTRY_TOKEN}" }
}
\`\`\`

## Pass secrets by reference

Never hardcode a token. Use \`\${ENV_VAR}\` expansion so the value comes from the environment, not the committed file:

\`\`\`json
"github": {
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-github"],
  "env": { "GITHUB_PERSONAL_ACCESS_TOKEN": "\${GITHUB_TOKEN}" }
}
\`\`\`

## Same shape, different files

Most clients use nearly the same server entry, but each one reads a different file:

| Client | Project file | Root key |
|---|---|---|
| Claude Code | \`.mcp.json\` | \`mcpServers\` |
| Cursor | \`.cursor/mcp.json\` (global: \`~/.cursor/mcp.json\`) | \`mcpServers\` |
| VS Code | \`.vscode/mcp.json\` | \`servers\` |
| Windsurf | global \`mcp_config.json\` | \`mcpServers\` (remote URL key: \`serverUrl\`) |

Checking the file into the repo gives every contributor, and every Codespace, the same toolset. Just keep one copy per client you support, or generate them all from one source.

## Tool schemas

Each server advertises its tools with a JSON Schema \`inputSchema\`, and optionally an \`outputSchema\`. The 2026 spec revision moved both to full **JSON Schema 2020-12**, so \`$defs\`, \`oneOf\` and similar keywords now work. The input root must still be an object. See the JSON Schema 2020-12 template for a starting point.

## Security notes

- An MCP server can execute arbitrary code. Only add servers from sources you trust.
- Give each server the least access it needs — a read-only DB role, a scoped API token.
- Keep real tokens out of the file; rely on environment-variable expansion.

Open the MCP config template and ask the workspace to "add a Postgres MCP server over stdio" or "add an HTTP MCP server with a bearer token", then diff the result.`,
};
