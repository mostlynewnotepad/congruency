#!/usr/bin/env python3
"""vm_registry.py — THE VM REGISTRY (ticket #455): every VM image on this host, tagged, deduped by
content address, with its RESOLVED STATE, recorded into the registry that already exists.

WHAT IT IS FOR. The lab is dark and nothing recorded why. All six libvirt domains are `shut off` and
every one of their disk paths is dead: the XMLs name `~/bin/config/vm/<disk>`, but the images
actually live at `<project>/config/vm/<disk>`. One directory move darkened the whole lab. Meanwhile
27GB of `config/forge/large-blobs/<sha256>` sits unlabelled — some of it byte-identical to the live
lab, some of it deltas whose bases are gone. Nothing on this host could answer "which VM is which".

This tool answers it. It SCANS (read-only), identifies every VM image by CONTENT (sha256), dedupes
— the same bytes in two places is ONE artifact with two locations — resolves each image's backing
chain and libvirt referrers, and REPORTS the lab honestly. With `--record` it registers each image
through the governed `artifact.record` route as kind='forge-vm'.

    python3 tools/vm_registry.py                  # the report (READ-ONLY: writes NOTHING)
    python3 tools/vm_registry.py --json           # the same, for machines
    python3 tools/vm_registry.py --record         # + register via artifact.record (ticket_artifacts)
    python3 tools/vm_registry.py --forge-ledger   # + register in forge.db (see THE GATE below)
    python3 tools/vm_registry.py --selftest       # synthetic lab in a temp dir; no db, no network

────────────────────────────────────────────────────────────────────────────────────────────────
THE TAG. Every image registers as kind='forge-vm' — `kind` IS the tag, the column the registry
already has. `name` is the image/domain name (`workstation`, `noble-arm64-base`), `forge_sha` is the
sha256 content address (already the filename in `config/forge/large-blobs/<sha256>`), and `version`
is the image's identifying version where one exists, else the short sha (no VM image on this host
carries a discoverable version string, so in practice every version is the short sha — stated
plainly rather than invented).

────────────────────────────────────────────────────────────────────────────────────────────────
THE STATUSES, AND WHY AN IMAGE CAN BE IN MORE THAN ONE.

An artifact's states are not exclusive: `config/vm/appliance-run.qcow2` is simultaneously a COPY (its
bytes are also in large-blobs), an ORPHANED-DELTA (its backing file is gone) and the disk a domain
names at a moved path. Collapsing that to one word would throw away two thirds of the answer. So each
artifact carries EVERY state that is true of it (`states`), plus one PRIMARY `status` for the table,
chosen by this precedence:

    COPY            > the same bytes are registered at MORE THAN ONE location (byte-identical, by
                      sha256 — not by name, not by size).
    ORPHANED-DELTA  > the image declares a backing file that does NOT exist at the declared path.
                      Sub-state `recoverable` when those base bytes are found elsewhere in the lab
                      (so an operator COULD rebase); `unrecoverable` when they are nowhere on this
                      host. This tool never rebases — it only says which it is.
    STALE-PATH      > a referrer (a libvirt domain's XML, or another image's backing pointer) names a
                      path where these bytes are NOT, while the bytes DO exist somewhere else.
    LIVE            > the image's chain resolves (its base is present, or it has no base) and no
                      referrer points at a path that fails.
    UNREFERENCED    > no domain names it and it is in no backing chain.

DOMAINS ARE REPORTED SEPARATELY FROM ARTIFACTS, and that separation is the point. A domain's disk is
STALE-PATH; the ARTIFACT those bytes belong to may be a COPY. Both facts are true, and the report
states both rather than picking one — the domain table is the "which VM wants what, and does it
resolve" view; the artifact table is the "what distinct images exist, and what is their state" view.

WHERE THE BYTES ACTUALLY ARE. For a path that does not resolve, this tool locates the real bytes by
(1) the exact rebase `<anything>/config/vm/<tail>` -> `<project>/config/vm/<tail>` — the single
directory move that darkened this lab — else (2) a basename match within the lab. Rule (2) is an
INFERENCE and is labelled as such in the output (`by-basename`); rule (1) is an exact tail match.
Neither is applied to change anything on disk.

────────────────────────────────────────────────────────────────────────────────────────────────
WHAT COUNTS AS A VM IMAGE — DECIDED BY CONTENT, NEVER BY EXTENSION.

The extension lies here, provably: `config/vm/noble-arm64-base.img` is named `.img` but is a QCOW2.
And `qemu-img info` calls EVERY file it cannot identify "raw", so trusting it would register a gzip
blob as a VM image. So identification is by magic bytes:

    qcow2  : the QCOW magic 'QFI\\xfb' at offset 0.
    iso    : the ISO9660 identifier 'CD001' at offset 32769.
    raw    : an MBR boot signature 0x55AA at offset 510 AND a partition table at 446..510 that
             PARSES (>=1 entry whose boot flag is 0x00/0x80, whose type is non-zero and whose sector
             count is non-zero).

That last clause is load-bearing, not pedantry. A bare FAT volume carries the SAME 0x55AA boot
signature as an MBR, so "0x55AA means raw disk" would misfile
`large-blobs/902be6c484ad...` (a 64MiB `mkfs.fat` volume) as a VM image. Requiring the partition
table to parse separates them: the real disk images yield partition entries (0x0c FAT32-LBA + 0x83
Linux), the FAT volume yields none.

Anything else is NOT registered. It is listed under SKIPPED with the reason, so the exclusion is
auditable rather than silent. A file is registered ANYWAY, whatever its magic, if the lab itself
vouches for it: a libvirt domain names it, or it is some image's backing file, or its sha256 matches
an image found elsewhere.

────────────────────────────────────────────────────────────────────────────────────────────────
THE CONTENT ADDRESS. `config/vm` files are hashed (there is no other address for them) — ~10GB in
about 5 seconds on this host's SSD. In the two blob stores the FILENAME IS the sha256 by
construction, so it is used as the address and not recomputed; `--verify-blobs` re-hashes them and
reports any filename that lies. (Spot-checked at build time: `cafa1a96...` and `6ac10823...` both
hash to their own names.)

────────────────────────────────────────────────────────────────────────────────────────────────
DIRECTORY SERVICES — AND A CORRECTION TO THIS TICKET'S PREMISE, MEASURED ON THIS HOST.

Ticket #455 asks that registering VMs make them findable through the universal resolver (#193,
`tools/resolver.py`), whose `forge-artifacts` probe answers a sha256 query. It states that recording
through `artifact.record` will close that gate "with no new query surface". **It will not, and this is
the one claim in the ticket that the code refutes.** They are two different tables in two different
database FILES:

  * `artifact.record` INSERTs into `ticket_artifacts (id, ts, ticket_id, name, version, forge_sha,
    kind)` in the congruency state db (`migrations/0014_ticket_artifacts.sql:7-26`).
  * resolver.py's `forge-artifacts` probe reads `artifacts` — a DIFFERENT table, keyed on its own
    `sha256` column, in the FORGE ledger `config/forge/forge.db` (`resolver.py:551-553`, the db
    resolved at `resolver.py:260-261`).

`resolver.py` contains no reference to `ticket_artifacts` at all. So a fully populated
`ticket_artifacts` leaves `resolver.py <sha256>` returning exactly what it returns today: 0. The
ticket's own words for that outcome are "a FAILED ticket", and no amount of `artifact.record` can
avoid it.

Both halves are therefore implemented, and they are separate flags because they are separate acts:

    --record        the ticket's letter: register through the governed route. Populates
                    `ticket_artifacts`; `artifact.list` then returns the images. Changes NOTHING
                    about what the resolver can see.
    --forge-ledger  the ticket's PURPOSE: register in the forge ledger's `artifacts` table, the one
                    the resolver actually probes. This is the ONLY thing that closes the gate.

`--forge-ledger` is OFF by default because the ticket mandates a read-only tool, and it is an
additive `INSERT OR IGNORE` (never an UPDATE, never a DELETE) that copies NO bytes: the content
address is already satisfied by the blob that exists on disk. It is not routed through
`artifact.record` because `artifact.record` cannot reach that table, and no governed route can —
`api_routes` has no route that touches forge.db (every route's SQL runs against the state db).
The forge's own writer, `jazz-forge/forge/artifacts.py:57 put()`, is not used because it would COPY
each image into a second store (tens of GB, for images already stored), attempt an on-chain anchor,
and record only a basename where the gate needs a path.

READING THE RESOLVER'S ANSWER — the one line that misleads. After `--forge-ledger`, this is the
resolver's REAL output for the gate's sha, and it must be read correctly:

    $ python3 tools/resolver.py cafa1a965b591b7c4184b484ffd8e625981a79d48f9b4ae8a4adf7b4c5ade927
      probes:   content-sha256, forge-artifacts, git-object-db
      resolved: 0 blob(s) -> 0 de-overlapped match(es)
      forge artifacts (content-addressed by sha256): config/vm/noble-arm64-base.img   <-- THE ANSWER
      (no match — the collection is empty)

`resolved: 0 blob(s)` and `(no match)` stay printed, and that is NOT this registry failing. Those
lines count OMNI GIT BLOBS, and a 586MiB VM image is not one and never will be: resolver.py itself
says a forge artifact "is content-addressed by sha256 but is not an omni blob, so it has no
{repo, path, line-range} and is reported on its own channel rather than faked into a match"
(resolver.py:525-528). The forge-artifacts probe's answer is the `forge artifacts:` line — the
`artifacts` key in `--json`. Before this tool ran, that line was ABSENT and `--json` carried
`"artifacts": []`; after it, the probe names the image. That line IS the gate, and moving it is the
only thing registering can do without editing resolver.py, which is forbidden.

`filename` holds ONE location because that column is all the probe SELECTs (resolver.py:552). It
holds the LAB path (`config/vm/noble-arm64-base.img`) — the answer to "where is this VM". The image's
other locations, including its large-blobs copy, travel in `meta.locations`, because the ticket's
dedup rule is explicit that the same bytes in two places are ONE artifact with two locations, and
inserting a second row per location to make the probe echo both would break exactly that rule.

THE REPORT ALWAYS STATES THE GATE, run or not: for each image, whether resolver.py can currently see
it, and if not, the exact reason and the exact command that fixes it. `--gate-check` verifies it for
real by querying the same table the resolver queries.

(For the record, since a stale claim propagates: `forge_refactor_ticketer.py`'s docstring says #193
and #194 are "still REQUESTED — no resolver module exists to import today". That is stale. Both are
DONE and on disk at `tools/resolver.py` and `tools/source_dedup.py`; this tool read the former to
establish the gap above.)

────────────────────────────────────────────────────────────────────────────────────────────────
WHAT THIS TOOL MEASURES THAT #455's SUMMARY DOES NOT — reported because the registry's only value is
being true. Run it and read the table; these are not assertions, they are its output.

  * FIVE domains name `~/bin/config/vm`, not four. The ticket lists appliance, fabric-root,
    pi-imaging and workstation; `workstation-install` is equally stale (workstation-base.qcow2 and
    cidata.iso both resolve under config/vm). A sixth domain, named literally 'ubuntu workstation',
    names `~/code/iso/ubuntu25.10`, whose bytes are NOWHERE on this host — that disk is MISSING, not
    STALE-PATH, and the two are different problems with different fixes.
  * FOUR artifacts are COPY, not three. Besides the ticket's noble-arm64-base.img,
    raspios-trixie-arm64-lite.img and appliance-run.qcow2, the pi-imaging seed ISO
    (9c4c2c9aff70...) is byte-identical across config/vm and the SHARDED blob store.
  * A FOURTH orphaned delta with a recoverable base: `config/vm/pi-imaging/overlay.qcow2` (6.6G)
    backs onto `~/bin/config/vm/noble-arm64-base.img` — the same dead path as ec281818, and equally
    recoverable. The ticket names only ec281818.
  * The SHARDED store `config/forge/artifacts/blobs` holds NO qcow2 and no raw disk at all — 83 of
    its 84 blobs are already ledgered as run-output/xz/seed/squashfs, and its single VM-relevant
    entry is that seed ISO. The ticket's acceptance asks for "every image in ... both blob stores";
    what that store actually contains is one image, and registering its wheels and xz archives as
    kind='forge-vm' would make the tag mean nothing.
  * `config/vm/noble-arm64-base.img` is a QCOW2, not a raw .img, and `config/vm/workstation.qcow2`
    backs onto it by a RELATIVE name, so that one chain resolves and is the lab's only LIVE chain.

────────────────────────────────────────────────────────────────────────────────────────────────
WHAT IT WRITES.

By default: NOTHING. No file, no db row, no byte moved, no libvirt XML touched, no image rebased.
Every db it reads is opened with the sqlite URI flag `immutable=1`, never `mode=ro` — the state db is
WAL-journalled and `mode=ro` on a WAL db mints `-wal`/`-shm` sidecar files on every open, which is a
file this tool must not create (the #153 lesson, fixed the same way at `ticket_status.py:49-60` and
`resolver.py:340-345`). `qemu-img info` is invoked with `-U` so it never takes a write lock, and
`virsh` only ever runs `list`/`dumpxml`. Bytecode caching is disabled so no `__pycache__` is minted.
This tool DESCRIBES the lab; it does not repair it. Repair is a separate, operator-authorized ticket.

Only these flags write, and only what they say:
    --record        POSTs `artifact.record` (the governed route). Idempotent: it reads
                    `artifact.list` first and skips any (name, version, forge_sha, kind) already
                    recorded, because `artifact.record` is a plain INSERT
                    (`0014_ticket_artifacts.sql:21-22`) and would otherwise duplicate on a re-run.
    --forge-ledger  `INSERT OR IGNORE` into forge.db `artifacts` (additive only).
The one file this tool can ever create is the note-for-claude bug report (logs/bug_reports.jsonl,
git-ignored) written when an UNEXPECTED exception is thrown — the registry's contract for every tool
in this package.

Exit codes (each prints ONE line, never a traceback):
    0  the scan completed (--selftest: every check PASSED or SKIPPED with a named reason)
    1  --selftest: at least one check FAILED; or --gate-check: the gate is not closed
    2  a precondition failure — no lab directory, an unreadable store, a missing required tool
Pure-python stdlib + `virsh` + `qemu-img`, one file. Registry-gated per note-for-claude: it walks UP
to registry.json and refuses to run without it.
"""
import argparse
import glob
import hashlib
import json
import os
import re
import sqlite3
import struct
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

