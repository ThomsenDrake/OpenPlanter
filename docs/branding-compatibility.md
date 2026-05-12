# Cestus Branding Compatibility Notes

Cestus is the current product name. Some legacy `OpenPlanter` identifiers remain intentionally because they are part of persisted local state, wire formats, or existing installation paths.

## Intentionally Retained

- `.openplanter/` workspace state and `~/.openplanter/` user credentials remain the canonical storage locations for existing workspaces.
- `OPENPLANTER_*` environment variables remain supported configuration keys, including `OPENPLANTER_WORKSPACE`.
- `openplanter.session.v2`, `openplanter.trace.*`, `openplanter.session_handoff.v1`, `openplanter.obsidian_pack.v1`, and `openplanter.core` remain protocol/schema identifiers.
- `openplanter://...` frontend deep links and `openplanter.revelation|...` IDs remain internal link contracts.
- `com.openplanter.desktop` remains the Tauri application identifier so installed desktop apps update in place and keep existing app data.
- `openplanter-agent` remains a Python console-script alias for compatibility; `cestus-agent` is the primary command.
- `openplanter-desktop/` remains the source directory name until a separate repository/path migration is planned.
- Current external repository URLs still point at `OpenPlanter` remotes until the GitHub repositories are renamed.
- `OpenPlanterWorkspace` / `openplanter_workspace` remain migration-source names for detecting legacy workspace roots.
- Browser Harness result markers and default harness names using `OPENPLANTER` / `openplanter` remain protocol glue between Cestus and the external harness.

## Follow-Up Migration Candidates

- Add `CESTUS_*` environment variable aliases alongside `OPENPLANTER_*`.
- Plan a storage migration from `.openplanter/` to `.cestus/`, if the product should eventually stop writing legacy directories.
- Rename the `openplanter-desktop/` directory and update historical docs once repository remotes and build paths are migrated together.
