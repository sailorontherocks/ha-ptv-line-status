# Repository Guidelines

## Project Purpose

This repository contains a Home Assistant custom integration for Victorian public transport data.

The integration must follow current Home Assistant architecture, coding standards, and developer documentation.

Do not invent generic Python application structure when Home Assistant has an established convention.

## Project Structure

Use the Home Assistant custom integration structure:

custom_components/
  ptv_line_status/
    __init__.py
    manifest.json
    const.py
    config_flow.py
    coordinator.py
    sensor.py
    strings.json
    translations/

tests/
  components/
    ptv_line_status/

Do not create a generic `src/` directory.

Additional modules may be introduced when they provide a clear separation of responsibilities, for example an API client module or data models.

## Home Assistant Architecture

- Prefer config entries and UI configuration rather than YAML configuration.
- Use async Home Assistant APIs.
- Do not perform blocking network I/O in the Home Assistant event loop.
- Use a DataUpdateCoordinator when API data can be fetched once and shared by multiple entities.
- Keep API communication separate from Home Assistant entity logic.
- Prefer typed Python.
- Follow current Home Assistant developer documentation rather than relying on outdated examples.
- Preserve compatibility with supported Home Assistant versions.
- Do not access Home Assistant internals when a public API exists.

## Development Approach

Before implementing substantial functionality:

1. Understand the external API and its authentication model.
2. Define the Home Assistant user experience and entity model.
3. Agree on the architecture.
4. Implement the smallest useful vertical slice.
5. Add tests.
6. Run tests and linting before considering work complete.

Do not generate a large integration speculatively.

## Testing

Use pytest.

Mock external API calls. Tests must not depend on live external services.

Cover:
- successful API responses
- authentication failures
- HTTP/network failures
- malformed or incomplete responses
- empty results
- coordinator update failures
- config flow behavior
- entity state updates

Store sanitized API samples in tests/fixtures/ when useful.

## Security

Never commit:
- API keys
- credentials
- tokens
- secrets
- private Home Assistant configuration
- personal location or travel data

Use ignored local configuration or environment variables for development secrets.

## Git

Use small focused commits.

Prefer commit messages such as:

- feat: add PTV API client
- feat: add departures coordinator
- feat: add departure sensors
- fix: handle API timeout
- test: cover empty departures response

Do not commit generated caches, virtual environments, secrets, or local development configuration.

## Codex Behaviour

Before making major architectural changes, explain the proposed approach.

When uncertain about Home Assistant APIs or conventions, consult current Home Assistant developer documentation rather than guessing.

Do not remove working functionality merely to simplify implementation.

Do not make unrelated refactors while implementing a feature.

## Security and release rules

### Security

- Never read Home Assistant `.storage` files or any credential file unless the user explicitly authorises one exact file for one stated diagnostic purpose.
- `api-key.txt` is local and ignored. Never display, log, copy, stage, commit, or include its contents in command arguments, URLs, test fixtures, or output files.
- Never expose `KeyID` request headers or raw exceptions that may contain credentials.
- Use credentials only for the explicitly approved read-only PTV diagnostic request.
- Gitignore is not a security boundary: ignored credential files still require explicit task authorisation before reading.
- Never stage credentials, `api-key.txt`, Home Assistant storage, or diagnostic output containing secrets; never commit them or expose secrets in output, command arguments, URLs, or exceptions.

### Git and releases

- Never commit, push, tag, create a GitHub release, delete or move a tag, or force-push without the user's explicit approval for that action.
- An explicit request such as “release this patch locally and on GitHub” authorises the complete normal workflow: version bump, validation, commit, annotated tag, push, and stable GitHub release. Do not ask separately for approval of steps already authorised. Implementation-only requests do not authorise publication.
- Stop for conflicting tags, divergent branches, failed required checks, suspected staged secrets, or ambiguous release scope. Never force-push or move/delete published tags.
- Before a release, verify the working tree, manifest version, tag target, remote state, and that no credentials are staged.
- Use patch releases for backward-compatible fixes.
- Release tags must be annotated and match the manifest version, for example manifest `0.2.4` ↔ tag `v0.2.4`.
- Never overwrite an existing tag automatically; stop and ask.
- GitHub releases must be stable, non-draft, and non-prerelease.

For release preparation, publication, or resuming an interrupted release, follow
[the repository release skill](.agents/skills/release-ptv-line-status/SKILL.md).

### HACS

- Maintain a root `hacs.json`.
- Verify every release archive contains `hacs.json` and `custom_components/ptv_line_status/manifest.json`.
- Do not move an existing release tag to repair packaging; issue a new patch release.