# NO BYTECODE CACHE — this module must be able to say it creates no files, and "git-ignored" is not
# "not created". Same reasoning as resolver.py:224-230.
sys.dont_write_bytecode = True


# ── registry gate (note-for-claude: a tool that cannot see the registry throws) ───────────────────
def find_registry(start):
    d = os.path.abspath(start)
    while True:
        p = os.path.join(d, "registry.json")
        if os.path.isfile(p):
            return d, json.load(open(p))
        nxt = os.path.dirname(d)
        if nxt == d:
            raise RuntimeError("registry.json not found walking up from %s — refusing to run" % start)
        d = nxt


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT, REGISTRY = find_registry(HERE)
HOME = os.path.expanduser("~")

# The lab and the two blob stores. Resolved exactly as the rest of the package resolves the forge:
# an env override, else <project>/config/... — the same fallback resolver.py:258-261 and
# ForgeView.php:32-34 use. NOT derived from ROOT: ROOT is the congruency checkout (and in a pair
# worktree it is the worktree), while the lab lives beside the project, not inside the repo.
PROJECT = os.environ.get("JAZZ_PROJECT") or os.path.join(HOME, "code", "installed", "jazz-project")
VM_DIR = os.environ.get("JAZZ_VM_DIR") or os.path.join(PROJECT, "config", "vm")
LARGE_BLOBS = os.path.join(PROJECT, "config", "forge", "large-blobs")
SHARD_BLOBS = os.path.join(PROJECT, "config", "forge", "artifacts", "blobs")
FORGE_DB = os.environ.get("FORGE_DB") or os.path.join(PROJECT, "config", "forge", "forge.db")

