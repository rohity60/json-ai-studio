import type { BlogPost } from '@/content/types';

export const post: BlogPost = {
  meta: {
    slug: 'json-ld-structured-data-guide',
    title: 'JSON-LD Structured Data: Examples for Article, Product, FAQ and Organization',
    description:
      'What JSON-LD is, how @context, @type, @id and @graph fit together, and copy-ready schema.org examples for Article, Product, FAQPage, Organization and BreadcrumbList, plus the mistakes that lose rich results.',
    updatedAt: '2026-11-21',
    author: 'JSON AI Studio',
    tags: ['json-ld', 'schema.org', 'seo', 'structured-data'],
    readingTime: '7 min',
    aiSummary:
      'JSON-LD is JSON that describes a page using the schema.org vocabulary, embedded in a <script type="application/ld+json"> tag. @context is "https://schema.org", @type names the entity, @id gives it a stable URI, and @graph holds several linked entities in one block. Common types are Article, Product (with Offer), Organization, BreadcrumbList and FAQPage. Markup must match visible content, dates should be ISO 8601 with a timezone, and server-side injection must escape "</" to avoid XSS.',
    relatedTemplates: ['json-ld-structured-data', 'json-schema'],
    relatedBlogs: ['json-schema-guide'],
    faq: [
      {
        q: 'Where do I put JSON-LD on the page?',
        a: 'Inside a <script type="application/ld+json"> tag, in either the head or the body. Search engines read it from either place. One script with an @graph is easier to maintain than many separate scripts.',
      },
      {
        q: 'JSON-LD vs Microdata: which should I use?',
        a: 'JSON-LD. It is the format search engines recommend, it keeps markup separate from your HTML and it is trivial to generate from data. Microdata and RDFa still work, but are harder to maintain.',
      },
      {
        q: 'Does structured data improve rankings?',
        a: 'Not directly. It makes your page eligible for rich results (stars, prices, breadcrumbs) and helps search engines and AI crawlers understand the entities on it, which can raise click-through. Some rich result types, such as FAQ snippets, are now shown only for a limited set of sites, so check the current eligibility rules.',
      },
    ],
  },
  body: `JSON-LD ("JSON for Linking Data") is how a page tells machines what it is about: this is an Article, written by this Person, published by this Organization on this date. You write it once in a \`<script type="application/ld+json">\` tag, and crawlers read it.

## The four keywords

\`\`\`json
{
  "@context": "https://schema.org",
  "@type": "Article",
  "@id": "https://example.com/blog/post#article",
  "headline": "The JSON Schema Guide"
}
\`\`\`

- **@context**: the vocabulary. Almost always \`https://schema.org\`.
- **@type**: what the thing is: \`Article\`, \`Product\`, \`Organization\`, \`Event\`, \`Recipe\` and so on.
- **@id**: a stable URI for the entity, so other nodes can reference it.
- **@graph**: an array of several entities in one block.

## Article

\`\`\`json
{
  "@context": "https://schema.org",
  "@type": "Article",
  "headline": "The JSON Schema 2020-12 Guide",
  "image": ["https://example.com/cover.png"],
  "datePublished": "2026-11-21T09:00:00+00:00",
  "dateModified": "2026-11-21T09:00:00+00:00",
  "author": { "@type": "Person", "name": "Jane Doe", "url": "https://example.com/authors/jane" }
}
\`\`\`

## Product with an Offer

\`\`\`json
{
  "@context": "https://schema.org",
  "@type": "Product",
  "name": "Trail Runner 3",
  "image": "https://example.com/shoe.png",
  "brand": { "@type": "Brand", "name": "Acme" },
  "offers": {
    "@type": "Offer",
    "price": "129.00",
    "priceCurrency": "USD",
    "availability": "https://schema.org/InStock"
  }
}
\`\`\`

## FAQPage

\`\`\`json
{
  "@context": "https://schema.org",
  "@type": "FAQPage",
  "mainEntity": [{
    "@type": "Question",
    "name": "Does tsconfig.json allow comments?",
    "acceptedAnswer": { "@type": "Answer", "text": "Yes, it is parsed as JSONC." }
  }]
}
\`\`\`

## Linking entities with @graph

Rather than repeating your Organization on every node, define it once with an \`@id\` and reference it:

\`\`\`json
{
  "@context": "https://schema.org",
  "@graph": [
    { "@type": "Organization", "@id": "https://example.com/#org", "name": "Example Inc." },
    { "@type": "Article", "headline": "...", "publisher": { "@id": "https://example.com/#org" } }
  ]
}
\`\`\`

## Mistakes that cost you rich results

- **Markup that doesn't match the page.** Prices, ratings and FAQs must be visible to users too.
- **Dates without a timezone.** Use full ISO 8601: \`2026-11-21T09:00:00+00:00\`.
- **Relative URLs.** Use absolute URLs for \`image\`, \`url\` and \`@id\`.
- **Invalid JSON.** One trailing comma and the whole block is ignored, silently.

## Security notes

- When you render JSON-LD server-side, escape \`</\` (for example as \`\\u003c/\`). A user-supplied value containing \`</script>\` can otherwise break out of the tag and cause XSS.
- Structured data is public and crawled. Never put private fields in it.

Open the JSON-LD template and ask the workspace to "convert this to a Product with an Offer" or "add an FAQPage node to the @graph", then validate the diff.`,
};
