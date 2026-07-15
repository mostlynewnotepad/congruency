#!/usr/bin/env python3
"""deployed_app_registry.py — the DEPLOYED-app registry: the ONLY allowlist that exempts a checkout
from reaping. Registered deployed code may live outside the forge indefinitely; everything else is
reapable (ticket #219).

THE RULE, quoted from ticket #219, which is its only source in this repository (nothing else here
defines it — do not go looking, and see THE REAPER DOES NOT EXIST YET): "The registry of code
allowed to live OUTSIDE the forge indefinitely: deployed production apps/utilities/scripts. A
checkout is exempt from reaping ONLY if it is registered here (path -> {name, kind=app|utility|
script, deployed=true}). Registration is a deliberate, auditable act (control-config object).
Everything not registered and not actively leased is reapable. ACCEPTANCE: a registered deployed app
is never reaped; removing it from the registry makes it reapable next cycle; the registry is the
single source of truth for 'code allowed to persist outside forge'."

  !! THIS ONE IS NOT NUMBERED, AND THAT IS DELIBERATE. Its siblings are: tools/clean_recheckout.py
  is "POLICY 1" (ticket #214's numbering) and tools/ban_editable_installs.py is "POLICY 2" (#215's).
  Ticket #219 assigns itself no number, so this file invents none — a number nothing in the repo
  grants would be a claim with no source. It is referred to throughout as THE REGISTRY RULE, and the
  siblings are cited by their full name. (pair_loop.py's own policies (1)/(2)/(3) are a third,
  unrelated numbering — branch naming/lifecycle/etc., pair_loop.py:39-43.)

TERMS, each defined at first use, because whoever reads this file did not watch it being written:

  * A CHECKOUT is a working tree on disk: real files you can open. It is the thing that gets reaped.
  * THE FORGE is the mirror store: 262 BARE git repositories under `config/forge/remotes/*.git`
    ("forge repo — a bare git repository under config/forge/remotes/*.git (the forge's mirror
    store). 'Bare' = no working tree", forge_refactor_ticketer.py:19-21). Bare means no working
    tree, so code IN the forge is not a checkout at all. OUTSIDE THE FORGE therefore means exactly
    what it says: a checkout, materialized on disk, living somewhere a reaper can see it.
  * To REAP a checkout is to delete it. REAPABLE means "a reaper is permitted to delete this";
    EXEMPT means "a reaper is forbidden to delete this". This file decides which, and does neither.
  * A REGISTRATION is one entry in the config object below: a path mapped to {name, kind, deployed}.
    Registration is what buys indefinite life outside the forge.
  * A LEASE is a TEMPORARY permission to exist, held by something actively using a checkout. It is
    the ticket's other exemption ("not registered AND not actively leased"). It is orthogonal to
    registration: a lease expires, a registration does not. See THE LEASE HALF — no lease store
    exists in this repository, so leases are an INPUT here, never invented.
  * A CONTROL-CONFIG OBJECT is this repository's FORGE-wide refactor standard #200, requirement 4:
    "NO hardcoded paths or params. A JSON/registry config object drives it ... a tool that cannot
    see its config THROWS rather than guessing a default" (quoted at forge2/.../coupler/_config.py:
    8-11). The registry of deployed apps IS that config object: it lives in registry.json, and it is
    the single source of truth this ticket asks for.

THE REAPER DOES NOT EXIST YET — READ THIS BEFORE LOOKING FOR IT. Ticket #219 names "the reaper" and
"actively leased" as if both were built. In this repository, as of this commit, NEITHER IS:

  * There is no checkout-reaper. `grep -rniE '\\breap' ` over the tree finds only pair_loop.py's
    WORKTREE reap — a different reaper with a different job: it removes the EPHEMERAL git worktree a
    pair worked in, once the ticket settles ("the WORKTREE is ephemeral: reaped on a successful
    merge (#216)", pair_loop.py:67; the implementation is `reap_worktree`, pair_loop.py:585). That
    reaper deletes a worktree it created minutes earlier; it knows nothing of deployed apps and
    consults no allowlist. It is NOT the reaper this ticket means, and this file does not change it.
  * There is no lease store. `grep -rniE '\\blease'` over the repository's python and SQL finds
    ZERO hits outside vendored third-party code.

So this file is the half that ticket #219 actually asks for and that CAN be built: the ALLOWLIST,
plus the VERDICT ORACLE a reaper calls to obey it (`decide()`, and `check` on the command line). The
reaper, when it is built, honors this rule by asking this module and deleting nothing it calls
EXEMPT. Nothing here is written as though that reaper already exists.

WHY THIS TOOL DOES NOT REGISTER ANYTHING — it is the answer to "deliberate and auditable". There is
no `register` subcommand, and its absence is the feature. Registration is an edit to registry.json:
a config change that is reviewed, committed, blamed and diffable. That is what makes it deliberate
(a human decided) and auditable (git says who, when and why, forever). A `register` subcommand would
let any process silently buy a checkout permanent immunity from the reaper, which is precisely the
act that most needs a reviewer. `emit-config` prints a template to paste; a human installs it.

  A CONSEQUENCE, STATED PLAINLY: this tool CREATES NO FILES and WRITES NOTHING in normal operation.
  Every subcommand opens registry.json for reading and prints. The only write anywhere in this file
  is bug_report(), on an UNEXPECTED INTERNAL FAULT (exit 2) — the repository's standard Variant-A
  sink. Read that "unexpected" strictly: the two things a user can do wrong — a usage error, and
  pointing --root somewhere with no registry.json (RegistryNotFound) — are REFUSALS, not faults.
  They print one line, file NO report, and create NO file. --selftest proves both claims in
  isolation: check [17] lists the directory before/after six runs, and check [19] snapshots THIS
  repository's real bug_reports sink around the gate run.

WHAT MAKES A REGISTRATION VALID — and, just as importantly, what does NOT. Exemption requires
exactly the three keys ticket #219 names, and NOTHING MORE:

    "<path>": {"name": "<name>", "kind": "app"|"utility"|"script", "deployed": true}

  * `name` must be a non-empty string. `kind` must be exactly one of app/utility/script — the three
    the ticket lists. `deployed` must be the JSON literal `true` (the boolean), not the STRING
    "true": a string is a different value, and "deployed": "false" is a non-empty string that would
    be truthy in python, which is exactly how a de-registered app would get silently re-exempted.
    This file compares `is True`, so that cannot happen.
  * NO OTHER KEY IS REQUIRED. The optional audit fields (`registered_by`, `ticket`, `reason`,
    `registered_on`) are read, printed by `list`/`check`, and NEVER gate the exemption. This is a
    deliberate reading of ACCEPTANCE 1 ("a registered deployed app is never reaped"): a registration
    written exactly as #219 spells it must be exempt, so requiring a field #219 does not name would
    break the acceptance it is meant to serve. Auditability comes from the config object being a
    reviewed, committed, diffable artifact — not from extra mandatory keys. (This is where the rule
    departs from POLICY 2, whose `reason` IS mandatory: #215's ticket names "--dev-debug --reason"
    explicitly, and a WAIVER of a ban is not the same act as a REGISTRATION under a rule.)
  * A malformed entry does NOT exempt. It is reported as not-a-registration, with the reason, so an
    operator whose exemption stopped working is told why instead of guessing. The failure lands on
    the reapable side because #219's default answer is "reapable" — but note that this file only
    ever RETURNS that verdict, so a malformed entry costs a printed refusal, never a deletion.

REGISTRY-FILE GATE vs ABSENT SECTION — these are two different things, and conflating them would
break the ticket. The registry FILE (registry.json) not being findable is a fault: this module
THROWS at import, per #200 requirement 4, exactly as its siblings do (`ROOT, REGISTRY =
find_registry(...)`, ban_editable_installs.py:227, clean_recheckout.py:201, pair_loop.py:168). But
an ABSENT `deployed_apps` SECTION is not a fault — it is the meaningful, correct state "nothing is
registered", whose answer is "everything is reapable". That IS ACCEPTANCE 2: removing an app from
the registry makes it reapable next cycle, and removing the last one empties the section. Treating
that as a crash would make de-registration impossible. This mirrors POLICY 2's `Phases`, which reads
an absent section as "no package is in dev-phase" (ban_editable_installs.py:611-613).
(As of this commit the repository's registry.json has NO `deployed_apps` section, so the answer here
is "nothing is registered, everything is reapable" — the correct answer, not an error.)

WHAT A REGISTRATION PROTECTS — the path, and everything under it. If "/srv/pay" is registered, then
"/srv/pay" and "/srv/pay/lib/db.py" are both EXEMPT, because reaping something inside a deployed app
destroys the deployed app, and ACCEPTANCE 1 says it is never reaped. Containment is matched on
canonical paths with a separator guard, so "/srv/payroll" is NOT under "/srv/pay" — a prefix match
on raw strings would say it was, and would wrongly exempt an unrelated checkout. Symlinks and
macOS's /var -> /private/var are resolved on both sides before comparing (the same realpath trap
ban_editable_installs.py:1735-1737 documents), so two spellings of one directory match.

THE LEASE HALF — why leases are an input and not a lookup. #219 says reapable = NOT registered AND
NOT actively leased. This file owns the first half authoritatively and CANNOT own the second: no
lease store exists (see THE REAPER DOES NOT EXIST YET). Inventing one would be inventing a source of
truth the ticket did not ask for, and would contradict "the registry is the single source of truth".
The two are different claims and stay different here:

  * the REGISTRY answers "may this code persist outside the forge INDEFINITELY?" — permanent, and
    #219 makes this file the single source of truth for it;
  * a LEASE answers "is someone using this RIGHT NOW?" — temporary, and whoever holds leases knows.

So a caller passes the leases it holds (`--leased <path>`, repeatable; `decide(..., leases=[...])`)
and this module combines the halves. A verdict distinguishes them: an EXEMPT checkout is registered;
a LEASED checkout is merely not-reapable-right-now and would become reapable when its lease drops.
With no leases passed — the default — the answer is the pure registry answer.

EXIT CODES (the CLI's whole contract):
    0  the rule permits persistence — `check` says EXEMPT (registered) or LEASED (not reapable now);
       `list`, `sweep` and `emit-config` completed; `--selftest` passed.
    2  UNEXPECTED — a Variant-A bug report was filed to the registry's bug_reports sink
       (note-for-claude: filename, function, time-of-occurance, methods-to-reproduce, possible-cause).
       Also the two REFUSALS, which file NO bug report and print no traceback, because neither is a
       fault: argparse's own exit for a USAGE error (a missing path, an unknown subcommand), and the
       config gate (`--root` pointed somewhere with no registry.json — "REFUSING: registry.json not
       found ...", see RegistryNotFound).
    3  REAPABLE — `check` on a checkout the rule does not protect: not registered (or registered
       malformed), and not leased. A reaper may delete it. Nothing is deleted by this tool.

USAGE (python only, per note-for-claude; registry-gated — a tool that cannot see registry.json throws):
    python3 deployed_app_registry.py list                        # the allowlist, as configured
    python3 deployed_app_registry.py list --json
    python3 deployed_app_registry.py check /srv/pay              # exit 0 EXEMPT, exit 3 REAPABLE
    python3 deployed_app_registry.py check /srv/tmp --leased /srv/tmp
    python3 deployed_app_registry.py sweep /srv                  # a reaper's worklist over a dir
    python3 deployed_app_registry.py sweep /srv --json --leased /srv/tmp
    python3 deployed_app_registry.py emit-config                 # a template to paste into registry.json
    python3 deployed_app_registry.py --selftest                  # proves the ACCEPTANCE, touches nothing
    python3 deployed_app_registry.py --root /path/to/repo list   # use another repo's registry.json
"""
import argparse
import json
import os
import sys
import time
import traceback


