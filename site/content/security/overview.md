---
description: The threat model in one page, the protections that exist, what is optional, and the limits that are accepted rather than fixed.
---
This page is a map of the security design. The authoritative, file-and-line-level version is [the full threat model](@security/policy) (`SECURITY.md`), which is written to be checked against the code rather than trusted. Report vulnerabilities privately through [GitHub's private vulnerability reporting](https://github.com/http-solution/cartogen-ai-qgis-plugin/security/advisories/new), never in a public issue, and never include real keys or sensitive data.

## Threat model

The plugin runs a model in a tool-calling loop against a real QGIS project. Two inputs are **untrusted**:

1. **The model's own output.** A provider response, a prompt-injected instruction hidden in fetched web, OSM or HDX content, or a plain model mistake can all produce a tool call with attacker-influenced arguments: a script to run, a URL to fetch, SQL to execute.
2. **Content fetched from the internet** that is fed back into the model's context and may be written to look like instructions.

**You are trusted**: you can already run arbitrary Python in the QGIS console. The protections exist for the case where the *model*, not you, ends up driving a dangerous action, through injection, hallucination or a compromised provider.

## Protections

| # | Protection | How it works | State |
|---|---|---|---|
| 1 | **Script sandbox** (`execute_pyqgis_script`) | Static AST validation (blocked modules, builtins and attribute chains such as the `().__class__.__bases__` escape; blocked Qt classes that read files, launch processes or open sockets) plus a curated allow-list of about 50 builtins, so `eval`, `open` and `getattr` cannot be resolved. | On |
| 1b | **Process isolation** | The script runs in a **separate OS process** with its own `QgsApplication` and a temp-file copy of the project, so it never sees the plugin's credentials, conversation history or Python object graph. File-backed layers are handed over as copies; database and web layers are read-only in the worker. If isolation is unavailable the tool **refuses to run** instead of falling back to the plugin's own process. | On |
| 1a | **Allow-listed Processing runner** | `run_allowlisted_processing_algorithm`: only algorithm ids already used in the codebase, unknown parameters rejected before running, output always in memory, no raw-argument parameters. | On |
| 2 | **Read-only SQL** | A keyword blocklist (DROP, DELETE, INSERT, COPY, PROGRAM, DBLINK and family…), a one-statement guard, and a database-level `READ ONLY` session that **fails closed**: if it cannot be confirmed the query is refused. The result layer cannot be edited. A read-only database role remains the real guarantee. | On |
| 3 | **SSRF guard** | Resolves the host and refuses loopback, private, link-local (including the `169.254.169.254` metadata endpoint), reserved and multicast addresses, IPv4 and IPv6. **Every redirect hop is re-checked**, because a URL that passed once could redirect to an unvalidated address. Bodies are size-capped. | On |
| 4 | **Credentials** | QGIS Auth Manager (encrypted), else process memory for the session with a warning; never plaintext on disk. Logs carry no credential and no exception text. | On |
| 5 | **Destructive-action gate** | `confirmed` is stripped from model-supplied arguments; only a UI click approves removal, project loading and in-place field edits. | On |
| 6 | **Prompt-injection guidance** | The prompt tells the model to treat fetched content as data, never instructions. **Prompt-level only; not enforced in code.** | On |
| 7 | **Scheduler limits** | Allow-listed tools, 1-minute floor, at most 5 schedules, same cloud override as running a workflow. | On |
| 8 | **Link and download hygiene** | Replies cannot forge internal links; remote answers are size-limited; archives that would expand past 256 MB are refused. | On |
| 9 | **Egress gate and model view** | Block or warn when a protected layer's data would reach a cloud provider; withhold its field names. | **Off by default** |
| 10 | **Plan gate** | Require a validated plan for DELETE and PUBLISH calls. | **Off by default** |
| 11 | **Prompt refiner** | Rewrites your message through the provider; doubles how often it leaves your machine. | **Off by default** |

The behavioural guards (loop guard, response guard, output router) are covered under [Guards and honesty checks](@architecture/guards).

## Accepted limits, stated plainly

These are not bugs waiting to be fixed; each was weighed and left.

- **This is not a formal sandbox.** Script restriction by blocklist is best-effort. Process isolation removes access to the plugin's in-memory state, **not** the machine's filesystem: the worker can still read and write files like any PyQGIS script. Treat the tool as file-I/O-capable with the interpreter-escape, process and network vectors closed.
- **Local file access is intentionally broad.** Tools that load or export your own files will read or write any path the model names. A prompt-injected instruction could get the model to read a local file and describe it in chat. Writes are bounded by normal OS permissions.
- **Prompt-injection guidance is not code-enforced.** A sufficiently adversarial payload may override it. There is no filter on what fetched content may contain.
- **DNS rebinding on the SSRF guard.** The host is resolved for the check and again for the fetch, so a purpose-built attacker-controlled resolver could in theory slip through. A full fix needs connection pinning with correct TLS handling, judged riskier than the narrow scenario.
- **Optional imagery model weights** are downloaded by the `ultralytics` package on first use; the plugin does not pin or verify them.
- **The egress gate prevents accidents, not determined bypass**: its mode is a setting on your own machine.
- **Chat history is saved in the project file by default.** The risk of a shared project carrying sensitive conversation is accepted by default and unmitigated for anyone who never opens Settings.
- **Downloads can be large.** Fetch tools ask above a size threshold (default 50 MB) and refuse whole-country WorldPop by default, but treat any fetch tool as a potential large download.

## Verified how

SECURITY.md lists adversarial tests run against the sandbox with confirmed findings, each now a permanent regression test (look for the `# Confirmed live` comments in the tests). In CI a secret scan runs on every push and the QGIS 4.2.2 live job exercises the sandbox, isolation and read-only SQL against a real PostGIS server. None of this is a substitute for a third-party audit. See [Testing and CI](@development/testing).
