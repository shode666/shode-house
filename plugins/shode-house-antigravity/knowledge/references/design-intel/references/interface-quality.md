# Interface quality critique card

Use this card when shaping a visual direction or reviewing a rendered interface. It
is vocabulary for judgment, not a style recipe. A pattern is a finding only when it
hurts the product's task, hierarchy, brand, accessibility or measured behavior.

## Read the interface precisely

- **Type**: check kerning in display text, line length and leading for reading,
  hierarchy between headline/body/labels, and tabular numbers where values must scan
  or compare. Prefer a specific product claim to interchangeable marketing copy.
- **Composition**: check optical rather than merely mathematical centering, visual
  weight, negative space, alignment and grouping. Progressive disclosure should
  reduce decision load without hiding a required action or consequence.
- **Interaction**: affordances must communicate what can be acted on; touch targets
  and focus states must remain usable; loading, success, empty and error states must
  explain what happened and what the user can do next.
- **Color and motion**: OKLCH may make palette relationships easier to reason about,
  but measured contrast is still the gate. Animation must be interruptible, preserve
  state, respect reduced motion and avoid layout shift.

## Anti-slop critique

Treat these as prompts to inspect context, never as automatic bans:

- Remove decorative badges, labels, icon tiles, cards, dividers or glow that do not
  encode hierarchy, state, grouping or action. Do not wrap every section in another
  rounded container.
- Show the actual product, task or representative data when that explains value
  better than abstract decoration. Keep one clear primary action; demote competing
  calls to action according to the user's next decision.
- Make headlines, examples and feedback specific to the product and current state.
  Use one coherent icon family and give meaningful icons accessible names.
- Verify readable contrast, useful spacing, stable loading behavior and feedback for
  success, failure and delay. Numeric tables and dashboards use tabular figures when
  alignment improves comparison.
- A familiar pattern such as a gradient, grid, glass panel or large icon is not a
  defect by itself. Record the concrete task/hierarchy/accessibility harm, or leave it
  as an intentional design choice.

## Background direction, with purpose

Paper or felt texture, fluted glass, contour or blueprint grids, halftone, dithering,
grainy gradients, blurred photography, ASCII and pixel treatments are optional art
directions. Choose one only when it reinforces brand/content and keeps foreground
legible. Specify fallback, contrast in every theme, responsive crop/scale, rendering
cost and reduced-transparency/reduced-motion behavior. Never stack effects merely to
make an empty composition look finished.

## Turn critique into evidence

For each affected critical user flow, record:

1. the user's goal and visible start state;
2. the primary action plus edge/error/loading states;
3. the visible outcome or recovery path;
4. a Playwright trace/screenshot and console/network findings from that flow;
5. applicable axe and manual keyboard/screen-reader results.

Playwright tests should exercise user-visible behavior with role/name or label
locators, web-first assertions and isolated state. A `data-testid` is an explicit
contract for cases where user-facing semantics cannot identify the element; CSS/XPath
structure is the last resort. State-changing flows still require before/after and
source-of-truth evidence from the runtime axis.

## Sources and provenance

- The design terms, background prompts and unslop examples supplied by the user are
  ideation input, not standards or evidence.
- Impeccable's slop catalog describes findings as reasons to inspect the page, task
  and intentional choices; this card adopts that contextual boundary, not its code.
- `nextlevelbuilder/ui-ux-pro-max-skill` remains the vendored proposal catalog. Its
  license notice and the catalog/evidence boundary remain in the parent README.
- Playwright's official best practices are the source for user-visible behavior,
  isolation, user-facing locators, web-first assertions and traces.