# ── registry gate (note-for-claude: "if a tool cannot see the registry it will throw an exception") ──
class RegistryNotFound(RuntimeError):
    """No registry.json above the starting directory — the #200 requirement-4 gate firing.

    This is a REFUSAL, not a fault, and the distinction is why this class exists. The tool was
    pointed somewhere that has no config; the correct answer is a one-line "I cannot see my config",
    exactly as a usage error is. It is deliberately NOT reported as a bug: bug_report() writes to
    the registry's shared `bug_reports` sink, and filing a report there for an expected refusal
    would (a) pollute a sink other tools read for REAL faults with entries that are nobody's bug,
    and (b) make this tool CREATE A FILE on a path its docstring promises creates none. Both were
    observed before this class existed — `--selftest`'s --root gate check filed a report into the
    repository's own logs/bug_reports.jsonl. Check [19] now asserts it does not.
    """


def find_registry(start):
    """Walk UP from `start` for registry.json; return (its directory, the parsed document).

    The walk starts at a FILE's directory, never at the working directory, so which directory you
    run this tool from never changes which config is found. Raises RegistryNotFound if none exists.
    """
    d = os.path.abspath(start)
    while True:
        p = os.path.join(d, "registry.json")
        if os.path.isfile(p):
            with open(p) as fh:
                return d, json.load(fh)
        nxt = os.path.dirname(d)
        if nxt == d:
            raise RegistryNotFound("registry.json not found walking up from %s — refusing to run"
                                   % start)
        d = nxt


