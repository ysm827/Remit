<p align="center"><img src="./assets/remit-icon.png" alt="Remit logo" width="140" /></p>

# Remit 2.0

A local mathematical modeling workbench with coordinator, modeler, coder and writer roles. [中文说明](README.md).

**[Windows candidate — 2026-10-03](https://github.com/zhou2030109-glitch/Remit/releases/tag/candidate-20261003-7407a60)** includes the current optimization and CI fixes. CI and bundled runtime checks pass; installer lifecycle and independent user-machine validation are pending. Its embedded version remains 2.0.1, so use the candidate filename and checksum to identify it.

## Product preview

[![Remit modeling workbench](./assets/remit-2-workbench.png)](./assets/remit-2-workbench.png)

<p align="center"><sub>Remit 2.0 · Read, model, compute and write with your modeling team. Click to view full size.</sub></p>

## Agent architecture

```mermaid
flowchart TB
    U[Problem · Data · User requirements] --> C[Tuantuan · Coordinator]
    C --> M[Lingling · Modeler]
    M --> P[Diandian · Coder]
    P --> V[Validation and checkpoints]
    V --> W[Momo · Writer]
    V -->|Repair needed| P
    W --> O[Paper workspace · LaTeX · PDF]
    H[User review and acceptance] -.-> C
    H -.-> M
    O --> H
    classDef agent fill:#f7fee7,stroke:#a3b629,color:#20251b;
    classDef artifact fill:#f6f7f8,stroke:#9aa2a9,color:#20251b;
    class C,M,P,W agent;
    class U,V,O,H artifact;
```

## Version 2.0

This release brings the current team conversation, resumable execution, paper workspace,
evidence-based figure selection and typography defaults into the original Remit repository.
The logo, community QR code, Star History branch and previous commit history are retained.
See [release notes](docs/releases/2.0.1.md) and [upgrade/rollback instructions](docs/upgrading-to-v2.md).
The exact pre-upgrade source is preserved on [legacy/pre-2.0](https://github.com/zhou2030109-glitch/Remit/tree/legacy/pre-2.0).

Native unsigned Windows/macOS installers are uploaded to the [2.0 release](https://github.com/zhou2030109-glitch/Remit/releases/tag/v2.0.1)
only after the package checks pass. Source availability does not imply an installer has finished building.

## Run with Docker

Install Git and Docker with Linux containers and Compose:

```sh
git clone https://github.com/zhou2030109-glitch/Remit.git
cd Remit
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

## Star History ⭐

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/zhou2030109-glitch/Remit/refs/heads/star-history/assets/star-history/star-history-dark.svg?v=2" />
    <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/zhou2030109-glitch/Remit/refs/heads/star-history/assets/star-history/star-history-light.svg?v=2" />
    <img alt="Remit Star History" src="https://raw.githubusercontent.com/zhou2030109-glitch/Remit/refs/heads/star-history/assets/star-history/star-history-light.svg?v=2" width="800" />
  </picture>
</p>

## WeChat community

Scan the QR code to join the **Remit (数模 Agent)** WeChat group for usage
questions, mathematical modeling workflows, feedback, and development discussion.

<p align="center">
  <a href="./assets/remit-wechat-group-20260929.png">
    <img src="./assets/remit-wechat-group-20260929.png" alt="Remit WeChat group QR code, valid before October 6, 2026" width="360" />
  </a>
</p>

> Updated September 29, 2026. The image states that the QR code is valid before
> October 6. Click the image for full resolution; if it expires, open an issue
> to request an update.
