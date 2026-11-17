*This project has been created as part of the 42 curriculum by spujol-s, vvan-ach and sasanche.*

# Agent Smith

An autonomous agent that reasons, writes Python code, executes it inside a secure sandbox and iterates on the results to solve programming tasks (MBPP) and real-world software engineering issues (SWE-bench).

---

## Description

**Agent Smith** is a code-based agentic framework written in Python 3.10, built without any agent orchestration library. Instead of JSON tool calling, the LLM answers with Python code blocks that follow a **Thought → Code → Observation** loop: it reasons about the task, writes code that calls tools as regular Python functions, reads the execution output and refines its solution until it calls `final_answer(...)`.

The project has three main parts:

- **Sandbox:** a configurable execution boundary that restricts what LLM-generated code can do (imports, filesystem, network, time and memory).
- **MCP tool servers:** `mcp_tools_mbpp.py` and `mcp_tools_swebench.py`, exposing the tools the agent needs through the Model Context Protocol.
- **Agents:** `agent_mbpp.py` and `agent_swebench.py`, which drive the loop for each benchmark.

---

## System Architecture

> **Status:** *Pending: will be completed together with the agent loop.*

```
+--------------------------------------------------------------+
|                      Agent orchestrator                      |
|        LLM client · system prompt · code extraction          |
+------------------------------+-------------------------------+
                               | code to execute
                               v
+--------------------------------------------------------------+
|                SandboxRunner (parent process)                |
|   AST validation · timeout supervision · tool-call relay     |
|                              |                               |
|               pipe (stdout, stderr, tool calls, result)      |
|                              v                               |
|   +------------------------------------------------------+   |
|   |               Child process (per run)                |   |
|   |  memory limit · allowlisted builtins · guarded open  |   |
|   |  guarded __import__ · network blocked · exec(code)   |   |
|   +------------------------------------------------------+   |
+------------------------------+-------------------------------+
                               | MCP tool calls (stdio / HTTP)
                               v
+--------------------------------------------------------------+
|                         MCP server(s)                        |
|      MBPP: run_tests · SWE-bench: files, search, git, tests  |
+--------------------------------------------------------------+
```