# The gate fires at IMPORT, exactly as pair_loop.py's does (ROOT, REGISTRY = find_registry(...),
# pair_loop.py:168), as clean_recheckout.py's does (:201) and as ban_editable_installs.py's does
# (:227): a tool that cannot see its registry throws rather than guessing. --root only chooses WHICH
# repo's config is read; it never disables this gate.
ROOT, REGISTRY = find_registry(os.path.dirname(os.path.abspath(__file__)))

#: Where this rule's config object lives inside the registry document. This is the rule's ADDRESS in
#: the config, not a configurable setting — a config-driven tool has to know which section is its own.
SECTION = "deployed_apps"

#: The three kinds ticket #219 names, and the only ones that register. Anything else is not a kind.
KINDS = ("app", "utility", "script")

#: Verdict states. EXEMPT and LEASED are not reapable; REAPABLE is.
EXEMPT = "EXEMPT"
LEASED = "LEASED"
REAPABLE = "REAPABLE"


def bug_report(root, reg, fn, exc, repro):
    """Variant-A bug report to the registry's bug_reports sink — the five fields note-for-claude
    names. Best-effort and fully defensive: a tool must never fail because its bug reporter did.

    Defensive on purpose, and not theoretically: `bug_reports` is a registry key, so its value is
    whatever the registry says. A non-string there (a dict, a list, None) makes os.path.join raise
    INSIDE this handler and replaces the original exception with a confusing one. The sink
    resolution is type-checked and everything below it is wrapped.
    """
    try:
        sink = (reg or {}).get("bug_reports", "logs/bug_reports.jsonl")
        if not isinstance(sink, str):
            sink = "logs/bug_reports.jsonl"
        path = os.path.join(root, sink)
        frames = traceback.extract_tb(exc.__traceback__)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a") as fh:
            fh.write(json.dumps({
                "filename": os.path.basename(__file__),
                "function": (frames[-1].name if frames else fn) or fn,
                "time-of-occurance": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "methods-to-reproduce": repro,
                "possible-cause": "%s: %s" % (type(exc).__name__, exc),
                "traceback": traceback.format_exc().splitlines()[-6:],
                "note": "DEPLOYED-app registry (the reaper's only allowlist) — ticket #219",
            }) + "\n")
        return path
    except Exception:  # noqa: BLE001 — the reporter is never allowed to be the failure
        return None