CONG = (os.environ.get("CONGRUENCY_URL") or "http://127.0.0.1:8899").rstrip("/")
LIBVIRT_URI = os.environ.get("LIBVIRT_DEFAULT_URI") or "qemu:///session"

KIND = "forge-vm"                  # THE TAG — the ticket's whole point
TICKET = 455
IMAGE_EXTS = (".qcow2", ".img", ".raw", ".iso")
SHORT = 12                         # short-sha length, used as `version` when none exists
CHUNK = 1 << 22                    # 4MiB hash reads
QEMU_TIMEOUT = 120
VIRSH_TIMEOUT = 60

STATUS_ORDER = ("COPY", "ORPHANED-DELTA", "STALE-PATH", "LIVE", "UNREFERENCED")


class Fault(Exception):
    """A precondition failure — reported as one line, exit 2."""


def bug_report(fn, exc, repro, cause):
    """Variant-A bug report to the registry's bug_reports sink (best-effort, never blocks).
    note-for-claude: every tool files a timestamped report when an exception is thrown. This is the
    ONLY file this tool can ever create, and only on an unexpected exception."""
    try:
        sink = os.path.join(ROOT, REGISTRY.get("bug_reports", "logs/bug_reports.jsonl"))
        os.makedirs(os.path.dirname(sink), exist_ok=True)
        with open(sink, "a") as fh:
            fh.write(json.dumps({
                "filename": "vm_registry.py", "function": fn,
                "time-of-occurance": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "methods-to-reproduce": repro, "possible-cause": str(cause),
                "traceback": traceback.format_exc().splitlines()[-6:],
                "note": "the VM registry (#455)",
            }) + "\n")
    except Exception:  # noqa: BLE001 — a failed bug report must never mask the original fault
        pass


def _secret(name):
    """A secret from .secrets/ats.env, else the environment.

    Walks UP from ROOT rather than looking only at `dirname(ROOT)` (the pair_loop.py:172-178 form):
    in a pair worktree ROOT is the worktree, whose parent is the worktrees directory, so the fixed
    form finds nothing and every token route silently 401s. Walking up finds the project's .secrets
    from the worktree AND from the main checkout.
    """
    if os.environ.get(name):
        return os.environ[name]
    d = ROOT
    while True:
        p = os.path.join(d, ".secrets", "ats.env")
        if os.path.isfile(p):
            for line in open(p):
                line = line.strip()
                if line.startswith(name + "="):
                    return line.split("=", 1)[1]
        nxt = os.path.dirname(d)
        if nxt == d:
            return None
        d = nxt


def run(*argv, **kw):
    """A subprocess, captured. Returns (rc, stdout, stderr); never raises on a non-zero rc."""
    try:
        p = subprocess.run(list(argv), capture_output=True, text=True,
                           timeout=kw.get("timeout", QEMU_TIMEOUT))
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError:
        return 127, "", "%s: not found" % argv[0]
    except subprocess.TimeoutExpired:
        return 124, "", "%s: timed out" % argv[0]
    except OSError as e:
        return 126, "", "%s: %s" % (argv[0], e)


def have(tool):
    return run(tool, "--version", timeout=20)[0] not in (127, 126)


# ── content identification: by magic bytes, never by extension ───────────────────────────────────
def partition_table(sector):
    """The MBR partition entries in a 512-byte boot sector, or None when this is not an MBR.

    Returns [] for a sector that carries the 0x55AA boot signature but no usable partition entry —
    a bare FAT volume looks exactly like that (its VBR shares the signature), so [] means "boot
    sector, but not a partitioned disk" and None means "not a boot sector at all".
    """
    if len(sector) < 512 or sector[510:512] != b"\x55\xaa":
        return None
    ents = []
    for i in range(4):
        e = sector[446 + i * 16: 446 + (i + 1) * 16]
        boot, typ = e[0], e[4]
        if boot not in (0x00, 0x80):
            return None                      # not a partition table (BPB data sits here on a FAT VBR)
        _lba, count = struct.unpack("<II", e[8:16])
        if typ != 0 and count > 0:
            ents.append({"type": "0x%02x" % typ, "lba": _lba, "sectors": count})
    return ents


def identify(path):
    """(format, reason) — 'qcow2' | 'iso' | 'raw' | (None, why-not) — from the bytes alone.

    The extension is not consulted: config/vm/noble-arm64-base.img is a QCOW2 despite its name, and
    `qemu-img info` reports 'raw' for anything it cannot identify (a gzip, a tarball), which would
    register non-images as VMs.
    """
    try:
        with open(path, "rb") as fh:
            head = fh.read(512)
            fh.seek(32769)
            iso = fh.read(5)
    except OSError as e:
        return None, "unreadable: %s" % e
    if head[:4] == b"QFI\xfb":
        return "qcow2", "qcow2 magic"
    if iso == b"CD001":
        return "iso", "ISO9660 identifier at 32769"
    parts = partition_table(head)
    if parts:
        return "raw", "MBR with %d partition(s): %s" % (
            len(parts), ", ".join(p["type"] for p in parts))
    if parts == []:
        return None, "boot signature but no partition table (a bare filesystem volume, not a disk)"
    return None, "no qcow2/ISO9660/MBR signature"


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for c in iter(lambda: fh.read(CHUNK), b""):
            h.update(c)
    return h.hexdigest()


def qemu_info(path):
    """`qemu-img info` as a dict, or {} when qemu-img cannot read it.

    `-U` (force-share) so the probe never takes a write lock on an image — this tool must not be able
    to disturb a domain even if one were running.
    """
    rc, out, _err = run("qemu-img", "info", "-U", "--output=json", path)
    if rc != 0:
        return {}
    try:
        return json.loads(out)
    except ValueError:
        return {}


# ── libvirt ──────────────────────────────────────────────────────────────────────────────────────
def domains(uri=LIBVIRT_URI):
    """[(name, [disk...])] for every defined domain, or a Fault-free ([], reason) when virsh is absent.

    `list --all --name` prints ONE NAME PER LINE deliberately: this host has a domain literally named
    'ubuntu workstation', and the default table output cannot be split on whitespace without tearing
    that name in half (and then dumpxml fails on the fragment).
    """
    rc, out, err = run("virsh", "-c", uri, "list", "--all", "--name", timeout=VIRSH_TIMEOUT)
    if rc == 127:
        return [], "virsh not on PATH — the domain view is unavailable"
    if rc != 0:
        return [], "virsh -c %s failed: %s" % (uri, (err or out).strip().splitlines()[:1])
    out_doms = []
    for name in (l.strip() for l in out.splitlines()):
        if not name:
            continue
        rc2, xml, err2 = run("virsh", "-c", uri, "dumpxml", name, timeout=VIRSH_TIMEOUT)
        if rc2 != 0:
            out_doms.append({"domain": name, "disks": [], "error": (err2 or "").strip()[:120]})
            continue
        disks = []
        try:
            root = ET.fromstring(xml)
        except ET.ParseError as e:
            out_doms.append({"domain": name, "disks": [], "error": "unparsable XML: %s" % e})
            continue
        for disk in root.iter("disk"):
            src = disk.find("source")
            if src is None:
                continue
            p = src.get("file") or src.get("dev")
            if p:
                drv = disk.find("driver")
                disks.append({"device": disk.get("device") or "disk", "path": p,
                              "declared_format": (drv.get("type") if drv is not None else None)})
        out_doms.append({"domain": name, "disks": disks, "error": None})
    return out_doms, None


