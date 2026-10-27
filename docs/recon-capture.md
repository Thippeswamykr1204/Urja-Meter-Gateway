# Browser capture instructions

Use a local browser session to record the portal network shape without saving credentials or session values.

## Before capture

1. Start from a clean browser profile or an isolated private window.
2. Open Chrome or Firefox DevTools with `F12`, `Ctrl+Shift+I`, or `Cmd+Option+I`.
3. Select the **Network** tab.
4. Enable **Preserve log** and disable cache while DevTools is open.
5. Clear the network log before each request sequence.

## Record these sequences

Capture only the requests needed to identify the portal contract:

1. Login and the first authenticated page.
2. Meter list with one search or filter change.
3. One meter detail page.
4. One consumption range or granularity change.
5. Hierarchy or distribution view.
6. Any pagination, export, bulk, or download action that is visible.

For each sequence, note the method, path, status, redirect target, query parameter names, form field names, response content type, relevant response headers, cookie names and attributes, CSRF field names, pagination names, and timing information. Do not copy values from password, authorization, cookie, token, email, or personal-data fields.

## Export and sanitize

1. Right-click the relevant request group and choose **Save all as HAR with content**.
2. Store the raw HAR outside the repository.
3. Run the sanitizer from the repository root:

```text
python tools/sanitize_har/main.py /private/path/capture.har \
  --output fixtures/portal/sanitized.har \
  --fixtures-dir fixtures/portal/responses \
  --summary docs/recon-notes.md
```

The command replaces credential-shaped values, email addresses, cookie values, and session markers with stable placeholders. It also checks the generated HAR before writing it. Do not commit the raw HAR. The repository ignores `*.har` by default.

## What to provide for application changes

Provide only the generated `docs/recon-notes.md`, the sanitized HAR if needed for parser tests, and sanitized response fixtures. Portal behavior remains `UNVERIFIED` when a request or response shape was not captured.