# ── paths ─────────────────────────────────────────────────────────────────────────────────────────
def canon(path, root=None):
    """One canonical spelling of a path, so two spellings of one directory compare equal.

    Relative paths resolve against `root` (the repo holding registry.json), never the working
    directory: a registration must mean the same checkout no matter where the reaper runs from.
    realpath resolves symlinks and macOS's /var -> /private/var, the trap ban_editable_installs.py
    documents at :1735-1737. A path that does not exist still canonicalizes fine — registrations are
    read and compared long before anyone asks whether the checkout is still on disk.
    """
    p = os.path.expanduser(str(path))
    if not os.path.isabs(p):
        p = os.path.join(root or ROOT, p)
    return os.path.realpath(p)


def contains(parent, child):
    """Is `child` the SAME path as `parent`, or a path UNDER it? Both must already be canon()ical.

    The separator guard is the whole point: a raw `child.startswith(parent)` says "/srv/payroll" is
    under "/srv/pay", which would exempt an unrelated checkout from reaping on a string coincidence.
    """
    if parent == child:
        return True
    return child.startswith(parent.rstrip(os.sep) + os.sep)


# ── the config object ─────────────────────────────────────────────────────────────────────────────
def config_template():
    """A template of this rule's config object, for an operator to fill in and install.

    This is scaffolding printed on request, not a default: nothing here is applied unless a human
    installs it in registry.json, and until they do, nothing is registered and everything is
    reapable. The three keys per entry are exactly the three ticket #219 names; the rest are the
    optional audit fields, shown because a template that hides them teaches the wrong shape.
    """
    return {
        SECTION: {
            "_comment": ("The ONLY allowlist that exempts a checkout from reaping (ticket #219). A "
                         "checkout is exempt ONLY if registered here. Removing an entry makes that "
                         "checkout reapable next cycle. Editing this section is the deliberate, "
                         "auditable act of registration — git records who, when and why."),
            "apps": {
                "/absolute/path/to/deployed/checkout": {
                    "name": "example-app",
                    "kind": "app",
                    "deployed": True,
                    "registered_by": "(optional, audit only) who decided this",
                    "ticket": "(optional, audit only) the ticket that authorized it",
                    "reason": "(optional, audit only) why this may live outside the forge forever",
                    "registered_on": "(optional, audit only) YYYY-MM-DD",
                },
            },
        },
    }


class Registration:
    """One validated entry: a path, and what the registry says about it.

    `valid` is the whole question — only a valid registration exempts. `why` explains a rejected
    entry, because an operator whose exemption stopped working is entitled to the reason.
    """

    AUDIT_FIELDS = ("registered_by", "ticket", "reason", "registered_on")

    def __init__(self, raw_path, decl, root=None):
        self.raw_path = raw_path
        self.decl = decl if isinstance(decl, dict) else None
        self.path = canon(raw_path, root)
        self.name = None
        self.kind = None
        self.valid = False
        self.why = ""
        self._validate()

    def _validate(self):
        d = self.decl
        if d is None:
            self.why = "the entry is not a JSON object: %r" % (self.decl,)
            return
        name = d.get("name")
        if not isinstance(name, str) or not name.strip():
            self.why = ("the entry has no non-empty string `name`: %r — #219's shape is "
                        "{name, kind, deployed}" % (name,))
            return
        kind = d.get("kind")
        if kind not in KINDS:
            self.why = ("`kind` is %r, and only %s register (#219 names exactly these three)"
                        % (kind, "/".join(KINDS)))
            return
        dep = d.get("deployed")
        if dep is not True:
            self.why = ("`deployed` is %r, not the JSON literal true — only a deployed checkout is "
                        "exempt (a string like \"true\"/\"false\" is not the boolean, and is not "
                        "accepted: that is how a de-registered app would silently stay exempt)"
                        % (dep,))
            return
        self.name = name.strip()
        self.kind = kind
        self.valid = True

    def audit(self):
        """The optional audit fields that were actually recorded. Never gates the exemption."""
        if not self.decl:
            return {}
        return {k: self.decl[k] for k in self.AUDIT_FIELDS
                if self.decl.get(k) not in (None, "")}

    def describe(self):
        """The registration in one line, for the operator who must decide whether it is still true."""
        if not self.valid:
            return "INVALID registration — %s" % (self.why or "(no reason given)")
        bits = ["%s (%s)" % (self.name, self.kind)]
        for k, v in self.audit().items():
            bits.append("%s=%s" % (k, v))
        return "; ".join(bits)

    def as_dict(self):
        return {"path": self.path, "configured_path": self.raw_path, "name": self.name,
                "kind": self.kind, "valid": self.valid, "why": self.why, "audit": self.audit()}


