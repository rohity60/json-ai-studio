# Frontend Requirements — JSON AI Studio MVP

Derived from PRD v1.0. Only what the **client / UI layer** must implement.
Technical decisions are documented in `docs/adr/`.

---

## 1. Layout & Navigation

| # | Requirement | Priority |
|---|-------------|----------|
| L-01 | Root layout with site title "JSON AI Studio" and tagline | MVP |
| L-02 | Responsive two-panel layout: left (chat/upload) + right (diff/preview) | MVP |
| L-03 | Persistent session/version badge in header or sidebar | MVP |

## 2. JSON Upload & Parsing UI

| # | Requirement | Priority |
|---|-------------|----------|
| U-01 | Drag-and-drop zone for `.json` file upload | MVP |
| U-02 | Textarea input as alternative paste method for raw JSON | MVP |
| U-03 | Client-side syntax validation feedback on paste/upload (show error line/column) | MVP |
| U-04 | Render the uploaded JSON as an expandable **tree view** | MVP |
| U-05 | "Load existing session" and "Import previous version" placeholders for future wiring | MVP |

## 3. Conversational Editing Workspace (SSE)

> **Streaming context**: The backend returns SSE events — `thinking` → `diff` (multiple) → `complete`. The frontend must handle all three phases in sequence.

| # | Requirement | Priority |
|---|-------------|----------|
| C-01 | Persistent chat panel displaying full conversation history (user messages + AI streaming responses) | MVP |
| C-02 | Input text area with "Send" button; Enter to submit, Shift+Enter for newline | MVP |
| C-03 | On send, POST to `/api/chat` and receive SSE stream via `fetch` + `ReadableStream` | MVP |
| C-04 | **Streaming phase handling**: render thinking text inline → accumulate diff entries → on `complete`, update JSON preview panel | MVP |
| C-05 | Placeholder examples (inline hint): "Increase timeout from 30 to 60", "Add retry count of 5", etc. | MVP |
| C-06 | Auto-scroll chat to bottom on new messages and during streaming | MVP |

## 4. Visual Diff Viewer

| # | Requirement | Priority |
|---|-------------|----------|
| D-01 | Display diff between "before" and "after" versions of the JSON | MVP |
| D-02 | Color-coded diff: <span style="color:green">+ added</span>, <span style="color:orange;color:#e68a00">~ modified</span>, <span style="color:red">- deleted</span> | MVP |
| D-03 | Side-by-side comparison view for the JSON tree | MVP |
| D-04 | Tree-level expand/collapse toggles within the diff | MVP |
| D-05 | Search/filter changes by keyword or change type (added/modified/deleted) | MVP |

## 5. Incremental Approval Workflow UI

| # | Requirement | Priority |
|---|-------------|----------|
| A-01 | Per-change toggle: **Accept** / **Reject** for each proposed modification | MVP |
| A-02 | Global actions: "Accept All" / "Reject All" | MVP |
| A-03 | After acceptance, update the working JSON tree and refresh the view | MVP |

## 6. Version Management UI

| # | Requirement | Priority |
|---|-------------|----------|
| V-01 | Sidebar or dropdown listing all versions (original, working, approved) | MVP |
| V-02 | Click a version to restore / preview it in the diff viewer | MVP |
| V-03 | Visual indicator for the currently active / "working" version | MVP |

## 7. Export

| # | Requirement | Priority |
|---|-------------|----------|
| E-01 | Download button for current (approved) JSON as pretty-printed file | MVP |
| E-02 | Download option for minified JSON (toggle or secondary button) | MVP |

## 8. State Management

| # | Requirement | Priority |
|---|-------------|----------|
| S-01 | Global client state holds: current JSON, conversation history, diff result, active version | MVP |
| S-02 | Session recovery: persist conversation + working JSON in `localStorage` to survive refresh | MVP |

## 9. UX / Quality

| # | Requirement | Priority |
|---|-------------|----------|
| X-01 | Loading spinners while awaiting backend responses (chat, diff, validation) | MVP |
| X-02 | Empty states and tooltips explaining each section to first-time users | MVP |
| X-03 | Toast notifications for success / error events from the API | MVP |

## 10. Excluded from MVP (Frontend)

- Git integration UI
- Multi-file editing panels
- Team collaboration / commenting overlays
- Enterprise governance controls
