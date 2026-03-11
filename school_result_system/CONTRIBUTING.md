# Contributing Guide

## Development Workflow

1. Create a feature branch.
2. Make small, focused changes.
3. Run checks before commit:
   - `python manage.py makemigrations --check`
   - `python manage.py test`
4. Commit code + migrations together.

## Migration Policy

This project has existing production-like migration history. To keep it stable:

1. Never rename or delete committed migrations that may already be applied.
2. Always generate new migrations for model changes.
3. Use explicit migration names:
   - `python manage.py makemigrations <app> --name <short_action_name>`
   - Example: `python manage.py makemigrations results --name add_result_workflow_status`
4. Ensure migrations are clean before PR:
   - `python manage.py makemigrations --check`
5. If a migration touches only `id` type drift or historical cleanup, isolate it in a dedicated migration and document why.

## Role and Authorization Changes

When editing permissions or protected views:

1. Add/adjust tests for each affected role.
2. Verify denied roles get safe redirects or `403`.
3. Verify allowed roles can complete full workflow actions.

## Results Workflow Changes

For any change to academic workflows (`draft`, `submitted`, `approved`, `released`):

1. Keep state transitions explicit in view/service logic.
2. Add regression tests for invalid transitions.
3. Ensure parent/student visibility still depends on released state.

## Pull Request Checklist

- [ ] `makemigrations --check` passes
- [ ] tests pass
- [ ] role-based access verified
- [ ] no breaking migration rewrites
- [ ] user-facing behavior documented
