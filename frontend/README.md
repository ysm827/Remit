# Remit frontend

Vue 3 + TypeScript + Vite interface for the Remit mathematical modeling workbench.

```bash
pnpm install
pnpm run dev
pnpm run lint
pnpm test
pnpm run build
```

The development server uses the API and WebSocket endpoints configured in the frontend environment files.

The Vitest suite uses jsdom and mocked API/WebSocket boundaries. It exercises project navigation, stale asynchronous responses, reconnect recovery, CSV selection, and sanitized Markdown/KaTeX rendering without starting the backend or calling model providers.
