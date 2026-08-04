---
name: deepseek
description: Delegate code-writing to DeepSeek V4 Flash via API. Use whenever this project's iron rules (CLAUDE.md) call for DeepSeek to actually write or implement code, instead of writing the code yourself.
---

Per this project's iron rules, **DeepSeek V4 Flash writes the code** — you (Claude) plan, spec, and orchestrate; you do NOT hand-write substantial implementation code. Use the wrapper script `scripts/deepseek.ps1` instead of calling curl by hand.

## Workflow

1. Write a precise coding spec to a temp file (task, target file path, interfaces, constraints, acceptance criteria). Vague specs produce bad code — be explicit.
2. Invoke DeepSeek via the **streaming Python caller** (primary channel — the PowerShell one suffers dropped connections on long generations):

```
python scripts/deepseek_call.py <spec.txt> <target-file> 32000
```

(Needs DEEPSEEK_API_KEY in the process env; pass the key as an optional 4th arg if the shell didn't inherit it. Exit 3 = truncated → rerun with a higher token limit. Always give ≥32000 tokens: the reasoning phase alone can burn >10k. After generation, strip markdown fences if the first line starts with ``` and re-run `python -m py_compile`.)

3. Read the produced file, sanity-check it.
4. Send it to **Codex (`mcp__codex__codex`) for review/acceptance** (iron rule). If Codex rejects, feed the feedback back into a new spec and re-run DeepSeek. Loop until Codex accepts.

## Script options

- `-PromptFile <path>` — coding spec (or `-Prompt "..."`, or pipe via stdin).
- `-OutFile <path>` — write DeepSeek's output here (dir auto-created, UTF-8 no BOM). Omit to print to stdout.
- `-MaxTokens <n>` — default 8192. DeepSeek V4 Flash is a **reasoning model**; raise this (e.g. 12000+) for larger files or the output gets truncated (`finish_reason=length`).
- `-System <str>` / `-SystemFile <path>` — override the default "code engine" system prompt.
- `-ShowReasoning` — also print the model's reasoning to stderr.
- `-Raw` — dump the full raw JSON response.
- `-Model <id>` — default `deepseek-v4-flash`; use `deepseek-v4-pro` for harder tasks.

stdout carries only the code. Usage, warnings, and reasoning go to stderr. Key is read from `DEEPSEEK_API_KEY` (never pass it on the command line).
