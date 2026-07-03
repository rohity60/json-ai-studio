Product Requirement Document (PRD)Project: AI JSON Studio (Cloud SaaS & Google Cloud Integrations)Target Execution Engine: AI Coding AgentGoal: Build a secure, multi-tenant cloud application that uses LLMs to structure, validate, fix, and chunk massive JSON files, with plug-and-play extension layers for Google Cloud (Vertex AI & Firebase).1. Executive Summary & Core ValueAI JSON Studio is an intelligent control plane for managing sprawling, complex JSON configurations. Its primary value is solving the "context window and formatting crash" problem when individual developers or automated agents try to manipulate massive JSON datasets (up to 50,000+ lines).Monetization ArchitectureWeb SaaS (Pro Tier): Paid via Stripe for processing large files. Uses a central LLM token pool.Google Integrations (Enterprise): High-margin. End-users install the extension and supply their own Google Cloud billing/token infrastructure.2. Technical Stack & Repository StructureThe agent must construct a single codebase structured as follows:text├── src/
│   ├── backend/          # Python Fast API
│   │   ├── main.py       # API Router & Middleware
│   │   ├── chunker.py    # Custom JSON chunking logic
│   │   └── auth.py       # JWT & OAuth validations
│   └── web_saas/         # Next.js UI for the web application
└── integrations/
    ├── google-vertex/    # Vertex AI OpenAPI Spec & Manifest
    │   └── openapi.yaml
    └── google-firebase/  # Firebase Extension Core Logic
        ├── extension.yaml
        └── functions/    # Firebase Cloud Functions (Node.js/Python)
Use code with caution.3. Core Functional Requirements (Backend Engine)Requirement 3.1: Intelligent JSON Chunking & MergingProblem: Massive JSON files exceed LLM token context limits or cause the LLM to output malformed, truncated strings.Agent Instruction: Implement a semantic JSON parser in chunker.py.Input: A raw JSON string (> 5MB) and an editing prompt (e.g., "Change all production database timeout limits to 60s").Logic:Parse the JSON text into an abstract syntax tree (AST) or structural dictionary object.Break the dictionary into nested logical blocks (e.g., top-level keys or specific array blocks).Send only the relevant targeted blocks to the LLM alongside the system prompt.Re-assemble and merge the altered blocks cleanly back into the master JSON without dropping unedited keys, tracking formatting parameters.Requirement 3.2: Automated Syntax and Schema RepairLogic: If an LLM or human output fails json.loads(), pass the broken text to a lightweight, targeted correction prompt to fix trailing commas, unescaped quotes, or bad bracket closures instantly.4. Google Workspace & Cloud Native System DesignIntegration 4.1: Google Vertex AI ExtensionThe agent must generate a functional openapi.yaml file inside /integrations/google-vertex/ that maps your backend engine to Google's Vertex AI Agent Builder [1.3.4, 0.1].Agent Code Generation Prompt for Vertex Specification:yamlopenapi: 3.0.0
info:
  title: AI JSON Studio Engine
  version: 1.0.0
  description: Connects Gemini agents directly to an advanced JSON parsing and repair tool.
paths:
  /api/v1/process-json:
    post:
      summary: Parse, chunk, and execute targeted edits on massive JSON files.
      operationId: processJsonConfig
      parameters:
        - name: Authorization
          in: header
          required: true
          schema:
            type: string
          description: Bearer token supplied automatically by the user's Vertex AI Google Service account.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                raw_json:
                  type: string
                  description: The massive target JSON payload.
                instruction:
                  type: string
                  description: The structural edit or migration rule to execute.
      responses:
        '200':
          description: Successfully parsed and compiled JSON configuration.
          content:
            application/json:
              schema:
                type: object
                properties:
                  fixed_json:
                    type: string
                  validation_passed:
                    type: boolean
Use code with caution.Integration 4.2: Firebase Extension ConfigurationThe agent must generate an extension.yaml file inside /integrations/google-firebase/. This configuration defines how customers host your tool using their own serverless computing budgets.Agent Code Generation Prompt for Firebase Manifest:yamlname: ai-json-studio-validator
version: 1.0.0
specVersion: v1beta

displayName: AI JSON Schema Control Plane
description: Automatically scans, parses, and formats incoming configuration collections inside Firestore using local project Gemini credits.

license: Apache-2.0

resources:
  - name: monitorJsonConfigUpdate
    type: firebaseextensions.v1beta.function
    properties:
      eventTrigger:
        eventType: providers/cloud.firestore/eventTypes/document.write
        resource: projects/${PROJECT_ID}/databases/(default)/documents/configs/{configId}
      sourceDirectory: functions
      runtime: python311

params:
  - param: GEMINI_API_KEY
    label: Vertex / Gemini API Resource Access
    description: Google project endpoint or billing key to fuel the AI computations.
    type: secret
    required: true
Use code with caution.5. Security & Token Authentication FlowTo clear Google M&A compliance checks, your SaaS platform and your integrations must use zero-trust permission models:Identity Verification: The API routes in auth.py must support JWT validation for your core web clients.Google Passthrough: When executing actions via the Vertex AI Extension, your backend must validate incoming Google OAuth signatures. It extracts the temporary token from the request header, mapping the underlying AI query cost directly to Google's internal APIs rather than drawing from your platform account pool.6. MVP Success Criteria for the AI AgentTo verify your agent successfully implements this PRD, it must run code verification scripts satisfying these test parameters:Test 1: Successfully processes a 10,000+ line malformed JSON file, fixes syntax errors, executes a dynamic string update, and returns a cleanly minified payload.Test 2: Confirms the openapi.yaml format parses through standard Swagger validators with zero parsing or route mapping errors.Would you like to run a quick initialization command to have your agent generate the base backend framework code immediately, or should we refine the specific chunking prompt logic inside the script?
