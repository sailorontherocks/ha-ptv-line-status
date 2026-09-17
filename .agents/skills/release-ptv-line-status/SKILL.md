---
name: release-ptv-line-status
description: Prepare, validate, publish, or resume a release of this repository's PTV Line Status Home Assistant integration. Use for release tasks; implementation-only requests do not authorise publication.
---

# Release PTV Line Status

Read the root [AGENTS.md](../../../AGENTS.md) and any applicable instructions
first. Its security, authorisation, release, and HACS rules govern this procedure.
Keep work within the user's requested release scope. A local-only request ends
at its authorised stage; invoking this skill does not itself grant publication
authority. Use configured GitHub authentication; never request pasted credentials.

## Inspect and select

1. Inspect `git status --short --branch`, staged and unstaged diffs, current branch,
   configured remote, local tags (including peeled commit targets), remote branch
   and tag refs, and GitHub releases. The expected repository is
   `sailorontherocks/ha-ptv-line-status`; verify the remote before using it.
2. Identify the exact intended files/hunks and outgoing commits. Compare the
   remote branch with local history, inspecting both commit messages and diffs.
   Ensure a branch push would publish only authorised work, including earlier
   local commits. Report unrelated outgoing work or divergence before proceeding.
   Preserve unrelated staged/unstaged edits; a clean worktree is not required.
3. Determine whether this is a new release or an interrupted one. For a new
   release, read `custom_components/ptv_line_status/manifest.json` and version
   history, then select the next appropriate unused version. Use a patch for
   compatible fixes; flag breaking changes for a version decision. Do not infer
   versions from config-flow `VERSION` or stale tags alone. Check local and remote
   tag availability, and do not silently substitute a version when the intended
   tag conflicts.

## Prepare and validate

4. Update manifest `version`, the versioned User-Agent in
   `custom_components/ptv_line_status/api.py`, and any matching test assertion.
   Update existing release metadata if applicable. Leave config-flow `VERSION`
   unchanged unless a separately scoped configuration migration requires it.
5. Run the established required checks from the repository root:

   ```sh
   .venv/bin/python -m pytest
   .venv/bin/ruff check custom_components tests
   .venv/bin/ruff format --check custom_components tests
   .venv/bin/python -m compileall -q custom_components tests scripts
   .venv/bin/python -m json.tool hacs.json
   .venv/bin/python -m json.tool custom_components/ptv_line_status/manifest.json
   git diff --check
   ```

   Parse `strings.json` and `translations/en.json`, checking that their structures
   and English contents agree and cover any new flow fields/errors. Run focused
   tests as needed. Also audit repository-wide Ruff lint/format. The historical
   `scripts/diagnose_gtfs_mapping.py` lint/format failures must be reported
   separately after confirming that file is unchanged; do not fix unrelated
   issues as part of a release or silently waive new failures. Failed required
   checks stop publication. Check current project tooling rather than assuming
   these historical exceptions still apply.
   If unrelated edits affect validation, run checks in an isolated checkout of
   the intended release tree; passing checks on a different dirty tree is insufficient.
6. Validate root `hacs.json` and inspect packaging settings: if `zip_release`,
   `filename`, or custom paths are configured, verify their referenced assets and
   layout exist. Confirm both required paths from AGENTS.md are in the intended
   release tree, not merely present as untracked/ignored worktree files.
7. Show the proposed diff. Stage only named release files or selected hunks;
   never use blanket `git add`. Review `git diff --cached` and
   `git diff --cached --check`, including all staged paths, for secrets and scope.
   If unrelated work is already staged, preserve it and isolate the release
   staging rather than including it. Do not read credential files to compare
   secret values. Commit only the reviewed release changes with a descriptive
   message.

## Publish and verify

8. Record the full release commit SHA. Read the manifest and HACS metadata from
   that commit and inspect `git archive` contents. Recheck remote state and tag
   availability immediately before publication. Create annotated `vX.Y.Z` at that
   exact commit with message `PTV Line Status X.Y.Z`; verify its peeled target
   and manifest version. Follow AGENTS.md for any conflict.
9. Push explicit branch and tag refspecs, disabling implicit tag following:
   `git -c push.followTags=false push origin refs/heads/main:refs/heads/main`, then
   `git -c push.followTags=false push origin refs/tags/vX.Y.Z:refs/tags/vX.Y.Z`.
   Substitute only the verified authorised branch/version. Never use `push --tags`.
10. Verify the remote tag exists and resolves to the recorded commit before
    creating the release. Use `gh release create vX.Y.Z --verify-tag` with the
    verified repository, title `PTV Line Status X.Y.Z`, and concise notes based
    on actual changes and material limitations. Apply the stable publication
    rules in AGENTS.md. Mark the newest stable release Latest; avoid making a
    historical release Latest. Do not change repository visibility.
11. Verify the remote branch SHA, peeled tag target, release URL, title and
    draft/prerelease flags. Inspect the actual published source archive (and any
    HACS-selected asset) for the required files and matching manifest version.
    Inspect remaining working-tree and staged changes.

## Resume an interrupted release

Inspect completed steps before mutating anything. Reuse the intended version and
commit when only publication is missing; interruption alone is not a version
bump. If its tag already exists, verify annotation, peeled target, and manifest
before reusing it. If the matching remote tag exists, skip its push. If the
matching published release exists, verify it and skip creation. Report any tag
or release mismatch precisely and stop without overwriting it. Resume only the
missing authorised steps; preserve unrelated work throughout.

## Handoff

Report version, full commit SHA, annotated tag, release URL (or unpublished stage),
validation results and known pre-existing failures, and remaining local edits.
For a published release, instruct the user to refresh HACS, update **PTV Line
Status**, and restart Home Assistant. Mention any release-specific migration or
configuration steps; do not imply existing entries need recreation without cause.
