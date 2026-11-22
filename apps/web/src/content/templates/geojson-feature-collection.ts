import type { Template } from '@/content/types';

export const template: Template = {
  meta: {
    id: 'geojson-feature-collection',
    slug: 'geojson-feature-collection',
    title: 'GeoJSON FeatureCollection',
    description:
      'A GeoJSON FeatureCollection (RFC 7946) with a Point, a LineString and a Polygon, each carrying properties. This is the format Leaflet, Mapbox, PostGIS and most map tools import.',
    category: 'Data',
    provider: 'GeoJSON',
    difficulty: 'beginner',
    estimatedReadTime: '5 min',
    tags: ['geojson', 'gis', 'maps', 'rfc7946', 'coordinates'],
    schemaVersion: 'RFC 7946',
    featured: false,
    updatedAt: '2026-11-21',
    author: 'JSON AI Studio',
    starterPrompts: [
      'Add a property "category" to every feature',
      'Add a second store as a Point feature',
      'Change the polygon into a MultiPolygon with a hole',
      'Remove all features where open is false',
    ],
    relatedTemplates: ['json-schema', 'elasticsearch-query'],
    relatedBlogs: ['geojson-guide'],
    purpose:
      'Represent geographic features (points, lines and areas) along with their attributes in plain JSON.',
    whenToUse:
      'Sharing map data between tools, feeding a web map, storing shapes in a document database, or exporting query results from PostGIS.',
    requiredFields: [
      'type: "FeatureCollection" at the root, "Feature" for each feature',
      'features: the array of Feature objects',
      'geometry: per feature, with its own type and coordinates',
      'properties: per feature, an object or null',
    ],
    optionalFields: [
      'id: a per-feature identifier',
      'bbox: [minLon, minLat, maxLon, maxLat] bounding box',
    ],
    bestPractices: [
      'Coordinates are [longitude, latitude], in that order. Swapping them is the most common GeoJSON bug.',
      'Close polygon rings: the first and last positions must be identical.',
      'Outer rings go counter-clockwise and holes clockwise (the right-hand rule).',
      'Round coordinates to about 6 decimals (roughly 10 cm); more only adds file size.',
    ],
    security: [
      'Location data can identify people; strip or coarsen it before sharing.',
      'Bound feature counts and coordinate arrays when accepting uploads.',
    ],
    formatSignature: ['/type', '/features/*/geometry'],
  },
  json: {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        id: 'store-1',
        geometry: { type: 'Point', coordinates: [-122.4194, 37.7749] },
        properties: { name: 'Downtown Store', open: true },
      },
      {
        type: 'Feature',
        id: 'route-1',
        geometry: {
          type: 'LineString',
          coordinates: [
            [-122.4194, 37.7749],
            [-122.4098, 37.7858],
            [-122.4021, 37.7936],
          ],
        },
        properties: { name: 'Delivery route', length_km: 2.4 },
      },
      {
        type: 'Feature',
        id: 'zone-1',
        geometry: {
          type: 'Polygon',
          coordinates: [
            [
              [-122.43, 37.77],
              [-122.4, 37.77],
              [-122.4, 37.79],
              [-122.43, 37.79],
              [-122.43, 37.77],
            ],
          ],
        },
        properties: { name: 'Delivery zone', fee: 4.99 },
      },
    ],
  },
};
