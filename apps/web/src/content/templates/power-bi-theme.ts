import type { Template } from '@/content/types';

export const template: Template = {
  meta: {
    id: 'power-bi-theme',
    slug: 'power-bi-theme',
    title: 'Power BI Report Theme JSON',
    description:
      'A complete Power BI report theme: brand data colors, structural colors, sentiment and diverging colors, text classes, and visualStyles defaults for every visual. Import it with View → Themes → Browse for themes.',
    category: 'Data',
    provider: 'Microsoft Power BI',
    difficulty: 'intermediate',
    estimatedReadTime: '6 min',
    tags: ['power bi', 'power bi theme', 'report theme', 'dataColors', 'visualStyles', 'dashboard'],
    schemaVersion: 'Power BI report theme',
    featured: true,
    updatedAt: '2026-11-22',
    author: 'JSON AI Studio',
    starterPrompts: [
      'Replace the data colors with a colorblind-safe palette',
      'Make it a dark theme',
      'Turn off titles on every visual by default',
      'Use Segoe UI 11pt for all labels',
    ],
    relatedTemplates: ['sample-json-data', 'json-schema'],
    relatedBlogs: ['power-bi-theme-json-guide', 'sample-json-data-guide'],
    purpose:
      'Apply consistent brand colors, fonts and visual defaults to every page and visual of a Power BI report from one JSON file.',
    whenToUse:
      'Branding a report or a whole organisation\'s reports, switching a report to dark mode, or removing repetitive per-visual formatting.',
    requiredFields: [
      'name: the theme name shown in Power BI',
    ],
    optionalFields: [
      'dataColors: array of hex colors used for series, in order',
      'firstLevelElements / secondLevelElements / thirdLevelElements / fourthLevelElements: text and line colors from primary to subtle',
      'background / secondaryBackground: canvas and visual backgrounds',
      'tableAccent: grid and header accent in tables and matrices',
      'good / neutral / bad: KPI and sentiment colors',
      'maximum / center / minimum / null: diverging and conditional-formatting colors',
      'textClasses: callout, title, header and label font size, family and color',
      'visualStyles: default formatting per visual type ("*" = all visuals) and per style ("*" = all)',
    ],
    bestPractices: [
      'Give dataColors at least 8 colors; Power BI cycles through them for extra series.',
      'Use textClasses for fonts instead of setting fonts in visualStyles one by one.',
      'Start visualStyles with "*" / "*" for global defaults, then override specific visuals like "card".',
      'Check contrast: first-level text on background should meet WCAG AA (4.5:1).',
      'Use a JSON Schema-aware editor with Microsoft\'s published report theme schema to catch misspelled properties, which Power BI silently ignores.',
    ],
    security: [
      'Theme files only hold formatting, but they can reference background image URLs; use images from trusted hosts only.',
    ],
    formatSignature: ['/name', '/dataColors'],
  },
  json: {
    name: 'Acme Brand',
    dataColors: [
      '#1F6FEB',
      '#F78166',
      '#3FB950',
      '#D29922',
      '#A371F7',
      '#DB61A2',
      '#39C5CF',
      '#8B949E',
    ],
    firstLevelElements: '#1F2328',
    secondLevelElements: '#59636E',
    thirdLevelElements: '#D0D7DE',
    fourthLevelElements: '#8C959F',
    background: '#FFFFFF',
    secondaryBackground: '#F6F8FA',
    tableAccent: '#1F6FEB',
    good: '#1A7F37',
    neutral: '#9A6700',
    bad: '#CF222E',
    maximum: '#1F6FEB',
    center: '#F6F8FA',
    minimum: '#CF222E',
    null: '#8C959F',
    textClasses: {
      callout: { fontSize: 28, fontFace: 'Segoe UI Semibold', color: '#1F2328' },
      title: { fontSize: 12, fontFace: 'Segoe UI Semibold', color: '#1F2328' },
      header: { fontSize: 11, fontFace: 'Segoe UI Semibold', color: '#59636E' },
      label: { fontSize: 10, fontFace: 'Segoe UI', color: '#59636E' },
    },
    visualStyles: {
      '*': {
        '*': {
          title: [{ show: true, alignment: 'left' }],
          border: [{ show: false }],
          background: [{ show: true, transparency: 0 }],
          dropShadow: [{ show: false }],
        },
      },
      page: {
        '*': {
          background: [{ color: { solid: { color: '#F6F8FA' } }, transparency: 0 }],
        },
      },
      card: {
        '*': {
          categoryLabels: [{ show: true }],
        },
      },
    },
  },
};
