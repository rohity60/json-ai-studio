import type { BlogPost } from '@/content/types';

export const post: BlogPost = {
  meta: {
    slug: 'sample-json-data-guide',
    title: 'Sample JSON Data for Testing: Employees, Students, API Responses and More',
    description:
      'Copy-ready sample JSON: employee and student records, an array of objects, nested data, a REST API response, a Postman request body, plus how to import it into MongoDB and Power BI and how to generate a large file.',
    updatedAt: '2026-11-22',
    author: 'JSON AI Studio',
    tags: ['sample json', 'test data', 'employee json', 'student json', 'postman', 'mongodb', 'power bi'],
    readingTime: '8 min',
    aiSummary:
      'Sample JSON data for testing: employees (with nested address, skills array and a null manager), students (with a grades object and ISO dates), products with variants, and a paginated API response. A Postman raw JSON body needs Content-Type: application/json. mongoimport needs --jsonArray for a top-level array, or one document per line (JSONL). Power BI reads JSON via Get Data → JSON and needs "To Table" then Expand on records. Generate large files with a short script rather than by hand. Use example.com emails and never production data.',
    relatedTemplates: ['sample-json-data', 'sample-api-response', 'postman-collection', 'mongodb-schema-validation'],
    relatedBlogs: ['json-vs-jsonl', 'json-schema-guide', 'power-bi-theme-json-guide'],
    faq: [
      {
        q: 'Where can I get free sample JSON data?',
        a: 'Copy the examples on this page or open the Sample JSON Data template in the studio and ask for more rows ("add 50 employees in Sales"). For a live fake API, public mock services such as JSONPlaceholder return JSON over HTTP.',
      },
      {
        q: 'What is an array of objects in JSON?',
        a: 'A top-level [ ... ] whose elements are { ... } objects with the same keys, for example a list of employees. It is the most common shape for tabular data and what most import tools expect.',
      },
      {
        q: 'Why does mongoimport fail on my JSON file?',
        a: 'If the file is one big array, add --jsonArray. Without it, mongoimport expects one JSON document per line (JSON Lines). Also check for trailing commas and comments, which strict JSON does not allow.',
      },
      {
        q: 'How do I send JSON in a Postman request body?',
        a: 'Body → raw → JSON. Postman then sets Content-Type: application/json. Paste an object like the Postman example below and use {{variables}} for values that change between environments.',
      },
      {
        q: 'Can JSON store dates?',
        a: 'No. JSON has strings, numbers, booleans, null, objects and arrays. Store dates as ISO 8601 strings like "2024-03-15T09:30:00Z" and parse them in your code.',
      },
    ],
  },
  body: `Most people searching for "sample JSON" need the same few shapes: a list of people, some nested data, and an API response. Every example below is valid JSON you can paste straight into a parser, database or test.

## Sample employee JSON

An array of objects, each with every JSON type: string, number, boolean, null, nested object and array.

\`\`\`json
[
  {
    "id": 1001,
    "name": "Asha Rao",
    "email": "asha.rao@example.com",
    "department": "Engineering",
    "salary": 145000,
    "isActive": true,
    "hiredAt": "2019-04-01",
    "manager": null,
    "skills": ["go", "kubernetes"],
    "address": { "city": "Bengaluru", "country": "IN" }
  },
  {
    "id": 1002,
    "name": "Daniel Okafor",
    "email": "daniel.okafor@example.com",
    "department": "Engineering",
    "salary": 128000,
    "isActive": true,
    "hiredAt": "2021-09-13",
    "manager": 1001,
    "skills": ["typescript", "react"],
    "address": { "city": "Lagos", "country": "NG" }
  }
]
\`\`\`

\`manager\` holds another employee's \`id\`, which is how you model relationships in flat JSON. The top-level employee is \`null\`.

## Sample student JSON

\`\`\`json
{
  "students": [
    {
      "id": "S-001",
      "name": "Liam Chen",
      "age": 20,
      "course": "Computer Science",
      "enrolledAt": "2024-08-26T09:00:00Z",
      "grades": { "math": 91, "physics": 84, "programming": 97 },
      "scholarship": true
    },
    {
      "id": "S-002",
      "name": "Priya Nair",
      "age": 19,
      "course": "Economics",
      "enrolledAt": "2025-08-25T09:00:00Z",
      "grades": { "math": 78, "statistics": 88 },
      "scholarship": false
    }
  ]
}
\`\`\`

\`grades\` is an object (subject → score) rather than an array because each subject appears once. Use an array when order matters or keys repeat.

## Nested JSON example

Deep nesting shows up in orders, configs and API payloads. This order has an object inside an array inside an object:

\`\`\`json
{
  "orderId": "ord_8f3a2c",
  "customer": {
    "id": "cus_19b7",
    "shipping": {
      "line1": "12 MG Road",
      "city": "Bengaluru",
      "geo": { "lat": 12.9756, "lng": 77.6066 }
    }
  },
  "items": [
    { "sku": "TSHIRT-BASIC", "qty": 2, "options": { "size": "M", "color": "black" } }
  ]
}
\`\`\`

The JSON Pointer to the color is \`/items/0/options/color\`. In JavaScript it is \`order.items[0].options.color\`.

## Sample API response JSON

A list endpoint usually wraps records in an envelope with pagination:

\`\`\`json
{
  "data": [
    { "id": "ord_8f3a2c", "status": "shipped", "total": { "amount": 5998, "currency": "USD" } }
  ],
  "meta": { "pagination": { "page": 1, "perPage": 20, "total": 37, "totalPages": 2 } },
  "links": { "next": "https://api.example.com/v1/orders?page=2", "prev": null },
  "errors": []
}
\`\`\`

And the matching error response:

\`\`\`json
{
  "data": null,
  "errors": [
    { "code": "not_found", "message": "Order ord_999 does not exist", "field": "id" }
  ]
}
\`\`\`

Money is stored in cents (\`5998\`) to avoid floating-point rounding. The full version is in the [Sample API Response template](/templates/sample-api-response).

## Sample JSON body for Postman

In Postman choose **Body → raw → JSON**, which sets \`Content-Type: application/json\`:

\`\`\`json
{
  "name": "Asha Rao",
  "email": "asha.rao@example.com",
  "role": "admin",
  "sendWelcomeEmail": false,
  "tags": ["beta", "internal"]
}
\`\`\`

Use \`{{baseUrl}}\` or \`{{userEmail}}\` variables for values that differ per environment. Postman's dynamic variables such as \`{{$randomEmail}}\` generate fresh fake values on every send.

## Importing sample JSON into MongoDB

\`mongoimport\` accepts two shapes:

\`\`\`bash
# A file that is one big array
mongoimport --db test --collection employees --file employees.json --jsonArray

# A file with one document per line (JSON Lines)
mongoimport --db test --collection employees --file employees.jsonl
\`\`\`

Forgetting \`--jsonArray\` on an array file is the most common import error. See [JSON vs JSONL](/blog/json-vs-jsonl) for when to use which.

## Loading sample JSON into Power BI

1. **Get Data → JSON** and pick the file.
2. Power Query shows a **List**. Choose **To Table**.
3. Click the expand icon on the column to turn each record's fields into columns. Expand nested objects (like \`address\`) the same way.

Arrays inside records (like \`skills\`) expand into extra rows, so decide whether you need them before expanding. To style the report, see [Power BI theme JSON](/blog/power-bi-theme-json-guide).

## Generating a large JSON file

For load tests you need thousands of rows. Generate them rather than writing them by hand:

\`\`\`python
import json, random

depts = ["Engineering", "Sales", "People"]
rows = [
    {
        "id": i,
        "name": f"Employee {i}",
        "email": f"employee{i}@example.com",
        "department": random.choice(depts),
        "salary": random.randint(40_000, 180_000),
        "isActive": random.random() > 0.1,
    }
    for i in range(1, 10_001)
]

with open("employees.json", "w") as f:
    json.dump(rows, f, indent=2)
\`\`\`

For files over a few hundred MB, write JSON Lines instead so tools can stream them line by line.

## Rules that keep sample data valid

- Keys and strings use **double quotes**. Single quotes are invalid.
- **No trailing commas** and **no comments**.
- One root value per file (an object or an array).
- Dates are ISO 8601 strings; JSON has no date type.
- Use \`example.com\` emails and fake phone numbers. Never copy production records into fixtures.

## Make it your own

Open the [Sample JSON Data template](/templates/sample-json-data) in the studio and ask in plain English: "add 20 students with a city field", "give every product a discount price", or "write a JSON Schema for the employees array". Each change shows up as a diff you accept or reject.
`,
};
