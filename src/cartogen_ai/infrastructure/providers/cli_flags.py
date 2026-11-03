"""Which command-line flags the CLI bridge may do without, and how to read a CLI's refusal of one (PLAN-053 stage 2).

Pure: no process is run here, no other provider module is imported. `cli_bridge` builds the command lines from the tables below, runs the CLI, and
asks this module what a rejection means.

Why this exists: Claude Code and Codex change their flags between versions, and the plugin cannot know every version's flag list. It does not guess
from a version number. It runs the command as before; only if the CLI itself says it does not know a flag does it act, and only by the table:
- REQUIRED flags switch off what would let the CLI act on its own (its tools, MCP servers, user slash commands, user configuration and rules, a
  writable sandbox) or carry what the user asked for (the prompt, the output format, the chosen model). The bridge never runs without one. It stops
  and says which flag, which CLI version, and what to do.
- DROPPABLE flags only change what a CLI keeps on disk or how many turns it may take (`--no-session-persistence`, `--ephemeral`, `--max-turns`,
  `--skip-git-repo-check`). The bridge runs once more without the rejected flag, tells the user what that means, and remembers it for that program.

Status: the rejection wordings below are the usual ones of the argument parsers these CLIs use (commander, clap), written from knowledge of those
libraries, NOT copied from a run of either CLI. Which flags each CLI version really accepts is not recorded anywhere here, on purpose.
Which flags are droppable is a judgement (flagged in the pull request that added this): a longer droppable list means more old CLIs work and more
local traces; a shorter one means the reverse."""
import re

# (flag name, tokens placed on the command line, required, what dropping it means). The order is the command line's order.
CLAUDE_FLAGS = [
    ("-p", ("-p",), True, ""),
    ("--output-format", ("--output-format", "json"), True, ""),
    ("--tools", ("--tools", ""), True, ""),
    ("--strict-mcp-config", ("--strict-mcp-config",), True, ""),
    ("--disable-slash-commands", ("--disable-slash-commands",), True, ""),
    ("--no-session-persistence", ("--no-session-persistence",), False,
     "Claude Code may keep this conversation in its own history on this computer."),
    ("--max-turns", ("--max-turns", "1"), False,
     "Claude Code is not told to stop after one turn; its tools are still off, so it only may take longer."),
]
CLAUDE_TAIL = ("--system-prompt-file",)                      # takes the file path at build time; required

CODEX_FLAGS = [
    ("exec", ("exec",), True, ""),
    ("--json", ("--json",), True, ""),
    ("--sandbox", ("--sandbox", "read-only"), True, ""),
    ("--skip-git-repo-check", ("--skip-git-repo-check",), False,
     "Codex may refuse to run because the working folder is not a git repository; the run then fails with its own message."),
    ("--ephemeral", ("--ephemeral",), False, "Codex may keep a session file of this conversation on this computer."),
    ("--ignore-user-config", ("--ignore-user-config",), True, ""),
    ("--ignore-rules", ("--ignore-rules",), True, ""),
]

_REJECTION = re.compile(
    r"(?:unknown|unrecognized|unrecognised|unexpected|invalid|unsupported)\s+(?:option|flag|argument|arg|parameter)s?\b[:\s]*['\"`\u2018\u2019]?(-{1,2}[A-Za-z][\w-]*)",
    re.IGNORECASE)
_DASHLESS = re.compile(r"unknown\s+arguments?:\s*([A-Za-z][\w-]*(?:\s*,\s*[A-Za-z][\w-]*)*)", re.IGNORECASE)


def rejected_flags(stderr_text):
    """The flags a CLI's error text says it does not know, in order of first appearance, each once. [] when the text is not such a rejection. Pure."""
    text = str(stderr_text or "")
    found = []
    for match in _REJECTION.finditer(text):
        flag = match.group(1)
        if flag not in found:
            found.append(flag)
    for match in _DASHLESS.finditer(text):
        for name in re.split(r"\s*,\s*", match.group(1)):
            flag = "--" + name
            if flag not in found:
                found.append(flag)
    return found


ALWAYS_REQUIRED = ("--model", "--system-prompt-file")       # sent outside the tables above; the user chose the model and the prompt must arrive


def sort_rejected(flags, rejected):
    """(droppable names, required names, {name: consequence}) for the rejected flags this adapter actually sent. A rejected flag the adapter does not
    send is ignored; `--model` and `--system-prompt-file` count as required. Pure."""
    by_name = {name: (required, consequence) for name, _tokens, required, consequence in flags}
    droppable, required, notes = set(), [], {}
    for flag in rejected:
        if flag in ALWAYS_REQUIRED:
            required.append(flag)
            continue
        if flag not in by_name:
            continue
        is_required, consequence = by_name[flag]
        if is_required:
            required.append(flag)
        else:
            droppable.add(flag)
            notes[flag] = consequence
    return droppable, required, notes


def build(flags, skip=()):
    """The flag tokens of `flags` in order, leaving out the droppable ones named in `skip`. Raises ValueError when `skip` names a required flag. Pure."""
    skip = set(skip or ())
    required = {name for name, _tokens, req, _c in flags if req}
    if skip & required:
        raise ValueError(f"{sorted(skip & required)[0]} is required and cannot be left out.")
    tokens = []
    for name, group, _required, _consequence in flags:
        if name not in skip:
            tokens.extend(group)
    return tokens


def required_message(label, version, flag_names):
    """What to tell the user when a CLI does not know a safety flag. Pure."""
    shown = ", ".join(f"`{n}`" for n in flag_names)
    which = f" (version {version})" if version else ""
    return (f"Your {label}{which} does not know the option {shown}, which Cartogen AI needs to keep the CLI from acting on its own. "
            "It was not run. Update the CLI to a current version, or choose another connection in Settings.")


def dropped_message(label, version, flag_name, consequence):
    """What to tell the user when a droppable flag is left out. Pure."""
    which = f" (version {version})" if version else ""
    return f"Your {label}{which} does not know `{flag_name}`, so it is run without it. {consequence}".strip()
