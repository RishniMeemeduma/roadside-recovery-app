# Contributing

## Commit message convention

Use [Conventional Commits](https://www.conventionalcommits.org/) style:

```
<type>(<scope>): <short summary>

<optional body explaining WHY — not what, the diff already shows that>

<optional footer, e.g. "Closes #12">
```

**Types:** `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `ci`, `perf`, `style`

**Examples:**
- `fix(dispatch): wrap offer creation in transaction.atomic()`
- `feat(admin): add soft-delete for user records`
- `ci: add ruff + coverage to GitHub Actions`
- `docs(readme): document DVLA_API_KEY env var`

**Rules:**
- Summary under 70 characters, imperative mood ("add", not "added")
- No trailing period on the summary line
- Body wraps at 72 characters, explains the motivation
- Reference issues with `Closes #N` or `Refs #N` in the footer

Set the template so `git commit` opens it for you:

```
git config commit.template .gitmessage
```

## Local quality checks

Before opening a PR:

```bash
pip install -r requirements-dev.txt
pre-commit install                # one-time
ruff check . && ruff format --check .
coverage run manage.py test && coverage report
```

CI runs the same checks on every push and PR.

## Branching

- Branch off `master`
- Name: `<type>/<short-slug>` (e.g. `fix/dispatch-race-condition`)
- Keep PRs focused — one concern per PR