def domain_states(uri=LIBVIRT_URI):
    rc, out, _e = run("virsh", "-c", uri, "list", "--all", timeout=VIRSH_TIMEOUT)
    st = {}
    if rc != 0:
        return st
    for line in out.splitlines():
        m = re.match(r"\s*(\S+)\s+(.+?)\s{2,}(.+?)\s*$", line)
        if m and m.group(1) not in ("Id", "--"):
            st[m.group(2).strip()] = m.group(3).strip()
    return st


# ── locating bytes that moved ────────────────────────────────────────────────────────────────────
def locate(wanted, by_path, vm_dir):
    """(actual_path, rule) — where the bytes a dead path WANTS actually are, or (None, None).

    Rule 1 `rebase`: the exact tail after '/config/vm/' re-rooted at the real lab. This is the single
        directory move that darkened this lab (~/bin/config/vm -> <project>/config/vm), so the tail
        matches exactly and the answer is certain.
    Rule 2 `by-basename`: a unique basename match inside the lab. An INFERENCE — labelled as such in
        the output, and refused when the basename is ambiguous (two files, same name, different
        directories) because a guess presented as an answer is worse than "unknown".
    """
    if not wanted:
        return None, None
    if os.path.exists(wanted):
        return wanted, "exact"
    marker = os.path.sep + os.path.join("config", "vm") + os.path.sep
    if marker in wanted:
        cand = os.path.join(vm_dir, wanted.split(marker, 1)[1])
        if os.path.exists(cand):
            return cand, "rebase"
    base = os.path.basename(wanted)
    hits = sorted({p for p in by_path if os.path.basename(p) == base})
    if len(hits) == 1:
        return hits[0], "by-basename"
    return None, None


# ── the scan ─────────────────────────────────────────────────────────────────────────────────────
def candidates(vm_dir, large_blobs, shard_blobs):
    """[(path, store)] — every file worth identifying, from the lab and both blob stores.

    The lab is walked RECURSIVELY: the ticket's glob is `config/vm/*.{qcow2,img}`, but the domain
    `pi-imaging` names `pi-imaging/overlay.qcow2` — a 7GB image one directory down — and a registry
    that cannot name the image a domain references does not answer "which VM is which". Both blob
    stores are flat/sharded and every entry is a candidate regardless of name (their names are hashes,
    so they carry no extension at all).
    """
    out = []
    for root, dirs, files in os.walk(vm_dir):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in sorted(files):
            if f.lower().endswith(IMAGE_EXTS):
                out.append((os.path.join(root, f), "lab"))
    for p in sorted(glob.glob(os.path.join(large_blobs, "*"))):
        if os.path.isfile(p):
            out.append((p, "large-blobs"))
    for p in sorted(glob.glob(os.path.join(shard_blobs, "*", "*"))):
        if os.path.isfile(p):
            out.append((p, "shard-blobs"))
    return out


def address(path, store, verify):
    """(sha256, trusted_from) for a candidate.

    In the blob stores the filename IS the content address by construction, so it is used as-is: a
    scan of ~27GB that re-hashes what is already addressed buys nothing. `--verify-blobs` re-hashes
    and reports any filename that lies.
    """
    base = os.path.basename(path)
    if store in ("large-blobs", "shard-blobs") and re.fullmatch(r"[0-9a-f]{64}", base) and not verify:
        return base, "filename"
    return sha256_file(path), "hashed"


def scan(vm_dir, large_blobs, shard_blobs, uri=LIBVIRT_URI, verify=False):
    """The whole read-only pass: identify -> address -> dedup -> resolve chains/referrers -> classify."""
    doms, dom_note = domains(uri)
    dstates = domain_states(uri) if not dom_note else {}

    by_sha, skipped, lies = {}, [], []
    seen_paths = {}
    for path, store in candidates(vm_dir, large_blobs, shard_blobs):
        fmt, why = identify(path)
        try:
            size = os.path.getsize(path)
        except OSError as e:
            skipped.append({"path": path, "store": store, "reason": "unreadable: %s" % e})
            continue
        if fmt is None:
            skipped.append({"path": path, "store": store, "reason": why, "size": size})
            continue
        sha, how = address(path, store, verify)
        if verify and store in ("large-blobs", "shard-blobs"):
            base = os.path.basename(path)
            if re.fullmatch(r"[0-9a-f]{64}", base) and base != sha:
                lies.append({"path": path, "filename_says": base, "bytes_are": sha})
        seen_paths[path] = sha
        a = by_sha.setdefault(sha, {"sha256": sha, "size": size, "format": fmt, "locations": [],
                                    "identified_by": why})
        a["locations"].append({"path": path, "store": store, "addressed_by": how})

    # a second pass: anything the lab VOUCHES for, whatever its magic said (a domain names it, or it
    # is a backing file). Such a file is a VM image by the lab's own testimony.
    vouched = set()
    for d in doms:
        for disk in d["disks"]:
            vouched.add(os.path.realpath(disk["path"]))
    for a in list(by_sha.values()):
        info = qemu_info(a["locations"][0]["path"])
        if info.get("full-backing-filename"):
            vouched.add(os.path.realpath(info["full-backing-filename"]))
    reclaimed = []
    for s in list(skipped):
        if os.path.realpath(s["path"]) in vouched and "unreadable" not in s["reason"]:
            fmt = (qemu_info(s["path"]).get("format") or "raw")
            sha, how = address(s["path"], s["store"], verify)
            seen_paths[s["path"]] = sha
            a = by_sha.setdefault(sha, {"sha256": sha, "size": s.get("size", 0), "format": fmt,
                                        "locations": [], "identified_by": "vouched by the lab"})
            a["locations"].append({"path": s["path"], "store": s["store"], "addressed_by": how})
            skipped.remove(s)
            reclaimed.append(s["path"])

    # chains + names + referrers
    by_path = dict(seen_paths)
    for sha, a in by_sha.items():
        info = qemu_info(a["locations"][0]["path"])
        a["virtual_size"] = info.get("virtual-size")
        declared = info.get("backing-filename")
        full = info.get("full-backing-filename")
        a["backing_file"] = declared
        a["backing_resolved"] = full
        a["backing_exists"] = bool(full and os.path.exists(full))
        a["backing_recoverable_at"] = None
        a["backing_recoverable_rule"] = None
        a["backing_sha256"] = None
        if declared and not a["backing_exists"]:
            where, rule = locate(full or declared, by_path, vm_dir)
            if where:
                a["backing_recoverable_at"] = where
                a["backing_recoverable_rule"] = rule
        if a["backing_exists"]:
            a["backing_sha256"] = by_path.get(os.path.realpath(full)) or by_path.get(full)
        elif a["backing_recoverable_at"]:
            a["backing_sha256"] = by_path.get(a["backing_recoverable_at"])
        a["domains"] = []
        a["referrers"] = []
        a["used_as_base_by"] = []

    # who refers to whom
    for d in doms:
        for disk in d["disks"]:
            actual, rule = locate(disk["path"], by_path, vm_dir)
            disk["resolves"] = os.path.exists(disk["path"])
            disk["actual_path"] = actual
            disk["actual_rule"] = rule
            disk["state"] = ("LIVE" if disk["resolves"] else
                             ("STALE-PATH" if actual else "MISSING"))
            sha = by_path.get(actual) if actual else None
            disk["sha256"] = sha
            if sha and sha in by_sha:
                by_sha[sha]["domains"].append(d["domain"])
                if not disk["resolves"]:
                    by_sha[sha]["referrers"].append(
                        {"by": "domain:" + d["domain"], "wants": disk["path"], "actual": actual,
                         "rule": rule})
    # the inbound half of the chain: an image that IS some delta's present base is in a chain, and so
    # is LIVE rather than UNREFERENCED. Without this the base of a working chain reads as "nothing
    # refers to me", which is exactly backwards.
    for sha, a in by_sha.items():
        if a["backing_exists"] and a["backing_sha256"] and a["backing_sha256"] in by_sha:
            by_sha[a["backing_sha256"]]["used_as_base_by"].append(sha)

    # a delta's backing pointer is a referrer too
    for sha, a in by_sha.items():
        if a["backing_file"] and not a["backing_exists"] and a["backing_recoverable_at"]:
            tgt = by_path.get(a["backing_recoverable_at"])
            if tgt and tgt in by_sha:
                by_sha[tgt]["referrers"].append(
                    {"by": "backing:" + a["sha256"][:SHORT], "wants": a["backing_resolved"],
                     "actual": a["backing_recoverable_at"], "rule": a["backing_recoverable_rule"]})

    for sha, a in by_sha.items():
        a["locations"].sort(key=lambda l: (l["store"] != "lab", l["path"]))
        a["domains"] = sorted(set(a["domains"]))
        a["name"] = derive_name(a)
        a["version"] = sha[:SHORT]
        a["states"] = states_of(a)
        a["status"] = next(s for s in STATUS_ORDER if s in a["states"])
        a["kind"] = KIND

    return {"domains": doms, "domain_note": dom_note, "domain_states": dstates,
            "artifacts": sorted(by_sha.values(), key=lambda a: (-a["size"], a["sha256"])),
            "skipped": skipped, "reclaimed": reclaimed, "filename_lies": lies,
            "vm_dir": vm_dir, "large_blobs": large_blobs, "shard_blobs": shard_blobs}


