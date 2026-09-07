---
trigger: always_on
---

# Deep Work & Verification Rule

For non-trivial development tasks, do not immediately modify code.

## 1. Inspect before acting

- First inspect the relevant project structure, files, existing implementation, dependencies, and data flow.
- Understand how the requested feature currently works before changing it.
- If information can be verified from the codebase, do not guess.
- Search for existing patterns and reusable implementations before introducing new architecture.
- Identify which files and existing features could be affected.

## 2. Reason about the problem

Before implementation:

- Identify the actual root cause or requirement.
- Distinguish symptoms from root causes.
- Consider multiple implementation approaches when appropriate.
- Prefer the smallest safe change that is consistent with the existing architecture.
- Do not unnecessarily rewrite working code.
- Do not silently change unrelated behavior.

For substantial or multi-file changes, create a clear implementation plan before editing.

The plan should include:

- current behavior
- problem or requirement
- affected files/components
- proposed changes
- possible side effects
- testing and verification strategy

## 3. Implement carefully

- Follow existing project conventions and architecture.
- Preserve backward compatibility unless the user explicitly requests otherwise.
- Avoid temporary hacks when the root cause can be fixed properly.
- Do not suppress errors merely to make tests pass.
- Do not remove existing functionality unless required.

## 4. Verify after implementation

After making changes:

- Run relevant tests.
- Run build, type-check, lint, or other available validation when appropriate.
- Actually run the application when practical.
- Verify the requested behavior instead of assuming the code change works.
- Check for regressions in related functionality.

For UI changes:

- Inspect the actual rendered UI.
- Use browser verification when available.
- Compare the result against the user's screenshot, reference, or existing design.
- Check layout, spacing, text, interactions, responsive behavior, and errors.
- If visual correctness matters, use screenshots to verify the final result.

## 5. Final review

Before reporting completion, compare the final implementation against the original request.

Confirm:

- all requested requirements were addressed
- no requirements were accidentally omitted
- existing functionality still works
- tests or validation were actually executed
- the real application behavior was checked when possible
- unresolved issues are explicitly reported

Never claim something was tested, verified, or completed unless it was actually checked.

If verification cannot be performed, clearly state what was not verified and why.