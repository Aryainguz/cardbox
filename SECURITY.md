# Security

## Reporting a vulnerability

Please report security issues privately through GitHub's **Report a vulnerability** button (Security tab), not in a
public issue. You'll get a reply within a few days.

## What to know

- **The app and the voice studio** listen on `127.0.0.1` only. They refuse requests whose `Host` isn't a loopback
  name (DNS rebinding) and refuse changes coming from another website's origin (cross-site requests).
- **Your voice** recordings and cloned voice stay on your machine, in `~/Cardbox/voices`. Nothing is uploaded.
- **The render API** (`server/`) is meant to run behind your own network controls. Set `CARDBOX_API_KEYS` before
  exposing it, and a strong `CARDBOX_WEBHOOK_SECRET` if you use webhooks. Specs are rendered by a local
  subprocess; don't expose the API to untrusted users without sandboxing the worker.
- **Voice cloning** must only be used with your own voice or one you have explicit permission to use.