def derive_name(a):
    """The image's name: its lab filename's stem, else a domain that names it, else the short sha.

    STEM FIRST, and that order matters. Naming an image after the domain that references it collides:
    the `workstation` domain names BOTH workstation.qcow2 and workstation-seed.iso, so a
    domain-first rule files two different images under one name and the registry can no longer say
    which is which — the exact failure this tool exists to end. The stem is unique per file and is
    what the ticket's own examples are ('workstation', 'noble-arm64-base'). Two distinct images may
    still share a stem (config/vm/cidata.iso and config/vm/workstation-build/cidata.iso are both
    'cidata'); they stay distinct rows because `version` is the short sha of their differing bytes.

    A blob-store entry is named by its own hash, so its stem carries no information — the short sha
    IS its honest name, and it is used rather than inventing one.
    """
    for loc in a["locations"]:
        if loc["store"] == "lab":
            return re.sub(r"\.(qcow2|img|raw|iso)$", "", os.path.basename(loc["path"]), flags=re.I)
    if a["domains"]:
        return sorted(a["domains"])[0]
    return a["sha256"][:SHORT]


def states_of(a):
    """EVERY state true of this artifact. Not exclusive — see the module docstring."""
    st = []
    if len(a["locations"]) > 1:
        st.append("COPY")
    if a["backing_file"] and not a["backing_exists"]:
        st.append("ORPHANED-DELTA")
    if a["referrers"]:
        st.append("STALE-PATH")
    chain_ok = (not a["backing_file"]) or a["backing_exists"]
    if chain_ok and not a["referrers"]:
        in_chain = bool(a["domains"] or a["backing_file"] or a["used_as_base_by"])
        st.append("LIVE" if in_chain else "UNREFERENCED")
    if not st:
        st.append("LIVE" if chain_ok else "UNREFERENCED")
    return st


def recoverability(a):
    if "ORPHANED-DELTA" not in a["states"]:
        return None
    return "recoverable" if a["backing_recoverable_at"] else "unrecoverable"


# ── the registries ───────────────────────────────────────────────────────────────────────────────
def rest(route, obj=None, method=None, key=None):
    """The governed REST surface, exactly as pair_loop.py:205-217 calls it."""
    url = CONG + "/rest.php?route=" + route
    if obj is not None and (method or "POST") == "GET":
        url += "&" + "&".join("%s=%s" % (k, urllib.request.quote(str(v))) for k, v in obj.items())
        obj = None
    data = json.dumps(obj).encode() if obj is not None else None
    req = urllib.request.Request(url, data=data, method=method or ("POST" if data else "GET"),
                                 headers={"Content-Type": "application/json",
                                          "X-Api-Key": key or ""})
    with urllib.request.urlopen(req, timeout=20) as r:
        out = json.loads(r.read().decode())
    if isinstance(out, dict) and out.get("error"):
        raise Fault("route %s failed: %s" % (route, out["error"]))
    return out


def already_recorded(ticket, key):
    """{(name, version, forge_sha, kind)} already in ticket_artifacts for this ticket.

    `artifact.record` is a plain INSERT (0014_ticket_artifacts.sql:21-22) with no uniqueness
    constraint, so a second run would silently double every row. History here is append-only — a
    duplicate cannot be cleaned up afterwards — so the duplicate must never be created.
    """
    rows = rest("artifact.list", {"ticket_id": ticket}, method="GET", key=key).get("rows", [])
    return {(r.get("name"), r.get("version"), r.get("forge_sha"), r.get("kind")) for r in rows}


def record_all(res, ticket, key, poster=None, lister=None):
    """Register every artifact through `artifact.record`. Returns (recorded, skipped_existing)."""
    lister = lister or (lambda: already_recorded(ticket, key))
    poster = poster or (lambda obj: rest("artifact.record", obj, key=key))
    have_rows = lister()
    done, skip = [], []
    for a in res["artifacts"]:
        row = {"ticket_id": ticket, "name": a["name"], "version": a["version"],
               "forge_sha": a["sha256"], "kind": KIND}
        sig = (a["name"], a["version"], a["sha256"], KIND)
        if sig in have_rows:
            skip.append(sig)
            continue
        poster(row)
        have_rows.add(sig)
        done.append(sig)
    return done, skip


