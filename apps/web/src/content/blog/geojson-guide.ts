import type { BlogPost } from '@/content/types';

export const post: BlogPost = {
  meta: {
    slug: 'geojson-guide',
    title: 'GeoJSON Explained: Format, Geometry Types and Examples',
    description:
      'A practical guide to GeoJSON (RFC 7946): FeatureCollection, Feature and geometry types, the [longitude, latitude] order, polygon ring rules and the mistakes that make shapes disappear from a map.',
    updatedAt: '2026-11-21',
    author: 'JSON AI Studio',
    tags: ['geojson', 'gis', 'maps', 'rfc7946'],
    readingTime: '6 min',
    aiSummary:
      'GeoJSON (RFC 7946) encodes geographic data as JSON. A FeatureCollection holds Features; each Feature has a geometry (Point, LineString, Polygon, their Multi* variants or a GeometryCollection) and a properties object. Coordinates are [longitude, latitude] in WGS 84. Polygon rings must be closed (first position equals last), with outer rings counter-clockwise and holes clockwise. Round coordinates to about 6 decimals and never swap lon/lat.',
    relatedTemplates: ['geojson-feature-collection', 'json-schema'],
    relatedBlogs: ['json-schema-guide'],
    faq: [
      {
        q: 'Is it [lat, lng] or [lng, lat]?',
        a: 'GeoJSON is always [longitude, latitude] (x, y), optionally followed by altitude. Many map UIs and APIs display lat, lng, so swapping them is the most common bug. A point that lands in the ocean or Antarctica usually means swapped coordinates.',
      },
      {
        q: 'Can GeoJSON use a different coordinate system?',
        a: 'RFC 7946 removed the old "crs" member: coordinates are WGS 84 longitude/latitude. Reproject other systems (such as Web Mercator meters or a national grid) before writing GeoJSON.',
      },
      {
        q: 'How big can a GeoJSON file get?',
        a: 'It is plain text, so large datasets get heavy quickly. Round coordinates, simplify geometries for display, and for very large or tiled data consider vector tiles, FlatGeobuf or GeoParquet, keeping GeoJSON as the interchange format.',
      },
    ],
  },
  body: `GeoJSON is the JSON format for maps. Leaflet, Mapbox, OpenLayers, PostGIS, QGIS and most GIS APIs read and write it. The whole spec is small, but a few rules trip everybody up.

## The structure

\`\`\`json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": { "type": "Point", "coordinates": [-122.4194, 37.7749] },
      "properties": { "name": "Downtown Store" }
    }
  ]
}
\`\`\`

- **FeatureCollection**: the usual root, holding a \`features\` array.
- **Feature**: one thing on the map, with a \`geometry\` and a \`properties\` object (your attributes, or \`null\`).
- **geometry**: the shape.

## Geometry types

| Type | coordinates | Example use |
|---|---|---|
| \`Point\` | \`[lon, lat]\` | a store |
| \`LineString\` | \`[[lon, lat], …]\` | a route |
| \`Polygon\` | \`[[[lon, lat], …]]\` (rings) | a delivery zone |
| \`MultiPoint\` / \`MultiLineString\` / \`MultiPolygon\` | arrays of the above | islands, multi-part areas |
| \`GeometryCollection\` | \`geometries: [...]\` | mixed shapes (use sparingly) |

## Rule 1: longitude first

\`[-122.4194, 37.7749]\` is San Francisco. \`[37.7749, -122.4194]\` is somewhere in Antarctica. GeoJSON is **x, y**, which means **longitude, latitude**, even though most people say "lat, long".

## Rule 2: close and wind your polygons

A Polygon is an array of **linear rings**. The first ring is the outer boundary and any others are holes.

- Each ring must be **closed**: the last position repeats the first.
- RFC 7946 says outer rings go **counter-clockwise** and holes **clockwise**. Many tools are lenient about this, but some renderers and validators are not.

\`\`\`json
"coordinates": [[
  [-122.43, 37.77], [-122.40, 37.77], [-122.40, 37.79], [-122.43, 37.79], [-122.43, 37.77]
]]
\`\`\`

## Rule 3: WGS 84 only

Modern GeoJSON has no \`crs\` member. Coordinates are WGS 84 degrees. If your data is in meters (Web Mercator) or a local grid, reproject it first.

## Keep files small

- Six decimal places is about 10 cm of precision. Anything more just adds bytes.
- Simplify geometries for display zoom levels.
- Put shared attributes in \`properties\` and keep them flat. It makes filtering easy.

## Security and privacy notes

- Location history and home addresses are personal data. Aggregate or coarsen them before sharing.
- Cap feature counts and coordinate array sizes when you accept uploads.

Open the GeoJSON template and ask the workspace to "add a category property to every feature" or "remove features where open is false", then diff the result.`,
};
