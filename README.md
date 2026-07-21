# skill-token-bench

**Token-efficiency benchmark for agent skills, CLI intercepts, and memory tools.**

Dockerize an agent + a treatment, run the same task suite **before and after**, and keep a durable record of token impact (input / output / cache / estimated USD).

Example question this answers:

> Does [`i-have-adhd`](https://github.com/ayghri/i-have-adhd) on Haiku reduce tokens on a ladder of prompts→coding tasks — and by how much?

It also covers other intervention shapes:

| Treatment kind | Example | What it usually moves |
| --- | --- | --- |
| `skill` | [i-have-adhd](https://github.com/ayghri/i-have-adhd) | Output tokens / verbosity |
| `cli_intercept` | [rtk](https://github.com/rtk-ai/rtk) | Input tokens from tool/command output |
| `memory` | [claude-mem](https://github.com/thedotmack/claude-mem) | Cache write/read + restated context over sessions |

## Quick start

```bash
cd skill-token-bench
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Offline demo (mock agent — no API key)
stb list
stb run haiku-i-have-adhd
cat results/haiku-i-have-adhd/report.md
```

## How it works

```
experiment.yaml
  ├─ agent     (mock | claude-code | …)
  ├─ suite     (tasks: prompt → coding)
  ├─ baseline  (usually treatments/none)
  └─ treatment (skill | cli_intercept | memory | custom)
        │
        ▼
   for each arm × repeat × task:
     prepare treatment → stage workspace → run agent (local or Docker)
        │
        ▼
   results/<experiment>/
     report.json   # machine-readable durable metrics
     report.md     # human summary + deltas
     runs/...      # per-task outputs + raw telemetry
```

**Primary metric:** mean total tokens (treatment − baseline). Negative delta = savings.

Secondary metrics: input/output/cache tokens, estimated USD, wall time, output chars, success rate (so a “cheaper” skill that fails tasks is visible).

## Treatments

Treatments live under `benchmarks/treatments/<name>/treatment.yaml`.

### Skill (`kind: skill`)

Mounts / injects a `SKILL.md` (local `fixture/` or git source).

```yaml
name: i-have-adhd
kind: skill
source:
  git: https://github.com/ayghri/i-have-adhd
  ref: main
  path: skills/i-have-adhd
```

Bundled offline fixture: `benchmarks/treatments/i-have-adhd/fixture/SKILL.md`.  
Use `--fetch-remote` to clone the upstream skill instead.

### CLI intercept (`kind: cli_intercept`)

Stages wrapper binaries on `PATH` (rtk-style). Coding suites exercise the input-token path.

```yaml
name: rtk
kind: cli_intercept
binary: rtk
wrap_commands: [git, npm, pytest, cargo, ls]
```

### Memory (`kind: memory`)

Longer-running / multi-task model. `warmup_task_ids` mark tasks that write memory; later tasks measure cache/context effects.

```yaml
name: claude-mem
kind: memory
warmup_task_ids: [explain-git-rebase]
```

## Suites

| Suite | Intent |
| --- | --- |
| `simple-prompts` | Short text — output-style skills |
| `coding-basic` | Small code + noisy logs — CLI intercepts |
| `prompt-to-coding` | Mixed ladder for headline skill comparisons |

Add a suite by creating `benchmarks/suites/<name>/suite.yaml` (+ optional `fixtures/`).

## Experiments

| Experiment | Agent | Treatment |
| --- | --- | --- |
| `haiku-i-have-adhd` | mock | skill |
| `haiku-rtk` | mock | cli_intercept |
| `haiku-claude-mem` | mock | memory |
| `claude-code-haiku-i-have-adhd` | claude-code (Docker) | skill |

```bash
stb run haiku-rtk
stb run haiku-claude-mem

# Live Claude Code (needs ANTHROPIC_API_KEY; Docker image falls back to mock without it)
stb docker-build
stb run claude-code-haiku-i-have-adhd --docker
```

## Docker

```bash
stb docker-build
# image: skill-token-bench/agent-base:latest
```

The image mounts the task workspace, optional skill directory, and CLI intercept `bin/` into the container, then runs `docker/agent-base/entrypoint.py`, which emits a final JSON line with token usage.

## CLI

```bash
stb list                 # suites / treatments / experiments
stb validate <exp>       # parse-check wiring
stb run <exp> [--fetch-remote] [--docker|--local]
stb report results/<exp>
stb docker-build
```

## Extending

1. **New skill/tool** — add `benchmarks/treatments/<name>/` with `treatment.yaml` + optional `fixture/`.
2. **New tasks** — add/edit a suite YAML; attach `workspace_fixture` for coding tasks.
3. **New agent** — implement `AgentAdapter` in `src/skill_token_bench/agents/` and register it.
4. **Custom treatment** — `kind: custom` with `install_commands` / env hooks.

## Design notes

- **Before/after is first-class** — every experiment has baseline + treatment arms.
- **Tokens are the durable score** — pass rate is kept so efficiency isn’t gamed by empty answers.
- **Intervention-agnostic** — skills, PATH intercepts, and memory plugins share one report shape.
- **Mock agent is intentional** — CI and local demos stay deterministic; swap `agent.kind` for live harnesses.

## Development

```bash
pip install -e ".[dev]"
pytest -q
ruff check src tests
```

## License

MIT
