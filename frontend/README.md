# Remit frontend

Vue 3 + TypeScript + Vite.

```sh
pnpm install --frozen-lockfile
cp .env.example .env.development
pnpm dev --host 127.0.0.1 --port 15173
```

On Windows use `Copy-Item .env.example .env.development`. Development uses the backend at port 18000. Production builds use the same origin as the backend page.

Run `pnpm test` for behavior tests and `pnpm build` for type checking and production output.
