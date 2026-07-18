import type { Template } from '@/content/types';

export const template: Template = {
  meta: {
    id: 'mongodb-schema-validation',
    slug: 'mongodb-schema-validation',
    title: 'MongoDB $jsonSchema Validation',
    description:
      'A MongoDB collection validator using $jsonSchema to enforce required fields, types and enums on a users collection — schema safety without an ORM.',
    category: 'Databases',
    provider: 'MongoDB',
    difficulty: 'advanced',
    estimatedReadTime: '6 min',
    tags: ['mongodb', 'schema', 'validation', 'jsonschema', 'database'],
    schemaVersion: 'draft-04',
    featured: false,
    updatedAt: '2026-07-15',
    author: 'JSON AI Studio',
    starterPrompts: [
      'Add a minimum length for the name field',
      'Make the phone field required',
      'Add an enum for the role field',
      'Loosen validation to warn instead of reject',
    ],
    relatedTemplates: ['elasticsearch-query'],
    relatedBlogs: [],
    purpose:
      'Enforce document structure at the database layer so malformed writes are rejected before they land.',
    whenToUse:
      'Passed to db.createCollection(..., { validator }) or collMod to guarantee shape on a critical collection.',
    requiredFields: [
      '$jsonSchema — the JSON Schema the documents must satisfy',
      'bsonType — MongoDB\'s typed equivalent of JSON Schema "type"',
      'required — the list of mandatory fields',
    ],
    optionalFields: [
      'properties — per-field type/constraint definitions',
      'enum — allowed values for a field',
      'additionalProperties — whether unknown fields are allowed',
    ],
    bestPractices: [
      'Start with validationLevel "moderate" and action "warn", then tighten.',
      'Use bsonType (not type) so ObjectId, Date and Decimal128 validate correctly.',
      'Keep the validator in version control alongside migrations.',
    ],
    security: [
      'Validation is integrity, not authorization — pair with role-based access.',
      'Reject additionalProperties on sensitive collections to block field injection.',
    ],
  },
  json: {
    $jsonSchema: {
      bsonType: 'object',
      required: ['email', 'createdAt'],
      additionalProperties: false,
      properties: {
        _id: { bsonType: 'objectId' },
        email: {
          bsonType: 'string',
          pattern: '^.+@.+$',
          description: 'must be a valid email and is required',
        },
        role: {
          bsonType: 'string',
          enum: ['admin', 'member', 'viewer'],
          description: 'must be one of the allowed roles',
        },
        age: { bsonType: 'int', minimum: 0, maximum: 120 },
        createdAt: { bsonType: 'date' },
      },
    },
  },
};
