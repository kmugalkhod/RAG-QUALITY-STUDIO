# 0002. Workspace UI redesign: decision record

Build spec: [index.md](index.md).

## Context

The Studio workspace grew screen by screen. The one authored stylesheet is 5766 lines with 26 font sizes, 35 distinct spacing values, 33 raw color literals outside the token block, seven breakpoints and more than fifty arbitrary Tailwind values in components. The button primitive has eight sizes. The result is inconsistent rhythm between screens, controls below touch size on desktop, and a purple accent the owner now considers generic.

The app is dark only and the frontend standards forbid a partial light theme, so a light theme must be complete or absent. Mobile navigation is a top hamburger, away from the thumb. Backend failures surface per page with no shared signal. The widget is a separate app with its own colors and shares nothing with Studio.

The owner authorized replacing the current visual authority on 2026-09-30 and wants a polished, professional standard: an 8pt grid, at most five type sizes, complete light and dark palettes, 44px or larger targets, symmetrical control layouts, and real loading, empty, error and disconnected states. Behavior and the API must not change. The project builds with a Tracer Bullet approach and a Beta workflow, so the design must be provable one screen at a time in the real app. A redesign that lands all at once cannot be verified that way and would block the quality slices queued behind it.

## Options considered

### Option 1: Fix in place, restyle within the current tokens

Keep the existing semantic tokens and selectors, change values and tidy spacing screen by screen without a new token layer or lint guard.

**Pros**:
- Smallest change set and no new tooling.
- No coexistence of two systems.

**Cons**:
- The current token set has no spacing or type scale, so the grid cannot be enforced; drift returns immediately.
- A light theme cannot be added without restructuring the token block anyway.
- Leaves the 26 sizes and 35 spacing values in place unless every selector is touched, which is the full rewrite in disguise.

### Option 2: New token layer, screens migrated one at a time (chosen)

Add the approved light and dark token sets, the scales and resized primitives first, keep the old semantic names as aliases, then migrate each screen and delete its legacy selectors in the same change. A lint guard with a shrinking allowance prevents new off grid values.

**Pros**:
- Fits Tracer Bullet: tokens, primitives, shell and Overview form a verified thread before widening.
- Every step leaves a working app and can be reverted alone.
- The stylesheet only shrinks; the allowance counter makes progress measurable.

**Cons**:
- Two visual languages coexist during the migration.
- Old global element rules (such as `h2 { margin: 0 }`) outrank utilities while unlayered, so they leak into migrated screens until moved. Step 1 moves them below utilities (see the revision below).
- More total changes than a single rewrite.

### Option 3: Replace the stylesheet and primitives in one change

Write a new stylesheet and primitives from scratch and switch every screen in one large change.

**Pros**:
- No coexistence period and no aliases.
- Cleanest final result on paper.

**Cons**:
- Cannot be verified incrementally; a single large change across eleven routes and two theme passes is exactly the big bang rewrite that ships late and breaks working screens.
- Blocks all other frontend work until it lands.
- Rollback means losing everything at once.

## Rationale

Option 2 is the only path that honors the Tracer Bullet approach and the Beta workflow: one thread through tokens, primitives, shell and Overview is verified with real screenshots before the rest moves (basis: your `AGENTS.md`, build approach and delivery sequence). It is the strangler pattern applied inside one stylesheet, which the frontend standards already ask for by requiring superseded declarations to be removed in the same change rather than appended (basis: `docs/frontend-standards.md`, styling rules). Option 1 fails the brief because the grid and the light theme need a token layer that does not exist. Option 3 is the big bang rewrite failure pattern.

The palette is near monochrome with one desaturated blue accent because the owner rejected the purple accent as generic, and the verified references (Vercel Geist, Supabase) show that serious tools rely on neutral surfaces, hairline borders at 8 to 14 percent opacity and a single accent used sparingly (basis: Geist and Supabase design system pages, links below). Linear's indigo was not adopted because it reads purple. Control sizes of 40px default, 48px on touch and 32px compact on pointer devices reconcile the owner's 44 to 48px touch rule with desktop density (basis: Apple Human Interface Guidelines 44pt minimum and Material 3 48dp minimum, links below). Table rows at 44px and headers at 36px follow the Supabase table pattern.