class Registry:
    """The registry's `deployed_apps.apps` map: which checkouts may live outside the forge forever.

    Fully defensive about types for the reason bug_report() is: every value here comes from
    registry.json, so it is whatever someone typed. A malformed declaration must never crash a
    verdict and must never silently EXEMPT — it is reported as not-a-registration, which keeps the
    answer on the side #219 defaults to.

    An ABSENT section is NOT an error: it is "nothing is registered", and its answer is "everything
    is reapable" (see REGISTRY-FILE GATE vs ABSENT SECTION in the module docstring). The gate that
    throws is find_registry(), which fires at import.
    """

    def __init__(self, reg, root=None):
        self.root = root or ROOT
        sec = (reg or {}).get(SECTION)
        sec = sec if isinstance(sec, dict) else {}
        apps = sec.get("apps")
        self.entries = []
        self.rejected = []
        if isinstance(apps, dict):
            for raw, decl in apps.items():
                r = Registration(raw, decl, self.root)
                (self.entries if r.valid else self.rejected).append(r)

    def all(self):
        """Every entry, valid or not — `list` shows both, so a typo is visible rather than silent."""
        return sorted(self.entries + self.rejected, key=lambda r: r.path)

    def covering(self, path):
        """The valid registration protecting `path`, or None.

        Protection covers the registered path and everything under it (see WHAT A REGISTRATION
        PROTECTS). The most specific match wins, so a nested registration's name is the one
        reported.
        """
        p = canon(path, self.root)
        hits = [r for r in self.entries if contains(r.path, p)]
        return max(hits, key=lambda r: len(r.path)) if hits else None

    def rejected_covering(self, path):
        """A MALFORMED entry that would have covered `path` had it been well-formed, or None.

        This is what turns a silent reaping into an explained one: the operator typed something,
        it did not parse, and the verdict says so instead of "not registered".
        """
        p = canon(path, self.root)
        hits = [r for r in self.rejected if contains(r.path, p)]
        return max(hits, key=lambda r: len(r.path)) if hits else None


# ── the verdict ───────────────────────────────────────────────────────────────────────────────────
class Verdict:
    """What the rule says about ONE checkout. `reapable` is the whole answer a reaper needs."""

    def __init__(self, path, state, why, registration=None):
        self.path = path
        self.state = state
        self.why = why
        self.registration = registration

    @property
    def reapable(self):
        return self.state == REAPABLE

    @property
    def exempt(self):
        """Registered — permitted to persist INDEFINITELY. Strictly stronger than not-reapable: a
        LEASED checkout is also not reapable, but only until its lease drops."""
        return self.state == EXEMPT

    def line(self):
        return "%-8s %s\n         %s" % (self.state, self.path, self.why)

    def as_dict(self):
        d = {"path": self.path, "state": self.state, "reapable": self.reapable,
             "exempt": self.exempt, "why": self.why}
        if self.registration:
            d["registration"] = self.registration.as_dict()
        return d


def decide(path, registry, leases=()):
    """THE ORACLE. What ticket #219 says about one checkout — the call a reaper makes and obeys.

    Returns a Verdict. Deletes nothing, writes nothing, and does not care whether `path` exists:
    the rule is about permission, not about the filesystem.

    The order is #219's own sentence, "Everything not registered and not actively leased is
    reapable", read as written — registration is checked FIRST because it is the indefinite,
    authoritative answer, and a lease only ever adds a temporary reprieve on top:

      1. covered by a valid registration -> EXEMPT   (never reaped; ACCEPTANCE 1)
      2. else covered by a lease the caller holds -> LEASED (not reapable right now)
      3. else -> REAPABLE (ACCEPTANCE 2: absence is what makes it reapable)

    `leases` is whatever the caller holds (see THE LEASE HALF — this repository has no lease store,
    so leases are an input and are never invented here). Empty leases give the pure registry answer.
    """
    p = canon(path, registry.root)
    reg = registry.covering(p)
    if reg is not None:
        if reg.path == p:
            why = "registered: %s" % reg.describe()
        else:
            why = ("inside the registered deployed %s %r at %s — reaping it would destroy that "
                   "deployed app, so it is exempt too" % (reg.kind, reg.name, reg.path))
        return Verdict(p, EXEMPT, why, reg)

    for l in leases or ():
        lp = canon(l, registry.root)
        if contains(lp, p):
            return Verdict(p, LEASED, ("not registered, but the caller holds a lease on %s — a "
                                       "lease is TEMPORARY: this becomes reapable when it drops, "
                                       "because only registration buys indefinite life" % lp))

    bad = registry.rejected_covering(p)
    if bad is not None:
        return Verdict(p, REAPABLE, ("an entry at %s would cover this, but it is not a valid "
                                     "registration, so it exempts nothing — %s"
                                     % (bad.path, bad.why)), bad)
    return Verdict(p, REAPABLE, "not registered in registry.json's %s.apps, and no lease was "
                                "supplied — nothing permits it to persist outside the forge" % SECTION)


# ── the command line ──────────────────────────────────────────────────────────────────────────────
def load(root):
    """(root, registry document) for --root, honouring the same gate as the import-time one."""
    if root is None:
        return ROOT, REGISTRY
    return find_registry(os.path.abspath(root))


