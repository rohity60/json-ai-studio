import type { BlogPost } from '@/content/types';

export const post: BlogPost = {
  meta: {
    slug: 'docker-daemon-json-guide',
    title: 'The Docker daemon.json Guide',
    description:
      'What goes in /etc/docker/daemon.json, the options that matter most in production — log rotation, storage driver, live-restore — and how to apply changes safely.',
    updatedAt: '2026-07-15',
    author: 'JSON AI Studio',
    tags: ['docker', 'devops', 'daemon', 'production'],
    readingTime: '5 min',
    aiSummary:
      'daemon.json configures the Docker Engine host-wide. The highest-impact settings are log rotation (prevents full disks), the overlay2 storage driver, and live-restore. Validate with dockerd --validate before restarting.',
    relatedTemplates: ['docker-daemon'],
    relatedBlogs: [],
    faq: [
      {
        q: 'Where does daemon.json live?',
        a: 'On Linux, /etc/docker/daemon.json. On Docker Desktop, it is edited through the app settings UI.',
      },
      {
        q: 'How do I apply changes?',
        a: 'Restart the daemon (systemctl restart docker). Validate first with `dockerd --validate` to catch JSON or option errors.',
      },
    ],
  },
  body: `\`daemon.json\` configures the Docker **Engine** itself — not a single container, but the whole host. A few options prevent the most common production incidents.

## Stop disks filling up

By default, container logs grow forever. This one block is the setting people wish they had set sooner:

\`\`\`json
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" }
}
\`\`\`

Now each container keeps at most three 10 MB log files.

## Use overlay2

\`"storage-driver": "overlay2"\` is the modern default and what you want on any current kernel. Avoid legacy drivers like \`devicemapper\`.

## Survive daemon restarts

\`"live-restore": true\` keeps your containers running while the Docker daemon itself restarts or upgrades — essential for zero-downtime host maintenance.

## Tune concurrency

\`max-concurrent-downloads\` and \`max-concurrent-uploads\` smooth out image pulls on busy CI hosts.

## Apply changes safely

1. Edit \`/etc/docker/daemon.json\`.
2. **Validate**: \`dockerd --validate\`.
3. Restart: \`systemctl restart docker\`.

A malformed daemon.json can stop Docker from starting, so always validate first.

## Security notes

- Never expose the daemon over \`tcp://\` without TLS — it is root-equivalent.
- Bind \`metrics-addr\` to \`127.0.0.1\` only.

Open the daemon.json template and ask the workspace to "cap logs at 5 files of 20MB" or "add a registry mirror", then diff the result.`,
};