The bottom tab bar on mobile follows the thumb reach rule in the brief and the device control app precedent, where primary controls sit in the lower part of the screen (basis: Home Assistant tile cards for symmetrical control clusters and explicit unavailable state). Vibration is limited to primary actions on coarse pointers because the web exposes it only on Android Chrome and noisy feedback in tables would harm the experience. The disconnected banner is a global signal from a health poll because per page errors cannot tell the user the whole backend is down, and a full screen blocker would hide data already on screen.

## Evidence

### UI audit of the current implementation (2026-09-30, read only scan)

- Stylesheet `frontend/src/app/styles.css`: 5766 lines; dark only, `color-scheme: dark`, no `data-theme` handling; 26 distinct font sizes from 9px to a clamp up to 5.25rem; 35 distinct pixel spacing values from 1 to 200px; 33 raw hex literals outside `:root`; selector groups for experiments (about lines 188 to 386), playground (480 to 687), chunks and documents (1911 to 2084), pipelines (about 1992 to 2001), React Flow overrides (3164 onward), ingestion (3306 to 3854) and auth (5537 onward). Tokens exist for colors, sidebar, status, two surfaces, radius, a 150ms transition, chat width 900px, inspector width 340px and React Flow variables. No spacing or type scale tokens.
- Primitives: Button has variants default, destructive, outline, secondary, ghost, link and sizes default 32px, xs 24px, sm 32px, lg 40px, icon 36px, icon-xs 24px, icon-sm 32px, icon-lg 40px. Input is 36px with a 44px mobile fallback. Primitives present: accordion, alert, badge, checkbox, input, label, native select, progress, separator, skeleton, table, tabs, textarea.
- Shell: sidebar `w-54` (216px), header 48px, seven routes (overview, knowledge base, pipelines, deployments, playground, experiments, settings), hamburger toggle below 760px, page padding 28px desktop. Breakpoints in use: 720, 760, 960, 980, 1000, 1100 and 1150px.
- Feature pages: all have loading and error states with local retry; states are hand built per page; two `style={{}}` props and more than fifty arbitrary Tailwind values across `src/`.
- Widget: independent stylesheet with `--accent`, `--accent-soft`, `--user` and `--line` variables, three appearance colors, 68px launcher, no shared tokens.
- Errors: `src/lib/api.ts` maps statuses to safe messages with a 12s timeout; there is no global offline or disconnected state.

### Reference research (2026-09-30, public pages, verified by a read only agent)

Mobbin was requested but every search (screens, flows, sections) returned "Mobbin MCP requires a paid plan". A direct browser visit with agent-browser was also tried; every Mobbin page redirects to login, the automated window cannot use Google sign in, and the owner chose to skip Mobbin, so no Mobbin reference was used. Seven public references were fetched instead; each URL below loaded at the time of research.

| Reference | Patterns adopted | Patterns rejected |
|---|---|---|
| Vercel Geist design system | Spacing scale on 4 and 8 multiples; weights 400 read, 500 interact, 600 announce; neutral surfaces with a single accent | Display sizes above 24px; marketing section spacing |
| Linear design system | Dense 4 to 8px gaps without shrinking targets; semi transparent borders at 5 to 8 percent | Indigo accent (reads purple); weight 510 (needs the variable font) |
| Supabase design system | 44px data rows, 36px header rows; borders instead of shadows in dark mode; CSS property theming | Emerald accent (would collide with success) |
| Material Design 3 | 48dp touch minimum, 8dp gap between targets, 44dp pointer minimum | Elevation tiers and tonal surfaces |
| Apple Human Interface Guidelines | 44pt minimum target, larger for accuracy critical controls | Platform specific navigation chrome |
| Home Assistant tile cards | Symmetrical control clusters; explicit unavailable state; multiple controls per card without horizontal scroll | Card colored backgrounds |
| Dify workflow studio | Right side settings panel; dotted canvas grid; compact node cards with a single config line | Multi branch node types outside the validated graph |