def forge_ledger_register(res, forge_db, dry=False):
    """Register every artifact in the FORGE ledger's `artifacts` table — the table resolver.py's
    `forge-artifacts` probe actually reads (resolver.py:551-553).

    Additive only: `INSERT OR IGNORE` against the table's own UNIQUE(name, version, sha256)
    constraint, so a re-run inserts nothing and no row is ever updated or deleted. NO bytes are
    copied: the content address is already satisfied by the blob on disk, which is precisely why the
    forge's own `put()` (which would copy tens of GB into a second store) is not used.

    `filename` carries the image's PRIMARY location project-relative — that column is what the probe
    returns, so it must name where the bytes are, and `config/vm/noble-arm64-base.img` is the answer
    the gate asks for. Every other location travels in `meta.locations`.
    """
    if not dry and not os.path.isfile(forge_db):
        raise Fault("no forge ledger at %s — set FORGE_DB (this tool never creates it)" % forge_db)
    rows = []
    for a in res["artifacts"]:
        primary = a["locations"][0]["path"]
        rel = os.path.relpath(primary, PROJECT) if primary.startswith(PROJECT) else primary
        meta = {
            "registered_by": "vm_registry.py (#455)",
            "status": a["status"], "states": a["states"],
            "locations": [os.path.relpath(l["path"], PROJECT) if l["path"].startswith(PROJECT)
                          else l["path"] for l in a["locations"]],
            "domains": a["domains"],
            "backing_file": a["backing_file"],
            "backing_exists": a["backing_exists"],
            "backing_recoverable_at": a["backing_recoverable_at"],
            "recoverability": recoverability(a),
            "virtual_size": a["virtual_size"],
        }
        rows.append((time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), a["name"], a["version"],
                     a["sha256"], KIND, a["size"], rel, json.dumps(meta, sort_keys=True)))
    if dry:
        return 0, len(rows)
    con = sqlite3.connect(forge_db, timeout=15)
    try:
        before = con.execute("SELECT count(*) FROM artifacts").fetchone()[0]
        con.executemany(
            "INSERT OR IGNORE INTO artifacts (ts,name,version,sha256,kind,size,filename,meta) "
            "VALUES (?,?,?,?,?,?,?,?)", rows)
        con.commit()
        after = con.execute("SELECT count(*) FROM artifacts").fetchone()[0]
    finally:
        con.close()
    return after - before, len(rows)


def gate_status(res, forge_db):
    """What resolver.py can currently SEE, asked of the same table its probe reads.

    Opened `immutable=1` — read-only with no sidecar files (the #153 lesson; resolver.py:340-345).
    """
    out = {"forge_db": forge_db, "exists": os.path.isfile(forge_db), "visible": [], "invisible": []}
    if not out["exists"]:
        out["note"] = "no forge ledger on this host — resolver.py's forge-artifacts probe has nothing to read"
        out["invisible"] = [a["sha256"] for a in res["artifacts"]]
        return out
    con = sqlite3.connect("file:%s?immutable=1" % forge_db, uri=True)
    try:
        have_tbl = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='artifacts'").fetchone()
        if not have_tbl:
            out["note"] = "forge ledger has no `artifacts` table — the probe cannot answer"
            out["invisible"] = [a["sha256"] for a in res["artifacts"]]
            return out
        for a in res["artifacts"]:
            hit = con.execute("SELECT filename FROM artifacts WHERE lower(sha256) = ?",
                              (a["sha256"].lower(),)).fetchall()
            (out["visible"] if hit else out["invisible"]).append(a["sha256"])
    finally:
        con.close()
    return out


# ── the report ───────────────────────────────────────────────────────────────────────────────────
def mib(n):
    if n is None:
        return "?"
    for unit, div in (("T", 1 << 40), ("G", 1 << 30), ("M", 1 << 20), ("K", 1 << 10)):
        if n >= div:
            return "%.1f%s" % (n / div, unit)
    return "%dB" % n


def short(p):
    """A path shown relative to the project when it lives there, else with ~ for $HOME."""
    if p is None:
        return "(none)"
    if p.startswith(PROJECT + os.sep):
        return os.path.relpath(p, PROJECT)
    if p.startswith(HOME + os.sep):
        return "~" + p[len(HOME):]
    return p


