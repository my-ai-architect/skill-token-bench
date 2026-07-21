# claude-mem fixture

Offline stand-in for [thedotmack/claude-mem](https://github.com/thedotmack/claude-mem).

For real runs, use `--fetch-remote` or replace this directory with a checkout /
installed plugin for your agent harness. The mock agent and docker entrypoint
simulate cache-write on warmup tasks and cache-read on subsequent tasks.
