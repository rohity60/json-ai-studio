import type { Template } from '@/content/types';

export const template: Template = {
  meta: {
    id: 'mcp-server-config',
    slug: 'mcp-server-config',
    title: 'MCP Server Config (.mcp.json)',
    description:
      'A Model Context Protocol server config — the .mcp.json shared by Claude Code, Cursor and Windsurf — wiring up a local stdio server and a remote HTTP server so AI agents can call external tools.',
    category: 'AI',
    provider: 'MCP',
    difficulty: 'beginner',
    estimatedReadTime: '5 min',
    tags: ['mcp', 'model-context-protocol', 'ai', 'claude-code', 'tools'],
    schemaVersion: 'mcp-v1',
    featured: true,
    updatedAt: '2026-07-18',
    author: 'JSON AI Studio',
    starterPrompts: [
      'Add a Postgres MCP server over stdio',
      'Add an HTTP MCP server with a bearer token',
      'Pass a GITHUB_TOKEN env var to the github server',
      'Remove the filesystem server',
    ],
    relatedTemplates: ['claude-code-settings', 'continue-dev-config'],
    relatedBlogs: ['mcp-json-guide'],
    purpose:
      'Declare the Model Context Protocol servers an AI agent may connect to, so it can read files, query databases or call APIs through a standard tool interface.',
    whenToUse:
      'Giving Claude Code, Cursor or Windsurf access to external tools in a repo — checked in as .mcp.json so the whole team shares the same servers.',
    requiredFields: [
      'mcpServers — a map of server name to its launch/connection config',
      'command — the executable for a stdio server (or type + url for remote)',
    ],
    optionalFields: [
      'args — command-line arguments passed to a stdio server',
      'env — environment variables (often secret references) for the server',
      'type — "stdio" (default), "http" or "sse" for remote servers',
      'headers — auth headers for an http/sse server',
    ],
    bestPractices: [
      'Reference secrets via ${ENV_VAR} rather than hardcoding tokens in the file.',
      'Scope each server to the least access it needs (e.g. a read-only DB role).',
      'Commit .mcp.json so every contributor and Codespace gets the same servers.',
    ],
    security: [
      'Never commit real tokens; use environment-variable expansion for anything secret.',
      'Only add servers from sources you trust — an MCP server can execute arbitrary code.',
      'Prefer read-only credentials for database and API servers.',
    ],
  },
  json: {
    mcpServers: {
      filesystem: {
        command: 'npx',
        args: ['-y', '@modelcontextprotocol/server-filesystem', './src'],
      },
      github: {
        command: 'npx',
        args: ['-y', '@modelcontextprotocol/server-github'],
        env: {
          GITHUB_PERSONAL_ACCESS_TOKEN: '${GITHUB_TOKEN}',
        },
      },
      sentry: {
        type: 'http',
        url: 'https://mcp.sentry.dev/mcp',
        headers: {
          Authorization: 'Bearer ${SENTRY_TOKEN}',
        },
      },
    },
  },
};
