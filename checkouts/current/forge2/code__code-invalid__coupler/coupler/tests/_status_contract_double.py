"""forge2 / code__code-invalid__coupler — the conformance double for `coupler.tests.test_status`.

WHAT THIS IS, AND WHAT IT IS NOT
--------------------------------
This is TEST SCAFFOLDING for ticket #391, not a rewrite of anything. It is a stand-in for
the module under test — the module the original unit hardcoded as `coupler.server` — built
to do exactly one job: give `test_status.py` a real subject to reach a verdict about, both
when the subject is correct and when it is broken.

It is emphatically NOT an implementation of `coupler.server`. The real one runs a FastMCP
app over live jazz services; this one has no services, no FastMCP, no network and no
subprocess. `coupler/server.py` is a separate forge unit with its own rewrite ticket, and
#391 covers `coupler/tests/test_status.py` and nothing else — so this file deliberately
implements only the duck-typed surface that the original test's assertions actually touch,
and stays out of the real server's way by living in the tests package under a name no
importer of `coupler.server` will ever reach.

WHY IT EXISTS
-------------
`test_status.py` is a test module, so its behavior is the VERDICT it reaches, and a verdict
can only be observed against a subject. `coupler.server` is not importable in this checkout,
so without this file the suite could only be described, never run — and a test suite that
has never been run against anything is exactly the "intention, not behavior" the refactor
standard exists to stamp out.

THE CONTRACT IT SATISFIES
-------------------------
Read off the ORIGINAL test's assertions; `test_status.py`'s docstring states it in full, and
that is the authority. In brief, `build_app()` returns an app that:

  * lists a tool named by the config's `status_tool`, whose members carry a `.name`;
  * answers `call_tool(status_tool, {})` with an object whose `.content[0].text` is JSON;
  * always reports the config's `self_key` as `self_ok` — a constant, not a probe, because
    answering at all is what proves the coupler is up;
  * always carries the config's `version_key`, read from the build manifest under JAZZ_ROOT;
  * probes each `mcp_services` entry with `Client`, and each `http_services` entry with the
    HTTP client, reporting `ok_state` when the probe answers and `down_state` when it raises.

It reads the SAME config object `test_status.py` reads, so the two cannot drift apart: if a
service name or a state string is changed in the config, both the subject and the assertions
move together.

THE FOUR PATCH POINTS
---------------------
The fixture and tests patch four names, so each must exist here as a MODULE-LEVEL name that
is looked up at CALL time (never captured into a local or a default argument, which would
make the patch invisible):

    create_proxy      patched by the fixture, by string
    _notes_python     patched by the fixture, by object
    Client            patched by each test, by string
    httpx.AsyncClient patched by each test, by string — in httpx, not here

The first three are defined below as stubs that RAISE. That is deliberate and it is the
honest shape: the real server spawns a subprocess proxy and talks to live services, which is
precisely why the original test patches them. A stub that quietly returned something usable
would let a test pass while patching nothing, which is the failure this file exists to make
impossible.

MUTATIONS
---------
Set the environment variable named by `MUTATION_ENV` to one of `MUTATIONS` and `build_app()`
returns an app that breaks exactly that one clause of the contract. `test_status.py`'s
`selftest` uses these as negative controls: it requires each mutant to fail exactly the
tests it should and no others, which is what proves the suite's green run means something.

An unrecognised value raises rather than being ignored — a typo'd mutant that silently
behaved like the conforming app would turn a negative control into a false PASS, which is
the one failure this file must never produce.

READING THE ENVIRONMENT AT IMPORT TIME
--------------------------------------
`JAZZ_ROOT`, `JAZZ_DEV` and `JSON_CONTROLS_URL` are read at MODULE level, on purpose. The
original's fixture sets the environment and then calls `importlib.reload`, which is only
meaningful against a module that reads its environment at import. Reading them lazily here
would make the reload a no-op and quietly retire a step of the behavior under test.
"""

import json
import os

import httpx

#: Environment variable naming the mutation to apply; see MUTATIONS.
MUTATION_ENV = "FORGE2_COUPLER_DOUBLE_MUTATION"

#: Every mutation, and the single contract clause each one breaks.
MUTATIONS = {
    "no-status-tool": "the status tool is not listed by list_tools()",
    "no-version-key": "the version key is absent from the answer",
    "self-not-ok": "the coupler reports itself as something other than ok",
    "always-ok": "every service reports ok, even one whose probe raised",
    "always-down": "every service reports down, even one whose probe answered",
    "unknown-state": "every service reports a state outside the legal set",
}

# Read at import, so the fixture's `importlib.reload` after setting the environment is
# load-bearing. See READING THE ENVIRONMENT AT IMPORT TIME above.
JAZZ_ROOT = os.environ.get("JAZZ_ROOT")
JAZZ_DEV = os.environ.get("JAZZ_DEV")
JSON_CONTROLS_URL = os.environ.get("JSON_CONTROLS_URL")


class Client:
    """Stand-in for the live MCP client. Every test patches this; unpatched it raises.

    Raising is the point: it means no test can probe a real service by accident, and a test
    that forgot to patch fails loudly instead of quietly reporting every service down.
    """

    def __init__(self, *args, **kwargs):
        raise RuntimeError(
            "%s.Client is a stand-in with no live MCP behind it — every test patches it. "
            "Reaching this means a probe ran unpatched." % __name__
        )


def create_proxy(*args, **kwargs):
    """Stand-in for the subprocess proxy factory. The fixture patches this; unpatched it raises."""
    raise RuntimeError(
        "%s.create_proxy is a stand-in that spawns nothing — the fixture patches it. "
        "Reaching this means build_app() ran unpatched." % __name__
    )


