# Remit Agent

A local mathematical modeling workbench with coordinator, modeler, coder and writer roles. [中文说明](README.md).

## Run with Docker

Install Git and Docker with Linux containers and Compose:

```sh
git clone https://github.com/zhou2030109-glitch/Remit-Agent.git
cd Remit-Agent
docker compose -f docker-compose.release.yml up -d --build
```

Open <http://localhost:18000> and configure your own API endpoint, key, model and protocol in model settings. The first build downloads scientific libraries, Chinese fonts and LaTeX. Model usage is billed by your provider. Docker uses Python; local MATLAB requires your own installation and license.

Configuration and tasks persist in named volumes. `down` preserves them; `down -v` deletes them.

For Windows source setup, install Python 3.12, uv, Node.js 24 and pnpm 10. Run `uv sync --locked` inside `backend`, copy `.env.example` to `.env.dev`, then run `pnpm install --frozen-lockfile` inside `frontend` and copy its `.env.example` to `.env.development`. Run `win_start.bat` from the root and open <http://localhost:15173>. Use `win_stop.bat` to stop the application. Source installations need XeLaTeX for PDF export.

## Scope

Upload a problem and attachments, review the plan, run experiments, inspect evidence and approve results, then edit and compile the paper. A synthetic example is provided at `backend/app/example/urban_cooling/`.

This is an actively developed source release. Generated code can fail and model services can time out. Automated tests do not certify scientific correctness or contest compliance. The application is for trusted local use; it does not provide public multi-user authentication. Local generated code runs with local process permissions.

No private tasks, credentials, uploaded contest datasets, personal paper excerpts, logs, environments or build outputs are included. The optional personal paper library is empty; general writing guidance and licensed open-source contest skills remain available.

See [release validation](docs/release-validation.md), [configuration](docs/configuration.md), [distribution](docs/distribution.md), and [contest adapters](docs/competition-adapters.md).

## License and provenance

Remit-owned code is under [MIT](LICENSE). Read [NOTICE](NOTICE.md), [third-party notices](THIRD_PARTY_NOTICES.md) and the [source provenance audit](docs/originality-audit.md) for scope, history and separate third-party licenses.