The sandbox and the MCP tools are independent security domains: the sandbox restricts what the generated Python code can do, while MCP tool actions run outside it. On SWE-bench, the tools do not touch the host's files: every action is a command (`cat`, `grep`, `find`, `git`...) executed with `docker exec` inside the task's container (see [SWE-bench](#swe-bench-mcp_tools_swebenchpy)).

---

## Agent Loop Explanation

> **Status:** *Pending: will be detailed once the MBPP and SWE-bench agents are finished.*

- **Thought:** the LLM analyzes the task, previous outputs and errors.
- **Code:** the LLM writes a Python code block, which is extracted from its response.
- **Observation:** the sandbox executes the code and returns `stdout`, `stderr` and any error (including timeouts and security violations) to the LLM.
- **Termination:** the loop ends when the code calls `final_answer(...)` or when the iteration, token or time limits are reached.

---

## Sandbox Design

The sandbox is the safety boundary between untrusted LLM-generated code and the system. It is configured with a Pydantic model (`SandboxConfig`) that can be loaded from a JSON file (`sandbox_template.json`):

| Field | Default | Purpose |
|---|---|---|
| `authorized_imports` | `math`, `collections.*`, `re`, `json`... | Module allowlist (`pkg.*` also allows submodules) |
| `allowed_directories` | `/testbed`, `/tmp/agent` | Directories the code may access |
| `max_execution_time_seconds` | `30` | Execution timeout |
| `max_memory_mb` | `512` | Memory the code may allocate |

### Security layers

1. **Static analysis (AST), before any execution.** The code is parsed and rejected with a `SecurityError` if it contains:
   - imports of modules outside `authorized_imports`, or relative imports;
   - direct calls to dynamic-execution or reflection functions (`eval`, `exec`, `compile`, `__import__`...);
   - access to dunder attributes or names (`obj.__class__`, `__subclasses__`, `__globals__`, `__builtins__`...), except a small allowlist of harmless ones such as `__init__` or `__name__`;
   - access to frame and code introspection attributes (`gi_frame`, `f_back`, `f_globals`, `tb_frame`...), which can be used to climb the call stack up to the runner's real builtins.

   A syntax error is not raised to the caller: it is returned as a failed execution so the LLM can fix it.

2. **Allowlisted builtins (`BuiltinsGuard`).** The `__builtins__` of the sandboxed code is built from an empty dictionary and only receives an explicit list of safe builtins, the builtin exception classes and `__build_class__` (needed by `class` statements). Everything else does not exist inside the sandbox, including `getattr`, `setattr`, `delattr`, `globals`, `locals`, `vars`, `eval`, `exec`, `compile`, `input` and `breakpoint`. Two builtins are replaced by guarded versions:
   - `__import__` checks every runtime import against the same allowlist as the AST validator, so the restriction does not depend on static analysis alone. It also returns a **restricted copy** of the module instead of the real one: without private names (`_os`) and without references to unauthorized modules. Authorized modules import other modules internally (`random` keeps `os` as `random._os`, `typing` keeps `sys`), and the real module would let the code reach them (`random._os.system(...)`). Authorized submodules (`collections.abc`) are copied the same way. Functions keep working, because they still use their original module internally;
   - `open` goes through `FileSystemGuard`.

3. **Filesystem restriction (`FileSystemGuard`).** Paths are resolved with `Path.resolve()`, which normalizes `..` and follows symlinks, and are accepted only if they are inside one of the `allowed_directories` (`Path.is_relative_to`). Anything else raises a `SecurityError`.

4. **Network restriction (`NetworkGuard`).** `socket` is not in the default import allowlist, so it cannot be imported. As a second layer, `socket.socket` is replaced during execution by a function that raises `SecurityError`.

5. **Process isolation, memory limit and timeout.** Each `SandboxRunner.run()` forks a new child process to execute the code:
   - **Memory:** the child applies `resource.setrlimit(RLIMIT_AS, ...)` to itself, so the limit never affects the agent. `RLIMIT_AS` limits virtual address space, not resident RAM. The forked child already maps the interpreter and everything the agent imported, so the limit is that baseline plus `max_memory_mb`: the code itself can allocate at most `max_memory_mb`. Exceeding it produces a `MemoryError` that is reported to the LLM.
   - **Timeout:** the parent waits for the child with a deadline and kills it (`process.kill()`) when it expires. We did not use `signal.alarm`/`SIGALRM` because:
     - it only works in the main thread, while the MCP server may run tools in worker threads;
     - Python only runs signal handlers between bytecodes, so a long operation in C (e.g. `10 ** 10 ** 8`) is not interrupted;
     - the `TimeoutError` it raises is an `Exception`, so the sandboxed code could catch it with `except Exception` and keep running.
   - **Side effects:** the code cannot corrupt the agent's state, and patching `socket.socket` only affects the child, so the agent can keep using the network (LLM API, MCP over HTTP) while code runs.

6. **Results (`ExecutionResult`).** The child streams its `stdout` and `stderr` to the parent through a pipe as they are written, so the partial output is kept when the code times out. The result is an immutable dataclass with `success`, `stdout`, `stderr`, `error`, `result_env`, `is_finished` and `final_answer_value`. `result_env` holds the final variables of the execution namespace; only picklable values can be sent back, so modules and functions defined by the code are dropped. Every error caused by the code (syntax errors, `SecurityError`, exceptions, timeouts, memory errors) is **returned** in `error`, never raised, so the agent loop can show it to the LLM. Only `KeyboardInterrupt` and `SystemExit` are propagated, so they reach the agent loop, as the subject requires.

### Known limitations and trade-offs

- **The in-process restrictions can be bypassed with strings.** The AST validator only sees attribute names written in the code. Allowed modules can still access attributes by name at run time: for example, `operator.attrgetter("__class__")`, or a format string such as `"{0.__class__}".format(x)`. Removing `getattr` closes the most direct route, but not these. Escapes through authorized modules (`random._os`, `typing.sys`) are closed by the restricted module copies.
- **Process isolation is what limits the damage.** Pure-Python sandboxes (`exec` with restricted globals) are known to be bypassable, so the child process is the real boundary. Even if code escapes the Python-level restrictions, it is still limited in memory and time, is killed at the end of each run and shares no state with the agent. Stronger isolation (seccomp, namespaces, containers) would require tools outside the standard library, which the subject does not allow.
- **`fork` start method.** It makes each run start in a few milliseconds and avoids serializing the sandbox configuration, but it is Unix-only, like `resource`.

---

## Tool Implementation Details

Tools are served by MCP servers and exposed inside the sandbox as regular Python functions. The sandbox owns the MCP client: `SandboxRunner(mcp_stdio="python mcp_tools_mbpp.py")` (or `mcp_url=...`) connects when used as a context manager (`with SandboxRunner(...) as runner:`), and closes the connection at the end. When the sandboxed code calls a tool, the child process sends the call to the parent through the pipe, the parent runs it through the MCP client and sends back the result. Tools therefore run outside the sandbox limits, and the sandbox timeout does not count the time spent in them.

`runner.manual` describes every available function for the LLM's system prompt: tools with Python-style signatures built from their JSON Schema (`read_file(filepath: str, start_line: int, end_line: int) -> str`), plus the server's resources (`read_resource(uri)`) and prompts (`get_prompt(name, **arguments)`), if any. Only the first line of each docstring is used, to keep the prompt short.

- **`final_answer(answer)`:** provided by the sandbox itself, not by an MCP server, and always available. It stops the execution at once (even inside `try`/`except Exception`), and the result has `is_finished=True` and `final_answer_value` set, which tells the agent loop that the task is complete.

### MBPP (`mcp_tools_mbpp.py`)

- **`run_tests(candidate_code, test_list, test_imports=None)`:** joins the test imports, the candidate code and the assertions, and executes them with `SandboxRunner`, so the import allowlist and the timeout also apply to the tests. It always returns a message: success, the assertion error or traceback, a timeout, or a `SecurityError`.

### SWE-bench (`mcp_tools_swebench.py`)

| Tool | Behavior |
|---|---|
| `read_file(filepath, start_line, end_line)` | Returns the requested lines in `cat -n` style: `<line_number>: <line_content>` |
| `edit_file(filepath, old_str, new_str)` | Replaces an exact string in a file |
| `list_files(directory, pattern)` | Lists the files (not subdirectories) directly inside a directory that match a glob pattern, sorted by name |
| `search_code(pattern, file_pattern)` | grep-like search: `/absolute/path.py:<line_number> <line_content>` |
| `search_function_or_class_definition_in_code(name)` | Finds `def` / `class` definitions, same output format |
| `find_references(name, filepath, line)` | Finds usages of a symbol (whole-word match), same output format |
| `run_command(command, workdir)` | Runs a shell command (60 s timeout) and returns exit code, stdout and stderr |
| `get_patch()` | Returns `git diff` of the current changes |
| `run_tests()` | Runs `SWE_BENCH_TEST_CMD`, `/eval.sh` or `pytest` (300 s timeout) |

**Execution in the task container.** On SWE-bench the repository lives inside a Docker container, while the sandbox and the MCP server run on the host. The tools therefore never use Python file operations: each one builds a command, and a single function, `_exec`, decides where it runs. If the `SWE_CONTAINER` environment variable is set, the command is run with `docker exec` inside that container (working directory `/testbed`); otherwise it runs locally. The MCP server does not inherit the agent's environment, so the variable is passed explicitly: `SandboxRunner(mcp_stdio=..., mcp_env={"SWE_CONTAINER": name})`.

- **Path validation:** every tool that receives a path resolves it with `realpath` **where the commands run**, so a symlink or `..` inside the container is resolved correctly, and returns an error if it is outside the allowed directories. Searches also validate their root directory.
- **No command injection:** paths and patterns are always passed as separate arguments, never inside a shell script. `edit_file` writes with `sh -c 'cat > "$1"' sh <path>` and the new content through stdin, so a file named `a; rm -rf /testbed` is just a file name. Patterns go after `-e` and paths after `--`, so a value starting with `-` is never read as an option.
- **Output truncation:** outputs longer than 10,000 characters keep their start and end, with a note asking the LLM to narrow the command, the search or the line range. This protects the LLM's context, for example from a full test suite output. `get_patch` is never truncated, because the patch is the final answer.
- **`run_command` runs any shell command:** validating `workdir` does not restrict what the command itself can do. This is acceptable because MCP tool actions are outside the sandbox's security domain, and on SWE-bench they run inside the task's container.

---

## Instructions

### Requirements

- Python 3.10
- [`uv`](https://docs.astral.sh/uv/)
- Linux or macOS (the sandbox uses `fork` and the `resource` module)

### Installation

```bash
git clone <repository-url>
cd agent_smith
make install        # runs `uv sync`
```

### API keys

API keys are read from environment variables, never from the source code:

```bash
export OPENROUTER_API_KEY="your-api-key"
```

### Sandbox

`uv run sandbox` opens an interactive console where every snippet runs inside the sandbox:

```bash
make run                                               # = uv run sandbox sandbox_template.json
uv run sandbox                                         # ./sandbox_template.json (created with defaults if missing)
uv run sandbox path/to/config.json                     # custom configuration
uv run sandbox --mcp-stdio "python mcp_tools_mbpp.py"  # start an MCP server and expose its tools
uv run sandbox --mcp-server http://localhost:8000/mcp  # connect to a running MCP server
uv run sandbox --help
```

The console prints the manual of the available functions. Type one or more lines and an **empty line** to run them. Each snippet runs in a fresh sandbox, exactly like each step of the agent, so imports and definitions must be in the same snippet as the code that uses them. `exit`, `quit` or Ctrl+D leave; Ctrl+C stops a running snippet without closing the console.

```
>>> import math
... print(math.sqrt(16))
...
4.0
>>> import os
...
SecurityError: Unauthorized import detected: 'os' (line 1)
```

### Agents

*Pending: usage of `agent_mbpp.py` and `agent_swebench.py`.*

### Tests and code quality

```bash
make test           # pytest
make lint           # flake8 + mypy
make lint-strict    # flake8 + mypy --strict
make clean          # remove caches and the virtual environment
```

---

## Benchmark Results and Analysis

> **Status:** *Pending: the full report will be in [`BENCHMARK_REPORT.md`](BENCHMARK_REPORT.md).*

| Benchmark | Model | Tasks solved | Avg. iterations | Avg. tokens (in / out) |
|---|---|---|---|---|
| MBPP | — | — | — | — |
| SWE-bench | — | — | — | — |

---

## Resources

### References

- Wang et al., *Executable Code Actions Elicit Better LLM Agents* (CodeAct), 2024: <https://arxiv.org/abs/2402.01030>
- Austin et al., *Program Synthesis with Large Language Models* (MBPP), 2021: <https://arxiv.org/abs/2108.07732>
- Jimenez et al., *SWE-bench: Can Language Models Resolve Real-World GitHub Issues?*, 2023: <https://arxiv.org/abs/2310.06770>
- Model Context Protocol specification: <https://modelcontextprotocol.io/>
- MCP Python SDK: <https://github.com/modelcontextprotocol/python-sdk>
- Python documentation: [`ast`](https://docs.python.org/3.10/library/ast.html), [`multiprocessing`](https://docs.python.org/3.10/library/multiprocessing.html), [`resource`](https://docs.python.org/3.10/library/resource.html), [`builtins`](https://docs.python.org/3.10/library/builtins.html)
- Hugging Face *smolagents* documentation, read as a reference for code agents (not used as a dependency, as the subject requires): <https://huggingface.co/docs/smolagents>

### Use of AI
- **Code review of the sandbox:** finding bugs and bad practices, such as imports failing inside the sandbox, the runner failing on `pkg.*` patterns, MBPP tests executed without the sandbox, and SWE-bench tools without path validation.
- **Sandbox design discussion:** the trade-offs between in-process `exec` and a child process, the builtins allowlist, the AST checks against sandbox escapes, and how to apply memory limits without affecting the agent.
- **MCP integration:** understanding the MCP SDK, the synchronous facade over its asynchronous client, and generating the tool manual from JSON Schema.
- **SWE-bench container execution:** the design of running the tools through `docker exec`, path validation inside the container and avoiding command injection.
- **Testing:** test design (fixtures, `parametrize`, a fake `docker` executable to test container mode without Docker).
- **Documentation:** help structuring and reviewing this README.