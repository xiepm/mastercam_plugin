# Adapter review — bounded independent review

Date: 2026-10-29. Scope: `ai/mcp/runtime.py`, `models.py`, `server.py`, `ai/bridge/PluginBridge.cs`, `ai/tools/local_setup.py`, `install_skill.py`. No source edits, native calls, real configuration reads or installer execution. Only this report was written. Exploration stopped at the owner's request.

The existing `ai/validation/native-acceptance.json` records 35 native calls covering six actions, regeneration, rollback, same-request replay, wrong-hash rejection and second-apply rejection, with the original 13 operations / 57 geometries / 11 tools and selection/timestamps preserved. The findings below concern additional paths; they do not contradict that acceptance.

## Actionable findings

### P1 — Preview mismatch mutates the still-applicable plan

Location: `ai/bridge/PluginBridge.cs:146–150`; `Bind` assignments at lines 85–108.

Apply saves the old preview string, then calls `Bind(p,...)`, which replaces `p.Preview` and its execution delegates **before** comparison. If the rebuilt preview differs, the exception leaves the plan `Prepared`, with the new preview/delegates and the original approved hash. A second apply with a **new request ID**, the same plan/hash, unchanged baseline and a stable rebuilt preview can pass the comparison and apply the replacement preview.

This requires a rebuilt-preview mismatch that passes the preceding baseline check. It is a different branch from replaying a completed request or applying an already-applied plan. The control-flow defect was reproduced in a minimal in-memory state-machine model: first attempt rejects A→B but retains Prepared/B/original-hash; second attempt applies B using original-hash. No actual SDK drift was induced or claimed.

Fix: build into a temporary candidate; compare against an immutable approved preview before replacing delegates. Invalidate the original plan on any rebuild mismatch/failure. Add a regression test that forces preview drift, then verifies that a new request ID with the old hash cannot apply.

### P2 — Write contracts coerce booleans into machining numbers and numbers into consent flags

Location: `ai/mcp/models.py:5–16`.

`Contract` forbids extra fields and nonfinite values but does not enable strict validation for floats/bools. The actual model accepted:

```json
{"Depth": true, "Incremental": 0, "DetachAssociativeDepth": 1}
```

and returned:

```json
{"Depth": 1.0, "Incremental": false, "DetachAssociativeDepth": true}
```

Thus an invalidly typed request becomes a numeric depth and explicit permission to detach association before reaching the native contract. Review/apply is still required; this is not a bypass of that separate authorization step.

Fix: strict numeric/boolean validation at the public boundary, including explicit confirmation flags; retain rejection tests for booleans in numeric fields and numeric/string substitutes for booleans. Reproduction used the real model with locally available Pydantic 2.13.4; the pinned 2.13.5 environment was not executed in this review.

### P2 — A failure before native submission permanently leaves an unresolved request lock

Location: `ai/mcp/runtime.py:100–123`, especially 114 and 123.

The request JSON is written before the generated script. If `run.csx` cannot be written, native submission has never happened, but the outer exception handler retains `active.json` merely because `request.json` exists. Status then reports `unknown_or_running`; all subsequent native calls are blocked, and no native result can arrive.

Reproduced using the actual Runtime code with an entirely in-memory filesystem and an injected script-write refusal: backend invocation count **0**, active lock retained, next call rejected as unresolved.

Fix: distinguish definitely-not-submitted failures from potentially-submitted failures. Persist a terminal local failure and release the active marker for the former; preserve the current fail-closed behavior once submission may have occurred. Add this case beside the existing timeout/replay tests.

### P2 — Relative workspace produces a relative registered configuration path

Location: `ai/tools/local_setup.py:13–19,25`.

The runtime's workspace is resolved, but `out` is built from the original argument. With `--workspace review-work --register`, the saved `MC_PLUGIN_AI_CONFIG` is `review-work\\plugin-ai-config.json`. A later Codex launch from another working directory resolves a different file or fails to find the configuration.

Reproduced by executing the actual setup source against an in-memory filesystem/configuration; no real configuration was touched.

Fix: resolve the output configuration path before writing it or registering it, or reject relative workspace arguments. Test installation and launch from different working directories.

### P2 — Choosing a workspace in the checkout can expose private configuration in distribution

Location: `ai/tools/local_setup.py:13–16,22–23`; repository `.gitignore`.

The selected upstream's full `env`/arguments are copied into `plugin-ai-config.json`, and registration also copies the entire Codex config into `codex-before-plugin-ai.toml`. Nothing rejects a workspace inside the distributable checkout. Neither generated filename is ignored by the inspected repository rules.

Actual setup source, executed with a fake configuration containing only a synthetic sentinel, copied that sentinel into both files when the workspace was the checkout root. Read-only `git check-ignore` confirmed neither filename was excluded. **No actual credential disclosure was observed or claimed.** The risk requires sensitive upstream/config values plus subsequent inclusion of generated files in a commit/archive.

Fix: keep private runtime configuration and full backups outside the publishable checkout, even if the script workspace is inside it; add generated-file exclusions as defense in depth. Do not publish copied configuration/backup files.

## Review boundaries and current changes

- Confirmed current inspection exposes TipAngle/PilotDia and ChamferMill requires an actual angle strictly between 0 and 180 degrees; no missing-angle finding is raised.
- Confirmed the added concurrent-config reread guard in local_setup and pagination in mc_catalog. Neither resolves the relative-path or private-output issues above.
- No additional actionable finding established in install_skill.py during this bounded review.
- Native replay/rollback/regeneration tests were read, not rerun. Normal same-ID replay and unknown-after-submission handling were not found to permit duplicate submission.
- The preview issue is a source/control-flow finding with a state-machine reproduction, not a demonstrated native wrong-write. Python setup/runtime reproductions intercepted all filesystem writes in memory.
- No full security audit, arbitrary SDK mutation coverage, public credential scan or post-fix verification is claimed.

## Inspected source identities

| Repository-relative file | SHA256 |
|---|---|
| ai/mcp/runtime.py | 695E721D07A3C77C7FA8BE818ECEA690557DE5230C5EB0DC5CEA57152CB01253 |
| ai/mcp/models.py | FB7679A6F52A3958A068596D808B39ED1F0CB6CA57147CB476140CB1C570576C |
| ai/mcp/server.py | ACF03C374ED4FF1312BA0F16F7418FAC2DC2E7AC9AA6C1520121DECEC1CB3535 |
| ai/bridge/PluginBridge.cs | 4BD1A55D97AA06384EEB99EDC5553FE4C5E481EA3E07343782319CD66E013172 |
| ai/tools/local_setup.py | 9784DD66C4428203AFE310CD0FBB4EA2704D66BD54C9221BF0231DA62140A0FA |
| ai/tools/install_skill.py | 214E934A0FA44E9387583E9674267C59C4AE0D03C5B58F0C42BC915CEF7F0BF4 |

The paginated server hash is newer than the server hash recorded in the existing native acceptance file. Findings apply to the inspected versions above, not unreviewed later fixes.
