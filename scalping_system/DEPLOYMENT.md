# BTC Delta Desk — Web / PWA Deployment

## Product modes
- Web: responsive browser workstation.
- PWA: installable Android/desktop application shell using the browser's Install App action.
- Engine: Python paper-trading backend and Delta collector.

## Security defaults
The dashboard binds to 127.0.0.1 by default. For internet deployment, place it behind HTTPS and a reverse proxy/authentication layer. Set BTC_DASHBOARD_TOKEN to protect /api/state and /health.

Live exchange execution is disabled in the current build. Do not expose an execution adapter through the web server.

## Local
.venv/bin/python dashboard_server.py
Open http://127.0.0.1:8790

## PWA
Open the web URL in Chrome/Android browser and choose Install app / Add to home screen. The manifest and service worker are included.

## Container
Build with: docker build -t btc-delta-desk .
Run with: docker run --rm -p 8790:8790 -e BTC_DASHBOARD_TOKEN=<long-random-token> btc-delta-desk

For production, terminate TLS at a trusted reverse proxy and restrict the API to authenticated users/VPN. Do not put exchange API keys in browser code.

## Production checklist
1. HTTPS.
2. Strong API token or SSO at the proxy.
3. Private network/VPN for trading APIs.
4. Persistent encrypted storage for trade state.
5. Process supervisor/container restart policy.
6. Monitoring for collector freshness and disk growth.
7. Backups of paper trade state.
8. Walk-forward validation before any live execution work.
