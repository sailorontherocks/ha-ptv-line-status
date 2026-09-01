# Repository Guidelines

## Project Purpose

This repository contains a Home Assistant custom integration for Victorian public transport data.

The integration must follow current Home Assistant architecture, coding standards, and developer documentation.

Do not invent generic Python application structure when Home Assistant has an established convention.

## Project Structure

Use the Home Assistant custom integration structure:

custom_components/
  ptv/
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
    ptv/

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