def report(res, gate, ticket):
    L = []
    A = L.append
    A("VM REGISTRY — the lab as it actually is        %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
    A("  lab: %s     blob stores: %s, %s" % (short(res["vm_dir"]), short(res["large_blobs"]),
                                             short(res["shard_blobs"])))
    A("")

    A("DOMAINS (libvirt %s) — what each VM WANTS, and whether it resolves" % LIBVIRT_URI)
    if res["domain_note"]:
        A("  (unavailable) %s" % res["domain_note"])
    elif not res["domains"]:
        A("  (none defined)")
    for d in res["domains"]:
        st = res["domain_states"].get(d["domain"], "?")
        A("  %-22s [%s]" % (d["domain"], st))
        if d.get("error"):
            A("      ! %s" % d["error"])
        for disk in d["disks"]:
            A("      %-6s %-12s wants: %s" % (disk["device"], disk["state"], short(disk["path"])))
            if disk["state"] == "STALE-PATH":
                A("      %-19s bytes ARE at: %s   (%s)" % ("", short(disk["actual_path"]), disk["actual_rule"]))
            elif disk["state"] == "MISSING":
                A("      %-19s bytes: NOT FOUND on this host" % "")
        if not d["disks"] and not d.get("error"):
            A("      (no disks)")
    A("")

    A("ARTIFACTS — one row per DISTINCT image (deduped by sha256), tagged kind=%r" % KIND)
    A("  %-13s %-28s %-6s %8s  %-15s %s" % ("sha256", "name", "fmt", "size", "status", "locations"))
    for a in res["artifacts"]:
        nm = a["name"] if len(a["name"]) <= 28 else a["name"][:27] + "…"
        A("  %-13s %-28s %-6s %8s  %-15s %d" % (
            a["sha256"][:SHORT], nm, a["format"], mib(a["size"]),
            a["status"], len(a["locations"])))
        for loc in a["locations"]:
            A("      at %s   [%s]" % (short(loc["path"]), loc["store"]))
        extra = [s for s in a["states"] if s != a["status"]]
        if extra:
            A("      also: %s" % ", ".join(extra))
        if a["domains"]:
            A("      domains: %s" % ", ".join(a["domains"]))
        if a["backing_file"]:
            rec = recoverability(a)
            A("      backing: %s   base %s" % (
                short(a["backing_resolved"] or a["backing_file"]),
                "PRESENT" if a["backing_exists"] else "MISSING (%s)" % rec))
            if a["backing_recoverable_at"]:
                A("      base bytes ARE at: %s   (%s)" % (short(a["backing_recoverable_at"]),
                                                          a["backing_recoverable_rule"]))
        for r in a["referrers"]:
            A("      referrer %s wants it at %s" % (r["by"], short(r["wants"])))
    if not res["artifacts"]:
        A("  (none found)")
    A("")

    if res["skipped"]:
        A("SKIPPED — present in a scanned directory but NOT a VM image (by content, not by name)")
        # Grouped, not listed: the sharded store holds ~84 non-image blobs (wheels, xz archives, run
        # outputs) and printing each would bury the lab under its own inventory. Every skipped path
        # and reason is in --json; anything skipped in the LAB itself is always named, because a VM
        # image the tool refused to register is exactly what a reader needs to see.
        groups = {}
        for s in res["skipped"]:
            groups.setdefault((s["store"], s["reason"]), []).append(s)
        for (store, reason), items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            A("  %-13s %3d file(s)  %s" % (store, len(items), reason))
            if store == "lab" or len(items) <= 3:
                for s in items:
                    A("      %-58s %8s" % (short(s["path"]), mib(s.get("size"))))
        A("  (every skipped path and reason is in --json)")
        A("")
    if res["reclaimed"]:
        A("RECLAIMED — not image-shaped, but the lab vouches for them (a domain or a chain names them)")
        for p in res["reclaimed"]:
            A("  %s" % short(p))
        A("")
    if res["filename_lies"]:
        A("!! BLOB FILENAMES THAT LIE (--verify-blobs): the name is not the content address")
        for x in res["filename_lies"]:
            A("  %s  says %s.. but hashes to %s.." % (short(x["path"]), x["filename_says"][:SHORT],
                                                      x["bytes_are"][:SHORT]))
        A("")

    A("DIRECTORY SERVICE — what tools/resolver.py (#193) can SEE")
    A("  resolver.py's forge-artifacts probe reads `artifacts` in the FORGE ledger")
    A("    %s   (resolver.py:551-553, db at resolver.py:260-261)" % short(gate["forge_db"]))
    A("  `artifact.record` writes `ticket_artifacts` in the CONGRUENCY state db")
    A("    (migrations/0014_ticket_artifacts.sql:7-26) — resolver.py never reads that table.")
    if gate.get("note"):
        A("  %s" % gate["note"])
    A("  visible to resolver.py now: %d of %d image(s)" % (len(gate["visible"]), len(res["artifacts"])))
    if gate["invisible"]:
        A("  INVISIBLE (resolver.py <sha256> returns 0 for these): %d" % len(gate["invisible"]))
        for s in gate["invisible"][:6]:
            A("      %s.." % s[:SHORT])
        if len(gate["invisible"]) > 6:
            A("      ... and %d more" % (len(gate["invisible"]) - 6))
        A("  to close it:  python3 tools/vm_registry.py --forge-ledger")
        A("  (--record alone populates ticket_artifacts and does NOT change this line)")
    else:
        A("  the gate is CLOSED — every image resolves through the forge-artifacts probe.")
    A("")
    A("  ticket_artifacts (via artifact.record, ticket #%d): %s" % (
        ticket, res.get("recorded_note",
                        "nothing recorded THIS run — pass --record. (This line reports this run "
                        "only; it does not read the table, so it never claims the table is empty. "
                        "Ask it directly: rest.php?route=artifact.list&ticket_id=%d)" % ticket)))
    return "\n".join(L)


# ── selftest ─────────────────────────────────────────────────────────────────────────────────────
def synth(td):
    """A synthetic lab in a throwaway temp dir: one LIVE chain, one ORPHANED-DELTA, one COPY pair,
    one STALE-PATH. Returns None on success, or a NAMED reason to skip."""
    if not have("qemu-img"):
        return "qemu-img is not on PATH — the synthetic lab cannot be built"
    lab = os.path.join(td, "vm")
    os.makedirs(lab)

    # LIVE: a delta whose base is present, right beside it.
    base = os.path.join(lab, "live-base.img")
    rc, _o, e = run("qemu-img", "create", "-f", "qcow2", base, "8M")
    if rc != 0:
        return "qemu-img create failed: %s" % e.strip()[:120]
    rc, _o, e = run("qemu-img", "create", "-f", "qcow2", "-b", base, "-F", "qcow2",
                    os.path.join(lab, "live-delta.qcow2"))
    if rc != 0:
        return "qemu-img create -b failed: %s" % e.strip()[:120]

    # ORPHANED-DELTA: a base that is nowhere. -u (unsafe) is REQUIRED to name a backing file that
    # does not exist, and -u makes the size parameter mandatory (qemu-img cannot probe an absent
    # base for it) — hence the explicit 8M.
    rc, _o, e = run("qemu-img", "create", "-f", "qcow2", "-b", os.path.join(td, "gone", "nowhere.img"),
                    "-F", "qcow2", "-u", os.path.join(lab, "orphan.qcow2"), "8M")
    if rc != 0:
        return "qemu-img create -u failed: %s" % e.strip()[:120]

    # COPY: the same bytes in two places (a second 'store' dir stands in for large-blobs).
    twin = os.path.join(lab, "twin.qcow2")
    rc, _o, e = run("qemu-img", "create", "-f", "qcow2", twin, "16M")
    if rc != 0:
        return "qemu-img create twin failed: %s" % e.strip()[:120]
    blobs = os.path.join(td, "large-blobs")
    os.makedirs(blobs)
    with open(twin, "rb") as fh:
        raw = fh.read()
    with open(os.path.join(blobs, hashlib.sha256(raw).hexdigest()), "wb") as fh:
        fh.write(raw)

    # STALE-PATH: a delta whose backing names <td>/moved/stale-base.img, while those bytes live in
    # the lab. The rebase rule cannot fire (the path holds no '/config/vm/'), so this exercises the
    # by-basename inference.
    stale_base = os.path.join(lab, "stale-base.img")
    rc, _o, e = run("qemu-img", "create", "-f", "qcow2", stale_base, "24M")
    if rc != 0:
        return "qemu-img create stale-base failed: %s" % e.strip()[:120]
    rc, _o, e = run("qemu-img", "create", "-f", "qcow2", "-b", os.path.join(td, "moved", "stale-base.img"),
                    "-F", "qcow2", "-u", os.path.join(lab, "stale-delta.qcow2"), "24M")
    if rc != 0:
        return "qemu-img create stale-delta failed: %s" % e.strip()[:120]

    # a NON-image, to prove the content classifier excludes it
    with open(os.path.join(lab, "notes.img"), "wb") as fh:
        fh.write(b"this is not a disk image\n" * 64)
    return None


def selftest():
    import tempfile
    ok, fail, skip = [], [], []

    def check(name, cond, detail=""):
        (ok if cond else fail).append(name)
        print("  %-4s %s%s" % ("PASS" if cond else "FAIL", name, ("   " + detail) if detail else ""))

    print("vm_registry --selftest — a synthetic lab in a throwaway temp dir")
    with tempfile.TemporaryDirectory() as td:
        reason = synth(td)
        if reason:
            print("  SKIP  %s" % reason)
            print("selftest: SKIPPED (named reason above) — 0 failed")
            return 0
        lab = os.path.join(td, "vm")
        blobs = os.path.join(td, "large-blobs")
        shard = os.path.join(td, "shard")           # deliberately absent -> a store that is not there
        before = snapshot(td)

        res = scan(lab, blobs, shard, uri="test:///default")
        by_name = {a["name"]: a for a in res["artifacts"]}
        gate = gate_status(res, os.path.join(td, "no-such-forge.db"))

        check("scan found the 6 synthetic images", len(res["artifacts"]) == 6,
              "found %d: %s" % (len(res["artifacts"]), sorted(by_name)))
        check("a qcow2 with a PRESENT base -> LIVE",
              by_name.get("live-delta", {}).get("status") == "LIVE",
              "got %r" % by_name.get("live-delta", {}).get("status"))
        check("...and the base of that live chain is LIVE too (not UNREFERENCED)",
              by_name.get("live-base", {}).get("status") == "LIVE",
              "got %r" % by_name.get("live-base", {}).get("status"))
        check("...the base knows which delta uses it",
              by_name.get("live-base", {}).get("used_as_base_by") ==
              [by_name.get("live-delta", {}).get("sha256")])
        check("a qcow2 with a MISSING base -> ORPHANED-DELTA",
              by_name.get("orphan", {}).get("status") == "ORPHANED-DELTA",
              "got %r" % by_name.get("orphan", {}).get("status"))
        check("that orphan is reported UNRECOVERABLE",
              recoverability(by_name.get("orphan", {"states": []})) == "unrecoverable")
        twin = by_name.get("twin")
        check("two byte-identical files -> ONE artifact", twin is not None and
              len([a for a in res["artifacts"] if a["sha256"] == (twin or {}).get("sha256")]) == 1)
        check("...with TWO locations recorded", twin is not None and len(twin["locations"]) == 2,
              "locations=%s" % (len(twin["locations"]) if twin else "n/a"))
        check("...and status COPY", (twin or {}).get("status") == "COPY",
              "got %r" % (twin or {}).get("status"))
        stale = by_name.get("stale-base")
        check("a file whose referrer points at a moved path -> STALE-PATH",
              (stale or {}).get("status") == "STALE-PATH", "got %r" % (stale or {}).get("status"))
        check("...and the report names WANTS vs ACTUALLY",
              bool(stale and stale["referrers"] and stale["referrers"][0]["actual"] == stale["locations"][0]["path"]))
        check("a non-image .img is NOT registered (content, not extension)",
              any(s["path"].endswith("notes.img") for s in res["skipped"]) and
              "notes.img" not in [os.path.basename(l["path"]) for a in res["artifacts"] for l in a["locations"]])
        check("an absent blob store is a fact, not a crash", os.path.isdir(shard) is False)
        check("every artifact is tagged kind=%r" % KIND,
              all(a["kind"] == KIND for a in res["artifacts"]))
        check("version defaults to the short sha",
              all(a["version"] == a["sha256"][:SHORT] for a in res["artifacts"]))
        check("an absent forge ledger -> every image INVISIBLE, no crash",
              len(gate["invisible"]) == len(res["artifacts"]) and not gate["visible"])

        # the recorder, driven against an in-process stub: no network, no live db.
        posted = []
        done, skipped_rows = record_all(res, 999, key=None,
                                        poster=lambda o: posted.append(o),
                                        lister=lambda: set())
        check("--record posts one artifact.record per image",
              len(posted) == len(res["artifacts"]) and len(done) == len(posted))
        check("...each with ticket_id/name/version/forge_sha/kind",
              all(set(p) == {"ticket_id", "name", "version", "forge_sha", "kind"} and
                  p["kind"] == KIND for p in posted))
        posted2 = []
        done2, skip2 = record_all(res, 999, key=None, poster=lambda o: posted2.append(o),
                                  lister=lambda: {(a["name"], a["version"], a["sha256"], KIND)
                                                  for a in res["artifacts"]})
        check("--record is IDEMPOTENT (already-recorded rows are skipped)",
              posted2 == [] and len(skip2) == len(res["artifacts"]))

        n_ins, n_rows = forge_ledger_register(res, os.path.join(td, "no-such-forge.db"), dry=True)
        check("--forge-ledger dry run builds a row per image", n_rows == len(res["artifacts"]) and n_ins == 0)

        after = snapshot(td)
        stray = sorted(set(after) - set(before))
        check("the scan created NO file in the lab", not stray, "created: %s" % stray)
        check("the scan modified NO file in the lab",
              all(before[p] == after[p] for p in before if p in after))

    print("selftest: %d passed, %d failed%s" % (len(ok), len(fail),
                                                (", %d skipped" % len(skip)) if skip else ""))
    return 1 if fail else 0


def snapshot(root):
    """{path: (size, mtime_ns, sha1-of-first-4k)} for every file under root — the before/after proof
    that a read-only pass really was read-only (the #153 lesson: test it the way an adversary will)."""
    out = {}
    for base, _dirs, files in os.walk(root):
        for f in files:
            p = os.path.join(base, f)
            try:
                st = os.stat(p)
                with open(p, "rb") as fh:
                    head = hashlib.sha1(fh.read(4096)).hexdigest()
                out[p] = (st.st_size, st.st_mtime_ns, head)
            except OSError:
                out[p] = ("unreadable",)
    return out


# ── cli ──────────────────────────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(
        prog="vm_registry.py",
        description="The VM registry (#455): every VM image, tagged kind='forge-vm', deduped by "
                    "sha256, with its resolved state. READ-ONLY unless --record/--forge-ledger.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Default output is a table and writes NOTHING. --record registers through the "
               "governed artifact.record route (ticket_artifacts). --forge-ledger registers in "
               "forge.db, the table tools/resolver.py actually probes — the only thing that makes "
               "an image findable by sha256. See the module docstring for why those are different.")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--record", action="store_true",
                    help="register each image via artifact.record (ticket_artifacts). Idempotent.")
    ap.add_argument("--forge-ledger", action="store_true",
                    help="additively register each image in forge.db's artifacts table (INSERT OR "
                         "IGNORE, copies no bytes) — closes the #193 resolver gate")
    ap.add_argument("--gate-check", action="store_true",
                    help="exit 1 unless every image is visible to resolver.py's forge-artifacts probe")
    ap.add_argument("--verify-blobs", action="store_true",
                    help="re-hash the blob stores instead of trusting <sha256> filenames")
    ap.add_argument("--ticket", type=int, default=TICKET, help="ticket id to record against (default: %d)" % TICKET)
    ap.add_argument("--vm-dir", default=VM_DIR, help="the image lab (default: %s)" % VM_DIR)
    ap.add_argument("--large-blobs", default=LARGE_BLOBS, help="flat blob store (default: %s)" % LARGE_BLOBS)
    ap.add_argument("--shard-blobs", default=SHARD_BLOBS, help="sharded blob store (default: %s)" % SHARD_BLOBS)
    ap.add_argument("--forge-db", default=FORGE_DB, help="the forge ledger (default: %s)" % FORGE_DB)
    ap.add_argument("--libvirt-uri", default=LIBVIRT_URI, help="libvirt connect uri (default: %s)" % LIBVIRT_URI)
    ap.add_argument("--selftest", action="store_true",
                    help="synthetic lab in a temp dir; no network, no live db, no writes outside it")
    a = ap.parse_args()

    if a.selftest:
        return selftest()

    if not os.path.isdir(a.vm_dir):
        raise Fault("no image lab at %s — pass --vm-dir or set JAZZ_VM_DIR (this tool never "
                    "creates it)" % a.vm_dir)

    res = scan(a.vm_dir, a.large_blobs, a.shard_blobs, uri=a.libvirt_uri, verify=a.verify_blobs)

    if a.record:
        key = _secret("CONGRUENCY_API_KEY")
        try:
            done, skipped_rows = record_all(res, a.ticket, key)
            res["recorded_note"] = "%d recorded, %d already present" % (len(done), len(skipped_rows))
        except (urllib.error.URLError, OSError) as e:
            raise Fault("artifact.record unreachable at %s (%s) — is the congruency server up?"
                        % (CONG, e))
    if a.forge_ledger:
        n_new, n_rows = forge_ledger_register(res, a.forge_db)
        res["forge_ledger_note"] = "%d new row(s) of %d image(s) (INSERT OR IGNORE)" % (n_new, n_rows)

    gate = gate_status(res, a.forge_db)

    if a.json:
        print(json.dumps({"generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
                          "kind": KIND, "ticket": a.ticket,
                          "vm_dir": res["vm_dir"], "domains": res["domains"],
                          "domain_states": res["domain_states"], "domain_note": res["domain_note"],
                          "artifacts": [dict(x, recoverability=recoverability(x)) for x in res["artifacts"]],
                          "skipped": res["skipped"], "reclaimed": res["reclaimed"],
                          "filename_lies": res["filename_lies"],
                          "directory_service": gate,
                          "recorded": res.get("recorded_note"),
                          "forge_ledger": res.get("forge_ledger_note")},
                         indent=2, sort_keys=False))
    else:
        print(report(res, gate, a.ticket))
        if res.get("forge_ledger_note"):
            print("  forge ledger (--forge-ledger): %s" % res["forge_ledger_note"])

    if a.gate_check and gate["invisible"]:
        print("gate-check: FAILED — %d image(s) invisible to resolver.py" % len(gate["invisible"]),
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Fault as e:
        print("vm_registry: %s" % e, file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as e:  # noqa: BLE001 — the registry's contract: file a report, exit non-zero
        bug_report("main", e, "python3 tools/vm_registry.py " + " ".join(sys.argv[1:]), e)
        print("vm_registry: unexpected error: %r (a bug report was filed)" % e, file=sys.stderr)
        sys.exit(2)
