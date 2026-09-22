# Working scripts, kept for reuse

Every script used to answer a request lives here, not in a scratch directory
(owner's rule, 2026-09-21). Before writing a new throwaway script, look here.
Run from the repository root with `.venv/bin/python` (the system `python3` has
no `cryptography`). Adding a script means adding a line to the table below.

## What a "mutation check" is (plain words)

To know that a test really protects a rule, break the rule on purpose and see
whether the test notices. A **mutation** is one deliberate defect put in the
code (remove a check, flip a comparison, skip a step). The script applies it,
runs the targeted tests, then **restores the file**. If a test fails, the
defect was **caught**: the test does its job. If everything stays green, the
mutation **survived**: the test is too weak, so a test is added (or the change
is shown to be equivalent, which changes no behaviour). Nothing here changes the
real code for good.

## Index

| Path | What it does |
|---|---|
| `mutation_check.py SPEC` | Generic runner: applies each mutation of a spec, runs its tests, restores the files, lists survivors. |
| `mutations/spec_issue_*.py` | Specs for the runner (#60, #65, #70, #85). |
| `mutations/issue_1xx_2026-09-21.py` | Mutation checks of #108, #109, #110, #133 to #137 (the controls of the admin API, the command line, the models and the agent settings); run from the repository root. |
| `tools/verify_session_issues.py` | Fresh end-to-end check of #103, #108, #109, #110, #133 and #104 (#134 to #138) against the current tree, the live container and the live engine: 40 checks, one PASS or FAIL line each. Its only write to the live application is one backup file. |
| `tools/create_plan_issues_2026-09-21.py` | Record of the script that created the sub-issues of the 2026-09-21 plan; not to be re-run. |
| `mutations/issue_*.py` | Earlier self-contained mutation scripts, one per issue (#47 to #84); run them directly. |
| `mutations/issue_105_mutations.py` | Mutation checks of #105 (model routing: rule validation, the ctx-size clamp, the no-pointless-retry fallback guard); run directly. |
| `mutations/issue_115_mutations.py` | Mutation checks of #115 (the tool-calling foundation in `app/tools.py`: the capability-probe cache and classification, the rounds cap, the identical-call guard, the per-call timeout, the size cap, the untrusted-data label); run directly. |
| `mutations/issue_116_mutations.py` | Mutation checks of #116 (the MCP manager, admin service and catalogue: the disabled-tool guard, per-call timeout, concurrency limit, backoff, result cap, the vetted-builtin and duplicate-name checks, the field bounds, the allow-list and disabled-tool filters in the catalogue); run directly. |
| `rehearsals/*.sh` | Real Docker and real-data-copy runs (#48, #60, #70, #78, #89, #91); see `rehearsals/README.md`. |
| `tools/verify_closed_issues.py` | Fresh end-to-end check of closed issues on a throwaway database and a mock model. |
| `tools/run_test_groups.py` | Runs the targeted test files of each issue and prints the last pytest line. |
| `tools/mock_llm_counting.py`, `tools/run_turns.py` | A mock model that answers with the number of messages it received, and a client that runs N turns (used to show a conversation surviving a restart). |
| `no_network_turn.py` | One real chat turn against the live engine with every connection outside this machine refused and counted (#138); prints the completion's HTTP status and the count (expected 0). |
| `agent_prompts_turn.py` | Real turns against the live engine with three agents of one user, two with opposite system prompts and one with none (#110), on a throwaway database. |
| `tools/repro_request_unique_constraint.py` | Reproduces #85 (denied person writes again: `IntegrityError`) on a throwaway database. |
| `tools/check_claude_split.py` | Checks that no rule bullet was lost when `CLAUDE.md` was split (#71). |
| `tools/scan_changed_files.sh` | gitleaks on the changed and new files only (the whole tree includes the real `.env`). |
| `live/email_poller_instrumented.py` | Live run of only the email adapter against the real mailbox, every IMAP command logged, never credentials. |
| `live/summary_real_model.py` | Summary and exact token counts against the real llama-server (#86, #87). |
| `live/stuck_adapter_demo.py` | Real application with an email adapter stuck on a silent IMAP server: healthy then unhealthy (#90). |
| `live/email_failed_turn_live.py` | Live check of the failed-turn path on the real mailbox (#51). |
| `live/agent_selection_check.py` | Checks agent selection through the API and the dispatcher with a fake model (#54). |
| `live/tool_calling_benchmark.py` | #115's benchmark: tool-selection accuracy and argument-validity rate at T = 1, 5, 10, 20 exposed tools, against a real llama-server without `--skip-chat-parsing`. |
| `../bench_log_search.py` | Times log search at 1k, 10k and 100k rows (#56). |
| `../update_requirements.sh` | Regenerates the dependency locks in `python:3.12-slim` (#69). |

The `live/` scripts talk to the real mailbox: read them before running.