Cached report: `docs/.agent-cache/research/workspace-ui-redesign.md`.

### Old CSS layer revision (2026-09-30)

**What happened.** Step 1 as first written wrapped all the old CSS in a layer below Tailwind's `utilities`. The build measured about 170 elements whose layout changed, so the wrap was backed out and the old CSS left unlayered while this was revised.

**Why.** Unlayered CSS outranks every layered rule, whatever its specificity. A static scan of `className` strings found:

- 140 call sites that put old classes and Tailwind utilities on the same element (367 old class names in total). The biggest are `AnswerResult.tsx` (17), `DocumentInspector.tsx` (11), `WorkspaceSidebar.tsx` (10) and `ProjectOverview.tsx` (10). Wherever both set the same property, the old rule had always won, so today's look depends on the utility never applying. Put the old CSS below utilities and those dead utilities suddenly apply.
- About 15 old element rules with no class (`*`, `body`, `a`, `button`, `h2`, `h3`, `footer`, `progress`, `summary`, `main:focus`, `input[type='file']`, the reduced motion rule). Unlayered, these outrank utilities on every screen, migrated ones too. For example `h2 { margin: 0 }` cancels any `mb-*` on a migrated heading, and `footer { padding: 20px 48px }` hits any footer. Eight headings today carry margin or font utilities that these rules silently cancel.
- Four `.app-shell .react-flow__*` overrides. React Flow's stylesheet is unlayered, so any layer would put them below it.
- Every descendant element selector in the old CSS is scoped under an old class (for example `.pipeline-validation h2`), so it reaches only elements inside that class.

**Options weighed.**

1. **Split (chosen).** Class rules go into `@layer legacy`, ordered after `utilities`. Element rules go into `base`. The React Flow overrides go into the unlayered vendor block, and only the utilities hit by the moved element rules are edited. A guard keeps old classes out of migrated files. Pros: zero visual change, proven by a computed style diff. Old element rules stop leaking into migrated screens. Close out still deletes one named block. Cons: isolation rests on a regex guard rather than the cascade, so dynamic class names need review. About 140 utilities stay dead until their screen migrates.
2. **Layer below utilities and fix every conflict.** This was the original plan, plus reconciling all 140 sites in step 1. Pros: the cascade itself guarantees new styles win. Cons: step 1 then restyles every screen at once, which works against one screen at a time and Tracer Bullet, and makes step 1 hard to review or revert.
3. **Stay unlayered and add only the guard.** Pros: no move at all. Cons: the old element rules keep beating utilities on migrated screens, and there is no named block to delete at close out.

**Why the split.** The strangler pattern needs the old system to keep working unchanged while the new one grows beside it. Only the split gives a zero change step 1 and also stops the global rules from reaching new screens. Its main weakness (guard, not cascade) is limited in practice: old descendant selectors are all class scoped, so a migrated file that names no old class cannot be matched by any old rule. The runner up is option 2, the right choice only if you want the old screens restyled early anyway.

**Cross check of the revision (Fable 5.1, 2026-09-30).** It found no reason to drop the split, and the owner chose to apply every recommended fix:

- Wrapper classes (`app-shell` and two route wrappers) are exempt from the guard until close out, because 800 legacy selectors hang off `.app-shell`.
- An earlier line wrongly said step 1 deletes about 140 dead utilities. Class rules still outrank them, so only utilities hit by the moved element rules change.
- React Flow's unlayered stylesheet now wins ties that legacy used to win (the attribution link color), so the editors are in the parity routes and such rules move to the vendor block.
- Partly dead utilities get a narrower replacement. Preflight duplicates are deleted rather than moved.
- The parity run gains a tablet width, pseudo elements, seeded data, a fixed clock, font loading and a 0.5px tolerance. The guard now parses with `postcss`, uses base classes only and checks every string in migrated files.
- Clerk's stylesheet turned out to hold no unlayered rules. Its widgets are checked by hand.

