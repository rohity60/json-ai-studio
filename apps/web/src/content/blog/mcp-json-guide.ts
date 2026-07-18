import type { BlogPost } from '@/content/types';

export const post: BlogPost = {
  meta: {
    slug: 'mcp-json-guide',
    title: 'The .mcp.json Guide',
    description:
      'How .mcp.json wires Model Context Protocol servers into Claude Code, Cursor and Windsurf — stdio vs remote servers, passing secrets via environment variables, and scoping access safely.',
    updatedAt: '2026-07-18',
    author: 'JSON AI Studio',
    tags: ['mcp', 'model-context-protocol', 'ai', 'claude-code'],
    readingTime: '5 min',
    aiSummary:
      '.mcp.json declares the MCP servers an AI agent can use. Each entry is either a local stdio server (command + args + env) or a remote one (type http/sse + url + headers). It is the same format across Claude Code, Cursor and Windsurf. Reference secrets with ${ENV_VAR}, scope credentials to least privilege, and only add servers you trust — they can run code.',
    relatedTemplates: ['mcp-server-config'],
    relatedBlogs: [],
    faq: [
      {
        q: 'Is .mcp.json the same across tools?',
        a: 'The mcpServers shape is shared by Claude Code, Cursor and Windsurf, so one file generally moves between them. Some tools add their own extra keys, but the server definitions are compatible.',
      },
      {
        q: 'stdio or http — which server type?',
        a: 'stdio (the default) launches a local process and talks over stdin/stdout — best for filesystem or CLI-backed tools. http/sse connects to a hosted server by URL — best for SaaS tools like Sentry or Linear.',
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

**Remote (http / sse)** — the agent connects to a hosted URL:

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

## One file, many tools

Because Claude Code, Cursor and Windsurf all read the same \`mcpServers\` shape, checking \`.mcp.json\` into the repo gives every contributor — and every Codespace — the same toolset.

## Security notes

- An MCP server can execute arbitrary code. Only add servers from sources you trust.
- Give each server the least access it needs — a read-only DB role, a scoped API token.
- Keep real tokens out of the file; rely on environment-variable expansion.

Open the MCP config template and ask the workspace to "add a Postgres MCP server over stdio" or "add an HTTP MCP server with a bearer token", then diff the result.`,
};