def do_list(a, root, reg):
    r = Registry(reg, root)
    rows = r.all()
    if a.json:
        print(json.dumps({"root": root, "section": SECTION,
                          "registered": [x.as_dict() for x in rows]}, indent=2))
        return 0
    print("the DEPLOYED-app registry — registry.json -> %s.apps  [%s]" % (SECTION, root))
    if not rows:
        print("  (none registered — every checkout outside the forge is reapable)")
        print("\n  Nothing is registered, which is a state and not an error: #219's default answer\n"
              "  is 'reapable'. `emit-config` prints the object to paste into registry.json.")
        return 0
    for x in rows:
        print("  %-8s %s\n           %s" % ("OK" if x.valid else "INVALID", x.path, x.describe()))
    n_bad = sum(1 for x in rows if not x.valid)
    print("\n  %d registered, %d exempt from reaping, %d INVALID (exempting nothing)"
          % (len(rows), len(rows) - n_bad, n_bad))
    return 0


def do_check(a, root, reg):
    v = decide(a.path, Registry(reg, root), a.leased)
    if a.json:
        print(json.dumps(v.as_dict(), indent=2))
    else:
        print(v.line())
    return 3 if v.reapable else 0


def do_sweep(a, root, reg):
    """A reaper's worklist: the verdict for every immediate child of a directory.

    Immediate children only, and deliberately: a checkout is a top-level thing in the directory a
    reaper sweeps, and recursing would ask the rule about every file inside a deployed app — whose
    answer is already EXEMPT by containment. Reads the directory listing; deletes nothing.
    """
    r = Registry(reg, root)
    base = canon(a.dir, root)
    if not os.path.isdir(base):
        print("not a directory: %s" % base, file=sys.stderr)
        return 2
    kids = sorted(os.path.join(base, k) for k in os.listdir(base))
    kids = [k for k in kids if os.path.isdir(k)]
    verdicts = [decide(k, r, a.leased) for k in kids]
    if a.json:
        print(json.dumps({"dir": base, "verdicts": [v.as_dict() for v in verdicts]}, indent=2))
        return 0
    print("sweep %s — what the DEPLOYED-app registry permits (nothing is deleted by this tool)" % base)
    if not verdicts:
        print("  (no checkouts here)")
    for v in verdicts:
        print("  " + v.line().replace("\n         ", "\n           "))
    n = sum(1 for v in verdicts if v.reapable)
    print("\n  %d checkout(s): %d REAPABLE, %d protected (%d registered, %d leased)"
          % (len(verdicts), n, len(verdicts) - n,
             sum(1 for v in verdicts if v.exempt),
             sum(1 for v in verdicts if v.state == LEASED)))
    return 0


