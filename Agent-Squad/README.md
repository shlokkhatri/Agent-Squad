# Agent Squad Integration

This integration connects the existing five CrewAI agents into a sequential
software-development workflow:

Orchestrator intake -> Planner -> Coder -> Reviewer -> Coder revision ->
Final Reviewer -> Tester -> **verified pytest run** -> (bounded correction
loop) -> delivery report.

Test status is never taken from what an LLM says the tests did. After every
crew run the workflow executes pytest itself and uses that real result.

## Before running

1. Keep your existing six tested repository tools unchanged.
2. Extract this ZIP into the project root and allow the included files to
   overwrite the corresponding existing files.
3. Ensure the target repository exists under `workspace/repositories/`.
4. Add `GEMINI_API_KEY=your_key` to the project-root `.env` file.
5. Optionally set `LLM_MODEL=gemini/gemini-2.5-flash`.

## Install dependencies

Activate your existing virtual environment, then run:

```powershell
pip install -r requirements.txt
```

## Run the tests

```powershell
pytest
```

No LLM calls are made and no real API key is needed (the tests set a
placeholder). The workflow tests use fake crews to exercise the real
correction loop, git baseline, and pytest verification. The original
per-file scripts (`python -m tests.test_agents`, ...) still work.

## Start the API

From the project root:

```powershell
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs`.

## Example request

POST `/api/run` (waits until the workflow finishes, which can take minutes):

```json
{
  "repository_name": "sample_project",
  "user_request": "Add a health-check endpoint to the FastAPI application."
}
```

The repository name must identify a directory inside
`workspace/repositories/` (otherwise `404`). Only one run per repository at a
time (otherwise `409`). A Gemini quota failure returns `503`.

## Background jobs

For long runs, start a job and poll it instead of holding a request open:

- `POST /api/jobs` (same body as `/api/run`) -> `202` with `job_id` and
  `status_url`
- `GET /api/jobs/{job_id}` -> live `stage` (`initial_development`,
  `verifying_tests`, `correction_1`, ...) and, once finished, the full
  `result`
- `GET /api/jobs` -> the most recent jobs, newest first

Final `status` values: `completed`, `completed_with_open_review_findings`
(tests pass but the final reviewer said CHANGES REQUIRED),
`completed_with_test_failures`, `completed_with_unverified_tests` (no tests
ran), `failed`.

Jobs are kept in memory only: they are lost on restart, and only the latest
100 are remembered.

## Safety boundaries

- File operations remain confined to the selected workspace repository.
- The Coder receives read, search, and write tools, but not the delete tool.
- The test runner executes `python -m pytest` only; it does not accept arbitrary
  shell commands.
- Git tools are read-only and inspect status/diffs.
- This integration does not commit, push, create branches, or open remote
  merge requests.
- Pytest executes code from the selected repository (including code the Coder
  just wrote). Environment variables whose names contain KEY, TOKEN, SECRET,
  PASSWORD or CREDENTIAL are removed from the pytest process, but it still runs
  as you, on your machine. Only run it on repositories you trust.
- Pytest runs with this project's Python environment, so the target
  repository's dependencies must be installed in it.
- Repositories without Git history get a local baseline commit
  (`git init`, ignore rules in `.git/info/exclude`) so reviewers can diff.
  Repositories that already have `.git` are left untouched.
- The API has no authentication. Do not expose it beyond localhost.
