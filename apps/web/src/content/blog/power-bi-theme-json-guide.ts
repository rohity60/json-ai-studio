import type { BlogPost } from '@/content/types';

export const post: BlogPost = {
  meta: {
    slug: 'power-bi-theme-json-guide',
    title: 'Power BI Theme JSON: Colors, Fonts and visualStyles Explained',
    description:
      'How to write a Power BI report theme JSON file: dataColors, structural colors, sentiment colors, textClasses and visualStyles. Includes a full copy-ready theme, a dark variant and how to import, export and debug themes.',
    updatedAt: '2026-11-22',
    author: 'JSON AI Studio',
    tags: ['power bi', 'power bi theme json', 'report theme', 'dataColors', 'visualStyles'],
    readingTime: '8 min',
    aiSummary:
      'A Power BI report theme is a JSON file with a name, a dataColors array for series, structural colors (firstLevelElements to fourthLevelElements, background, secondaryBackground, tableAccent), sentiment colors (good, neutral, bad), diverging colors (maximum, center, minimum, null), textClasses for fonts (callout, title, header, label) and visualStyles for per-visual defaults keyed by visual name and style name, with "*" as a wildcard. Import via View → Themes → Browse for themes; export the current theme with Save current theme. Misspelled properties are ignored silently, so validate against Microsoft\'s report theme JSON schema.',
    relatedTemplates: ['power-bi-theme', 'sample-json-data'],
    relatedBlogs: ['sample-json-data-guide', 'json-schema-guide'],
    faq: [
      {
        q: 'How do I apply a JSON theme in Power BI Desktop?',
        a: 'View → Themes (the dropdown arrow) → Browse for themes, then pick the .json file. It applies to the whole report. To share it, publish the report or distribute the file.',
      },
      {
        q: 'How do I get the JSON of the theme I am using now?',
        a: 'View → Themes → Save current theme. Power BI writes a .json file you can edit and re-import. This is the easiest way to start from a built-in theme.',
      },
      {
        q: 'Why did part of my theme not apply?',
        a: 'Power BI ignores properties it does not recognise, without an error. Check spelling and nesting (visualStyles values are arrays of objects), and check that the visual or report does not already override the setting; manual formatting on a visual wins over the theme.',
      },
      {
        q: 'How many dataColors should a theme have?',
        a: 'At least 8. Power BI uses them in order for series and cycles through generated shades when it runs out.',
      },
    ],
  },
  body: `A Power BI report theme is a single JSON file that sets colors, fonts and default formatting for every visual in a report. Instead of formatting 40 visuals by hand, you change one file.

## A minimal theme

\`\`\`json
{
  "name": "Acme Brand",
  "dataColors": ["#1F6FEB", "#F78166", "#3FB950", "#D29922",
                 "#A371F7", "#DB61A2", "#39C5CF", "#8B949E"],
  "background": "#FFFFFF",
  "firstLevelElements": "#1F2328",
  "tableAccent": "#1F6FEB"
}
\`\`\`

Only \`name\` is required. Everything else falls back to the default theme.

## Colors

### dataColors

The palette for series, in order: the first measure or category uses the first color, and so on. Give at least 8 colors and check them for colorblind safety.

### Structural colors

| Property | Used for |
|---|---|
| \`firstLevelElements\` | Primary text, titles, primary lines |
| \`secondLevelElements\` | Labels, secondary text, axis titles |
| \`thirdLevelElements\` | Gridlines, borders |
| \`fourthLevelElements\` | Disabled or very subtle elements |
| \`background\` | Visual and canvas background |
| \`secondaryBackground\` | Secondary fills such as slicer dropdowns |
| \`tableAccent\` | Table and matrix grid accent |

Older themes use \`foreground\`, \`foregroundNeutralSecondary\` and similar names; the level names above are the current ones.

### Sentiment and diverging colors

\`\`\`json
"good": "#1A7F37",
"neutral": "#9A6700",
"bad": "#CF222E",
"maximum": "#1F6FEB",
"center": "#F6F8FA",
"minimum": "#CF222E",
"null": "#8C959F"
\`\`\`

\`good\`/\`neutral\`/\`bad\` drive KPI visuals and waterfall charts. \`maximum\`/\`center\`/\`minimum\` are the defaults for conditional-formatting color scales.

## Fonts: textClasses

\`\`\`json
"textClasses": {
  "callout": { "fontSize": 28, "fontFace": "Segoe UI Semibold", "color": "#1F2328" },
  "title":   { "fontSize": 12, "fontFace": "Segoe UI Semibold", "color": "#1F2328" },
  "header":  { "fontSize": 11, "fontFace": "Segoe UI Semibold", "color": "#59636E" },
  "label":   { "fontSize": 10, "fontFace": "Segoe UI",          "color": "#59636E" }
}
\`\`\`

The four primary classes cascade to secondary ones (for example \`label\` feeds smaller labels), so setting these four covers most text. Use fonts installed on the viewers' machines or available in the Power BI service.

## visualStyles

\`visualStyles\` sets default formatting per visual. Its shape is always:

\`\`\`text
visualStyles → <visual name or "*"> → <style name or "*"> → <card name> → [ { properties } ]
\`\`\`

\`\`\`json
"visualStyles": {
  "*": {
    "*": {
      "title":      [{ "show": true, "alignment": "left" }],
      "border":     [{ "show": false }],
      "dropShadow": [{ "show": false }]
    }
  },
  "page": {
    "*": {
      "background": [{ "color": { "solid": { "color": "#F6F8FA" } }, "transparency": 0 }]
    }
  },
  "card": {
    "*": {
      "categoryLabels": [{ "show": true }]
    }
  }
}
\`\`\`

- \`"*"\` as the visual name means every visual; then name specific visuals (\`card\`, \`lineChart\`, \`tableEx\`, \`slicer\`, \`page\`) to override.
- Each card value is an **array** containing one object. Forgetting the array is the most common mistake.
- Colors inside visualStyles use the nested form \`{ "solid": { "color": "#hex" } }\`.

## A dark variant

Swap the structural colors and keep the palette bright enough to stand out:

\`\`\`json
{
  "name": "Acme Dark",
  "dataColors": ["#58A6FF", "#FF7B72", "#56D364", "#E3B341",
                 "#BC8CFF", "#FF9BCE", "#76E3EA", "#B1BAC4"],
  "background": "#0D1117",
  "secondaryBackground": "#161B22",
  "firstLevelElements": "#E6EDF3",
  "secondLevelElements": "#9198A1",
  "thirdLevelElements": "#30363D",
  "fourthLevelElements": "#6E7681",
  "tableAccent": "#58A6FF"
}
\`\`\`

Also set the page background in \`visualStyles.page\` so the canvas behind visuals turns dark too.

## Import, export and debug

- **Import:** View → Themes → Browse for themes.
- **Export the current theme:** View → Themes → Save current theme. Great as a starting point.
- **Customize in the UI:** View → Themes → Customize current theme, then Save current theme to see the JSON it produced.
- **Nothing changed?** Power BI ignores unknown or misspelled properties silently. Validate the file against Microsoft's report theme JSON schema (published in the \`microsoft/powerbi-desktop-samples\` GitHub repo) in an editor that supports \`$schema\`.
- **One visual will not change?** Formatting set directly on a visual overrides the theme. Use "Reset to default" on that visual.

## Edit it with AI

Open the [Power BI Theme template](/templates/power-bi-theme) in the studio and ask "make this colorblind-safe", "switch to a dark theme" or "hide borders on all visuals". Each change arrives as a diff you can accept or reject.
`,
};