def do_emit(a, root, reg):
    print(json.dumps(config_template(), indent=2))
    print("\n# Paste the %r object into registry.json at %s and edit it. Registration is a\n"
          "# deliberate, auditable act: this tool never writes it for you — git is the audit trail."
          % (SECTION, os.path.join(root, "registry.json")), file=sys.stderr)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="deployed_app_registry.py",
        description="The DEPLOYED-app registry (ticket #219): the ONLY allowlist that exempts a "
                    "checkout from reaping. Registered deployed code may live outside the forge "
                    "indefinitely; everything not registered and not actively leased is reapable. "
                    "This tool DECIDES and PRINTS; it never reaps, never registers, creates no "
                    "files. Registration is an edit to registry.json — see `emit-config`.",
        epilog="Exit: 0 the rule permits persistence (EXEMPT/LEASED) or the command completed; "
               "2 unexpected (bug report filed) or a usage refusal; 3 REAPABLE — the rule protects "
               "this checkout from nothing.")
    ap.add_argument("--root", help="repository whose registry.json is read (default: this file's)")
    ap.add_argument("--selftest", action="store_true",
                    help="prove the ACCEPTANCE end-to-end in a throwaway dir; touches nothing here")
    sub = ap.add_subparsers(dest="cmd")

    def leased(p):
        p.add_argument("--leased", action="append", default=[], metavar="PATH",
                       help="a path the CALLER holds a lease on (repeatable). This repository has "
                            "no lease store, so leases are an input: a lease is temporary and only "
                            "registration buys indefinite life.")

    p = sub.add_parser("list", help="print the allowlist as configured (valid entries and typos)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=do_list)

    p = sub.add_parser("check", help="the verdict for ONE checkout: exit 0 EXEMPT/LEASED, 3 REAPABLE")
    p.add_argument("path")
    p.add_argument("--json", action="store_true")
    leased(p)
    p.set_defaults(fn=do_check)

    p = sub.add_parser("sweep", help="a reaper's worklist: the verdict for each child of a directory")
    p.add_argument("dir")
    p.add_argument("--json", action="store_true")
    leased(p)
    p.set_defaults(fn=do_sweep)

    p = sub.add_parser("emit-config", help="print the config object to paste into registry.json")
    p.set_defaults(fn=do_emit)

    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not getattr(a, "fn", None):
        ap.print_help()
        return 2
    try:
        root, reg = load(a.root)
        return a.fn(a, root, reg)
    except RegistryNotFound as exc:
        # A REFUSAL, not a fault: one line, no traceback, and NO bug report — see RegistryNotFound.
        print("REFUSING: %s" % exc, file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        where = bug_report(ROOT, REGISTRY, a.cmd, exc,
                           "python3 %s %s" % (os.path.basename(__file__), " ".join(argv or sys.argv[1:])))
        print("UNEXPECTED: %s: %s%s" % (type(exc).__name__, exc,
                                        ("\n  bug report filed: %s" % where) if where else ""),
              file=sys.stderr)
        return 2


# ── selftest ──────────────────────────────────────────────────────────────────────────────────────
def selftest():
    """Prove ticket #219's ACCEPTANCE against real directories in a throwaway tree.

    Nothing in this repository is read for a verdict and nothing anywhere is written: every fixture
    is a temp dir, and check [17] proves the no-files claim in isolation the way #153's lesson
    demands — a directory listing before and after, with nothing else touching it.
    """
    import shutil
    import subprocess
    import tempfile

    checks = []

    def ck(name, ok, detail=""):
        checks.append((name, bool(ok)))
        print("  %s  %s%s" % ("PASS" if ok else "FAIL", name, ("  [%s]" % detail) if detail else ""))

    base = tempfile.mkdtemp(prefix="deployed_app_registry_selftest_")
    try:
        srv = os.path.join(base, "srv")
        for d in ("pay", "payroll", "scratch", "cron", "leased-thing"):
            os.makedirs(os.path.join(srv, d))
        os.makedirs(os.path.join(srv, "pay", "lib"))
        pay = os.path.join(srv, "pay")

        def reg_doc(apps):
            return {"bug_reports": "logs/bug_reports.jsonl", SECTION: {"apps": apps}}

        live = reg_doc({pay: {"name": "payments", "kind": "app", "deployed": True,
                              "registered_by": "steve", "ticket": "219",
                              "reason": "production payments app"},
                        os.path.join(srv, "cron"): {"name": "nightly", "kind": "script",
                                                    "deployed": True}})
        R = Registry(live, base)

        # ── ACCEPTANCE 1 — a registered deployed app is never reaped ──
        v = decide(pay, R)
        ck("ACCEPTANCE 1 — a registered deployed app is EXEMPT (never reaped)",
           v.exempt and not v.reapable, v.state + ": " + v.why[:90])
        ck("...and the verdict names the registration, so the reason is auditable at the verdict",
           v.registration and v.registration.name == "payments" and "steve" in v.why, v.why[:110])
        v2 = decide(os.path.join(pay, "lib"), R)
        ck("...and a path INSIDE it is exempt too (reaping it would destroy the deployed app)",
           v2.exempt, v2.state + ": " + v2.why[:90])
        ck("...and a registration with ONLY #219's three keys works (no extra key is required)",
           decide(os.path.join(srv, "cron"), R).exempt)
        ck("...for every kind #219 names (app/utility/script)",
           all(Registration("/x", {"name": "n", "kind": k, "deployed": True}).valid for k in KINDS))

        # the separator guard — the string-coincidence trap
        v = decide(os.path.join(srv, "payroll"), R)
        ck("a NEIGHBOUR whose name merely starts with a registered path is NOT exempt "
           "(/srv/payroll is not under /srv/pay)", v.reapable, v.state)

        # ── ACCEPTANCE 2 — removing it from the registry makes it reapable next cycle ──
        gone = Registry(reg_doc({os.path.join(srv, "cron"): {"name": "nightly", "kind": "script",
                                                             "deployed": True}}), base)
        v = decide(pay, gone)
        ck("ACCEPTANCE 2 — de-registering the app makes it REAPABLE on the next read of the config",
           v.reapable and not v.exempt, v.state + ": " + v.why[:70])
        empty = Registry(reg_doc({}), base)
        ck("...and emptying the registry makes everything reapable", decide(pay, empty).reapable)
        no_sec = Registry({"bug_reports": "logs/bug_reports.jsonl"}, base)
        ck("...and an ABSENT section is 'nothing registered' (a state, not a crash) — otherwise "
           "de-registering the LAST app would be impossible", decide(pay, no_sec).reapable)

        # ── ACCEPTANCE 3 — the registry is the single source of truth ──
        v = decide(os.path.join(srv, "scratch"), R)
        ck("ACCEPTANCE 3 — an unregistered checkout is REAPABLE (nothing else can exempt it)",
           v.reapable, v.state)
        ck("...deployed=false does NOT exempt (registered is not the same as deployed)",
           decide("/q", Registry(reg_doc({"/q": {"name": "n", "kind": "app", "deployed": False}}),
                                 base)).reapable)
        ck("...the STRING \"true\" does NOT exempt — it is truthy in python, and that is exactly "
           "how a de-registered app would silently stay exempt",
           decide("/q", Registry(reg_doc({"/q": {"name": "n", "kind": "app", "deployed": "true"}}),
                                 base)).reapable)
        ck("...an unknown kind does not exempt", decide("/q", Registry(
            reg_doc({"/q": {"name": "n", "kind": "daemon", "deployed": True}}), base)).reapable)
        bad = Registry(reg_doc({"/q": {"name": "", "kind": "app", "deployed": True}}), base)
        v = decide("/q", bad)
        ck("...a MALFORMED entry exempts nothing, and the verdict EXPLAINS it rather than saying "
           "'not registered'", v.reapable and "not a valid registration" in v.why, v.why[:80])

        # ── the lease half ──
        lt = os.path.join(srv, "leased-thing")
        v = decide(lt, R, leases=[lt])
        ck("a caller-held lease makes an unregistered checkout NOT reapable...",
           not v.reapable and v.state == LEASED, v.state)
        ck("...but NOT exempt — a lease is temporary; only registration buys indefinite life",
           not v.exempt and "TEMPORARY" in v.why, v.why[:80])
        ck("...and with no lease supplied the same checkout is reapable again "
           "(the lease is the caller's, never invented here)", decide(lt, R).reapable)

        # ── [17] SIDE EFFECTS — the 'creates no files' claim, proven in isolation ──
        rj = os.path.join(base, "registry.json")
        with open(rj, "w") as fh:
            json.dump(live, fh)
        before = sorted(os.listdir(base))
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")

        def cli(*args):
            r = subprocess.run([sys.executable, os.path.abspath(__file__), "--root", base] + list(args),
                               capture_output=True, text=True, cwd=base, env=env)
            return r.returncode, r.stdout + r.stderr

        code, out = cli("check", pay)
        ck("CLI: `check` on a registered app exits 0 and prints EXEMPT",
           code == 0 and EXEMPT in out, "exit %s: %s" % (code, out.strip()[:100]))
        code, out = cli("check", os.path.join(srv, "scratch"))
        ck("CLI: `check` on an unregistered checkout exits 3 (REAPABLE) — the contract a reaper "
           "reads", code == 3 and REAPABLE in out, "exit %s: %s" % (code, out.strip()[:100]))
        code, out = cli("check", lt, "--leased", lt)
        ck("CLI: --leased makes it exit 0 (LEASED)", code == 0 and LEASED in out,
           "exit %s: %s" % (code, out.strip()[:80]))
        code, out = cli("sweep", srv, "--leased", lt)
        ck("CLI: `sweep` gives a reaper its worklist over a real directory",
           code == 0 and "payroll" in out and "REAPABLE" in out and "5 checkout(s)" in out,
           "exit %s: %s" % (code, out.strip()[-120:]))
        code, out = cli("list")
        ck("CLI: `list` prints the allowlist with its audit fields",
           code == 0 and "payments" in out and "steve" in out, "exit %s" % code)
        code, out = cli("emit-config")
        tmpl = json.loads(out.split("\n#")[0])
        ck("CLI: `emit-config` prints a template that IS valid config (it round-trips through the "
           "parser and registers)", code == 0 and SECTION in tmpl
           and Registry({SECTION: {"apps": {"/e": dict(tmpl[SECTION]["apps"][
               "/absolute/path/to/deployed/checkout"], **{})}}}, base).entries != [], out[:80])

        after = sorted(os.listdir(base))
        ck("[17] SIDE EFFECT — six subcommand runs created NO file and removed none "
           "(#153's lesson, proven before/after in isolation)", before == after,
           "before=%s after=%s" % (before, after))
        ck("...and the registry.json it read is byte-identical afterwards (it is opened read-only)",
           json.load(open(rj)) == live)

        # ── the #200 config gate, and [19]: refusing is not a fault, so it files no bug report ──
        # THIS REPO's real sink, snapshotted around the gate run. The gate USED to file a Variant-A
        # report here — a non-bug written into a sink other tools read for real faults, and a file
        # created by a tool that promises to create none. The check below is why it no longer can.
        sink = os.path.join(ROOT, (REGISTRY or {}).get("bug_reports", "logs/bug_reports.jsonl")
                            if isinstance((REGISTRY or {}).get("bug_reports"), str)
                            else "logs/bug_reports.jsonl")
        sink_before = (os.path.isfile(sink), os.path.getsize(sink) if os.path.isfile(sink) else 0)

        nowhere = os.path.join(base, "nowhere")   # under base, but base's registry.json is ABOVE it,
        os.makedirs(nowhere)                      # so use a dir whose whole parent chain has none:
        r = subprocess.run([sys.executable, os.path.abspath(__file__), "--root", os.sep, "list"],
                           capture_output=True, text=True, cwd=base, env=env)
        ck("a --root with no registry.json anywhere above it REFUSES (the #200 gate: a tool that "
           "cannot see its config refuses rather than guessing a default)",
           r.returncode == 2 and "registry.json not found" in (r.stdout + r.stderr),
           "exit %s: %s" % (r.returncode, (r.stdout + r.stderr).strip()[-90:]))
        ck("...with a one-line refusal and NO traceback (a misuse is not a fault)",
           "Traceback" not in (r.stdout + r.stderr) and "REFUSING" in (r.stdout + r.stderr),
           (r.stdout + r.stderr).strip()[-90:])
        sink_after = (os.path.isfile(sink), os.path.getsize(sink) if os.path.isfile(sink) else 0)
        ck("[19] ...and files NO bug report into THIS REPO's real sink — the gate is a refusal, and "
           "a refusal must not create a file or pollute the sink other tools read for real faults",
           sink_before == sink_after, "%s: before=%s after=%s" % (sink, sink_before, sink_after))

        bad = [n for n, ok in checks if not ok]
        print("\n== selftest == %d/%d checks passed%s"
              % (len(checks) - len(bad), len(checks), "" if not bad else "; FAILED: " + "; ".join(bad)))
        return 1 if bad else 0
    finally:
        shutil.rmtree(base, ignore_errors=True)
        print("== selftest == throwaway tree removed (this repo, its registry and the db were "
              "never touched)")


if __name__ == "__main__":
    sys.exit(main())