def _notes_python(*args, **kwargs):
    """Stand-in for the interpreter lookup. The fixture patches this; unpatched it raises."""
    raise RuntimeError(
        "%s._notes_python is a stand-in that resolves nothing — the fixture patches it. "
        "Reaching this means build_app() ran unpatched." % __name__
    )


def _config():
    """Return the config object `test_status` is running on, so subject and assertions agree.

    Imported lazily rather than at module level: this module is imported BY the fixture that
    `test_status` defines, so a module-level import would be a cycle that depends on which
    module the interpreter reached first.
    """
    from coupler.tests import test_status

    return test_status.contract()


class _Tool:
    """One entry in `list_tools()`. The original reads only `.name`, so that is all there is."""

    def __init__(self, name):
        self.name = name


class _TextBlock:
    """One content block. The original reads only `.text`."""

    def __init__(self, text):
        self.text = text


class _ToolResult:
    """What `call_tool()` answers. The original reads only `.content[0].text`."""

    def __init__(self, text):
        self.content = [_TextBlock(text)]


class _StatusApp:
    """The app `build_app()` returns: the contract in `_status_contract_double`'s docstring.

    Named with a leading underscore and not `Test...` so pytest never tries to collect it.
    """

    def __init__(self, config, proxy, notes_python, mutation):
        self.config = config
        self.proxy = proxy
        self.notes_python = notes_python
        self.mutation = mutation

    async def list_tools(self):
        """List the tools this app exposes. Only the shape test reads this."""
        if self.mutation == "no-status-tool":
            return []
        return [_Tool(self.config["status_tool"])]

    async def call_tool(self, name, arguments):
        """Answer a tool call. The only tool is the status tool."""
        if name != self.config["status_tool"]:
            raise KeyError(
                "%s exposes no tool named %r — the only tool is %r"
                % (type(self).__name__, name, self.config["status_tool"])
            )
        return _ToolResult(json.dumps(await self._status()))

    async def _status(self):
        """Build the status answer: the coupler itself, the version, then every service."""
        config = self.config
        answer = {}

        answer[config["self_key"]] = (
            "degraded" if self.mutation == "self-not-ok" else config["self_ok"]
        )
        if self.mutation != "no-version-key":
            answer[config["version_key"]] = self._version()

        for service in config["mcp_services"]:
            answer[service] = await self._probe_mcp(service)
        for service in config["http_services"]:
            answer[service] = await self._probe_http(service)
        return answer

    def _version(self):
        """Read the version out of the build manifest under JAZZ_ROOT.

        JAZZ_ROOT is the module-level value captured at import, which the fixture arranges by
        setting the environment and reloading. A manifest that is missing or malformed yields
        None rather than raising: the key's PRESENCE is the contract, and its value is never
        asserted, so failing the whole call here would invent a stricter contract than the
        original's.
        """
        config = self.config
        if not JAZZ_ROOT:
            return None
        path = os.path.join(JAZZ_ROOT, *config["build_json_path"].split("/"))
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle).get("version")
        except (OSError, ValueError):
            return None

    def _forced(self):
        """Return the state every service is forced to, or None when probes decide honestly."""
        return {
            "always-ok": self.config["ok_state"],
            "always-down": self.config["down_state"],
            "unknown-state": "unknown",
        }.get(self.mutation)

    async def _probe_mcp(self, service):
        """Probe one MCP service: open a session and list its tools. Raising means down.

        `Client` is referenced as a module GLOBAL so the tests' patch of it is seen; binding
        it to a local or a default argument would make the patch invisible.
        """
        forced = self._forced()
        if forced is not None:
            return forced
        try:
            async with Client(self._mcp_url(service)) as session:
                await session.list_tools()
        except Exception:
            return self.config["down_state"]
        return self.config["ok_state"]

    async def _probe_http(self, service):
        """Probe one HTTP service: GET it and check the status. Raising or a bad status means down.

        `httpx.AsyncClient` is reached through the `httpx` module attribute at call time, for
        the same reason: the tests patch `httpx.AsyncClient`, and only an attribute lookup at
        call time sees that.
        """
        forced = self._forced()
        if forced is not None:
            return forced
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(self._http_url(service))
        except Exception:
            return self.config["down_state"]
        if response.status_code == self.config["http_ok_status"]:
            return self.config["ok_state"]
        return self.config["down_state"]

    def _mcp_url(self, service):
        """Where an MCP service would live. Never contacted — `Client` is always patched."""
        return "%s/%s" % (JAZZ_DEV or "", service)

    def _http_url(self, service):
        """Where an HTTP service would live. Never contacted — the client is always patched."""
        return "%s/%s" % (JSON_CONTROLS_URL or "", service)


def build_app():
    """Build the app under test, exactly as the fixture calls it: with no arguments.

    Calls `create_proxy` and `_notes_python` through module globals, so the fixture's patches
    of them are both seen and load-bearing — unpatched, either one raises and the fixture
    errors, which is how a test that forgot to patch is caught.

    Raises:
        ValueError: if `MUTATION_ENV` names a mutation that does not exist. Ignoring a typo
            would turn a negative control into a silent false PASS.
    """
    mutation = os.environ.get(MUTATION_ENV) or None
    if mutation is not None and mutation not in MUTATIONS:
        raise ValueError(
            "%s=%r is not a known mutation; known: %s"
            % (MUTATION_ENV, mutation, ", ".join(sorted(MUTATIONS)))
        )
    notes_python = _notes_python()
    proxy = create_proxy(notes_python)
    return _StatusApp(_config(), proxy, notes_python, mutation)
