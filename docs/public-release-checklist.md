# Public release checklist

Use this checklist before changing repository visibility or publishing a
release.

## Repository

- [ ] The default branch is `main` and CI passes on the intended release SHA.
- [ ] Branch protection requires the backend and frontend CI jobs.
- [ ] Private vulnerability reporting is enabled in repository security settings.
- [ ] Repository description, homepage, topics, and social preview are set.
- [ ] Issue labels used by the templates (`bug`, `enhancement`) exist.
- [ ] No branch, tag, release asset, issue attachment, or PR contains credentials
      or private datasets.
- [ ] The known historical PR snapshot described in the provenance audit has
      been accepted as part of the public record or handled with GitHub Support.

## Source and distribution

- [ ] `LICENSE`, `NOTICE.md`, and `THIRD_PARTY_NOTICES.md` ship with source and
      installer artifacts.
- [ ] Bundled third-party license files remain under `tools/redis/LICENCES/`.
- [ ] Examples are synthetic or have explicit redistribution permission.
- [ ] `backend/.env.example` contains placeholders only.
- [ ] Release notes disclose breaking changes, supported platforms, and known
      security boundaries.
- [ ] The Windows installer was produced from the tagged commit and smoke-tested
      on a clean machine.

## Suggested first release

Tag the first tested public snapshot as `v0.1.0`. Keep the pre-1.0 stability
warning in the README and avoid presenting the local workstation design as a
public hosted service.
