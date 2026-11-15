# UX/UI agent practices review (shode-house-z47)

## Decision

Improve the existing `design` role with a contextual interface-quality critique card
and align its user-flow evidence with Playwright. Do not install or vendor another
plugin, detector or SDK. The current 20-skill boundary, design-intel catalog, design
runner and review axes already supply the correct architecture.

## Sources assessed

| Source | Useful idea | Decision |
|---|---|---|
| [`nextlevelbuilder/ui-ux-pro-max-skill`](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | Retrieval-based design vocabulary and stack guidance | Already vendored as an attributed MIT subset. Keep catalog as proposal, never evidence. |
| [Impeccable slop catalog](https://impeccable.style/slop/) / [`pbakaus/impeccable`](https://github.com/pbakaus/impeccable) | Name visual problems precisely; its slop findings are prompts to inspect task and intent, not automatic bans | Adapt the contextual critique boundary and vocabulary only. Do not copy or run Apache-2.0 code. |
| [`obra/superpowers`](https://github.com/obra/superpowers) | Test process instructions with scenarios; do not trust review alone | Already represented by routing/eval suites. Add a focused regression test for the new critique contract. |
| [`vercel/ai`](https://github.com/vercel/ai) | Provider-neutral agent loops and deterministic mock providers for AI applications | Valuable for target projects that use AI SDK, but not a UX-role dependency. No change here. |
| [`supabase/agent-skills`](https://github.com/supabase/agent-skills) | Small discoverable skills with lazy references and release artifacts | shode-house already uses lazy references and stricter packaging gates. Installing product-specific skills would widen scope. |
| [Playwright best practices](https://playwright.dev/docs/best-practices) | Test user-visible behavior, isolate tests, prefer user-facing locators, use web-first assertions and traces | Adopt in the critique card and correct selector priority in UI/runtime guidance. |

## Meaning of “AI slop” used here

“AI slop” means recurring model-default choices that make an interface generic,
over-decorated, poorly prioritized or less usable: repeated card shells, ornamental
labels, competing calls to action, interchangeable copy, arbitrary effects, weak
feedback and inaccessible contrast. It is not a fixed list of forbidden aesthetics.
A gradient, grid, glass effect, texture or large icon is acceptable when it supports
the product task, brand and hierarchy and survives accessibility/performance checks.

## Contribution assessment

No new skill or model profile is warranted. The reusable capability is already owned
by `design`; one lazy reference plus existing Phase 1b/3a runbooks covers it. The new
guidance prevents design review from confusing model-era style tells with demonstrated
UX defects. Its canonical owner is the design catalogue; it is lazy because only
visual direction, critique and polish work needs it. The focused test protects the
contextual boundary and Playwright evidence contract.

## License and execution boundary

No upstream code or dependency was downloaded, installed or executed. The existing
ui-ux-pro-max attribution remains unchanged. Impeccable concepts were independently
summarized with provenance rather than copied; its repository is Apache-2.0. The
other repositories supplied comparison evidence only.
