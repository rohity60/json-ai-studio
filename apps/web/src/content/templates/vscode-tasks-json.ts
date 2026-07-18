import type { Template } from '@/content/types';

export const template: Template = {
  meta: {
    id: 'vscode-tasks-json',
    slug: 'vscode-tasks-json',
    title: 'VS Code tasks.json (Task Runner)',
    description:
      'A .vscode/tasks.json defining build and test tasks — a default build task, a background watch task with a problem matcher, and a compound that chains them — the file behind Run Task in VS Code.',
    category: 'IDE',
    provider: 'VS Code',
    difficulty: 'beginner',
    estimatedReadTime: '5 min',
    tags: ['vscode', 'tasks', 'build', 'automation', 'ide'],
    schemaVersion: '2.0.0',
    featured: false,
    updatedAt: '2026-07-18',
    author: 'JSON AI Studio',
    starterPrompts: [
      'Add a task that runs the linter',
      'Make the build task the default',
      'Add a problem matcher for TypeScript',
      'Chain build then test with dependsOn',
    ],
    relatedTemplates: ['vscode-launch-json', 'vscode-settings'],
    relatedBlogs: ['vscode-tasks-json-guide'],
    purpose:
      'Define reusable build, test and watch commands VS Code can run from the Command Palette or wire into a debug preLaunchTask.',
    whenToUse:
      'Automating a repo in VS Code: a one-key build, a background watch that surfaces compiler errors as problems, or a chain that builds before testing.',
    requiredFields: [
      'version — the tasks schema version, "2.0.0"',
      'tasks — the array of task definitions',
      'label / type / command — per task',
    ],
    optionalFields: [
      'group — mark a task as the default build or test task',
      'problemMatcher — parse output into the Problems panel',
      'isBackground — for watch tasks that keep running',
      'dependsOn — run other tasks first (chaining)',
    ],
    bestPractices: [
      'Give exactly one build task group.kind "build" with isDefault true.',
      'Attach a problemMatcher to watch tasks so errors show in the Problems panel.',
      'Use dependsOn to compose tasks instead of shell && chains.',
    ],
    security: [
      'Do not embed secrets in command or args; read them from the environment.',
      'Be cautious with tasks that run on folder open (runOptions.runOn).',
      'Review any task that pipes to a shell to avoid command injection from inputs.',
    ],
  },
  json: {
    version: '2.0.0',
    tasks: [
      {
        label: 'build',
        type: 'shell',
        command: 'npm run build',
        group: { kind: 'build', isDefault: true },
        problemMatcher: ['$tsc'],
      },
      {
        label: 'watch',
        type: 'shell',
        command: 'npm run watch',
        isBackground: true,
        problemMatcher: ['$tsc-watch'],
      },
      {
        label: 'test',
        type: 'shell',
        command: 'npm test',
        group: 'test',
        dependsOn: ['build'],
      },
    ],
  },
};
