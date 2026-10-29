---
name: mastercam-plugin-suite
description: Explain, select and operate the installed Mastercam 2027 plugin suite, including Porsche/V++, LittleBee, operation tools, HSM, MP and X+, through its verified capability catalog and typed MCP workflows.
---

Use this skill when the user asks what these plugins do, how to use them, or asks AI to perform a supported plugin operation in Mastercam 2027. The capability catalog reflects release 2027.10.28.2; it distinguishes original plugins, independent rebuilds, typed automation, interactive routes and unsupported behavior.

Find the intended workflow with `mc_catalog`, then read its exact contract with `mc_capability`. Search Chinese names as well as module names. For a UI command not found by name, inspect `module.<moduleName>` and its `routes`. Do not infer behavior from an FT function name alone. See [concepts](references/concepts.md) for common terminology.

For Porsche/V++ automatic contours, hole healing or complex-hole operations, read [Porsche direct workflows](references/porsche.md). Four typed actions distinguish projection-only curves, three-stage contour machining, independent healed copies, and hole machining. Native `ViewID`, hole radius versus diameter, missing-tool creation, and explicit regeneration are material input distinctions.

For execution:

1. Call `mc_inspect`; use the returned saved document path, units, actual operation/entity IDs and internal tool slots. Native database IDs differ from tree order and displayed tool numbers.
2. Choose a typed action only when the catalog says `automation: typed`. `typed_candidate` describes a source API that still needs an adapter; it does not authorize inventing a tool. Use [execution contract](references/execution.md).
3. Supply parameters from the user's task, selected setup or identified engineering data. Missing material, cutter, feeds, compensation, depth reference or tolerance can change the machining result; resolve those before execution. Examples are not defaults.
4. Run `mc_prepare_change`, inspect `ok`, the concrete preview, ownership, affected IDs and limits. A preview may write analysis files but does not apply database edits.
5. Follow the user's execution preference. If preview approval is required and not already given for this concrete change, present the affected objects/parameters and wait. If the user already authorized automatic execution with adequate parameters, continue without asking again. `preview_sha256` binds a plan, not human approval.
6. Apply once with the returned plan ID/hash and a unique request ID. Success requires `ok=true`, the expected plan status, and successful actual readbacks. `mc_request_status` is the first action after a timeout. Never infer success from an IPC acknowledgment or resubmit an unknown mutation.
7. Offer or perform `mc_rollback_plan` when the authorized task requires rollback. It acts only on that plan's recorded changes and rejects conflicts. Saving/reopening/restarting invalidates its use; parameter rollback does not restore calculated toolpaths.

HSM regeneration is a separate `mc_regenerate_hsm_plan` step. Porsche contour and hole workflows regenerate during apply only when their explicit `Regenerate` parameter is true. Other regeneration/posting workflows use the existing Mastercam bridge only when actually needed and authorized. Keep raw returns and fresh readbacks. Creating operations, regenerating, simulating and postprocessing are distinct outcomes.

Interactive routes must be operated with the installed UI tools or by the user. Opening a window is not evidence that its machining/geometric operation completed. The original X+ functions and CIMCO simulation do not gain headless APIs merely by appearing in the catalog. Do not replace their absent interfaces with guessed DLL exports.

Read [examples](references/examples.md) only when constructing requests. Read [failure handling](references/execution.md#failure-handling) on errors. Preserve current part files; tests belong in explicitly disposable copies and must clean only their owned objects.

If MCP tools are not loaded, read the generated `references/connection.json` in the installed local skill for the actual repository/config paths. Use that repository's `ai/tools/call.py` with the interpreter where its pinned requirements are installed for a real stdio call, or reload the AI client's MCP connections. An unrelated default Python may have an incompatible MCP package. Do not claim that an unavailable tool was called. Distribution setup is documented in the repository's `ai/README.md`.