The simpler option it raised (move element rules only in step 3, with no class edits in step 1) was declined. The move is easiest to prove at zero change when nothing else changes at the same time.

**How it is proven.** A computed style diff (`e2e/legacy-parity.spec.ts`) records every element's computed styles and box on every route before the split and compares after. Step 1 ends at zero changed elements. It is the repeatable form of the measurement that found the 170.

### Cross check record (2026-09-30)

A read only critique found 32 decision gaps and 8 soundness points. The owner chose to apply all the recommended fixes. The fixes included raising `--border-strong` to 40% and 45% opacity, limiting `--foreground-subtle` to non text uses, and adding the token markers, the Tailwind scale reset and the legacy allowance. They also defined the Overview card states, the connection store, the Button aliases, request interception and the phone context in the journey, and axe contrast checks. A contrast recalculation of every token also nudged dark `--danger` from `#c8524a` to `#d9625a` and light `--warning` from `#9a6a12` to `#8f6210`, so each passes 4.5:1. One finding was rejected. The isolated stack's frontend already serves on port 5273, so the verify URL stays, with an added rule to stop the Vite dev server first.

A second read only critique on Opus found 32 more gaps and 8 soundness points. The owner chose to apply all the recommended fixes. The main changes were:

- Old CSS wrapped in `@layer legacy`, with the Tailwind scale reset deferred to close out and a dark theme fallback until then.
- Named size keys, a color palette reset, and new `--danger-fill`, `--surface-hover` and `--overlay` tokens. White on dark `#d9625a` was about 3.6:1, which failed.
- Button behavior in CSS (touch sizing, `:active`), `aria-disabled` wiring, and an offset focus ring.
- Five mobile tabs instead of six.
- Exact Overview copy, counts and statuses.
- 502 to 504 handling, with polling on `/api/ready`.
- A node summary helper, and 220px kept for horizontal layouts.
- Light and dark accent pairs in the widget.
- Typed fixtures and a held loading state in the journey, with sign in dropped from it because the test stack runs local auth.
- A token contrast Vitest, and context file amendments in step 1.

Checked against the repository: `npm run format:check` exists, so that finding was rejected. The frontend nginx config sets no content security policy today, so the external `theme-init.js` is future proofing rather than a current fix. The default answer template spaces nodes 116px apart vertically, so 80px cards fit.

## References

**Project sources** (verifiable, in this repo):
- `AGENTS.md`: Tracer Bullet build approach, frontend behavior rules, canonical dev URL, verification commands.
- `docs/frontend-standards.md`: single stylesheet rule, remove superseded declarations, accessibility and responsive requirements, shadcn CLI pin.
- `DESIGN.md`: the superseded visual authority; node geometry and panel widths that this spec regrids.
- `docs/scope/scope.md` row 14: the authorized redesign and its Done when line.
- Spec 0001 (public widget embed): the widget trust boundary this spec must not weaken.

**Practices & standards**:
- Strangler pattern for live migrations.
- WCAG 2.2 AA contrast (4.5:1 body text, 3:1 large text and UI components).
- 8pt spacing grid with a 4px half step.
- Touch target minimums: 44pt (Apple) and 48dp (Material 3).

**Links** (web verified during research on 2026-09-30):
- Vercel Geist design system summary: https://open-design.ai/plugins/design-system-vercel/
- Linear design system summary: https://open-design.ai/plugins/design-system-linear-app/
- Material Design 3, structure and touch targets: https://m3.material.io/foundations/designing/structure
- Apple Human Interface Guidelines: https://developer.apple.com/design/human-interface-guidelines/
- Supabase design system, tables: https://supabase.com/design-system/docs/ui-patterns/tables
- Home Assistant tile card: https://www.home-assistant.io/dashboards/tile/
- Dify workflows: https://dify.ai/workflows
