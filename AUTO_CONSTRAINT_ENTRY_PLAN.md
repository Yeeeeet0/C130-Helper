# Automatic speed and altitude entry - implementation plan

Status: implemented in the local test build. Simulated-CDU tests pass;
a captured cockpit run confirms combined entry and forward altitude propagation. Partial-entry forms and a complete successful run still need cockpit validation.
Public GitHub and the live release remain unchanged.

## Local implementation

- The armed route carries all planned fix occurrences as matching context, including fixes without constraints.
- After cleanup, a read-only LEGS scan compares earliest and latest ordered matches. Ambiguous
  constrained occurrences stop before any constraint typing. Unique matches are entered in one
  forward pass, reusing LEGS and its page controls.
- Inputs use `speed/altitude`, `speed/` or `/altitude` at the associated right line-select key.
  The combined form was accepted as 324/20000 in a captured cockpit run. Partial forms remain test assumptions.
- Every write checks the page, row identity, requested values and unspecified companion field.
  All other visible row identities and speeds must remain unchanged. ASC carries entered altitude
  forward, even over displayed arrival restrictions; later rows may retain their original altitude
  or take the just-entered altitude. This allowance carries across pages. Earlier rows cannot change.
  Later explicitly planned values are entered in flight order. Review arrival restrictions before EXEC. Already-correct targets are counted without typing. When either configured field differs, both configured fields are submitted; a blank side is used only for an unspecified field. Readback accepts
  equivalent feet/FL displays but requires an exact restriction, without an A/B qualifier.
- Whole knots and feet use the manual plan's rounding. Negative altitudes are rejected at arming
  until their input syntax is confirmed. No EXEC, blind retry or automatic restart is sent.
- Arrival radio setup follows successful constraint verification. Existing stop controls,
  route slots and default/accelerated timing apply. Progress counts verified requested fields.
- Simulated coverage includes both fields, partial fields, preserved qualifiers, repeated fixes,
  multiple pages, RTE 2, delayed page changes, rejection, corrupt readback, Stop and worker handover.

## Remaining cockpit validation

On an empty test route, set two fixes and verify a combined entry, speed-only and altitude-only.
Check that the blank side preserves an existing restriction, including A/B qualifiers. Capture
`cdu-route-diagnostic.jsonl` if the run stops. Repeat on RTE 2 and across a LEGS page boundary.
Inspect all values before manually choosing whether to EXEC. Do not retry a partial load blindly.

The original design checklist below records the intended verification work; its live-fixture
and cockpit-test items remain outstanding.

## Intended result

Load the route, finish SID/STAR selection and LEGS cleanup, then enter the explicitly planned
speed/altitude values at the correct fixes. Complete arrival radio setup afterwards.
Leave activation and EXEC to the pilot.

Each constraint has one numeric representation: `speed_kt` and `altitude_ft`.
Use the same whole-knot/whole-foot rounding as the manual plan. Mach, FL and metric are input views.
Do not create a second set of values or invent missing targets.

## What the installed module confirms

- ASC user manual, page 265: LEGS rows associate speed/altitude constraints with waypoints.
  With an empty scratchpad, a right line-select key opens that waypoint's data page.
- `Cockpit/Scripts/CNI_MU/pages/legs_progress.lua` draws five waypoint rows, each with speed and
  altitude readouts. Display formats include constraint qualifiers and feet/FL.
- `src/route_runner.py:legs_rows` already locates waypoint rows for cleanup, but currently discards
  the speed and altitude text. It needs a read-only extension before it can verify these fields.

These sources establish the displayed layout, not the accepted scratchpad grammar.
Do not assume that a displayed `speed/altitude` pair is a valid entry string.

## Work sequence

1. **Confirm entry syntax in a controlled cockpit test.** Capture the original page, scratchpad,
   key press and accepted page for: speed only, altitude only, both fields, replacing an existing
   value, and an unspecified companion field. Confirm the right LSK mapping, accepted units,
   qualifiers and provisional-page behaviour. Use an inactive test route; no automatic EXEC.
   If partial entry cannot preserve the companion field, determine a safe paired-entry method.

2. **Extend the LEGS reader.** Return row index/LSK, identifier, discontinuity state, raw speed,
   raw altitude, qualifier and unit. Keep the raw display as well as the parsed numeric value.
   Preserve the existing cleanup parser's refusal to act on unknown layouts.

3. **Build and validate targets.** Include only configured fields, in flight order, with waypoint
   identity, coordinates, section and occurrence context. Match against the final route, including
   procedure legs. Repeated visits to the same identifier must stay distinct. If more than one
   occurrence could match, stop for review; never choose the first identifier blindly.

4. **Add one forward constraint pass after cleanup.** Reuse the open LEGS page. Return to the
   first main LEGS page once, then advance page by page. Apply all matching targets on the current
   page before NEXT; do not cycle through INDEX/RTE for every field. Skip already-correct values
   after verifying them. A future optimization may combine passes only if row identity stays safe.

5. **Verify every write.** Clear/check the scratchpad, submit only the verified syntax, then confirm
   the selected route, waypoint row and resulting value. Preserve an unspecified speed/altitude,
   at the selected fix, including its at/above/below qualifier. Check that other row identities, speeds
   and earlier altitudes did not change. Permit only the observed forward altitude propagation on
   later rows, and make its effect on arrival restrictions clear to the pilot. Stop on rejection, unexpected navigation, ambiguous identity or failed readback.
   No blind retries and no automatic restart after a partial run.

6. **Integrate progress and controls.** Count only requested, verified speed/altitude fields.
   Reuse selected RTE 1/2, input speed, CAPS stop, app Stop and existing transport checks.
   Report which fields remain after failure. Continue arrival radio tuning only after the
   constraint pass succeeds. Identify this as a local test feature until cockpit validation is complete.

## Tests before enabling

- Real captured before/after fixtures for every supported entry form and unit display.
- Native/custom/airway fixes, repeated identifiers, intentional later returns and procedure overlap.
- Page boundaries, both route slots, existing qualifiers, one-field targets and already-correct values.
- Constraint rounding parity with the manual plan, legacy-plan conversion and no targets configured.
- Pause/disconnect/Stop during typing and readback; rejected entries and unexpected pages.
- Regression checks for route creation, custom records, discontinuities, duplicates and radio tuning.

Public release gate: simulated-CDU tests and a successful in-cockpit run for the supported ASC
version. The local test build now attempts constraint entry with verified readback. Public publishing
still requires an explicit instruction from the user.
