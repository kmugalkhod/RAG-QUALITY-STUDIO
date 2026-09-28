# Local answer deployment check

This is a loopback-only manual test page for the server-to-server endpoint. The page never receives the deployment key. Node holds it in memory and forwards one question at a time to the local API. Submitting a question can call a paid provider.

1. Revoke any server key that was pasted into a chat or other shared location, then create a fresh key in **Answer Deployments**.
2. From the repository root, run:

   ```sh
   node tools/deployment-check/server.mjs 867e39d4-3121-4933-99c6-5da6f99381fe
   ```

   Paste the key at the hidden terminal prompt, then press Enter. The key is not echoed or written to a file. Use a different deployment ID if needed.
3. Open <http://127.0.0.1:8787>, enter a question supported by the pinned index, and click **Ask deployment**. The page displays progress, the answer, and citations. Stop the helper with Ctrl+C.

The helper listens only on `127.0.0.1`, checks the page's origin and a per-process request token, and forwards only to the real local API on `127.0.0.1:8000`. It adds no public endpoint, website widget, or browser API key storage. Only one POST is made per submit; a retry of an unchanged question reuses the same idempotency key. Refresh the page after starting the helper to clear any earlier test result.
