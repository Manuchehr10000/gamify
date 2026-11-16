#!/usr/bin/env python3
"""Ship kit — the CTO check and its helpers.

Subcommands (run from the project root, or pass --root):
  setup       detect the backend and frontend folders, write ship.json (with the repo's name), copy templates and the CI
              files; refuses off dev, without origin/dev, or when the code found is another repo's (D90)
  link        store the project's Notion tracker in ship.json
  gate-dev    decide whether the commits since a ref may reach dev (the push gate and CI both use it)
  ci          the check GitHub runs on every push to dev and main, before any deploy
  ci-env      print the backend and frontend folders for the CI workflow
  ci-install  copy the CI workflow, this script and the deploy notes into .github/
  pickup      save a contract taken from the tracker as contracts/NNN-name.md, status building; the row's Repo
              column must name this repo (D89)
  quick       write a quick fix's contract (D92) from the owner's own words, status building, with no tracker row first
  split       save the sub-contracts Claude wrote for a chain head as draft contracts, checked against the head
  go          the owner read the split: every draft sub-piece becomes ready, in build order
  chain-next  pick up the next ready sub-piece of a chain (status building)
  chain-sync  move a head to on-dev once every sub-piece is on dev, or to dropped once every one is dropped
  chain-status list a chain: its head and each sub-piece with its state
  next-pick   which Ready row of this repo may build now: its Depends on rows are on dev or done (D93)
  claim-check after pickup wrote Building: does the row, read back, hold this session's Claim? Two sessions that
              took one row find out here, and the one that lost removes its uncommitted contract (issue #30).
              --recheck, before the push: is the row still this session's? Removes nothing
  sync-dev    rebase the building piece onto origin/dev and move its Base there; stops when another piece changed the
              same files (D93)
  ci-wait     wait for GitHub's Ship check on a commit pushed to dev: 0 passed · 1 failed or timed out · 2 can't ask
  set-tracker store a tracker row's URL in a contract (Code writes the rows of a chain's sub-pieces)
  check       run size + stack + leftovers against the building contract and print one screen
  size        count screens, endpoints and tables built since the contract's base commit
  stack       compare dependency files and new imports against the stack list
  leftovers   run vulture and knip; report findings on lines the piece added
  stack-add   add a package the owner approved to the stack list
  ondev       mark the building contract on-dev, once its commits are on origin/dev
  done        mark an on-dev contract done (the client accepted it)
  drop        drop a contract the client rejected (its code gets deleted)
  status      list every contract and its state
  copy-check  compare the tracker's copy of a contract with the repo file
  copy-mark   record that the tracker's copy now matches the repo file
  copy-render print the exact Notion text for a contract's tracker copy
  map         rebuild the build map (contracts/map/build-map.md) from dev: tables with key columns, endpoints and
              screens, counted by the size check's code; keeps the few lines Claude wrote on decisions and gaps (D91)
  map-status  is the map up to date with dev (0), stale (1) or missing (3), and does its Notion copy need writing
  map-render  print the exact Notion text for the build map's read-only copy
  map-copy-check compare the build map's Notion copy with the repo file (exit codes as copy-check)
  map-copy-mark record that the Notion copy now matches the map
  link-map    store the build map's Notion sub-page in ship.json
  env-check   exit 1 when a commit carries an env file (.env, .env.*; the example files are allowed)
  secret-scan  scan new commits for secrets with gitleaks: the push gate (every branch) and GitHub run it (D67–D70)
  secret-allow the owner's one-line clearing of a false alarm, written to .gitleaksignore (D68)
  adopt       the owner's one-line acceptance of code already on dev that no piece covers; the dev check starts
              after it (issue #40)
  lesson      record what stops a fixed bug next time: a test, a CLAUDE.md fact or a kit issue (D78)
  review-plan  the security review's scope (risky files, decided here), spend level, models and the reviewer's diff
  review-skip  write the skip note for a piece that changed no risky file
  review-write save the review from the checker's JSON, stamped with the code as it is now
  review-waive the owner's one-line waiver of a finding
  review-status the piece's Security line, and whether the review lets it reach dev
  review-waivers the waived findings not yet released: the release note lists them

The security review (D66): every piece with code needs contracts/reviews/<contract>.md, stamped with the code it
reviewed; the gate and GitHub refuse a missing or stale one, and an open critical or major finding.
A contract moves draft/ready → building → on-dev → done, or → dropped.
Parallel builds (D93): one piece builds per session (a cloud session, or a desktop worktree), not per repo. A contract's
`Depends on:` line names the pieces it needs on dev first; a piece with none builds alongside the others. Before its
check, sync-dev brings it up to date with what other sessions pushed.
A chain (D61): one head contract from chat (`Chain: head`), split by Claude Code into sub-contracts (`Head: <name>`)
that build one after another. The head is picked up like a piece, the split is saved as draft sub-pieces, the owner's
"go" makes them ready, and each sub-piece then goes building → on-dev with the usual check and push. The head owns
no code itself: it moves to on-dev when every sub-piece is on dev, and the client's one verdict on the head closes
them all. A head that is building or on dev blocks release like any piece.
The quick lane (D92): a one-line fix the owner asks for in Claude Code, in their own words. `quick` writes its contract
(`Quick: yes`, Size 0, no Fixes line); the check, the push gate and GitHub then hold it to the kit's limits: at most
QUICK_MAX_LINES lines added and as many removed, in at most QUICK_MAX_FILES files that already existed, and no new,
deleted or binary file, no dependency, deploy, CI workflow, env, SQL or migration file. ship.json can't raise them. It goes
building → on-dev → done like a piece; the owner's own look on dev is its verdict.
Exit codes: 0 pass · 1 fail · 2 usage, contract or tool error · 3 no contract building (and product code changed).
pickup and claim-check exit 5 when another session took the row (issue #30): pick another one.
copy-check and map-copy-check exit codes: 0 in-sync · 10 refresh · 11 no-record · 12 hand-edited; copy-check also
5 taken: the row's copy holds another session's Claim, so it is never overwritten.
Only python3 is required. vulture and knip are needed for `leftovers`; gitleaks 8 for `secret-scan` (every push).

ship.json folders: python_dir / node_dir are null (none), "." (the project root) or a subfolder.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import difflib
import fnmatch
import hashlib
import html
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

KIT_VERSION = "0.18.0"  # keep equal to plugins/mg-ship-kit/.claude-plugin/plugin.json
CONFIG = "ship.json"
CONTRACTS = "contracts"
SYNC_FILE = "notion-sync.json"  # in .ship/ (git-ignored): hash of the repo text last copied to the tracker
STATES = ("draft", "ready", "building", "on-dev", "done", "dropped")
BANNER_MARK = "Read-only copy of"  # first line of every tracker copy Claude Code writes
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "env", "dist", "build", "__pycache__", ".ship"}
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"  # git's empty tree: "since nothing"
ZERO_SHA = "0" * 40  # GitHub's `before` when a push creates the branch
TRACKS = ("devops", "cloudflare")  # D51, D94: picked per project from the start questions
DROPPED_TRACKS = ("railway",)  # D96: never run; a page that still names it sets its track again in chat
DEPLOY_WORKFLOW = ".github/workflows/deploy.yml"  # the cloudflare track's deploy, copied once (D97)
CF_BOOKKEEPING = ("deploy/", DEPLOY_WORKFLOW)  # the deploy files setup copies, listed in ship.json (D97)
CI_WORKFLOW = ".github/workflows/ship-check.yml"
CI_SCRIPT = ".github/ship/ship_check.py"
CI_NOTES = ".github/ship/README.md"
CLOUD_SETTINGS = ".claude/settings.json"  # declared the plugin for cloud sessions (D59); setup now takes the kit out (D65)
SECRETS_WORKFLOW = ".github/workflows/ship-secrets.yml"  # the secret scan on every other branch (D70)
CI_GITLEAKS_CONFIG = ".github/ship/gitleaks.toml"
GITLEAKS_IGNORE = ".gitleaksignore"  # the owner's allowed false alarms, one fingerprint each (D68)
GITLEAKS_VERSION = "8.30.1"  # keep equal to the pin in templates/ci/*.yml and the kit's own test workflow
GITLEAKS_HINT = (f"install gitleaks {GITLEAKS_VERSION} once on this machine: `brew install gitleaks` on a Mac, or "
                 f"the file for your system from https://github.com/gitleaks/gitleaks/releases/tag/v{GITLEAKS_VERSION}, "
                 "put on your PATH")
ALLOW_MARK = "# allowed "  # the line secret-allow writes above each fingerprint
PROJECT_CI_DIRS = (".github/workflows/", ".github/actions/")  # code GitHub runs: product code unless the kit's own
BOOKKEEPING_FILES = ("ship.json", "CLAUDE.md", ".gitignore", CLOUD_SETTINGS, GITLEAKS_IGNORE)
KIT_MARKETPLACE = "ship-kit"  # the name in .claude-plugin/marketplace.json
ENV_EXAMPLES = (".env.example", ".env.sample", ".env.template")  # env files that hold no secrets: these may be committed
GITIGNORE_ENV = [".env", ".env.*"] + [f"!{n}" for n in ENV_EXAMPLES]  # the lines setup adds to .gitignore
# The words line that opens a contract's body; its four labels follow the Backlog's Source (ship-spec). A chain's
# sub-piece opens with "From the head:" instead, since it traces to the head contract, not to the client (D61).
WORDS_LABEL_RE = re.compile(r"^\**(client['’]s words|from my notes on the client|users['’] words|owner['’]s words|from the head)\b", re.I)
HEADER_KEYS = ("Status", "Base", "Approved", "Tracker", "Removing", "Chain", "Head", "Lesson", "Repo", "Quick",
               "Depends on", "Claim")  # the lines above a contract's body
SETUP_BRANCH = "dev"  # setup's files land on dev, where the check runs (D90)
GO_PENDING = "pending: the owner's go on the chain"  # a sub-piece's Approved line between the split and the go
MAX_SUBS = 6  # a chain is two to six sub-pieces; more is two chains
QUICK_MAX_FILES = 3  # the quick lane (D92): the kit's limits, never the project's — ship.json can't raise them
QUICK_MAX_LINES = 10  # lines added, and lines removed, across the whole quick fix
MIGRATION_RE = re.compile(r"(^|/)[^/]*(migration|alembic)[^/]*(/|$)", re.I)
CI_NEVER_STARTED_S = 180  # ci-wait gives up this soon when no run of the check exists at all for the commit
SECRET_FIX = ("Take the key out of the code (read it from an environment file) and take it out of these commits "
              "before pushing: for the last commit, fix it and `git commit --amend`; for older ones, `git reset --soft "
              "<the commit before them>` and commit again. If the key was ever pushed anywhere, replace it at its "
              "source: it's exposed. If it's not a secret (a test value, an example), only the owner may clear it: on "
              "their one-line yes, run `ship_check.py secret-allow <fingerprint> --by <owner> --why \"<their words>\"`. "
              f"Never edit {GITLEAKS_IGNORE} by hand, and a `gitleaks:allow` comment clears nothing.")
ENV_FIX = ("Secrets never go in git (D4). Take the file out of git but keep it on disk (`git rm --cached <file>`), "
           "check that .gitignore has the env lines (setup adds them), commit, then push again. If it ever held a real "
           "password or key, change it: git history keeps the old file.")

# Import names that differ from the package name on PyPI.
DEFAULT_ALIASES = {
    "pillow": "PIL", "pyjwt": "jwt", "python-dotenv": "dotenv", "python-multipart": "multipart",
    "beautifulsoup4": "bs4", "scikit-learn": "sklearn", "opencv-python": "cv2", "pyyaml": "yaml",
    "psycopg2-binary": "psycopg2", "python-dateutil": "dateutil", "msgpack-python": "msgpack",
}
def python_stdlib(names: frozenset[str] | None = None) -> set[str]:
    """The standard library's top-level module names, from the Python that runs the check.

    Python 3.10+ lists them in sys.stdlib_module_names. Older Pythons (macOS ships 3.9 as /usr/bin/python3)
    don't, and an empty list made every `import json` look like a new package: read the library folder instead.
    """
    if names is None:
        names = getattr(sys, "stdlib_module_names", None)
    if names:
        return set(names)
    import sysconfig
    found = set(sys.builtin_module_names)
    lib = Path(sysconfig.get_paths()["stdlib"])
    for folder in (lib, lib / "lib-dynload"):
        if not folder.is_dir():
            continue
        for p in folder.iterdir():
            if p.name in ("site-packages", "dist-packages", "__pycache__") or p.name.startswith("."):
                continue
            if p.is_dir():
                if (p / "__init__.py").exists():
                    found.add(p.name)
            elif p.suffix in (".py", ".so", ".pyd"):
                found.add(p.name.split(".")[0])
    return found


PY_STDLIB = python_stdlib() | {"typing_extensions"}
NODE_BUILTINS = {"fs", "path", "os", "url", "http", "https", "crypto", "child_process", "util", "events",
                 "stream", "buffer", "assert", "process", "module", "readline", "zlib", "net", "tls"}
VULTURE_EXCLUDE = ["*/migrations/*", "*/alembic/*", "*/tests/*", "*/test/*", "*/models/*",
                   "*/venv/*", "*/.venv/*", "*/node_modules/*"]
VULTURE_IGNORE_DECORATORS = "@router.*,@app.*,@*.route,@pytest.fixture,@validator,@field_validator,@model_validator"
VULTURE_IGNORE_NAMES = ("upgrade,downgrade,revision,down_revision,branch_labels,depends_on,lifespan,"
                        "model_config,Config,orm_mode,from_attributes,json_schema_extra,__tablename__,__table_args__")


# ---------------------------------------------------------------- helpers
def sh(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=str(cwd) if cwd else None, text=True, capture_output=True)


def die(msg: str, code: int = 2) -> None:
    print(f"ship: {msg}", file=sys.stderr)
    sys.exit(code)


def load_config(root: Path) -> dict:
    p = root / CONFIG
    if not p.exists():
        die(f"Ship isn't set up here: there's no {CONFIG} in {root}. Run /mg-ship-kit:setup first.")
    return json.loads(p.read_text())


def save_config(root: Path, cfg: dict) -> None:
    (root / CONFIG).write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n")


def walk_files(base: Path):
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for f in filenames:
            yield Path(dirpath) / f


def norm_pkg(name: str) -> str:
    return re.sub(r"[-_.]+", "_", name.strip().lower())


def in_dir(f: str, d: str | None) -> bool:
    """Is repo-relative path f inside folder d? None = never, '.' = always."""
    if d is None or d == "":
        return False
    if d == ".":
        return True
    d = d.strip("/")
    return f == d or f.startswith(d + "/")


def dir_path(root: Path, d: str | None) -> Path:
    return root if d in (None, "", ".") else root / d


def is_test_file(f: str) -> bool:
    parts = f.replace("\\", "/").split("/")
    name = parts[-1].lower()
    return any(p in ("tests", "test", "__tests__", "spec", "fixtures") for p in parts[:-1]) or \
        name.startswith("test_") or ".test." in name or ".spec." in name or name.endswith("_test.py")


# ---------------------------------------------------------------- contracts
PLACEHOLDER_RE = re.compile(r"<[^>]*>")
BULLET = r"(?:[-*+]|\d+[.)])"  # a list item as people type it: -, *, + or 1. / 1)


def key_re(key: str) -> str:
    """A header key as people type it: any case, bold or not, spaces around the words and before the colon."""
    words = r"[ \t]+".join(re.escape(w) for w in key.split())
    return rf"[ \t]*\**[ \t]*{words}[ \t]*\**[ \t]*:\**"


def heading_re(name: str) -> str:
    """A heading line as people type it: any case, spaces anywhere, an optional colon at the end."""
    words = r"[ \t]+".join(re.escape(w) for w in name.split())
    return rf"^[ \t]*#{{1,4}}[ \t]*{words}[ \t]*:?[ \t]*$"


def section(text: str, name: str) -> str | None:
    """The body under a `## <name>` heading, up to the next heading; None when there is no such heading."""
    m = re.search(heading_re(name) + r"(.*?)(?=^[ \t]*#{1,4}[ \t]*\S|\Z)", text, re.M | re.S | re.I)
    return m.group(1) if m else None


TITLE_RE = re.compile(r"^[ \t]*#[ \t]*contract[ \t]*:[ \t]*(.+?)[ \t]*$", re.M | re.I)


def field(text: str, key: str) -> str | None:
    m = re.search(rf"^{key_re(key)}[ \t]*(\S.*?)[ \t]*$", text, re.M | re.I)
    return m.group(1) if m else None


class Contract:
    def __init__(self, path: Path, text: str | None = None):
        self.path = path
        self.text = path.read_text(encoding="utf-8") if text is None else text  # text: the contract at a commit
        self.name = path.stem
        self.status = (self._field("Status") or "draft").lower()
        if self.status not in STATES:
            die(f"{self.name}: the Status {self.status!r} isn't one the kit knows. Use one of: {', '.join(STATES)}.")
        self.base = self._field("Base") or ""
        self.approved = self._field("Approved") or ""
        self.tracker = self._field("Tracker") or ""
        self.removing = self._field("Removing") or ""
        self.fixes = (self._field("Fixes") or "").strip()  # a bug fix: what broke, as the client said it (D77)
        self.lesson = (self._field("Lesson") or "").strip()  # what stops it next time (D78)
        self.is_head = (self._field("Chain") or "").strip().lower() == "head"  # a chain's head contract (D61)
        self.head = (self._field("Head") or "").strip()  # a sub-piece: the name of its head contract
        self.repo = (self._field("Repo") or "").strip()  # the repo the piece was picked up in (D89)
        self.quick = bool((self._field("Quick") or "").strip())  # a quick fix, written in Claude Code (D92)
        self.depends = parse_depends(self._field("Depends on"))  # D93: None (older than the line), [] (none), names
        self.claim = (self._field("Claim") or "").strip()  # this session's token on the row (issue #30)
        m = TITLE_RE.search(self.text)
        self.title = m.group(1) if m else self.name  # the tracker row's Piece title
        if self.is_head and self.head:
            die(f"{self.name} has both a `Chain: head` line and a `Head:` line. A contract is a chain head or part of a "
                "chain, not both: remove one of the lines.")
        self.size: dict[str, tuple[int, list[str]]] = {}
        self._parse_size()

    @property
    def kind(self) -> str:
        """'piece', 'head' or 'sub' — for messages."""
        return "head" if self.is_head else ("sub" if self.head else "piece")

    def _field(self, key: str) -> str | None:
        return field(self.text, key)

    def set_status(self, status: str, extra: dict[str, str | None] | None = None) -> None:
        """Rewrite the Status line (and any header fields in extra; None removes a field)."""
        text = re.sub(rf"^{key_re('Status')}.*$", lambda m: f"Status: {status}", self.text, count=1,
                      flags=re.M | re.I)
        for key, val in (extra or {}).items():
            pat = re.compile(rf"^{key_re(key)}.*(?:\n|\Z)", re.M | re.I)
            if val is None:
                text = pat.sub("", text, count=1)
            elif pat.search(text):
                text = pat.sub(lambda m, k=key, v=val: f"{k}: {v}\n", text, count=1)
            else:  # add it under the Status line
                text = re.sub(r"^Status:.*$", lambda m, k=key, v=val: f"{m.group(0)}\n{k}: {v}", text, count=1, flags=re.M)
        self.path.write_text(text, encoding="utf-8")
        self.text, self.status = text, status
        self.base = self._field("Base") or ""
        self.approved = self._field("Approved") or ""
        self.tracker = self._field("Tracker") or ""
        self.removing = self._field("Removing") or ""
        self.lesson = (self._field("Lesson") or "").strip()

    def _parse_size(self) -> None:
        self.size, problems = parse_size(self.text)
        if problems:
            die(f"{self.name}: " + "; ".join(problems) + ".")

    def check_ready(self) -> None:
        """A building contract must carry a base commit and a real approval line."""
        if self.status != "building":
            return
        if not self.base or PLACEHOLDER_RE.search(self.base):
            die(f"{self.name} has no Base commit. Its Base: line must name the commit the piece starts from.")
        if not is_approval(self.approved):
            die(f"{self.name} has no approval. A piece builds only after the owner approves it in one line, like "
                f"`{approval_example()}`, with the owner's own name.")

    def count_problems(self) -> list[str]:
        return count_problems(self.size)


ZERO_WORDS = r"none|zero|nothing|no|n/a|[-—–]"  # how people write a count of 0


def parse_size(text: str) -> tuple[dict[str, tuple[int, list[str]]], list[str]]:
    """A contract's `## Size` section as {kind: (count, named items)}, with every problem found in it. A count
    written as none, zero, no or a dash is 0, and a kind with no line at all is 0 too: the size check still holds
    the code to it, so a real table against a missing `Tables:` line fails there."""
    size: dict[str, tuple[int, list[str]]] = {}
    sec = section(text, "Size")
    if sec is None:
        return size, ["there's no Size section. Add one, like:\n       ## Size\n       Screens: 1\n       "
                      "- /reports\n       Endpoints: none\n       Tables: none"]
    problems, current = [], None
    for line in sec.splitlines():
        m = re.match(r"^\s*\**\s*(Screens|Endpoints|Tables)\s*\**\s*:\**\s*(\d+|" + ZERO_WORDS + r")(?![\w/])",
                     line, re.I)
        if m:
            current = m.group(1).lower()
            size[current] = (int(m.group(2)) if m.group(2).isdigit() else 0, [])
            continue
        if re.match(r"^\s*\**\s*(Screens|Endpoints|Tables)\s*\**\s*:", line, re.I):
            key = line.strip().split(':')[0].strip("* ")
            problems.append(f"the count after `{key}:` isn't a number. Write it like `{key}: 2` or `{key}: none`")
            current = None
            continue
        b = re.match(rf"^\s*{BULLET}\s+(.+?)\s*$", line)
        # Drop code and bold marks only: a lone `*` is a catch-all route, a real item
        item = re.sub(r"`|\*\*", "", b.group(1)).strip() if b else ""
        if b and current and item and not PLACEHOLDER_RE.fullmatch(item):
            size[current][1].append(item)
    for k in ("screens", "endpoints", "tables"):
        size.setdefault(k, (0, []))
    return size, problems


def count_problems(size: dict[str, tuple[int, list[str]]]) -> list[str]:
    """Where a count and its named items disagree, or an endpoint lacks its method. A chain splits by the
    names, so a head (and each sub-piece) must name every item it counts."""
    out = []
    for kind in ("screens", "endpoints", "tables"):
        if kind not in size:
            continue
        n, items = size[kind]
        if n != len(items):
            listed = f" ({', '.join(items)})" if items else ""
            fix = "add the missing ones" if n > len(items) else "remove the extra ones"
            out.append(f"{kind.capitalize()} says {n} but lists {len(items)}{listed}. Change the number to "
                       f"{len(items)}, or {fix}")
        if kind == "endpoints":
            out += [f"the endpoint {it!r} has no method. Write it with one, like `GET {it}`"
                    for it in items if not norm_endpoint(it)[0]]
    return out


LINK_RE = re.compile(r"https?://[^\s,`]+")


def parse_depends(line: str | None, titles: list[str] | None = None) -> list[str] | None:
    """A contract's `Depends on:` line (D93): None when it has none (a contract from before the line), [] for
    `none`, else the entries it lists. An entry is a piece name or a row link. A piece name may hold a comma, so a
    comma separates entries only between whole names: a name in backticks is one entry (ship-spec writes them so),
    and with the tracker's piece titles at hand, the longest title that fits at each place is one entry. Without
    titles, bare text splits on every comma (status only; pickup always passes the titles)."""
    if line is None:
        return None
    line = re.sub(r"\*\*", "", line).strip()
    if line.lower().strip("`. ") in ("none", "nothing", "-", "—", ""):
        return []
    known = sorted({t.strip() for t in titles or [] if t.strip()}, key=len, reverse=True)

    def starts(at: int) -> int:
        """The length of the whole entry that begins at `at` (a link or a known title), or 0."""
        rest = line[at:]
        m = LINK_RE.match(rest)
        if m:
            return m.end()
        for t in known:
            end = len(t)
            if rest[:end].lower() == t.lower() and (end == len(rest) or re.match(r"\s*(,|$)", rest[end:])):
                return end
        return 0

    out, i = [], 0
    while i < len(line):
        if line[i] in ", \t":
            i += 1
            continue
        if line[i] == "`":
            j = line.find("`", i + 1)
            j = len(line) if j < 0 else j
            out.append(line[i + 1:j].strip())
            i = j + 1
            continue
        n = starts(i)
        if n:
            out.append(line[i:i + n].strip())
            i += n
            continue
        # text no title fits: up to the next comma where a whole entry starts (or the end), quoted as is
        j = i
        while True:
            j = line.find(",", j + 1)
            if j < 0:
                j = len(line)
                break
            k = j + 1
            while k < len(line) and line[k] in " \t":
                k += 1
            if k >= len(line) or line[k] == "`" or starts(k) or not known:
                break
        out.append(line[i:j].strip())
        i = j + 1
    return [n for n in out if n]


def depends_line(names: list[str]) -> str:
    """The `Depends on:` value for these entries: a name with a comma goes in backticks, so it reads back whole."""
    return ", ".join(f"`{n}`" if "," in n else n for n in names) or "none"


def approval_example(short: bool = False) -> str:
    """An approval line to copy, dated today: `Approved: 2026-11-16 by Sam`, or `Sam 16 Nov` with short."""
    today = dt.date.today()
    return f"Sam {today.day} {today.strftime('%b')}" if short else f"Approved: {today.isoformat()} by Sam"


def is_approval(text: str) -> bool:
    """A real `Approved:` line: not empty, not a placeholder, not the kit's own 'pending the go' marker."""
    t = (text or "").strip()
    return bool(t) and not PLACEHOLDER_RE.search(t) and not t.lower().startswith("pending")


def contracts_dir(root: Path) -> Path:
    return root / CONTRACTS


def list_contracts(root: Path) -> list[Contract]:
    d = contracts_dir(root)
    if not d.exists():
        return []
    out = []
    for p in sorted(d.glob("*.md")):
        if p.name.upper().startswith("TEMPLATE") or p.name.upper() == "README.MD":
            continue
        out.append(Contract(p))
    titles = [c.title for c in out]  # read a Depends on name with a comma whole when it is a piece of this repo
    for c in out:
        c.depends = parse_depends(c._field("Depends on"), titles)
    return out


def building_pieces(cs: list[Contract]) -> list[Contract]:
    """The contracts that own code right now: building, and not a chain head (a head never owns code itself)."""
    return [c for c in cs if c.status == "building" and not c.is_head]


def open_heads(cs: list[Contract]) -> list[Contract]:
    """Chain heads whose chain is still running: picked up, not yet on dev."""
    return [c for c in cs if c.is_head and c.status == "building"]


def here_only(root: Path, cs: list[Contract]) -> list[Contract]:
    """The contracts not yet on origin/dev: picked up in this session and not pushed (D93). Once a chain's first
    sub-piece lands, its head is on dev, and a session that pulled dev holds it too: that chain is another
    session's, or one already under way, and doesn't hold this session back."""
    dev = "refs/remotes/origin/dev"
    if not is_commit(root, dev):
        return cs
    return [c for c in cs if sh(["git", "cat-file", "-e", f"{dev}:{c.path.relative_to(root).as_posix()}"],
                                cwd=root).returncode != 0]


def subs_of(cs: list[Contract], head: Contract) -> list[Contract]:
    """A head's sub-pieces, in build order (the order they were saved in)."""
    return [c for c in cs if c.head == head.name]


def active_contract(root: Path, name: str | None) -> Contract | None:
    cs = list_contracts(root)
    if name:
        for c in cs:
            if c.name == name or c.path.name == name or c.name.startswith(name):
                c.check_ready()
                return c
        die(f"There's no contract called {name!r} in {CONTRACTS}/. Check the name against the files there.")
    building = building_pieces(cs)
    if not building:
        return None
    if len(building) > 1:
        die("More than one piece is building here (" + ", ".join(c.name for c in building) + "), and a session "
            "builds one at a time. Push the finished one to dev with /mg-ship-kit:cto-check, or drop it. (rule D93)")
    building[0].check_ready()
    return building[0]


def find_contract(root: Path, name: str | None, states: tuple[str, ...], what: str) -> Contract:
    """The contract named, or the only one in one of `states`."""
    cs = list_contracts(root)
    if name:
        for c in cs:
            if c.name == name or c.path.name == name or c.name.startswith(name):
                return c
        die(f"There's no contract called {name!r} in {CONTRACTS}/. Check the name against the files there.")
    hits = [c for c in cs if c.status in states]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        die(f"Nothing to {what}: no piece is {' or '.join(states)}.", 3)
    die(f"More than one piece fits ({', '.join(c.name for c in hits)}). Say which one, like --contract {hits[0].name}.")
    raise SystemExit  # unreachable


# ---------------------------------------------------------------- Notion text and the tracker copy
NOTION_TAG_RE = re.compile(r"</?(?:b|strong|i|em|u|s|code|span|mark)\b[^>]*>", re.I)
BLOCK_TAG_RE = re.compile(r"^\s*</?(?:callout|details|summary|columns?|toggle|empty-block|page|content)\b[^>]*>\s*$", re.I)


MD_ESCAPE_RE = re.compile(r"\\([\\`*_{}\[\]()#+\-.!<>|~:\"'$=^])")


def unescape_md(text: str) -> str:
    """Notion's markdown escapes undone: `sky\\_uz` → `sky_uz`. The connector returns text columns (Piece, Repo,
    Contract file) escaped, and tracker.md tells Claude to copy them as returned."""
    return MD_ESCAPE_RE.sub(r"\1", text or "")


def same_repo(a: str, b: str) -> bool:
    """Two repo names are the same repo: Notion's escapes undone, any case (D89)."""
    return unescape_md(a).strip().lower() == unescape_md(b).strip().lower()


def notion_to_plain(text: str) -> str:
    """Undo what Notion does to plain markdown on a round trip: inline tags, escapes, entities."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)  # Notion joins lines of one block with <br />
    text = re.sub(r"<(mention-date|date)\s[^>]*?start=\"([^\"]*)\"[^>]*?(?:/>|>.*?</\1>)", r"\2", text)
    text = re.sub(r"<mention(?:-[a-z-]+)?\s[^>]*?url=\"([^\"]*)\"[^>]*>(.*?)</mention(?:-[a-z-]+)?>",
                  lambda m: m.group(2).strip() or m.group(1), text)
    text = re.sub(r"<mention(?:-[a-z-]+)?\s[^>]*?url=\"([^\"]*)\"[^>]*/>", r"\1", text)
    text = NOTION_TAG_RE.sub("", text)
    text = unescape_md(text)
    text = re.sub(r"\[([^\]]*)\]\(([^)]*)\)", r"\1", text)
    text = html.unescape(text)
    out = []
    for line in text.splitlines():
        if BLOCK_TAG_RE.match(line):
            continue
        out.append(line.rstrip().replace("\t", "    "))
    return "\n".join(out)


def normalize_copy(text: str) -> str:
    """What a contract says, without formatting: compares the repo file with the tracker's copy."""
    lines = []
    for line in notion_to_plain(text).splitlines():
        s = line.strip()
        if not s or BANNER_MARK.lower() in s.lower() or PLACEHOLDER_RE.fullmatch(s.lstrip("-*> ").strip()):
            continue
        if re.match(rf"^{key_re('Tracker')}", s, re.I):  # metadata Notion may turn into a mention; not part of the contract
            continue
        s = re.sub(r"^>\s*", "", s)
        s = re.sub(r"^[*+]\s+", "- ", s)
        s = re.sub(r"^\d+[.)]\s+", "- ", s)
        s = re.sub(r"^#+\s*", "# ", s)
        s = s.replace("**", "").replace("__", "").replace("`", "")
        s = re.sub(r"\s+", " ", s)
        lines.append(s)
    return "\n".join(lines)


NOTION_ESCAPE_RE = re.compile(r"([\\*~`$\[\]<>{}|^])")


def notion_escape(text: str) -> str:
    return NOTION_ESCAPE_RE.sub(r"\\\1", text)


def render_notion_copy(c: Contract, root: Path) -> str:
    """The exact Notion text for a contract's tracker copy: a banner, then one block per line."""
    return render_copy(c.path.relative_to(root).as_posix(), c.text,
                       "Change the contract through Claude Code, not here.")


def render_copy(rel: str, text: str, how: str) -> str:
    """A read-only copy of a repo file for Notion (D1's pattern): a banner, then one block per line."""
    out = ['<callout icon="📄" color="gray_bg">',
           f"\tRead-only copy of `{rel}`, written by Claude Code. {how}",
           "</callout>"]
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    prev_list = False
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", s)
        b = re.match(rf"^{BULLET}\s+(.*)$", s)
        if m:
            block, is_list = f"{m.group(1)} {notion_escape(m.group(2))}", False
        elif b:
            block, is_list = f"- {notion_escape(b.group(1))}", True
        else:
            block, is_list = notion_escape(s), False
        out.append(block if (is_list and prev_list) else "\n" + block)
        prev_list = is_list
    return "\n".join(out).strip() + "\n"


def copy_hash(text: str) -> str:
    return hashlib.sha256(normalize_copy(text).encode("utf-8")).hexdigest()[:16]


def sync_path(root: Path) -> Path:
    return root / ".ship" / SYNC_FILE


def load_sync(root: Path) -> dict:
    p = sync_path(root)
    return json.loads(p.read_text()) if p.exists() else {}


def save_sync(root: Path, data: dict) -> None:
    sync_path(root).parent.mkdir(exist_ok=True)
    sync_path(root).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


# ---------------------------------------------------------------- git diff
class Change:
    """One changed file: its current text, the line numbers added since base, whether it is new."""

    def __init__(self, path: str, text: str, added: set[int], new: bool):
        self.path, self.text, self.added, self.new = path, text, added, new


HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def git_changes(root: Path, base: str) -> dict[str, Change]:
    if sh(["git", "rev-parse", "--verify", f"{base}^{{commit}}"], cwd=root).returncode != 0:
        die(f"The contract starts from commit {base!r}, which isn't in this copy of the repo. Fetch the full history "
            "(git fetch --unshallow), or check the contract's Base: line.")
    diff = sh(["git", "diff", "--no-color", "--unified=0", base, "--"], cwd=root)
    if diff.returncode != 0:
        die(f"git diff failed: {diff.stderr.strip()}")
    added: dict[str, set[int]] = {}
    new_files: set[str] = set()
    current = None
    pending_new = False
    for line in diff.stdout.splitlines():
        if line.startswith("--- "):
            pending_new = line[4:].strip() == "/dev/null"
            continue
        if line.startswith("+++ "):
            current = line[4:].strip()
            current = current[2:] if current.startswith("b/") else current
            if current == "/dev/null":
                current = None
            elif pending_new:
                new_files.add(current)
            pending_new = False
            continue
        m = HUNK_RE.match(line)
        if m and current:
            start, count = int(m.group(1)), int(m.group(2) or "1")
            added.setdefault(current, set()).update(range(start, start + count))
    untracked = [f for f in sh(["git", "ls-files", "--others", "--exclude-standard"], cwd=root).stdout.splitlines()
                 if f and not any(part in SKIP_DIRS for part in f.split("/")[:-1])]  # an unignored node_modules
    changes: dict[str, Change] = {}
    for f in set(added) | set(untracked):
        p = root / f
        if not p.is_file() or p.stat().st_size > 2_000_000:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        is_new = f in untracked or f in new_files
        lines = added.get(f) or (set(range(1, text.count("\n") + 2)) if is_new else set())
        changes[f] = Change(f, text, lines, is_new)
    return changes


def line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


# ---------------------------------------------------------------- size
EP_RE = re.compile(r"@(\w+)\.(get|post|put|patch|delete|head|options)\(\s*[\"']([^\"']*)[\"']", re.I | re.S)
ROUTER_RE = re.compile(r"\b(\w+)\s*=\s*APIRouter\(([^)]*)\)", re.S)
PREFIX_RE = re.compile(r"\bprefix\s*=\s*[\"']([^\"']*)[\"']")
ROUTE_KEY_RE = re.compile(r"\bpath\s*:\s*[\"']([^\"']+)[\"']")
ROUTE_TAG_RE = re.compile(r"<Route\b[^>]*\bpath\s*=\s*[\"']([^\"']+)[\"']", re.S)
TABLE_LIT_RE = re.compile(r"op\.create_table\(\s*[\"']([\w.]+)[\"']|CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\"'`]?([\w.]+)", re.I | re.S)
TABLE_VAR_RE = re.compile(r"op\.create_table\(\s*([A-Za-z_]\w*)\s*,", re.S)
METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")


def norm_path(p: str) -> str:
    p = re.sub(r"\{[^}]*\}|:[A-Za-z_]\w*", "{}", p.strip())
    return p.rstrip("/").lower() or "/"


def norm_endpoint(s: str) -> tuple[str, str]:
    """'GET /a/b' → ('GET', normalized path). A bare path gets method ''."""
    parts = s.strip().split(None, 1)
    if len(parts) == 2 and parts[0].upper() in METHODS:
        return parts[0].upper(), norm_path(parts[1])
    return "", norm_path(s)


def match_pair(kind: str, found: str, declared: str, exact: bool) -> bool:
    if kind == "endpoints":
        fm, fp = norm_endpoint(found)
        dm, dp = norm_endpoint(declared)
        if dm and dm != fm:
            return False
        # without exact, a path may lack a router prefix set elsewhere: '/logo' matches '/api/agency/logo'
        return dp == fp if exact else (fp != "/" and dp.endswith(fp))
    if kind == "screens":
        fp, dp = norm_path(found), norm_path(declared)
        if exact:
            return fp == dp
        # a nested route's path is relative: 'settings' under '/app' matches '/app/settings'
        return not found.strip().startswith("/") and fp != "/" and dp.endswith("/" + fp)
    return exact and norm_path(found) == norm_path(declared)


def assign(kind: str, found: list[str], declared: list[str]) -> tuple[set[str], list[str]]:
    """Match each found item to at most one declared item, exact matches first. Returns (matched, extra)."""
    free = list(declared)
    matched: set[str] = set()
    for exact in (True, False):
        for f in found:
            if f in matched:
                continue
            for d in free:
                if match_pair(kind, f, d, exact):
                    matched.add(f)
                    free.remove(d)
                    break
    return matched, [f for f in found if f not in matched]


def scan_items(f: str, text: str, py: str | None, nd: str | None, seen: dict[str, dict[str, str]],
               keep=lambda m: True) -> None:  # noqa: E731
    """The size check's counting (D15): the screens, endpoints and tables one file declares, into seen[kind][name] = f.
    keep(match) picks the lines that count: the size check keeps a piece's added lines, the build map (D91) all."""
    if is_test_file(f):
        return
    if in_dir(f, py) and f.endswith(".py"):
        prefixes = {}
        for r in ROUTER_RE.finditer(text):
            pm = PREFIX_RE.search(r.group(2))
            prefixes[r.group(1)] = pm.group(1).rstrip("/") if pm else ""
        for m in EP_RE.finditer(text):
            if keep(m):
                path = prefixes.get(m.group(1), "") + (m.group(3) or "/")
                seen["endpoints"].setdefault(f"{m.group(2).upper()} {path or '/'}", f)
        for m in TABLE_LIT_RE.finditer(text):
            if keep(m):
                seen["tables"].setdefault((m.group(1) or m.group(2)).lower(), f)
        for m in TABLE_VAR_RE.finditer(text):
            if keep(m):
                seen["tables"].setdefault(f"(unnamed: {m.group(1)})", f)
    elif in_dir(f, py) and f.endswith(".sql"):
        for m in TABLE_LIT_RE.finditer(text):
            if keep(m):
                seen["tables"].setdefault((m.group(1) or m.group(2)).lower(), f)
    if in_dir(f, nd) and f.endswith((".tsx", ".jsx", ".ts", ".js")):
        for m in ROUTE_TAG_RE.finditer(text):
            if keep(m):
                seen["screens"].setdefault(m.group(1), f)
        if "route" in Path(f).name.lower():
            for m in ROUTE_KEY_RE.finditer(text):
                if keep(m):
                    seen["screens"].setdefault(m.group(1), f)


def count_size(root: Path, cfg: dict, c: Contract) -> dict:
    changes = git_changes(root, c.base)
    py, nd = cfg.get("python_dir"), cfg.get("node_dir")
    seen: dict[str, dict[str, str]] = {"screens": {}, "endpoints": {}, "tables": {}}
    for f, ch in changes.items():
        text = ch.text
        scan_items(f, text, py, nd, seen, keep=lambda m, t=text, a=ch.added: line_of(t, m.start()) in a)
    result = {"base": c.base, "changed_files": len(changes), "categories": {}, "removing": bool(c.removing)}
    ok = True
    for k in ("screens", "endpoints", "tables"):
        declared_n, declared_items = c.size[k]
        if c.removing:  # removing a rejected piece adds nothing
            declared_n, declared_items = 0, []
        items = sorted(seen[k].items())
        ok_names, _ = assign(k, [n for n, _ in items], declared_items)
        matched = [f"{n}  ({f})" for n, f in items if n in ok_names]
        extra = [f"{n}  ({f})" for n, f in items if n not in ok_names]
        status = "PASS" if len(items) <= declared_n and not extra else "FAIL"
        ok = ok and status == "PASS"
        result["categories"][k] = {"declared": declared_n, "found": len(items), "status": status,
                                   "matched": matched, "extra": extra, "declared_items": declared_items}
    result["status"] = "PASS" if ok else "FAIL"
    return result


def quick_fit(root: Path, cfg: dict, c: Contract, ref: str | None) -> dict:
    """Whether a quick fix stays inside the lane (D92). ref None reads the working tree, untracked files included, as
    /mg-ship-kit:cto-check sees it; 'HEAD' reads the commit, as the gate and GitHub see it. Bookkeeping files don't
    count. The limits are the kit's constants: nothing in ship.json raises them."""
    problems: list[str] = []
    if c.fixes:
        problems.append("it has a Fixes line. A bug the client reported goes the normal way, as a piece with its "
                        "lesson (rule D77)")
    if c.is_head or c.head:
        problems.append("it's part of a chain. A quick fix stands on its own")
    if any(c.size[k][0] for k in ("screens", "endpoints", "tables")):
        problems.append("its Size isn't 0 screens, 0 endpoints, 0 tables. A quick fix adds none of these")
    rng = [c.base] + ([ref] if ref else [])
    kinds: dict[str, str] = {}
    counts: dict[str, tuple[int, int] | None] = {}
    for opt in ("--name-status", "--numstat"):
        r = sh(["git", "-c", "core.quotepath=off", "diff", opt, "--no-renames", *rng, "--"], cwd=root)
        if r.returncode != 0:
            die(f"git diff {opt} failed: {r.stderr.strip()}")
        for line in r.stdout.splitlines():
            parts = line.split("\t")
            if opt == "--name-status" and len(parts) >= 2:
                kinds[parts[-1]] = parts[0][:1]
            elif opt == "--numstat" and len(parts) >= 3:
                counts[parts[2]] = None if parts[0] == "-" else (int(parts[0]), int(parts[1]))
    if ref is None:
        for f in git_out(root, "-c", "core.quotepath=off", "ls-files", "--others", "--exclude-standard").splitlines():
            if f and not any(part in SKIP_DIRS for part in f.split("/")[:-1]):
                kinds[f] = "A"
    files = sorted(f for f in kinds if not is_bookkeeping(f, cfg))
    new = [f for f in files if kinds[f] == "A"]
    gone = [f for f in files if kinds[f] == "D"]
    binary = [f for f in files if kinds[f] not in ("A", "D") and f in counts and counts[f] is None]
    special = [f for f in files if DEP_FILE_RE.search(f) or INFRA_FILE_RE.search(f) or is_env_file(f)
               or is_project_workflow(f) or f.lower().endswith(".sql") or MIGRATION_RE.search(f)]
    added = sum((counts.get(f) or (0, 0))[0] for f in files)
    removed = sum((counts.get(f) or (0, 0))[1] for f in files)
    if len(files) > QUICK_MAX_FILES:
        problems.append(f"it changes {len(files)} files ({short_list(files)}); a quick fix changes at most {QUICK_MAX_FILES}")
    if added > QUICK_MAX_LINES:
        problems.append(f"it adds {added} lines; a quick fix adds at most {QUICK_MAX_LINES}")
    if removed > QUICK_MAX_LINES:
        problems.append(f"it removes {removed} lines; a quick fix removes at most {QUICK_MAX_LINES}")
    if new:
        problems.append(f"it adds new files ({short_list(new)}); a quick fix only edits files that already exist")
    if gone:
        problems.append(f"it deletes files ({short_list(gone)}); a quick fix only edits files that already exist")
    if binary:
        problems.append(f"it changes binary files ({short_list(binary)}), and their lines can't be counted")
    if special:
        problems.append(f"it changes dependency, deploy, CI, env, SQL or migration files ({short_list(special)}), "
                        "which always need a full piece")
    return {"status": "FAIL" if problems else "PASS", "files": len(files), "added": added, "removed": removed,
            "problems": problems}


# ---------------------------------------------------------------- stack
def read_python_packages(pdir: Path) -> set[str]:
    names: set[str] = set()
    for req in list(pdir.glob("requirements*.txt")):
        for line in req.read_text(errors="ignore").splitlines():
            line = line.split("#", 1)[0].strip()
            if not line or line.startswith(("-", "git+", "http://", "https://")):
                continue
            m = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)", line)
            if m:
                names.add(m.group(1).lower())
    pyproject = pdir / "pyproject.toml"
    if pyproject.exists():
        try:
            import tomllib  # py311+
            data = tomllib.loads(pyproject.read_text())
            deps = list(data.get("project", {}).get("dependencies", []))
            for grp in data.get("project", {}).get("optional-dependencies", {}).values():
                deps += list(grp)
            for d in deps:
                m = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)", d.strip())
                if m:
                    names.add(m.group(1).lower())
        except Exception:
            pass
    return names


def read_node_packages(ndir: Path) -> set[str]:
    pj = ndir / "package.json"
    if not pj.exists():
        return set()
    data = json.loads(pj.read_text())
    out = set()
    for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        out |= set(map(str.lower, data.get(key, {}).keys()))
    return out


def local_python_names(pdir: Path) -> set[str]:
    names = set()
    for p in pdir.iterdir() if pdir.exists() else []:
        if p.name in SKIP_DIRS or p.name.startswith("."):
            continue
        if p.is_dir() or p.suffix == ".py":
            names.add(p.stem)
    return names


def python_imports(text: str) -> set[str]:
    """Top-level modules a Python file imports, read with ast so docstrings never count."""
    import ast
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            out.add(node.module.split(".")[0])
    return out


def node_local_prefixes(ndir: Path) -> set[str]:
    """Path aliases from tsconfig*.json (compilerOptions.paths), e.g. '@hooks/*' → '@hooks'."""
    prefixes: set[str] = set()
    for ts in ndir.glob("tsconfig*.json"):
        try:
            raw = ts.read_text(errors="ignore")
            raw = re.sub(r"//[^\n]*", "", raw)
            raw = re.sub(r"/\*.*?\*/", "", raw, flags=re.S)
            raw = re.sub(r",\s*([}\]])", r"\1", raw)
            data = json.loads(raw)
            for key in data.get("compilerOptions", {}).get("paths", {}):
                prefixes.add(key.split("/*")[0].rstrip("/"))
        except Exception:
            continue
    return prefixes


def check_stack(root: Path, cfg: dict, c: Contract | None) -> dict:
    stack = cfg.get("stack", {})
    py_allowed = set(map(str.lower, stack.get("python", [])))
    nd_allowed = set(map(str.lower, stack.get("node", [])))
    aliases = {**DEFAULT_ALIASES, **cfg.get("aliases", {})}
    py, nd = cfg.get("python_dir"), cfg.get("node_dir")
    new_pkgs: list[str] = []
    if py is not None:
        new_pkgs += [f"python: {n}" for n in sorted(read_python_packages(dir_path(root, py)) - py_allowed)]
    if nd is not None:
        new_pkgs += [f"node: {n}" for n in sorted(read_node_packages(dir_path(root, nd)) - nd_allowed)]
    unknown: dict[str, list[str]] = {}
    if c and c.base:
        changes = git_changes(root, c.base)
        py_ok = {norm_pkg(x) for x in py_allowed} | {norm_pkg(aliases[a]) for a in aliases if a.lower() in py_allowed}
        py_local = local_python_names(dir_path(root, py)) if py is not None else set()
        nd_local = node_local_prefixes(dir_path(root, nd)) if nd is not None else set()
        for f, ch in changes.items():
            if is_test_file(f):
                continue
            if py is not None and f.endswith(".py") and in_dir(f, py):
                for top in python_imports(ch.text):
                    if top in PY_STDLIB or top in py_local or norm_pkg(top) in py_ok:
                        continue
                    unknown.setdefault(f"python: {top}", []).append(f)
            if nd is not None and f.endswith((".ts", ".tsx", ".js", ".jsx")) and in_dir(f, nd):
                for m in re.finditer(r"(?:from\s+|import\s+|require\(\s*)[\"']([^\"']+)[\"']", ch.text):
                    spec = m.group(1)
                    if spec.startswith((".", "/", "@/", "~", "src/", "node:")) or spec in NODE_BUILTINS:
                        continue
                    parts = spec.split("/")
                    pkg = "/".join(parts[:2]) if spec.startswith("@") else parts[0]
                    if parts[0] in nd_local or pkg in nd_local:
                        continue
                    if pkg.lower() not in nd_allowed:
                        unknown.setdefault(f"node: {pkg}", []).append(f)
    unknown_imports = [f"{k}  ({len(set(v))} file{'s' if len(set(v)) > 1 else ''}, e.g. {v[0]})"
                       for k, v in sorted(unknown.items())]
    return {"status": "FAIL" if new_pkgs or unknown_imports else "PASS",
            "new_packages": new_pkgs, "unknown_imports": unknown_imports}


# ---------------------------------------------------------------- leftovers
def find_tool(root: Path, cfg: dict, name: str) -> list[str] | None:
    override = cfg.get("tools", {}).get(name)
    if override:
        return override.split()
    if name == "vulture":
        py = dir_path(root, cfg.get("python_dir"))
        for cand in ([str(py / "venv/bin/vulture")], [str(py / ".venv/bin/vulture")], [str(root / ".venv/bin/vulture")],
                     ["vulture"], [sys.executable, "-m", "vulture"], ["pipx", "run", "vulture"], ["uvx", "vulture"]):
            exe = cand[0]
            if (os.path.isabs(exe) and os.path.exists(exe)) or (not os.path.isabs(exe) and shutil.which(exe)):
                if sh(cand + ["--version"]).returncode == 0:
                    return cand
        return None
    if name == "knip":
        nd = dir_path(root, cfg.get("node_dir"))
        local = nd / "node_modules/.bin/knip"
        if local.exists():
            return [str(local)]
        if shutil.which("npx"):
            return ["npx", "--yes", "knip"]
        return None
    return None


def split_findings(items: list[tuple[str, int | None, str]], changes: dict[str, Change], scope_all: bool):
    """items: (file, line, text). Returns (on this piece's added lines, pre-existing in changed files)."""
    mine, old = [], []
    for f, line, text in items:
        label = f"{f}:{line}  {text}" if line else f"{f}  {text}"
        if scope_all:
            mine.append(label)
            continue
        ch = changes.get(f)
        if not ch:
            continue
        if ch.new or (line is not None and line in ch.added):
            mine.append(label)
        else:
            old.append(label)
    return mine, old


def run_vulture(root: Path, cfg: dict, changes: dict[str, Change], scope_all: bool) -> dict:
    py = cfg.get("python_dir")
    if py is None:
        return {"status": "SKIP", "findings": [], "old": [], "note": "no python_dir in ship.json"}
    if not dir_path(root, py).exists():
        return {"status": "SKIP", "findings": [], "old": [], "note": f"no {py}/ folder yet"}
    tool = find_tool(root, cfg, "vulture")
    if not tool:
        return {"status": "FAIL", "findings": [], "old": [], "note": "vulture not found. Install: pip install vulture==2.16 (in the backend's venv)"}
    args = tool + [py, "--min-confidence", str(cfg.get("vulture_min_confidence", 60)),
                   "--exclude", ",".join(cfg.get("vulture_exclude", VULTURE_EXCLUDE)),
                   "--ignore-decorators", cfg.get("vulture_ignore_decorators", VULTURE_IGNORE_DECORATORS),
                   "--ignore-names", cfg.get("vulture_ignore_names", VULTURE_IGNORE_NAMES)]
    res = sh(args, cwd=root)
    if res.returncode not in (0, 1, 3):
        return {"status": "FAIL", "findings": [], "old": [], "note": f"vulture error: {res.stderr.strip()[:300]}"}
    items = []
    for line in res.stdout.splitlines():
        m = re.match(r"^(.+?):(\d+):\s*(.+)$", line.strip())
        if m:
            f = m.group(1).replace("\\", "/")
            f = f[2:] if f.startswith("./") else f
            items.append((f, int(m.group(2)), m.group(3)))
    mine, old = split_findings(items, changes, scope_all)
    return {"status": "FAIL" if mine else "PASS", "findings": mine, "old": old, "total": len(items)}


KNIP_LABELS = {"dependencies": "dependency", "devDependencies": "devDependency", "unlisted": "unlisted dependency",
               "unresolved": "unresolved import", "exports": "export", "types": "type", "nsExports": "namespace export",
               "nsTypes": "namespace type", "enumMembers": "enum member", "classMembers": "class member",
               "duplicates": "duplicate export", "binaries": "binary"}


def run_knip(root: Path, cfg: dict, changes: dict[str, Change], scope_all: bool) -> dict:
    nd = cfg.get("node_dir")
    if nd is None:
        return {"status": "SKIP", "findings": [], "old": [], "note": "no node_dir in ship.json"}
    ndp = dir_path(root, nd)
    if not ndp.exists():
        return {"status": "SKIP", "findings": [], "old": [], "note": f"no {nd}/ folder yet"}
    if not (ndp / "node_modules").exists():
        return {"status": "FAIL", "findings": [], "old": [], "note": f"node_modules missing in {nd}. Run `npm install` there first"}
    tool = find_tool(root, cfg, "knip")
    if not tool:
        return {"status": "FAIL", "findings": [], "old": [], "note": "knip not found. Install: npm i -D knip (in the frontend)"}
    res = sh(tool + ["--reporter", "json", "--no-progress"] + cfg.get("knip_args", []), cwd=ndp)
    out = res.stdout.strip()
    start = out.find("{")
    if start < 0:
        return {"status": "FAIL", "findings": [], "old": [], "note": f"knip gave no JSON: {(res.stderr or out)[:300]}"}
    try:
        data = json.loads(out[start:])
    except json.JSONDecodeError as e:
        return {"status": "FAIL", "findings": [], "old": [], "note": f"knip JSON unreadable: {e}"}
    prefix = "" if nd == "." else nd.rstrip("/") + "/"
    items = []
    for f in data.get("files", []):
        items.append((prefix + f, None, "unused file"))
    for issue in data.get("issues", []):
        f = prefix + issue.get("file", "")
        for kind, label in KNIP_LABELS.items():
            entries = issue.get(kind) or []
            if isinstance(entries, dict):
                entries = [v for vs in entries.values() for v in vs]
            for e in entries:
                if isinstance(e, list):
                    e = e[0] if e else {}
                name = e.get("name") if isinstance(e, dict) else str(e)
                line = e.get("line") if isinstance(e, dict) else None
                items.append((f, line, f"unused {label} '{name}'"))
    mine, old = split_findings(items, changes, scope_all)
    return {"status": "FAIL" if mine else "PASS", "findings": mine, "old": old, "total": len(items)}


def check_leftovers(root: Path, cfg: dict, c: Contract, scope_all: bool) -> dict:
    changes = {} if scope_all else git_changes(root, c.base)
    v = run_vulture(root, cfg, changes, scope_all)
    k = run_knip(root, cfg, changes, scope_all)
    return {"status": "FAIL" if "FAIL" in (v["status"], k["status"]) else "PASS", "vulture": v, "knip": k}


# ---------------------------------------------------------------- setup
def outside_repo(root: Path, rel: str) -> str | None:
    """Why a folder's code can never reach this repo's check (D90): it is its own git repo, or git ignores it.
    None when the folder is this repo's own code."""
    if rel in ("", "."):
        return None
    d = root / rel
    if (d / ".git").exists():
        return "its own git repo"
    if sh(["git", "check-ignore", "-q", "--", rel], cwd=root).returncode == 0:
        return "ignored by this repo's .gitignore"
    return None


def outside_reason(root: Path, rel: str) -> str | None:
    """outside_repo for a folder or any folder above it: 'tools/core/app' is outside when 'tools/core' is."""
    parts = Path(rel).parts
    for i in range(len(parts)):
        why = outside_repo(root, "/".join(parts[:i + 1]))
        if why:
            return why
    return None


def detect_dir(root: Path, markers: tuple[str, ...], max_depth: int = 2,
               skipped: list[tuple[str, str]] | None = None) -> str | None:
    """The shallowest folder holding one of the marker files. A folder whose code can't reach this repo's check
    (a nested repo, an ignored folder) is never a candidate; `skipped` collects those with the reason (D90)."""
    best = None
    reasons: dict[str, str | None] = {}
    for p in walk_files(root):
        rel = p.relative_to(root)
        if len(rel.parts) - 1 > max_depth:
            continue
        if p.name not in markers:
            continue
        cand = str(rel.parent).replace("\\", "/")
        if cand not in reasons:
            reasons[cand] = outside_reason(root, cand)
        why = reasons[cand]
        if why:
            if skipped is not None and (cand, why) not in skipped:
                skipped.append((cand, why))
            continue
        if best is None or len(cand) < len(best):
            best = cand
    return best


DEPLOY_NOTE = {
    "devops": "deploy: your devops connects the server's deploy to the Ship check, so nothing deploys unless it "
              f"passes. Give them {CI_NOTES} (section \"Your devops\").",
    "cloudflare": f"deploy: set Cloudflare and Neon up as {CI_NOTES} says (section \"Cloudflare\"): dev and main "
                  f"each deploy from {DEPLOY_WORKFLOW} after the Ship check passes, each with its own database.",
}


def install_cloudflare(root: Path, cfg: dict) -> list[str]:
    """Copy the cloudflare track's deploy files into the project, once (D97): a Worker that serves the frontend and
    passes /api/* to the FastAPI backend in a Cloudflare Container, and the workflow that deploys after the Ship
    check. Unlike the CI files they are the project's own from then on, so an existing deploy/ folder or deploy
    workflow is never touched. Returns the files written."""
    tpl = kit_root() / "templates" / "cloudflare"
    if (root / "deploy").exists() or (root / DEPLOY_WORKFLOW).exists():
        return []
    app = re.sub(r"[^a-z0-9-]+", "-", (cfg.get("repo") or root.name).lower()).strip("-") or "app"
    names = {"__APP__": app, "__BACKEND__": (cfg.get("python_dir") or "backend").strip("/"),
             "__FRONTEND__": (cfg.get("node_dir") or "frontend").strip("/")}
    pairs = [(f, "deploy/" + f.relative_to(tpl / "deploy").as_posix()) for f in sorted((tpl / "deploy").rglob("*"))
             if f.is_file()] + [(tpl / "workflows" / "deploy.yml", DEPLOY_WORKFLOW)]
    written = []
    for src, rel in pairs:
        text = src.read_text(encoding="utf-8")
        for k, v in names.items():
            text = text.replace(k, v)
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(text, encoding="utf-8")
        written.append(rel)
    return written


def current_branch(root: Path) -> str:
    b = git_out(root, "rev-parse", "--abbrev-ref", "HEAD")
    return "" if b == "HEAD" else b


def repo_name(root: Path) -> str | None:
    """The repo's name from its origin URL: git@github.com:org/name.git and https://github.com/org/name both give
    'name'. None without an origin."""
    url = git_out(root, "remote", "get-url", "origin").strip()
    if not url:
        return None
    tail = re.split(r"[/:]", url.rstrip("/"))[-1]
    tail = tail[:-4] if tail.endswith(".git") else tail
    return tail or None


def setup_refusals(root: Path, py: str | None, nd: str | None, skipped: list[tuple[str, str]]) -> str | None:
    """Why setup must stop before writing anything (D90). None when it may go on."""
    if not repo_name(root):
        return ("this repo has no `origin` remote, so the check can't tell which repo it is. Add the GitHub remote "
                "first (`git remote add origin <url>`), then run setup again.")
    if not is_commit(root, f"refs/remotes/origin/{SETUP_BRANCH}"):
        return (f"origin has no `{SETUP_BRANCH}` branch (or it isn't fetched). Ship's check runs on pushes to dev and "
                f"main: create dev from main (`git checkout -b dev main && git push -u origin dev`), check it out, "
                "then run setup again.")
    if current_branch(root) != SETUP_BRANCH:
        return (f"you're on `{current_branch(root) or '(no branch)'}`; setup's files land on `{SETUP_BRANCH}`, where "
                f"the check runs. `git checkout {SETUP_BRANCH}`, then run setup again.")
    for d, label in ((py, "backend"), (nd, "frontend")):
        why = outside_reason(root, d) if d not in (None, "", ".") else None
        if why:
            return (f"the {label} folder {d}/ is {why}: the GitHub check in this repo would never see its code. "
                    f"Run /mg-ship-kit:setup inside {d}/'s own repo instead; this repo gets no ship.json.")
    if py is None and nd is None and skipped:
        found = "; ".join(f"{d}/ ({why})" for d, why in skipped)
        return (f"the only code here is in {found}: the GitHub check in this repo would never see it. Run "
                "/mg-ship-kit:setup inside each of those repos instead; a workspace that only holds other repos gets "
                "no ship.json.")
    return None


def cmd_setup(args) -> int:
    root = Path(args.root).resolve()
    cfg_path = root / CONFIG
    if args.track in DROPPED_TRACKS:
        die(f"Nothing was set up: the {args.track} track no longer exists. In chat, say 'set the track' so "
            "ship-spec picks devops or cloudflare, then run setup again. (rule D96)")
    skipped: list[tuple[str, str]] = []
    if cfg_path.exists() and not args.force:
        cfg = json.loads(cfg_path.read_text())
        why = setup_refusals(root, cfg.get("python_dir"), cfg.get("node_dir"), skipped)
        if why:
            die(f"Nothing was set up. {why}")
        print(f"{CONFIG} exists; keeping it (use --force to rebuild).")
    else:
        tpl_dir = Path(__file__).resolve().parent.parent / "templates"
        py = args.python_dir if args.python_dir is not None else detect_dir(root, ("requirements.txt", "pyproject.toml"), skipped=skipped)
        nd = args.node_dir if args.node_dir is not None else detect_dir(root, ("package.json",), skipped=skipped)
        py = None if py in ("", "none") else py
        nd = None if nd in ("", "none") else nd
        why = setup_refusals(root, py, nd, skipped)
        if why:
            die(f"Nothing was set up. {why}")
        default_used = False
        if py is None and nd is None and args.python_dir is None and args.node_dir is None and not args.no_default_stack:
            # A new project with no dependency files yet: start from the kit's default stack (D15).
            d = json.loads((tpl_dir / "default-stack.json").read_text())
            py, nd = d["python_dir"], d["node_dir"]
            stack = {"python": sorted(d["python"]), "node": sorted(d["node"])}
            default_used = True
        else:
            stack = {"python": sorted(read_python_packages(dir_path(root, py))) if py is not None else [],
                     "node": sorted(read_node_packages(dir_path(root, nd))) if nd is not None else []}
        old = json.loads(cfg_path.read_text()) if cfg_path.exists() else {}
        # a rebuild redoes the folders and the stack list; everything else (tracker, track, tuning) stays
        cfg = {"aliases": {}, **old, "python_dir": py, "node_dir": nd, "stack": stack}
        save_config(root, cfg)
        show = lambda d: "none" if d is None else ("the project root" if d == "." else d)  # noqa: E731
        print(f"wrote {CONFIG}: backend in {show(py)} · frontend in {show(nd)} · "
              f"stack: {len(cfg['stack']['python'])} Python packages, {len(cfg['stack']['node'])} Node packages")
        if default_used:
            print("no dependency files found, so the stack list is the kit's default (FastAPI, Postgres, React). "
                  "Build the backend in backend/ and the frontend in frontend/, or rerun setup with "
                  "--python-dir/--node-dir (or --no-default-stack) if this project uses something else.")
    before = dict(cfg)
    name = repo_name(root)
    if cfg.get("repo") != name:  # D89: the name the tracker's Repo column must match
        if cfg.get("repo"):
            print(f"repo renamed: {cfg['repo']} → {name}")
        cfg["repo"] = name
    if args.track and cfg.get("track") != args.track:
        if cfg.get("track"):
            print(f"track changed: {cfg['track']} → {args.track}")
        cfg["track"] = args.track
    if not cfg.get("ci_since"):
        head = git_out(root, "rev-parse", "HEAD")
        if head:  # code already here when Ship arrives is not asked to belong to a piece
            cfg["ci_since"] = head
    if cfg != before:
        save_config(root, cfg)
    tpl = Path(__file__).resolve().parent.parent / "templates"
    gi = root / ".gitignore"
    lines = gi.read_text().splitlines() if gi.exists() else []
    add: list[str] = []
    if ".ship/" not in lines:
        add += ["# Ship kit scratch files (tracker pages being compared)", ".ship/"]
    env_missing = [l for l in GITIGNORE_ENV if l not in lines]
    if env_missing:
        add += ["# Ship kit: env files hold secrets and stay out of git; the example files may be committed"] + env_missing
    if add:
        gi.write_text("\n".join(lines + add) + "\n")
        if ".ship/" in add:
            print("added .ship/ to .gitignore")
        if env_missing:
            print("added the env lines to .gitignore (.env and .env.* stay out of git; .env.example may go in)")
    tracked = env_files(root)
    if tracked:
        print(f"WARNING: git tracks an env file: {short_list(tracked)}. Pushes to dev and main are refused until it's "
              f"out. {ENV_FIX}")
    cdir = contracts_dir(root)
    cdir.mkdir(exist_ok=True)
    t = cdir / "TEMPLATE.md"
    if not t.exists():
        shutil.copy(tpl / "contract.md", t)
        print(f"created {CONTRACTS}/TEMPLATE.md")
    cm = root / "CLAUDE.md"
    if not cm.exists():
        shutil.copy(tpl / "CLAUDE.md", cm)
        print("created CLAUDE.md from the template — fill the <placeholders>")
    else:
        for line in clean_claude_md(cm):
            print(line)
        if re.search(r"/ship:(setup|next|cto-check|done|drop)\b", cm.read_text()):
            print("WARNING: CLAUDE.md names the old commands (/ship:…). The plugin is mg-ship-kit since 0.4.0: change "
                  "them to /mg-ship-kit:…, or a session will look for commands that don't exist.")
    for name, side, hint in (("vulture", "python_dir", "pip install vulture==2.16   (inside the backend's venv)"),
                             ("knip", "node_dir", "npm i -D knip           (inside the frontend)")):
        if cfg.get(side) is None:
            continue
        if not dir_path(root, cfg[side]).exists():
            print(f"{name}: needed once {cfg[side]}/ exists → {hint}")
            continue
        print(f"{name}: {'found' if find_tool(root, cfg, name) else 'MISSING → ' + hint}")
    gl = find_gitleaks()
    print(f"gitleaks: found ({gitleaks_version(gl) or 'unknown version'})" if gl else
          f"gitleaks: MISSING → every push is refused until it's installed (D67). {GITLEAKS_HINT}")
    if gl and not cfg.get("secrets_history") and git_out(root, "rev-parse", "HEAD"):
        # D69: once per project, the whole history; it reports and never blocks
        code, found, note = scan_secrets(root, None)
        if code in (0, 1):
            report_scan(code, found, note, "the whole history (once, at setup)")
            if code == 1:
                print("History is reported, not blocked (D69): replace each key above at its source if it was ever "
                      "pushed. New commits are scanned on every push.")
            cfg["secrets_history"] = f"{dt.date.today().isoformat()}: {len(found)} found"
            save_config(root, cfg)
        else:
            print(f"secret scan of the history: {note}")
    elif not gl:
        print("secret scan of the history: waits for gitleaks; rerun setup once it's installed.")
    changed = install_ci(root)
    print(f"CI: the Ship check runs on GitHub on every push to dev and main ({CI_WORKFLOW}); "
          + (f"wrote {', '.join(changed)}" if changed else "files up to date") + f" (kit {KIT_VERSION})")
    print(drop_plugin_declaration(root))
    note = local_install_note(Path.home())
    if note:
        print(note)
    if cfg.get("kit_line") != KIT_VERSION:
        print(f"Kit line: the project page's Facts must say `Kit: mg-ship-kit {KIT_VERSION}` → write it, then run "
              "`kit-mark` (ship-spec compares it with its own version before each job)")
    print(f"repo: {cfg['repo']} → the tracker's Repo column must say this for a row to be picked up here (D89); "
          "on a project with several repos, the project page's Repos list must name it")
    track = cfg.get("track")
    if track == "cloudflare":
        wrote = install_cloudflare(root, cfg)
        # The deploy files are bookkeeping on this track (D97). The deploy workflow must be listed too: a project's
        # own workflows are product code otherwise (issue #34). An older setup listed only deploy/: add the rest.
        missing = [p for p in CF_BOOKKEEPING if p not in cfg.get("bookkeeping", [])]
        if missing and (wrote or "deploy/" in cfg.get("bookkeeping", [])):
            late = cfg_at(root, "HEAD") is not None
            cfg["bookkeeping"] = cfg.get("bookkeeping", []) + missing
            save_config(root, cfg)
        else:
            late = False
        if wrote:
            print(f"cloudflare: wrote {', '.join(wrote)}. They are this project's own from now on (setup never "
                  f"overwrites them), and deploy/ and {DEPLOY_WORKFLOW} count as bookkeeping.")
        else:
            print(f"cloudflare: deploy/ or {DEPLOY_WORKFLOW} is already here; left as it is."
                  + (f" Added {', '.join(missing)} to {CONFIG}'s bookkeeping list." if late else ""))
        if late:
            print(f"cloudflare: {CONFIG} was already in git, and its bookkeeping list counts from the next push. "
                  f"Commit and push {CONFIG} to dev first, then the deploy files in a second push.")
    print(f"track: {track}" if track else
          "track: not set → read the Track line in the project page's Facts and rerun setup with --track")
    if track in DEPLOY_NOTE:
        print(DEPLOY_NOTE[track])
    tr = cfg.get("tracker") or {}
    print("tracker: " + ((tr.get("page") or tr.get("data_source")) if tr
                         else "not linked → paste the project's Notion page link, then run `link`"))
    return 0


def cmd_link(args) -> int:
    root = Path(args.root).resolve()
    cfg = load_config(root)
    if not args.data_source.startswith("collection://"):
        die("--data-source must be the tracker's collection://… link, as a Notion fetch shows it.")
    cfg["tracker"] = {"page": args.page or "", "database": args.database or "", "data_source": args.data_source}
    save_config(root, cfg)
    print(f"linked the tracker in {CONFIG}: {args.data_source}")
    return 0


# ---------------------------------------------------------------- report
def print_report(c: Contract, size: dict | None, stack: dict | None, left: dict | None, ci: bool = False,
                 security: list[str] | None = None, lesson: str | None | bool = False,
                 quick: dict | None = None, migrations: str | None = None) -> str:
    lines = [f"Ship CTO check · contract {c.name} · base {c.base[:10]} · {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}"]
    overall = "PASS"
    if size:
        cats = size["categories"]
        lines.append(f"SIZE       {size['status']:4}  " + " · ".join(f"{k} {v['found']}/{v['declared']}" for k, v in cats.items()))
        for k, v in cats.items():
            if v["status"] != "FAIL":
                continue
            for it in v["extra"][:20]:
                lines.append(f"  extra {k[:-1]:9} {it}   (built, but the contract doesn't list it)")
            if len(v["extra"]) > 20:
                lines.append(f"  … {len(v['extra']) - 20} more extra {k}")
            if not v["extra"]:
                lines.append(f"  {k}: {v['found']} built, but the contract says {v['declared']} (every one it names "
                             "is there)")
        if size["status"] == "FAIL":
            lines.append("  → The piece built more than its contract asked for. If the client asked for it, the owner "
                         "approves a contract change in one line. If not, delete it.")
        overall = "FAIL" if size["status"] == "FAIL" else overall
    if stack:
        np_, ui = stack["new_packages"], stack["unknown_imports"]
        lines.append(f"STACK      {stack['status']:4}  packages: {len(np_)} new · imports: {len(ui)} not in the stack")
        for p in np_:
            lines.append(f"  package   {p}   (new: not on the stack list) → the owner approves it in one line "
                         "(stack-add), or remove it")
        for u in ui[:10]:
            lines.append(f"  import    {u}   (not on the stack list) → add its package with stack-add, map the "
                         "import to its package in ship.json, or remove the import")
        overall = "FAIL" if stack["status"] == "FAIL" else overall
    if left:
        v, k = left["vulture"], left["knip"]
        parts = []
        for label, r in (("python", v), ("node", k)):
            if r["status"] == "SKIP":
                continue
            parts.append(f"{label} {len(r['findings'])} on this piece's lines" +
                         (f" ({len(r.get('old', []))} pre-existing nearby)" if r.get("old") else ""))
        lines.append(f"LEFTOVERS  {left['status']:4}  " + (" · ".join(parts) or "nothing to scan"))
        for r in (v, k):
            if r.get("note") and r["status"] != "SKIP":
                lines.append(f"  note      {r['note']}")
            for f in r["findings"][:15]:
                lines.append(f"  {f}")
            if len(r["findings"]) > 15:
                lines.append(f"  … {len(r['findings']) - 15} more")
        if left["status"] == "FAIL":
            lines.append("  → This piece added code that nothing seems to use (the % is how sure the tool is). Delete "
                         "it, or use it. If it is used, such as a field a framework reads by itself, it's a false "
                         "alarm: tell Claude, and it marks it as one instead of deleting working code.")
        overall = "FAIL" if left["status"] == "FAIL" else overall
    if quick is not None:  # D92: a quick fix stays inside the lane's limits, or it isn't one
        lines.append(f"QUICK      {quick['status']:4}  {quick['files']} files · +{quick['added']} -{quick['removed']} lines"
                     f"   (the lane: {QUICK_MAX_FILES} existing files, {QUICK_MAX_LINES} lines each way)")
        lines += [f"  {p}" for p in quick["problems"]]
        if quick["problems"]:
            lines.append("  → Cut the change down to what the owner asked. If it really needs more, it's too big "
                         "for a quick fix: drop it and spec it as a piece in chat.")
        overall = "FAIL" if quick["status"] == "FAIL" else overall
    if migrations:  # D93: two parallel pieces each added a migration on the same parent
        lines.append(f"MIGRATIONS FAIL  {migrations}")
        overall = "FAIL"
    if security is not None:  # the gate and GitHub only: /mg-ship-kit:cto-check runs the review after this check
        if security:
            lines.append(f"SECURITY   FAIL  {len(security)} to settle")
            lines += [f"  {p}" for p in security]
            overall = "FAIL"
        else:
            lines.append("SECURITY   PASS")
    if c.fixes and lesson is not False:  # D78: a bug fix passes only with the lesson that stops it next time
        lines.append(f"LESSON     {'FAIL' if lesson else 'PASS'}  " + (lesson or c.lesson))
        overall = "FAIL" if lesson else overall
    if overall == "PASS":
        lines.append("RESULT: PASS — the piece can go to dev." if ci else
                     "RESULT: PASS — the piece can go to dev. Now suggest any CLAUDE.md lines this piece taught us. "
                     "(rule D33)")
    elif ci:
        lines.append("RESULT: FAIL — nothing deploys from this commit. In Claude Code, run /mg-ship-kit:cto-check, "
                     "fix what it shows, and push again.")
    else:
        lines.append("RESULT: FAIL — the piece can't go to dev yet. Fix each FAIL above, then "
                     "run /mg-ship-kit:cto-check again.")
    print("\n".join(lines))
    return overall


# ---------------------------------------------------------------- commands
def cmd_check(args) -> int:
    root = Path(args.root).resolve()
    cfg = load_config(root)
    c = active_contract(root, args.contract)
    if c and c.is_head:
        die(f"Nothing to check: {c.name} is a chain head, and a head has no code of its own. The check runs on "
            "each sub-piece in turn, through /mg-ship-kit:chain.", 2)
    if not c:
        heads = open_heads(list_contracts(root))
        if heads:
            print(f"ship: Nothing to check: no piece is building. The chain {heads[0].name} is open: pick up its "
                  "next sub-piece with /mg-ship-kit:chain.", file=sys.stderr)
        else:
            print("ship: Nothing to check: no piece is building. Pick up the next Ready piece with "
                  "/mg-ship-kit:next.", file=sys.stderr)
        return 3
    what = args.what
    x = taken_on_dev(root, c) if what == "check" else None
    if x:
        print(taken_message(c, x))
        return 1
    size = count_size(root, cfg, c) if what in ("check", "size") else None
    stack = check_stack(root, cfg, c) if what in ("check", "stack") else None
    left = check_leftovers(root, cfg, c, getattr(args, "all", False)) if what in ("check", "leftovers") else None
    quick = quick_fit(root, cfg, c, None) if what == "check" and c.quick else None
    mig = migration_problem(root, cfg, c.base, None) if what == "check" else None
    if args.json:
        print(json.dumps({"contract": c.name, "size": size, "stack": stack, "leftovers": left, "quick": quick,
                          "migrations": mig}, indent=2))
        return 1 if mig or "FAIL" in [x["status"] for x in (size, stack, left, quick) if x] else 0
    lesson = lesson_problem(root, c, None) if what == "check" else False
    return 0 if print_report(c, size, stack, left, lesson=lesson, quick=quick, migrations=mig) == "PASS" else 1


def cmd_stack_only(args) -> int:
    root = Path(args.root).resolve()
    cfg = load_config(root)
    c = active_contract(root, args.contract)
    stack = check_stack(root, cfg, c)
    if args.json:
        print(json.dumps(stack, indent=2))
    else:
        print(f"STACK      {stack['status']:4}  packages: {len(stack['new_packages'])} new · "
              f"imports: {len(stack['unknown_imports'])} not in the stack"
              + ("" if c else "   (packages only: no active contract, so no import scan)"))
        for p in stack["new_packages"]:
            print(f"  package   {p}")
        for u in stack["unknown_imports"]:
            print(f"  import    {u}")
    return 0 if stack["status"] == "PASS" else 1


def cmd_stack_add(args) -> int:
    root = Path(args.root).resolve()
    cfg = load_config(root)
    name = args.name.lower()
    lst = cfg.setdefault("stack", {}).setdefault(args.side, [])
    if name in lst:
        print(f"{name} already in the {args.side} stack")
        return 0
    lst.append(name)
    lst.sort()
    save_config(root, cfg)
    print(f"added {name} to the {args.side} stack list in {CONFIG}")
    return 0


def git_out(root: Path, *a: str) -> str:
    r = sh(["git", *a], cwd=root)
    return r.stdout.strip() if r.returncode == 0 else ""


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s[:48].strip("-") or "piece"


def cmd_pickup(args) -> int:
    """Save the approved contract from a tracker row as contracts/NNN-slug.md with Status: building."""
    root = Path(args.root).resolve()
    cfg = load_config(root)
    mine = (cfg.get("repo") or repo_name(root) or "").strip()  # setup writes it; before kit 0.13, read from origin
    want = unescape_md(args.repo).strip()  # the row's Repo column (D89), as the connector returned it
    if not mine:
        die(f"Nothing was picked up: {CONFIG} names no repo and there's no origin remote, so the row can't be "
            "matched to this repo. Add the remote (like `git remote add origin https://github.com/you/app.git`), then run "
            "/mg-ship-kit:setup once, on dev.")
    if want and not same_repo(want, mine):
        die(f"Nothing was picked up: this row is for the repo {want!r}, and this is {mine!r}. Open {want} and "
            "run /mg-ship-kit:next there.", 1)
    if not want and not args.single_repo:
        die("Nothing was picked up: the row's Repo column is empty. When a project has several repos, each row "
            "names its repo. Set it in chat (ship-spec fills it in when it specs a piece), then pick the row up "
            "again. (A project with one repo runs pickup with --single-repo.)", 1)
    cs = list_contracts(root)
    busy = building_pieces(cs)
    if busy:
        die(f"Nothing was picked up: {busy[0].name} is still building in this session, and a session builds one "
            "piece at a time. Push it to dev with /mg-ship-kit:cto-check, or drop it, or pick this row up in "
            "another session. (rule D93)", 2)
    heads = here_only(root, open_heads(cs))
    if heads:
        die(f"Nothing was picked up: the chain {heads[0].name} is still open in this session. Finish it with "
            "/mg-ship-kit:chain, or drop it, or pick this row up in another session.", 2)
    head = git_out(root, "rev-parse", "--short=10", "HEAD")
    if not head:
        die("Nothing was picked up: the repo has no commits yet. Make a first commit, then try again.")
    status = unescape_md(args.status or "").strip()
    if args.status is not None and status.lower() != "ready":
        die(f"Nothing was picked up: the row's Status is now {status or 'empty'}, not Ready. Another session "
            "picked it up first. Pick another row.", TAKEN)
    raw = notion_to_plain(Path(args.file).read_text(encoding="utf-8"))
    if field(raw, "Quick"):
        die("Nothing was picked up: this row is a quick fix (it has a Quick: line). A quick fix starts in Claude "
            "Code with /mg-ship-kit:quick, never from the tracker. (rule D92)", 1)
    if field(raw, "Head"):
        die("Nothing was picked up: this row is part of a chain (it has a Head: line). Its chain picks it up, "
            "through /mg-ship-kit:chain.", 1)
    name, approved, body = contract_parts(raw, unescape_md(args.name).strip() or None, need_approval=False)
    is_head = (field(raw, "Chain") or "").strip().lower() == "head"
    rows = ours = None
    if args.rows:
        _, rows, ours = mine_and_rows(root, args)
    depends = parse_depends(field(raw, "Depends on"), [r["piece"] for r in rows or []])
    # Every problem the owner fixes in the row, found in one go, so a fix never meets the next one on the rerun
    problems: list[str] = []
    if not is_approval(approved):
        problems.append("the row has no approval line. The owner approves a contract in one line, like "
                        f"`{approval_example()}`, with their own name")
    size, size_problems = parse_size(body)
    problems += [f"Size: {p}" for p in size_problems]
    if is_head and not size_problems:
        problems += [f"{p}. A chain head lists every item by name, because the split hands them out by name"
                     for p in count_problems(size)]
    problems += reuse_parse(body)[1]
    if is_head and (field(raw, "Fixes") or "").strip():
        problems.append("a chain head can't fix a bug. Remove the Fixes line, and spec the bug fix as its own "
                        "piece (rule D77)")
    floor, wait = 1, None
    if rows is not None:  # D93: the dependencies must be met, and the number comes from the tracker
        row = (find_row(rows, args.tracker) if args.tracker and page_id(args.tracker) else None) or find_row(rows, name)
        bad = depends_problems(rows, ours, row, depends, name)
        if bad and bad[0] == 1:
            problems.append(bad[1].rstrip("."))
        elif bad:
            wait = bad
        floor = next_number(root, ours)
    if problems:
        n = len(problems)
        die(f"Nothing was picked up. The row has {n} problem{'s' if n > 1 else ''} to fix in chat:\n"
            + "\n".join(f"  {i}. {p}" for i, p in enumerate(problems, 1))
            + "\nFix " + ("them all" if n > 1 else "it") + ", then pick the row up again.", 1)
    if wait:
        die(wait[1], wait[0])
    path = new_contract_path(root, name, floor)
    header = [f"# Contract: {name}", "Status: building", f"Base: {head}", f"Approved: {approved}", f"Repo: {mine}"]
    if depends is not None:
        header.append("Depends on: " + depends_line(depends))
    if is_head:
        header.append("Chain: head")
    if args.tracker:
        header.append(f"Tracker: {args.tracker}")
    claim = os.urandom(4).hex()  # issue #30: the copy carries it, so a read-back shows whose pickup the row holds
    header.append(f"Claim: {claim}")
    path.write_text("\n".join(header) + "\n\n" + body, encoding="utf-8")
    try:
        c = Contract(path)
        c.check_ready()
        reuse = reuse_lines(c.text)
    except SystemExit:
        path.unlink(missing_ok=True)
        raise
    added = adopt_packages(root, reuse)
    print(f"saved {path.relative_to(root)} · Status: building · Base: {head} · Claim: {claim}"
          + (" · a chain head: split it next (/mg-ship-kit:chain)" if is_head else ""))
    if reuse:
        print(f"reuse (D73): {sum(1 for r in reuse if r['verdict'] == 'adopt')} adopted, "
              f"{sum(1 for r in reuse if r['verdict'] == 'build')} to build"
              + (f"; added to the stack list in {CONFIG}: {', '.join(added)}. Commit {CONFIG} with the contract."
                 if added else "."))
    return 0


def cmd_quick(args) -> int:
    """Write a quick fix's contract (D92) from the owner's own words, Status building. It refuses what can't start
    (a piece building, a chain open, uncommitted product changes); the check, the gate and GitHub then hold the fix
    to the lane's limits (quick_fit), so the limits never rest on Claude's word."""
    root = Path(args.root).resolve()
    cfg = load_config(root)
    what, check, by = (" ".join((a or "").split()) for a in (args.what, args.check, args.by))
    again = f' Your line, to run again then: "{what}".' if what else ""
    if not what:
        die("Say the change in the owner's own words, like: --what \"Rename the Save button to Send\"", 2)
    if not by or PLACEHOLDER_RE.search(by):
        die("--by needs the owner's name: approving a quick fix is theirs to do.", 2)
    if not re.match(r"^when i\b.*\bthen i\b", check, re.I):
        die("--check must be one line saying what the owner looks at on dev, like: "
            "--check \"When I open the form then I see a Send button\"", 2)
    mine = (cfg.get("repo") or repo_name(root) or "").strip()
    if not mine:
        die(f"No quick fix was started: {CONFIG} names no repo and there's no origin remote. Add the remote (like `git remote add origin https://github.com/you/app.git`), then run "
            "/mg-ship-kit:setup once, on dev.")
    cs = list_contracts(root)
    busy = building_pieces(cs)
    if busy:
        die(f"No quick fix was started: {busy[0].name} is building in this session. Finish it with "
            "/mg-ship-kit:cto-check or drop it, then run /mg-ship-kit:quick again, or use another session. "
            f"(rule D93){again}", 1)
    heads = here_only(root, open_heads(cs))  # D93: a chain already on dev is another session's, or under way
    if heads:
        die(f"No quick fix was started: the chain {heads[0].name} is open in this session. Finish it with "
            "/mg-ship-kit:chain or drop it, then run /mg-ship-kit:quick again, or use another session. "
            f"(rule D93){again}", 1)
    head = git_out(root, "rev-parse", "--short=10", "HEAD")
    if not head:
        die("No quick fix was started: the repo has no commits yet. Make a first commit, then try again.")
    porcelain = sh(["git", "-c", "core.quotepath=off", "status", "--porcelain"], cwd=root).stdout
    dirty = [l[3:] for l in porcelain.splitlines() if len(l) > 3 and not is_bookkeeping(l[3:].strip('"'), cfg)
             and not any(part in SKIP_DIRS for part in l[3:].split("/")[:-1])]
    if dirty:
        die(f"No quick fix was started: there are uncommitted changes ({short_list(dirty, 5)}), and they would "
            f"count as part of the fix. Commit, stash or remove them first.{again}", 1)
    today = dt.date.today().isoformat()
    floor = next_number(root, mine_and_rows(root, args)[2]) if args.rows else 1  # D93: numbers from the tracker
    path = new_contract_path(root, f"quick {what}", floor)
    path.write_text("\n".join([
        f"# Contract: Quick: {what}", "Status: building", f"Base: {head}",
        f"Approved: {today} by {by}, in Claude Code (a quick fix, D92)", f"Repo: {mine}", "Quick: yes", "",
        f"Owner's words: \"{what}\", in Claude Code, {today}", "",
        "## What users see", f"- {what}", "",
        "## What's out",
        f"- Anything else. A quick fix changes at most {QUICK_MAX_LINES} lines in at most {QUICK_MAX_FILES} existing "
        "files, and adds no screen, endpoint, table, package or file.", "",
        "## How to check it", f"- {check}", "",
        "## Size", "Screens: 0", "Endpoints: 0", "Tables: 0", ""]), encoding="utf-8")
    try:
        Contract(path).check_ready()
    except SystemExit:
        path.unlink(missing_ok=True)
        raise
    print(f"saved {path.relative_to(root)} · Status: building · Base: {head} · a quick fix (D92). Its tracker row: "
          f"\"Quick: {what}\". Make the change, nothing else, then run the CTO check.")
    return 0


# ---------------------------------------------------------------- lessons (D76–D79)
KIT_REPO = "mgac-consulting/ship-kit"
KIT_ISSUE_RE = re.compile(rf"^https://github\.com/{re.escape(KIT_REPO)}/issues/\d+/?$")
def lesson_how(c: Contract) -> str:
    """How to record a lesson, with the piece's own name and real-looking examples of each kind."""
    cmd = f"ship_check.py lesson --contract {c.name}"
    return ("Ask the owner \"what stops this bug next time?\" and record one answer, in one of three ways:\n"
            f"    {cmd} --test tests/test_help_text.py      (a test this fix adds or changes)\n"
            f"    {cmd} --fact \"Help texts live in copy.py\"   (a CLAUDE.md line, on the owner's yes)\n"
            f"    {cmd} --kit https://github.com/{KIT_REPO}/issues/40   (a kit issue labelled lesson)")


def claude_md_lines(root: Path, ref: str | None = "HEAD") -> set[str]:
    """CLAUDE.md's lines, list markers dropped: at a commit, or (ref None) as the file is on disk."""
    if ref is None:
        p = root / "CLAUDE.md"
        text = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
    else:
        r = sh(["git", "show", f"{ref}:CLAUDE.md"], cwd=root)
        text = r.stdout if r.returncode == 0 else ""
    return {re.sub(rf"^\s*{BULLET}\s+", "", l).strip() for l in text.splitlines() if l.strip()}


def piece_changed(root: Path, c: Contract, ref: str | None = "HEAD") -> set[str]:
    """Files this piece changed since its Base: up to a commit, or (ref None) in the working tree, new files too."""
    if not c.base:
        return set()
    if ref is not None:
        return set(git_out(root, "diff", "--name-only", c.base, ref).split())
    return set(git_out(root, "diff", "--name-only", c.base).split()) | \
        set(git_out(root, "ls-files", "--others", "--exclude-standard").split())


def check_lesson(root: Path, c: Contract, kind: str, value: str, ref: str | None = "HEAD") -> str | None:
    """None when the lesson holds, else what's wrong with it."""
    if kind == "test":
        if not is_test_file(value):
            return f"{value} isn't a test file (test_*.py, *_test.py, *.test.*, *.spec.*, or under tests/)"
        if value not in piece_changed(root, c, ref):
            return f"{value} isn't among this piece's changes: the lesson is a test this fix adds or changes"
        return None
    if kind == "fact":
        line = re.sub(rf"^\s*{BULLET}\s+", "", value).strip()
        if not line:
            return "the fact is empty"
        return None if line in claude_md_lines(root, ref) else f"CLAUDE.md doesn't hold the line {line!r}"
    if kind == "kit":
        return None if KIT_ISSUE_RE.match(value) else f"{value!r} isn't the link of an issue on {KIT_REPO}"
    return f"unknown kind {kind!r}: test, fact or kit"


def lesson_problem(root: Path, c: Contract, ref: str | None = "HEAD") -> str | None:
    """A contract with a Fixes line passes only when its Lesson line holds (D78). None when fine or not a fix."""
    if not c.fixes:
        return None
    if not c.lesson:
        return (f"this piece fixes a bug (\"{c.fixes}\") but has no lesson yet, so the same bug could come back. "
                f"(rule D78)\n  {lesson_how(c)}")
    kind, _, value = c.lesson.partition(" ")
    err = check_lesson(root, c, kind.lower(), value.strip(), ref)
    return f"the lesson doesn't hold: {err}.\n  {lesson_how(c)}" if err else None


def cmd_lesson(args) -> int:
    """Record what stops a fixed bug next time (D76–D79), after checking it holds."""
    root = Path(args.root).resolve()
    c = find_contract(root, args.contract, ("building",), "building")
    if not c.fixes:
        die(f"{c.name} has no Fixes line, and a lesson only goes with a bug fix. (rule D77)")
    picked = [(k, v) for k, v in (("test", args.test), ("fact", args.fact), ("kit", args.kit)) if v]
    if len(picked) != 1:
        die("Give one lesson at a time: --test, --fact or --kit.")
    kind, value = picked[0][0], " ".join(picked[0][1].split())
    err = check_lesson(root, c, kind, value, None)
    if err:
        die(f"The lesson wasn't recorded: {err}.", 1)
    c.set_status(c.status, {"Lesson": f"{kind} {value}"})
    print(f"{c.name}: Lesson: {kind} {value}. Commit the contract with the fix.")
    return 0


# ---------------------------------------------------------------- the reuse block (D73, D74)
REUSE_ADOPT_RE = re.compile(r"^(?P<cap>[^:]+?):\s*adopt\s+(?P<pkg>[A-Za-z0-9@][\w.@/-]*)\s*\(\s*(?P<side>python|node)\s*,"
                            r"\s*(?P<lic>[^)]+?)\s*\)\s*(?P<rest>.*)$", re.I)
# After the bracket, any note may follow; only one that starts with `ok:` is the owner's word on the licence
REUSE_OK_RE = re.compile(r"^[\s—–\-:,;.]*ok\s*:\s*(?P<ok>\S.*)$", re.I)
REUSE_BUILD_RE = re.compile(r"^(?P<cap>[^:]+?):\s*build\b[\s—–\-:,;.]*(?P<why>.*)$", re.I)


def licence_key(lic: str) -> str:
    """'MIT License' → 'mit', 'Apache 2.0' → 'apache-2.0', 'BSD 3-Clause' → 'bsd-3-clause'."""
    s = re.sub(r"\b(license|licence)\b", "", lic.lower())
    return re.sub(r"[\s_]+", "-", s.strip()).strip("-")


def permissive_licences() -> set[str]:
    return {licence_key(x) for x in json.loads((kit_root() / "reference" / "licences.json").read_text())["permissive"]}


def reuse_lines(text: str) -> list[dict]:
    """The contract's `## Reuse` block, checked; it stops on any problem in it."""
    out, problems = reuse_parse(text)
    if problems:
        die("The contract's Reuse section has problems:\n" + "\n".join(f"  {i}. {p}" for i, p in
            enumerate(problems, 1)) + "\nFix them in chat, then try again. (rules D73, D74)", 1)
    return out


def reuse_parse(text: str) -> tuple[list[dict], list[str]]:
    """The contract's `## Reuse` block: each line adopts a package (python or node, with its licence) or says
    build. A licence that isn't on the kit's permissive list needs the owner's words (`— ok: <reason>`). Returns
    the lines read and every problem found."""
    sec = section(text, "Reuse")
    if sec is None:
        return [], []
    ok_list, out, problems = permissive_licences(), [], []
    for line in sec.splitlines():
        b = re.match(rf"^\s*{BULLET}\s+(.+?)\s*$", line)
        if not b:
            continue
        item = re.sub(r"`|\*\*", "", b.group(1)).strip()
        if PLACEHOLDER_RE.search(item):  # the template's example line: no package name has <…>
            continue
        m = REUSE_ADOPT_RE.match(item)
        if m:
            okm = REUSE_OK_RE.match(m.group("rest"))
            lic, ok = m.group("lic").strip(), (okm.group("ok").strip() if okm else "")
            alts = [licence_key(x) for x in re.split(r"\s+or\s+|\s*/\s*", lic, flags=re.I) if x.strip()]
            if not any(k in ok_list for k in alts) and not ok:  # a dual licence passes when either side does
                problems.append(f"{m.group('pkg')} uses the {lic} licence, which isn't on the kit's list of safe "
                                "licences. Only the owner can accept it, by adding their reason and name to the "
                                f"line, like:\n       {item.rstrip('. ')} — ok: internal tool only, "
                                f"{approval_example(short=True)} (rule D74)")
            out.append({"verdict": "adopt", "capability": m.group("cap").strip(), "package": m.group("pkg").lower(),
                        "side": m.group("side").lower(), "licence": lic, "ok": ok})
            continue
        m = REUSE_BUILD_RE.match(item)
        if m:
            out.append({"verdict": "build", "capability": m.group("cap").strip(), "why": (m.group("why") or "").strip()})
            continue
        cap = item.split(":")[0].strip() if ":" in item else "Charts"
        problems.append(f"the Reuse line {item!r} doesn't say adopt or build. Write it like one of these:\n"
                        f"       {cap}: adopt recharts (node, MIT)\n       {cap}: build — nothing we found fits")
    return out, problems


def adopt_packages(root: Path, reuse: list[dict]) -> list[str]:
    """Approving the contract approved its adopted packages (D73): add them to the stack list."""
    cfg = load_config(root)
    added = []
    for r in reuse:
        if r["verdict"] != "adopt":
            continue
        lst = cfg.setdefault("stack", {}).setdefault(r["side"], [])
        if r["package"] not in lst:
            lst.append(r["package"])
            lst.sort()
            added.append(f"{r['package']} ({r['side']})")
    if added:
        save_config(root, cfg)
    return added


def contract_parts(raw: str, name: str | None = None, need_approval: bool = True) -> tuple[str, str, str]:
    """(name, Approved line, body) of a contract's plain text, the header lines and any banner dropped."""
    m = TITLE_RE.search(raw)
    name = (name or (m.group(1) if m else "")).strip()
    if not name:
        die("The piece has no name. Pass the tracker row's title, like: --name \"Weekly report\"")
    approved = (field(raw, "Approved") or "").strip()
    if need_approval and not is_approval(approved):
        die("Nothing was picked up: the row has no approval line. The owner approves a contract in one line, "
            f"like `{approval_example()}`, with their own name. Add it in chat, then pick the row up again.", 1)
    body_lines, in_header = [], True
    header_re = re.compile("|".join(key_re(k) for k in HEADER_KEYS), re.I)
    for line in raw.splitlines():
        s = line.strip()
        if BANNER_MARK.lower() in s.lower():
            continue
        if in_header and (re.match(r"^##+[ \t]*\S", s) or WORDS_LABEL_RE.match(s)):
            in_header = False
        if in_header and (TITLE_RE.match(s) or header_re.match(s) or not s):
            continue
        body_lines.append(line)
    return name, approved, "\n".join(body_lines).strip() + "\n"


def new_contract_path(root: Path, name: str, floor: int = 1) -> Path:
    """contracts/NNN-slug.md, NNN one past the highest here, and at least `floor` (D93: the tracker's highest plus
    one, so two sessions don't both save 005)."""
    nums = [int(p.name[:3]) for p in contracts_dir(root).glob("[0-9][0-9][0-9]-*.md")]
    num = max((max(nums) + 1) if nums else 1, floor)
    contracts_dir(root).mkdir(exist_ok=True)
    return contracts_dir(root) / f"{num:03d}-{slugify(name)}.md"


# ---------------------------------------------------------------- the tracker's rows, for parallel builds (D93)
# One piece builds per session, not per repo. Notion is the only view every session shares, so /mg-ship-kit:next
# writes the tracker query's rows to a file and the script decides from it: which Ready row may build now, its
# contract number, and whether a drop would break a piece that depends on the one dropped.
ROWS_FILE = ".ship/tracker-rows.json"
MET = ("on dev", "done")  # a dependency is met once its piece is on dev or done
PAGE_ID_RE = re.compile(r"[0-9a-f]{32}")


def page_id(ref: str) -> str:
    """The Notion page id inside a link (dashes dropped), or '' when there is none."""
    m = PAGE_ID_RE.search((ref or "").lower().replace("-", ""))
    return m.group(0) if m else ""


def link_list(v) -> list[str]:
    """A link column as the tracker query gives it: a list, or Notion's JSON-encoded string ('["https://…"]', and
    '[]' when empty), or links separated by commas. Tried on a real tracker (D93)."""
    if isinstance(v, str):
        t = v.strip()
        if t.startswith("["):
            try:
                v = json.loads(t)
            except ValueError:
                v = re.split(r"[,\n]", t.strip("[]"))
        else:
            v = re.split(r"[,\n]", t)
    if not isinstance(v, list):
        v = [v] if v else []
    return [str(d).strip().strip("\"'") for d in v if str(d).strip().strip("\"'")]


def load_rows(path: str) -> list[dict]:
    """The tracker rows /mg-ship-kit:next wrote: a JSON list, one object per row, with piece, order, status, repo,
    head, depends (row links or piece names), contract_file and url, the values as the query returns them."""
    p = Path(path)
    if not p.is_file():
        die(f"{path} doesn't exist yet. Query the tracker and write its rows there first (see tracker.md, \"The rows "
            "file\").")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as e:
        die(f"{path} isn't valid JSON ({e}). Write it again from the tracker query.")
    if not isinstance(data, list):
        die(f"{path} must hold a JSON list of rows, and it doesn't.")
    rows = []
    for i, r in enumerate(data):
        if not isinstance(r, dict) or not str(r.get("piece") or "").strip():
            die(f"{path}: row {i + 1} has no piece name. Write the rows again from the tracker query.")
        order = r.get("order")
        try:
            order = float(order) if order not in (None, "") else None
        except (TypeError, ValueError):
            order = None
        text = lambda k: unescape_md(str(r.get(k) or "")).strip()  # the connector escapes markdown (`sky\\_uz`)
        rows.append({"piece": text("piece"), "order": order, "status": text("status"), "repo": text("repo"),
                     "head": ", ".join(link_list(r.get("head"))),
                     "depends": [unescape_md(d).strip() for d in link_list(r.get("depends"))],
                     "contract_file": text("contract_file"), "url": str(r.get("url") or "").strip()})
    return rows


def row_status(r: dict) -> str:
    return r["status"].lower()


def find_row(rows: list[dict], ref: str) -> dict | None:
    """The row a link or a piece name points at."""
    pid = page_id(ref)
    for r in rows:
        if pid and page_id(r["url"]) == pid:
            return r
    for r in rows:
        if r["piece"].lower() == unescape_md(ref).strip().lower():
            return r
    return None


def rows_of_repo(rows: list[dict], mine: str, single_repo: bool) -> list[dict]:
    """This repo's rows (D89): the Repo column names it, or, on a one-repo project, names nothing."""
    return [r for r in rows if same_repo(r["repo"], mine) or (single_repo and not r["repo"])]


def unmet(rows: list[dict], deps: list[str]) -> list[str]:
    """Why these dependencies don't let a piece build yet: one line each, empty when every one is on dev or done."""
    out = []
    for d in deps:
        r = find_row(rows, d)
        if r is None:
            out.append(f"{d} isn't a row in the tracker")
        elif row_status(r) == "dropped":
            out.append(f"{r['piece']} was dropped, so this piece needs changing in chat")
        elif row_status(r) not in MET:
            out.append(f"it waits for {r['piece']}, which isn't on dev yet ({r['status'] or 'no status'})")
    return out


def next_number(root: Path, rows: list[dict]) -> int:
    """One past the highest contract number in this repo's rows and in contracts/."""
    # Notion links a file name ending in .md (a web domain): "contracts/[007-x.md](http://007-x.md)" (D93)
    nums = [int(n) for r in rows for n in re.findall(r"(?:^|[/\[])(\d{3})-[\w.-]*?\.md", r["contract_file"])]
    nums += [int(p.name[:3]) for p in contracts_dir(root).glob("[0-9][0-9][0-9]-*.md")]
    return (max(nums) + 1) if nums else 1


def mine_and_rows(root: Path, args) -> tuple[str, list[dict], list[dict]]:
    """(this repo's name, every row, this repo's rows)."""
    cfg = load_config(root)
    mine = (cfg.get("repo") or repo_name(root) or "").strip()
    rows = load_rows(args.rows)
    return mine, rows, rows_of_repo(rows, mine, args.single_repo)


def cmd_next_pick(args) -> int:
    """Which Ready row of this repo may build now (D93): the lowest Order whose Depends on rows are all on dev or
    done. Prints JSON: the pick (or null), its contract number, the rows that wait and why, and this repo's rows
    building in other sessions. 0 a pick · 1 nothing may build now."""
    root = Path(args.root).resolve()
    mine, rows, ours = mine_and_rows(root, args)
    skip = {unescape_md(s).strip().lower() for s in (args.skip or [])}
    ready = [r for r in ours if row_status(r) == "ready" and not r["head"] and r["piece"].lower() not in skip]
    if args.name:
        ready = [r for r in ready if r["piece"].lower() == unescape_md(args.name).strip().lower()]
        if not ready:
            die(f"No Ready row in this repo is called {args.name!r}. Check the name in the tracker. (A chain's "
                "sub-piece is picked up through its chain.)", 1)
    ready.sort(key=lambda r: (r["order"] is None, r["order"] or 0, r["piece"].lower()))
    pick, waiting = None, []
    for r in ready:
        why = unmet(rows, r["depends"])
        if why:
            waiting.append({"piece": r["piece"], "why": "; ".join(why)})
            continue
        pick = r
        break
    print(json.dumps({"pick": pick, "number": next_number(root, ours), "waiting": waiting,
                      "building": [r["piece"] for r in ours if row_status(r) == "building"]}, indent=2,
                     ensure_ascii=False))
    return 0 if pick else 1


def depends_problems(rows: list[dict], ours: list[dict], row: dict | None, line: list[str] | None,
                     piece: str) -> tuple[int, str] | None:
    """Pickup's check of a row's Depends on (D93), as (exit code, why), or None when it may build now. The
    contract's line is the truth and the tracker's column mirrors it: they must name the same rows. A contract
    with no line (from before D93) builds only while nothing else of this repo is building."""
    if row is None:
        return 1, (f"the row {piece!r} isn't in {ROWS_FILE}. Query the tracker again and write every row there")
    column = row["depends"]
    if line is None:
        if column:
            return 1, (f"the row's Depends on column names {', '.join(column)}, but the contract has no Depends on "
                       f"line, and the line is what counts. Add it to the contract, like `Depends on: {column[0]}`")
        others = [r["piece"] for r in ours if row_status(r) == "building" and r is not row]
        if others:
            return 4, (f"Nothing was picked up: {piece} has no Depends on line (it was specced before the kit had "
                       "one), so it can only build while nothing else in this repo is building, and "
                       f"{', '.join(others)} {'is' if len(others) == 1 else 'are'}. Pick another row, or add a "
                       "Depends on line in chat.")
        return None
    named, missing = [], []
    for n in line:
        r = find_row(rows, n)
        (named if r else missing).append(r if r else n)
    if missing:
        titles = [r["piece"] for r in rows]
        shown = "; ".join(f"“{m}”" + (f" (did you mean “{close[0]}”?)" if (close := difflib.get_close_matches(
            m, titles, n=1, cutoff=0.6)) else "") for m in missing)
        return 1, (f"the Depends on line names {shown}, and the tracker has no row with "
                   f"{'that name' if len(missing) == 1 else 'those names'}. Check the spelling against the tracker")
    if any(r is row for r in named):
        return 1, f"{piece} depends on itself. Remove its own name from the Depends on line"
    col_rows = [find_row(rows, d) for d in column]
    if None in col_rows or {id(r) for r in named} != {id(r) for r in col_rows}:
        shown = ", ".join(column) or "nothing"
        return 1, (f"the contract's Depends on line ({depends_line(line)}) and the row's Depends on column "
                   f"({shown}) don't match. The line is what counts: make them name the same rows")
    why = unmet(rows, line)
    if why:
        return 4, f"Nothing was picked up: {piece} can't build yet, because {'; '.join(why)}. Pick another row."
    return None


# ---------------------------------------------------------------- one row, one session (issue #30)
# Notion has no lock. Two sessions that query the tracker before either marks a row Building both see it Ready.
# pickup refuses a row whose Status, fetched just before, isn't Ready; then each pickup writes a random Claim into
# its contract, so into the row's copy, and claim-check reads the row back: the last copy written wins, and the
# session whose Claim isn't there backs off before it builds anything. A race narrower than that slips through, so
# sync-dev and the check also refuse a piece that dev already holds from another session (taken_on_dev).
TAKEN = 5


def claim_in(text: str) -> str:
    return (field(notion_to_plain(text), "Claim") or "").strip()


def is_tracked(root: Path, path: Path) -> bool:
    return sh(["git", "ls-files", "--error-unmatch", path.relative_to(root).as_posix()], cwd=root).returncode == 0


def cmd_claim_check(args) -> int:
    """After pickup set the row Building and wrote its copy: read the row back. 0 this session holds it · 1 a write
    didn't land (write it again) · 5 another session holds it: this session's uncommitted contract is removed."""
    root = Path(args.root).resolve()
    c = find_contract(root, args.contract, ("building",), "claim")
    theirs = claim_in(Path(args.notion).read_text(encoding="utf-8"))
    if args.recheck:
        return claim_recheck(c, theirs)
    if not c.claim:
        die(f"{c.name} has no Claim: line (it was picked up before kit 0.16.5), so there's nothing to compare.")
    if args.status is None:
        die("--status is needed: the row's Status as the tracker shows it now (only --recheck goes without it).")
    status = unescape_md(args.status).strip()
    if theirs == c.claim and status.lower() == "building":
        print(f"claimed: the row holds {c.name}'s Claim ({c.claim}) and says Building. This session builds it.")
        return 0
    if theirs == c.claim or (not theirs and status.lower() in ("ready", "building")):
        what = "the copy" if status.lower() == "building" else "Status Building"
        print(f"not landed: the row says {status or 'no status'} and its copy holds "
              f"{'this Claim' if theirs else 'no Claim'}, so {what} didn't reach Notion. Write the Status and the "
              "copy again, read the row back and run claim-check again. Build nothing until it passes.")
        return 1
    rel = c.path.relative_to(root).as_posix()
    if is_tracked(root, c.path):
        undo = (f"{rel} is already committed here, so it was left as it is: ask the owner before building on; never "
                "/mg-ship-kit:drop it, which would mark the other session's row Dropped.")
    else:
        c.path.unlink()
        data = load_sync(root)
        if data.pop(c.name, None) is not None:
            save_sync(root, data)
        undo = f"{rel} was never committed, so it was removed."
        if sh(["git", "diff", "--quiet", "--", CONFIG], cwd=root).returncode != 0:
            undo += f" {CONFIG} changed too (pickup's reuse packages): `git checkout -- {CONFIG}`."
    print(f"taken: another session picked up {c.title} too, and the row now holds its pickup "
          f"({status or 'no status'}, Claim {theirs or 'none'}; this session's was {c.claim}). {undo} Leave the row "
          "alone: it is the other session's. Pick another piece with /mg-ship-kit:next.")
    return TAKEN


def claim_recheck(c: Contract, theirs: str) -> int:
    """Before the push (cto-check): is the row still this session's? The claim at pickup can pass in two sessions
    when the second one wrote after the first had read back; by now the row holds one Claim, so exactly one goes on.
    Removes nothing: the piece may hold hours of work."""
    if not c.claim:
        print(f"{c.name} has no `Claim:` line (a chain's sub-piece, a quick fix, or a pickup before kit 0.16.5): "
              "nothing to recheck.")
        return 0
    if theirs == c.claim:
        print(f"claimed: the row still holds {c.name}'s Claim ({c.claim}). Go on.")
        return 0
    if not theirs:
        print(f"no Claim on the row: its copy holds none, so it can't say whose piece it is. Refresh its copy "
              "(tracker.md), read the row back and run claim-check --recheck again. Push nothing until it passes.")
        return 1
    print(f"taken: the row now holds another session's Claim ({theirs}; this session's is {c.claim}). Another "
          f"session picked up {c.title} too and builds it. Push nothing. Ask the owner which to keep; never "
          "/mg-ship-kit:drop this one, which would mark the shared row Dropped, and never overwrite the row's copy.")
    return TAKEN


def taken_on_dev(root: Path, c: Contract, dev: str = "refs/remotes/origin/dev") -> Contract | None:
    """The contract on dev for the same tracker row as c, picked up by another session: two sessions built one piece.
    None when dev holds no such contract, or holds this session's own (pushed earlier)."""
    if not is_commit(root, dev):
        return None
    pid = page_id(c.tracker)
    for x in contracts_at(root, dev):
        same = (pid and page_id(x.tracker) == pid) or (not pid and not page_id(x.tracker) and not c.quick
                                                       and x.title.strip().lower() == c.title.strip().lower())
        if not same or x.status == "dropped":
            continue
        if c.claim and x.claim:
            if x.claim != c.claim:
                return x
            continue
        # No Claim on one side (picked up before kit 0.16.5): dev's file is this session's own when the commit that
        # added it there is already under HEAD (pushed from here, or pulled before this piece started)
        rel = f"{CONTRACTS}/{x.path.name}"
        added = git_out(root, "log", "-1", "--diff-filter=A", "--format=%H", dev, "--", rel)
        if not (added and is_ancestor(root, added, "HEAD")):
            return x
    return None


def taken_message(c: Contract, x: Contract) -> str:
    return (f"STOP: two sessions built the same piece. Dev already has {x.path.name} ({x.status}) for the row "
            f"{c.title!r}: another session picked it up and pushed it first. Nothing was changed. Ask the owner which "
            "one to keep. Usually it's dev's: then reset this branch to origin/dev. Don't use /mg-ship-kit:drop here, "
            "because it would mark the shared row Dropped.")


# ---------------------------------------------------------------- catching up with dev (D93)
def contracts_at(root: Path, ref: str) -> list[Contract]:
    """The contracts as they are at a commit (another session's states, after it pushed to dev)."""
    res = sh(["git", "ls-tree", "--name-only", f"{ref}:{CONTRACTS}"], cwd=root)
    out = []
    for n in res.stdout.split() if res.returncode == 0 else []:
        if not n.endswith(".md") or n.upper().startswith("TEMPLATE") or n.upper() == "README.MD":
            continue
        t = sh(["git", "show", f"{ref}:{CONTRACTS}/{n}"], cwd=root)
        if t.returncode == 0:
            out.append(Contract(contracts_dir(root) / n, t.stdout))
    return out


def alembic_heads(root: Path, cfg: dict, ref: str | None) -> list[str]:
    """Alembic revisions no other revision builds on, at a commit or (ref None) in the working tree. With more than
    one, `alembic upgrade head` refuses to run: two pieces each added a migration on the same parent."""
    py = cfg.get("python_dir")
    if py is None:
        return []
    if ref is None:
        base = dir_path(root, py)
        files = {f.relative_to(root).as_posix(): f.read_text(encoding="utf-8", errors="ignore")
                 for f in walk_files(base) if f.suffix == ".py"} if base.is_dir() else {}
    else:
        files = {f: t for f, t in ref_files(root, ref).items() if in_dir(f, py) and f.endswith(".py")}
    revs, downs = {}, set()
    for f, text in files.items():
        r = ALEMBIC_REV_RE.search(text)
        if not r or is_test_file(f):
            continue
        revs[r.group(1)] = f
        d = ALEMBIC_DOWN_RE.search(text)
        if d:
            downs |= set(re.findall(r"[\"']([^\"']+)[\"']", d.group(1)))
    return sorted(f"{r} ({f})" for r, f in revs.items() if r not in downs)


def migration_problem(root: Path, cfg: dict, before: str, ref: str | None) -> str | None:
    """D93: a piece may not leave more Alembic heads than there were before it (two parallel pieces that each
    added a migration on the same parent). None when fine."""
    now = alembic_heads(root, cfg, ref)
    if len(now) < 2:
        return None
    was = alembic_heads(root, cfg, before) if before and before != EMPTY_TREE and is_commit(root, before) else []
    if len(now) <= max(len(was), 1):
        return None
    return (f"the database migrations split in two ({len(now)} Alembic heads: {', '.join(now)}). Another piece added "
            "a migration on the same parent, and `alembic upgrade head` won't run like this. Point this piece's "
            "migration's down_revision at the other head, so they run in order, then run the check again.")


SYNC_STATE = ".ship/sync.json"  # a rebase the owner let run into its conflicts: the dev commit it goes onto


def rebase_open(root: Path) -> bool:
    return any((root / git_out(root, "rev-parse", "--git-path", d)).exists() for d in ("rebase-merge", "rebase-apply"))


def move_base(root: Path, c: Contract, tip: str) -> None:
    old = c.base
    c.set_status(c.status, {"Base": tip[:10]})
    print(f"{c.name}: rebased onto dev at {tip[:10]}; Base: {old[:10]} → {tip[:10]} (only commits already on dev are "
          f"between them). Commit {c.path.relative_to(root)} with the piece, and refresh its tracker copy.")


def unchecked_on_dev(root: Path, cfg: dict, tip: str) -> str | None:
    """Why the Base may not move to dev's tip: dev holds product code no check passed (issue #40). GitHub's check on
    this piece's push would start from the newest passed (or adopted) commit, and code after it that is before the
    Base belongs to no piece, so every push would fail. None when there is no such code, or GitHub can't be asked:
    then a note says so, and the push gate and GitHub still catch it."""
    gh = github_from_gh(root)
    if isinstance(gh, str):
        print(f"note: couldn't ask GitHub which commits on dev passed the check ({gh}). If dev holds code no check "
              "passed, GitHub will refuse this piece's push: then the owner adopts that code (ship_check.py adopt).")
        return None
    passed, running = None, False
    try:
        for sha in git_out(root, "rev-list", "--first-parent", "--max-count=50", tip).split():
            v = gh.verdict(sha)
            if v == "passed":
                passed = sha
                break
            running = running or v == "running"
    except SystemExit:
        print("note: GitHub didn't answer which commits on dev passed the check, so sync went on without asking.")
        return None
    since = passed or fallback_since(root, cfg)[0]
    a = adopted_start(root, since, tip, tip)
    if a:
        since = a["sha"]
    rules, _ = rules_since(root, cfg, since)
    code = product_files(root, rules, since, tip)
    if not code:
        return None
    if running:
        return (f"the Ship check is still running on dev for code another session pushed ({short_list(code)}). "
                "Nothing was changed. Wait for it to finish, then sync again.")
    return (f"STOP: dev holds code no check passed: {short_list(code)}, after {since[:10]} (the newest commit that "
            f"passed{' or was adopted' if a else ''}). Moving {{name}}'s Base past it would make GitHub refuse every "
            "push of this piece. Nothing was changed. Ask the owner: adopt it in one line (ship_check.py adopt "
            f"{tip[:10]} --by <owner> --why \"<their words>\"), or fix it on dev. Then sync again.")


def sync_continue(root: Path, cfg: dict, args) -> int:
    """After the owner let a conflicted rebase run and Claude resolved it: move the Base to the dev commit the rebase
    went onto, the one sync-dev recorded (never a commit Claude names)."""
    p = root / SYNC_STATE
    if not p.is_file():
        die("There's no sync to finish. One starts when sync-dev --owner-ok stops on conflicts.")
    st = json.loads(p.read_text(encoding="utf-8"))
    if rebase_open(root):
        die("The rebase is still open. Resolve the conflicts, `git add` the files, run `git rebase --continue`, "
            "then run sync-dev --continue again.", 1)
    c = active_contract(root, args.contract or st.get("contract"))
    if not c or c.name != st.get("contract"):
        die(f"That sync was for {st.get('contract')}, which isn't the piece building here.")
    if not is_ancestor(root, st["onto"], "HEAD"):
        die(f"The rebase was abandoned: dev's commit {st['onto'][:10]} isn't in this branch. Run sync-dev again.", 1)
    move_base(root, c, st["onto"])
    p.unlink()
    print("The review covers the code as it was: run it again (/mg-ship-kit:cto-check step 5) if a reviewed file "
          "changed.")
    return 0


def cmd_sync_dev(args) -> int:
    """Bring the building piece up to date with dev before its check and push (D93). Another session may have pushed
    a piece since this one started: rebase onto origin/dev and move the contract's Base to it, so the other piece's
    code doesn't count against this one. The Base moves only past commits already on dev. Stops, changing nothing,
    when both changed the same product file or the rebase conflicts: the pieces weren't independent. On the owner's
    word (--owner-ok) it goes on, and leaves a conflicted rebase open for Claude to resolve; --continue then moves
    the Base."""
    root = Path(args.root).resolve()
    cfg = load_config(root)
    if args.cont:
        return sync_continue(root, cfg, args)
    c = active_contract(root, args.contract)
    if not c:
        print("ship: no piece is building here, so there is nothing to bring up to date.", file=sys.stderr)
        return 3
    if c.is_head:
        die(f"{c.name} is a chain head and has no code to sync. Sync the sub-piece that's building.", 2)
    if not args.no_fetch:
        f = sh(["git", "fetch", "-q", "origin", "dev"], cwd=root)
        if f.returncode != 0:
            die(f"Couldn't fetch dev from GitHub ({f.stderr.strip() or 'no answer'}). The sync needs dev as GitHub has "
                "it: check the connection and try again.")
    dev = "refs/remotes/origin/dev"
    if not is_commit(root, dev):
        die("There's no dev branch from GitHub here (origin/dev). Run `git fetch origin dev`, then sync again.")
    tip = rev(root, dev)
    x = taken_on_dev(root, c, dev)
    if x:
        print(taken_message(c, x))
        return 1
    if is_ancestor(root, dev, "HEAD"):
        print(f"{c.name}: up to date with dev ({tip[:10]}); nothing to sync.")
        return 0
    if not is_commit(root, c.base):
        die(f"{c.name} starts from commit {c.base}, which isn't in this copy of the repo. Fetch the full history "
            "(git fetch --unshallow), then try again.")
    dirty = [l[3:] for l in sh(["git", "status", "--porcelain"], cwd=root).stdout.splitlines() if len(l) > 3]
    if dirty:
        print(f"dev moved since {c.name} started (another session pushed). Commit the piece's work, its contract file "
              f"with it ({short_list(dirty, 5)} aren't committed), then sync again.")
        return 1
    others = [x for x in contracts_at(root, dev) if x.status == "building" and not x.is_head and x.name != c.name]
    if others:
        print(f"{others[0].name} is building on dev: its session pushed it and hasn't pushed its on-dev mark yet. "
              "It does that right after the push: wait for it, then sync again.")
        return 1
    start = git_out(root, "merge-base", c.base, dev)
    early = product_files(root, cfg, start, c.base) if start else []
    if not start or early:
        print(f"{c.name} was picked up on top of code that isn't on dev ({short_list(early) or 'no shared history'}), "
              "so that code belongs to no piece. Ask the owner what it is.")
        return 1
    held = unchecked_on_dev(root, cfg, tip)
    if held:
        print(held.replace("{name}", c.name))
        return 1
    fork = git_out(root, "merge-base", "HEAD", dev)
    mine = set(product_files(root, cfg, fork, "HEAD"))
    theirs = set(product_files(root, cfg, fork, dev))
    both = sorted(mine & theirs)
    if both and not args.owner_ok:
        print(f"STOP: {c.name} and dev both changed {short_list(both)}. The pieces weren't independent after all, and "
              "taking dev's version in means changing another piece's code, which the client may be testing. Nothing "
              "was changed. Ask the owner how to go on; on their word, sync-dev --owner-ok goes ahead (the review "
              "runs again, since a reviewed file changes).")
        return 1
    r = sh(["git", "-c", "core.editor=true", "rebase", "--quiet", dev], cwd=root)
    if r.returncode != 0:
        clash = git_out(root, "diff", "--name-only", "--diff-filter=U").split()
        if args.owner_ok and rebase_open(root):
            (root / ".ship").mkdir(exist_ok=True)
            (root / SYNC_STATE).write_text(json.dumps({"contract": c.name, "onto": tip}) + "\n", encoding="utf-8")
            print(f"the rebase onto dev stopped on conflicts in {short_list(clash) or 'files git named'}, and is left "
                  "open on the owner's word. Resolve each: keep the other piece's code as dev has it, change only this "
                  f"piece's side. Then `git add` them, `git rebase --continue`, and sync-dev --continue.")
            return 1
        sh(["git", "rebase", "--abort"], cwd=root)
        print(f"STOP: the rebase onto dev conflicts in {short_list(clash) or 'files git named'}. The pieces weren't "
              "independent after all. Nothing was changed (the rebase was undone). Ask the owner how to go on; on "
              "their word, sync-dev --owner-ok leaves the rebase open for you to resolve.")
        return 1
    move_base(root, Contract(c.path), tip)
    m = migration_problem(root, cfg, tip, None)
    if m:
        print(f"note: {m}")
    return 0


# ---------------------------------------------------------------- chains (D61)
def head_named(root: Path, name: str | None, what: str) -> tuple[Contract, list[Contract]]:
    """The head contract named, or the only open one, with its sub-pieces."""
    cs = list_contracts(root)
    if name:
        hits = [c for c in cs if c.name == name or c.path.name == name or c.name.startswith(name)]
        if not hits:
            die(f"There's no contract called {name!r} in {CONTRACTS}/. Check the name against the files there.")
        if not hits[0].is_head:
            die(f"{hits[0].name} isn't a chain head: it has no `Chain: head` line.")
        return hits[0], subs_of(cs, hits[0])
    heads = open_heads(cs)
    if not heads:
        die(f"Nothing to {what}: no chain is open. Pick a chain head up first, with /mg-ship-kit:chain.", 3)
    if len(heads) > 1:
        die(f"More than one chain is open ({', '.join(c.name for c in heads)}). Say which, like --head {heads[0].name}.")
    return heads[0], subs_of(cs, heads[0])


def partition_problems(head: Contract, subs: list[tuple[str, Contract]], complete: bool = True) -> list[str]:
    """The split must cover the head exactly: every named item in the head's Size goes to one sub-piece, no
    sub-piece names an item the head doesn't, and the counts add up. That is what 'a sub-piece traces to the
    head' means mechanically."""
    problems = []
    for label, s in subs:
        problems += [f"{label}: {p}" for p in s.count_problems()]
    for kind in ("screens", "endpoints", "tables"):
        head_n, head_items = head.size[kind]
        free = list(head_items)
        total = 0
        for label, s in subs:
            n, items = s.size[kind]
            total += n
            for it in items:
                hit = next((d for d in free if match_pair(kind, it, d, exact=True)), None)
                if hit is None:
                    taken = any(match_pair(kind, it, d, exact=True) for d in head_items)
                    problems.append(f"{label}: the {kind[:-1]} {it} " + ("is already in another sub-piece" if taken
                                                                             else "isn't in the head's Size list"))
                else:
                    free.remove(hit)
        if not complete:  # a sub-contract couldn't be read: what it holds would show here as missing
            continue
        # A sub-piece that counts more than it names may hold the uncovered item: naming it there fixes both lines
        short = [label for label, s in subs if s.size[kind][0] > len(s.size[kind][1])]
        hint = (f" (maybe it's the one {short[0]} counts but doesn't name: naming it there fixes this too)"
                if short else "")
        for d in free:
            problems.append(f"the {kind[:-1]} {d} is in the head's Size list but in no sub-piece{hint}")
        if total != head_n:
            problems.append(f"{kind}: the sub-pieces add up to {total}, but the head says {head_n}")
    return problems


def cmd_split(args) -> int:
    """Save the sub-contracts Claude wrote for a head as draft contracts, checked against the head (the split stop)."""
    root = Path(args.root).resolve()
    load_config(root)
    head, subs = head_named(root, args.head, "split")
    if head.status != "building":
        die(f"{head.name} can't be split now: it's {head.status}. A head is split right after pickup, while it's "
            "building.", 1)
    if subs:
        die(f"{head.name} is already split into {len(subs)} sub-pieces ({', '.join(c.name for c in subs)}). "
            "To split it another way, drop the chain first.", 1)
    if not 2 <= len(args.files) <= MAX_SUBS:
        die(f"A chain has 2 to {MAX_SUBS} sub-pieces, and this split has {len(args.files)}. One sub-piece is just a "
            f"piece; more than {MAX_SUBS} is two chains. Spec it that way in chat.", 1)
    written: list[Path] = []
    parsed: list[tuple[str, Contract]] = []
    names: set[str] = set()
    problems: list[str] = []  # every problem in every sub-contract, found in one go
    floor = next_number(root, mine_and_rows(root, args)[2]) if args.rows else 1  # D93: numbers from the tracker
    try:
        for f in args.files:
            p = Path(f)
            if not p.is_file():
                problems.append(f"{f} isn't a file")
                continue
            raw = p.read_text(encoding="utf-8")
            m = TITLE_RE.search(raw)
            if not m:
                problems.append(f"{p.name} has no title line. Start it with one, like `# Contract: Weekly totals`")
                continue
            name, _, body = contract_parts(raw, need_approval=False)
            label = name
            if name.lower() in names:
                problems.append(f"two sub-pieces are both called {name!r}. Give each its own name")
                continue
            names.add(name.lower())
            ok = True
            m = re.search(heading_re("How to check it") + rf"\s*\n\s*{BULLET}\s+(\S.*?)\s*$", body, re.M | re.I)
            if not m or PLACEHOLDER_RE.fullmatch(m.group(1).strip()):
                problems.append(f"{label} has no check line. The chain stops on each sub-piece's check, so add one "
                                "under `## How to check it`, like:\n       - When I open /reports then I see this "
                                "week's total")
            size_problems = parse_size(body)[1]
            if size_problems:
                problems += [f"{label}: {sp}" for sp in size_problems]
                ok = False
            if not ok:
                continue
            path = new_contract_path(root, name, floor)
            header = [f"# Contract: {name}", "Status: draft", f"Head: {head.name}", f"Approved: {GO_PENDING}"]
            if head.repo:  # a sub-piece builds in its head's repo (D88); a cross-repo chain is a later door
                header.append(f"Repo: {head.repo}")
            path.write_text("\n".join(header) + "\n\n" + body, encoding="utf-8")
            written.append(path)
            parsed.append((name, Contract(path)))
        complete = len(parsed) == len(args.files)
        problems += partition_problems(head, parsed, complete)
        if problems:
            n = len(problems)
            note = "" if complete else ("\nOnce every sub-contract can be read, the split also checks that they "
                                        "cover the head exactly.")
            die(f"Nothing was split. The sub-contracts have {n} problem{'s' if n > 1 else ''} to fix:\n"
                + "\n".join(f"  {i}. {p}" for i, p in enumerate(problems, 1))
                + "\nFix " + ("them all" if n > 1 else "it") + ", then split again. Each sub-piece names only items "
                "the head names, and each item goes to exactly one sub-piece." + note, 1)
    except BaseException:  # a refused split, or any error on the way: leave nothing behind
        for p in written:
            p.unlink(missing_ok=True)
        raise
    print(f"split {head.name} into {len(written)} draft sub-pieces, in build order:")
    for i, p in enumerate(written, 1):
        print(f"  {i}. {p.relative_to(root)}")
    print("Nothing builds yet: the owner reads the sub-pieces and says go (`go --head`).")
    return 0


def cmd_go(args) -> int:
    """The owner read the split: every draft sub-piece becomes ready."""
    root = Path(args.root).resolve()
    load_config(root)
    head, subs = head_named(root, args.head, "start")
    if head.status != "building":
        die(f"{head.name} can't get a go now: it's {head.status}. The go is for a chain that's building.", 1)
    drafts = [c for c in subs if c.status == "draft"]
    if not subs:
        die(f"{head.name} isn't split yet. Split it first.", 1)
    if not drafts:
        die(f"Every sub-piece of {head.name} already has its go.", 1)
    owner = re.sub(r"^.*?\bby\s+", "", head.approved).strip() or head.approved
    stamp = f"{dt.date.today().isoformat()} by {owner}, go on chain {head.name}"
    for c in drafts:
        c.set_status("ready", {"Approved": stamp})
    print(f"go: {len(drafts)} sub-pieces of {head.name} are ready, in this order: " + ", ".join(c.name for c in drafts))
    return 0


def cmd_chain_next(args) -> int:
    """Pick up the next ready sub-piece of a chain: building, from this commit. Once a sub-piece of the chain is
    on dev, the next one starts only when GitHub's check is green on origin/dev (D61's second halt), or when the
    owner said so in their own words (--green)."""
    root = Path(args.root).resolve()
    load_config(root)
    head, subs = head_named(root, args.head, "continue")
    cs = list_contracts(root)
    busy = building_pieces(cs)
    if busy:
        die(f"{busy[0].name} is still building in this session, and a session builds one piece at a time. Push it "
            "to dev with /mg-ship-kit:cto-check, or drop it, then continue the chain. (rule D93)", 2)
    if not subs:
        die(f"{head.name} isn't split yet. Split it first.", 1)
    if any(c.status == "draft" for c in subs):
        die(f"{head.name} is waiting for the owner's go. They read the sub-pieces, then give it with "
            f"`go --head {head.name}`.", 1)
    ready = [c for c in subs if c.status == "ready"]
    if not ready:
        return cmd_chain_sync(args)
    if any(c.status in ("on-dev", "done") for c in subs) and not args.green:
        dev = "refs/remotes/origin/dev"
        if not is_commit(root, dev):
            die("There's no dev branch from GitHub here (origin/dev), so the last sub-piece's check can't be "
                "confirmed. Run `git fetch origin dev`, then continue.", 2)
        rc = wait_for_ci(root, rev(root, dev), args.timeout, args.poll)
        if rc != 0:
            print(f"the chain halts before its next sub-piece: GitHub's check on origin/dev isn't green. When the "
                  "Actions tab shows green, continue with `chain-next --green` (the owner's word).")
            return rc
    c = ready[0]
    base = git_out(root, "rev-parse", "--short=10", "HEAD")
    try:
        c.set_status("building", {"Base": base})
        c.check_ready()
    except SystemExit:
        c.set_status("ready", {"Base": None})
        raise
    left = len(ready) - 1
    print(f"{c.name}: Status: building · Base: {base} · sub-piece of {head.name} · {left} more after this one")
    return 0


def chain_state(head: Contract, subs: list[Contract]) -> tuple[str | None, str]:
    """What the head should be, from its sub-pieces, with the reason: 'on-dev' once every sub-piece is on dev or
    done; 'dropped' once every one is dropped; else None (still building). A dropped sub-piece among built ones
    holds the head back, since its items are in the head's Size but won't be built — unless the owner approved a
    head contract change that took those items out, which the head's Size list shows."""
    if not subs:
        return None, "not split yet"
    if all(c.status == "dropped" for c in subs):
        return "dropped", "every sub-piece was dropped"
    open_ = [c for c in subs if c.status not in ("on-dev", "done", "dropped")]
    if open_:
        return None, "waiting on " + ", ".join(f"{c.name} ({c.status})" for c in open_)
    orphans = []
    for c in subs:
        if c.status != "dropped":
            continue
        for kind in ("screens", "endpoints", "tables"):
            for it in c.size[kind][1]:
                if any(match_pair(kind, it, d, exact=True) for d in head.size[kind][1]):
                    orphans.append(f"{kind[:-1]} {it} ({c.name}, dropped)")
    if orphans:
        return None, ("these items are in the head's Size but their sub-piece was dropped, so the feature is not "
                      "what the head promises: " + ", ".join(orphans) + ". Either the owner approves a head contract "
                      "change that takes them out (one line), or the rest of the chain is dropped too.")
    return "on-dev", "every sub-piece is on dev"


def cmd_chain_sync(args) -> int:
    """Move the head with its sub-pieces: on-dev when all are on dev, dropped when all are dropped."""
    root = Path(args.root).resolve()
    head, subs = head_named(root, getattr(args, "head", None), "sync")
    want, why = chain_state(head, subs)
    moved = move_head(head, want)
    if not moved:
        print(f"{head.name}: {head.status} · {why}")
    return 0


def move_head(head: Contract, want: str | None) -> bool:
    """Set the head to what its sub-pieces say, if that is a move. Prints the move."""
    if want == "on-dev" and head.status == "building":
        head.set_status("on-dev")
        print(f"{head.name}: Status: on-dev — the chain is on dev. The client tests the whole feature there; "
              "one verdict closes it: /mg-ship-kit:done on the head.")
        return True
    if want == "dropped" and head.status in ("building", "on-dev"):
        head.set_status("dropped")
        print(f"{head.name}: Status: dropped — every sub-piece was dropped.")
        return True
    return False


def cmd_chain_status(args) -> int:
    root = Path(args.root).resolve()
    cs = list_contracts(root)
    heads = [c for c in cs if c.is_head]
    if args.head:
        head, _ = head_named(root, args.head, "list")
        heads = [head]
    if args.json:
        print(json.dumps([{"head": h.name, "status": h.status, "subs": [{"contract": c.name, "status": c.status,
                                                                          "tracker": c.tracker} for c in subs_of(cs, h)]}
                          for h in heads], indent=2))
        return 0
    if not heads:
        print("no chains")
    for h in heads:
        print(f"{h.name:40} {h.status:10} head")
        for c in subs_of(cs, h):
            print(f"  {c.name:38} {c.status:10} {c.tracker or '(no tracker row)'}")
    return 0


def cmd_set_tracker(args) -> int:
    root = Path(args.root).resolve()
    c = find_contract(root, args.contract, ("building", "on-dev"), "stamp")
    c.set_status(c.status, {"Tracker": args.tracker})
    print(f"{c.name}: Tracker: {args.tracker}")
    return 0


def github_from_gh(root: Path) -> GitHub | str:
    """A GitHub client for a session outside Actions, from the gh CLI's login; or one line on why there is none."""
    if shutil.which("gh") is None:
        return "`gh` isn't installed"
    tok = sh(["gh", "auth", "token"], cwd=root)
    if tok.returncode != 0 or not tok.stdout.strip():
        return "`gh` isn't logged in (`gh auth login`)"
    repo = sh(["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"], cwd=root)
    if repo.returncode != 0 or not repo.stdout.strip():
        return ("`gh` can't tell which GitHub repo this is (no GitHub remote, or several: `gh repo set-default`)")
    gh = GitHub(offline=True)
    gh.token, gh.repo = tok.stdout.strip(), repo.stdout.strip()
    return gh


def wait_for_ci(root: Path, sha: str, timeout: int, poll: int) -> int:
    """0 once GitHub's Ship check passed on sha as a push to dev · 1 red, or not green in time · 2 can't ask."""
    gh = github_from_gh(root)
    if isinstance(gh, str):
        print(f"can't ask GitHub whether the check passed: {gh}. Look at the repo's Actions tab yourself; "
              "the chain waits.")
        return 2
    start, deadline = time.time(), time.time() + timeout
    print(f"waiting for the Ship check on {sha[:10]} (dev) …")
    while True:
        try:
            v = gh.verdict(sha)
        except SystemExit:
            print("GitHub didn't answer (network, or the token lacks access to this repo's Actions). The chain "
                  "waits; run ci-wait again, or look at the Actions tab.")
            return 2
        if v == "passed":
            print(f"the Ship check passed on {sha[:10]} on dev.")
            return 0
        if v == "failed":
            print(f"the Ship check failed on {sha[:10]} on dev: red. The chain halts here. Read the run's log on the "
                  "Actions tab, fix it, push again.")
            return 1
        now = time.time()
        if v == "none" and now - start >= min(timeout, CI_NEVER_STARTED_S):
            print(f"no run of the Ship check exists for {sha[:10]} on dev after {int(now - start)}s. Is "
                  f"{CI_WORKFLOW} on dev, and are Actions on for this repo? The chain halts here.")
            return 1
        if now >= deadline:
            print(f"still running after {timeout}s. The chain halts here: check the Actions tab, then run ci-wait "
                  "again when it's green.")
            return 1
        time.sleep(poll)


def cmd_ci_wait(args) -> int:
    """Wait for GitHub's Ship check on a commit pushed to dev. A chain starts its next sub-piece only on green."""
    root = Path(args.root).resolve()
    sha = rev(root, args.sha) if is_commit(root, args.sha) else ""
    if not sha:
        die(f"{args.sha!r} isn't a commit in this repo.")
    return wait_for_ci(root, sha, args.timeout, args.poll)


def is_project_workflow(f: str) -> bool:
    """A GitHub workflow or action the project owns: code that runs on the runner with the repo's secrets, so it
    counts as product code like any other (issue #34). The kit's own two workflows stay bookkeeping."""
    return f.startswith(PROJECT_CI_DIRS) and f not in (CI_WORKFLOW, SECRETS_WORKFLOW)


def is_bookkeeping(f: str, cfg: dict | None = None) -> bool:
    """Files that carry no product code: contract states, kit setup, rules, the kit's CI files and the rest of
    .github/ (templates, settings) except the project's own workflows and actions, the readme, plus any paths
    the owner listed under `bookkeeping` in ship.json (a folder ends with '/'; globs allowed).
    The push gate and the GitHub check use this one list."""
    name = f.rsplit("/", 1)[-1].lower()
    if (f.startswith(CONTRACTS + "/") or f in BOOKKEEPING_FILES or (f.startswith(".github/") and not is_project_workflow(f))
            or ("/" not in f and (name.startswith("readme") or name.startswith("license")))):
        return True
    for pat in (cfg or {}).get("bookkeeping", []):
        if (pat.endswith("/") and f.startswith(pat)) or f == pat or fnmatch.fnmatch(f, pat):
            return True
    return False


def is_env_file(f: str) -> bool:
    """An env file that may hold secrets: `.env` or `.env.<anything>` in any folder, except the example files."""
    name = f.rsplit("/", 1)[-1].lower()
    return (name == ".env" or name.startswith(".env.")) and name not in ENV_EXAMPLES


def env_files(root: Path, ref: str | None = None) -> list[str]:
    """Env files git tracks: in the index (ref None) or in a commit's tree. Only the files themselves: a key
    pasted into code isn't found here."""
    args = ["git", "ls-files", "-z"] if ref is None else ["git", "ls-tree", "-r", "-z", "--name-only", ref]
    res = sh(args, cwd=root)
    return [f for f in res.stdout.split("\0") if f and is_env_file(f)] if res.returncode == 0 else []


def cmd_env_check(args) -> int:
    """Exit 1 when a commit carries an env file. The push gate runs it before a release; dev and the GitHub
    check run the same rule inside their own checks."""
    root = Path(args.root).resolve()
    found = env_files(root, args.ref)
    if found:
        print(f"an env file is in {args.ref}: {short_list(found)}. {ENV_FIX}")
        return 1
    return 0


# ---------------------------------------------------------------- the secret scan (D67–D70)
def find_gitleaks() -> str | None:
    return shutil.which("gitleaks")


def gitleaks_version(tool: str) -> str:
    r = sh([tool, "version"])
    return r.stdout.strip().lstrip("v") if r.returncode == 0 else ""


def gitleaks_config() -> Path:
    """The kit's gitleaks rules: gitleaks' own defaults, nothing taken out. Passed every time, so a .gitleaks.toml in
    the project (which could switch rules off) is never read. The CI copy sits next to the CI copy of this script."""
    here = Path(__file__).resolve().parent / "gitleaks.toml"
    return here if here.exists() else kit_root() / "templates" / "ci" / "gitleaks.toml"


def allow_problems(root: Path) -> list[str]:
    """Lines of .gitleaksignore that secret-allow didn't write: each fingerprint sits under its '# allowed' line."""
    p = root / GITLEAKS_IGNORE
    if not p.exists():
        return []
    bad, prev = [], ""
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if s and not s.startswith("#") and not prev.startswith(ALLOW_MARK):
            bad.append(s)
        prev = s
    return bad


def scan_secrets(root: Path, log_opts: list[str] | None) -> tuple[int, list[dict], str]:
    """Run gitleaks on the commits `git log <log_opts>` lists (None: the whole history).
    Returns (0 clean · 1 found · 2 can't scan, findings, note). Inline `gitleaks:allow` comments are ignored and the
    kit's rules are used, so only the owner's .gitleaksignore entries clear a finding (D68)."""
    tool = find_gitleaks()
    if not tool:
        return 2, [], f"gitleaks not found, so the secret scan can't run and nothing is pushed (D67). {GITLEAKS_HINT}."
    ver = gitleaks_version(tool)
    if not ver.startswith("8."):
        return 2, [], f"gitleaks {ver or '(unknown version)'} found; the kit needs 8.x. {GITLEAKS_HINT}."
    bad = allow_problems(root)
    if bad:
        return 2, [], (f"{GITLEAKS_IGNORE} has lines secret-allow didn't write: {short_list(bad, 3)}. Only the owner "
                       "clears a finding, through `ship_check.py secret-allow`: remove those lines.")
    if log_opts is not None and not log_opts:
        return 0, [], "no new commits"
    with tempfile.TemporaryDirectory() as td:
        report = Path(td) / "report.json"
        cmd = [tool, "git", "--no-banner", "--no-color", "--redact", "--ignore-gitleaks-allow", "--log-level", "error",
               "--config", str(gitleaks_config()), "--report-format", "json", "--report-path", str(report),
               "--exit-code", "1"]
        if log_opts:
            cmd += ["--log-opts", " ".join(log_opts)]
        r = sh(cmd + ["."], cwd=root)
        if r.returncode not in (0, 1):
            return 2, [], f"gitleaks failed (exit {r.returncode}): {(r.stderr or r.stdout).strip()[:300]}"
        try:
            found = json.loads(report.read_text()) if report.exists() else []
        except ValueError:
            return 2, [], "gitleaks wrote a report this script can't read."
    if r.returncode == 1 and not found:
        return 2, [], "gitleaks reported leaks but listed none."
    return (1 if found else 0), found, ""


def secret_lines(found: list[dict], n: int = 10) -> list[str]:
    out = [f"  {f.get('File')}:{f.get('StartLine')} · {f.get('RuleID')} · commit {str(f.get('Commit', ''))[:10]} · "
           f"fingerprint {f.get('Fingerprint')}" for f in found[:n]]
    if len(found) > n:
        out.append(f"  … and {len(found) - n} more")
    return out


def new_commits(root: Path, tip: str, exclude: list[str]) -> list[str] | None:
    """`git log` arguments for the commits in tip that aren't in any excluded ref, nor before setup (ci_since, as
    first written: older history is reported once at setup and never blocks, D69). [] when there's nothing new."""
    nots = [e for e in exclude if e == "--remotes" or is_commit(root, e)]
    s = locked_ci_since(root)
    if s and is_commit(root, s):
        nots.append(rev(root, s))
    opts = [tip] + (["--not"] + nots if nots else [])
    r = sh(["git", "rev-list", "--count", *opts], cwd=root)
    if r.returncode != 0:
        return None
    return opts if r.stdout.strip() != "0" else []


def ci_scan_range(root: Path, branch: str, before: str, after: str) -> list[str] | None:
    """The commits a GitHub push brought: after minus before, or, for a new branch, minus every other branch."""
    if before and before != ZERO_SHA and is_commit(root, before):
        return new_commits(root, after, [before])
    others = [r for r in git_out(root, "for-each-ref", "--format=%(refname)", "refs/remotes/origin").split()
              if r not in (f"refs/remotes/origin/{branch}", "refs/remotes/origin/HEAD")]
    return new_commits(root, after, others)


def report_scan(code: int, found: list[dict], note: str, what: str) -> None:
    if code == 0:
        print(f"secret scan: clean ({note or what}).")
    elif code == 1:
        print(f"secret scan: {len(found)} possible secret(s) in {what}:")
        for line in secret_lines(found):
            print(line)
        print(SECRET_FIX)
    else:
        print(f"secret scan: {note}")


def cmd_secret_scan(args) -> int:
    """Scan new commits for secrets: 0 clean · 1 found · 2 can't scan. The push gate runs it for every push (any
    branch, D70); GitHub runs it with --ci. --history scans everything and only reports (setup runs it once)."""
    root = Path(args.root).resolve()
    if args.history:
        code, found, note = scan_secrets(root, None)
        report_scan(code, found, note, "the whole history")
        if code == 1:
            print("History is reported, not blocked (D69). A key already pushed is exposed: replace it at its source. "
                  "New commits are scanned on every push.")
        return 0 if code == 1 else code
    if args.ci:
        branch = args.branch or os.environ.get("GITHUB_REF_NAME", "")
        after = args.after or os.environ.get("GITHUB_SHA", "") or "HEAD"
        before = args.before or os.environ.get("SHIP_BEFORE", "")
        if not is_commit(root, after):
            die(f"{after[:10]} isn't a commit in this checkout. Check out with fetch-depth 0.")
        opts, what = ci_scan_range(root, branch, before, rev(root, after)), f"the commits pushed to {branch or 'this branch'}"
    else:
        if not is_commit(root, args.ref):
            die(f"{args.ref!r} isn't a commit in this repo.")
        opts, what = new_commits(root, rev(root, args.ref), ["--remotes"]), f"commits not yet on GitHub ({args.ref})"
    if opts is None:
        print("secret scan: git couldn't list the new commits.")
        return 2
    code, found, note = scan_secrets(root, opts)
    report_scan(code, found, note, what)
    return code


def cmd_secret_allow(args) -> int:
    """The owner's one-line clearing of a false alarm (D68): its fingerprint goes into .gitleaksignore under a line
    naming the owner, the date and their words."""
    root = Path(args.root).resolve()
    fp, who, why = args.fingerprint.strip(), args.by.strip(), " ".join(args.why.split())
    if not fp or fp.startswith("#") or len(fp.split(":")) < 3:
        die("Give the fingerprint exactly as the secret scan printed it (commit:file:rule:line).")
    if not who or not why:
        die("--by needs the owner's name and --why their reason, in their own words.")
    p = root / GITLEAKS_IGNORE
    lines = p.read_text(encoding="utf-8").splitlines() if p.exists() else []
    if fp in (l.strip() for l in lines):
        print(f"already allowed: {fp}")
        return 0
    lines += [f"{ALLOW_MARK}{dt.date.today().isoformat()} by {who}: {why}", fp]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"allowed: {fp}. Commit {GITLEAKS_IGNORE} with your next commit; the scan skips this finding from now on.")
    return 0


def cmd_adopt(args) -> int:
    """The owner's one-line acceptance of code already on dev that no piece covers (issue #40): the dev check then
    starts after that commit. Without it, one such commit blocks every later push to dev. The secret scan still
    covers it: adoption moves only where the check starts, never the scan."""
    root = Path(args.root).resolve()
    cfg = load_config(root)
    who, why = args.by.strip(), " ".join(args.why.split())
    if not who or not why:
        die("--by needs the owner's name and --why their reason, in their own words.")
    if not is_commit(root, args.commit):
        die(f"{args.commit!r} isn't a commit in this repo.")
    sha, dev = rev(root, args.commit), "refs/remotes/origin/dev"
    if not is_commit(root, dev):
        die("There's no dev branch from GitHub here (origin/dev). Run `git fetch origin dev` first.")
    if not is_ancestor(root, sha, dev):
        die(f"{sha[:10]} isn't on dev yet. Only code already on dev can be adopted; new code goes through a piece: "
            "pick one up with /mg-ship-kit:next. (rule D1)")
    p = root / ADOPTED
    text = p.read_text(encoding="utf-8") if p.exists() else ADOPT_HEAD
    if any(a["sha"] == sha for a in adoptions(text)):
        print(f"already adopted: {sha[:10]}")
        return 0
    parent = git_out(root, "rev-parse", "--verify", "--quiet", f"{sha}^") or EMPTY_TREE
    files = product_files(root, cfg, parent, sha)
    subject = git_out(root, "log", "-1", "--format=%s", sha)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text.rstrip("\n") + f"\n- {sha} · {dt.date.today().isoformat()} by {who}: {why}\n", encoding="utf-8")
    print(f"adopted {sha[:10]} ({subject}): its product files are {short_list(files) if files else 'none'}. The dev "
          "check now starts after it, so it accepts every unchecked commit on dev up to this one too; the secret "
          f"scan still covers them. Commit {ADOPTED} on its own and push it to dev.")
    return 0


def cmd_ondev(args) -> int:
    """Mark the building contract on-dev once its piece is on origin/<branch>. A removal becomes dropped.
    All four must hold: the commit is on origin/<branch>; nothing outside contracts/ is uncommitted;
    the piece changed product code since its base; the check passes now."""
    root = Path(args.root).resolve()
    cfg = load_config(root)
    c = active_contract(root, None)
    if not c:
        if not args.quiet:
            print("ship: no contract is building.", file=sys.stderr)
        return 3
    ref = f"refs/remotes/origin/{args.branch}"
    if sh(["git", "rev-parse", "--verify", ref], cwd=root).returncode != 0:
        die(f"{ref} isn't here yet. Push to {args.branch} first, or run `git fetch origin {args.branch}`.", 1)
    if sh(["git", "merge-base", "--is-ancestor", "HEAD", ref], cwd=root).returncode != 0:
        die(f"This commit isn't on {args.branch} yet. Push it first; the push gate runs the check.", 1)
    porcelain = sh(["git", "status", "--porcelain"], cwd=root).stdout  # not stripped: column 1 matters
    dirty = [l[3:] for l in porcelain.splitlines() if len(l) > 3 and not l[3:].strip('"').startswith(CONTRACTS + "/")]
    if dirty:
        die(f"There are uncommitted changes ({', '.join(dirty[:5])}{' …' if len(dirty) > 5 else ''}) that aren't "
            f"on {args.branch}. Commit and push them, or remove them, then run ondev again.", 1)
    code = [f for f in git_out(root, "diff", "--name-only", c.base, "HEAD").splitlines() if f and not is_bookkeeping(f, cfg)]
    if not code:
        die(f"{c.name} stays building: {args.branch} has none of its code yet, only bookkeeping.", 1)
    size, stack = count_size(root, cfg, c), check_stack(root, cfg, c)
    left = check_leftovers(root, cfg, c, False)
    failed = [n for n, r in (("size", size), ("stack", stack), ("leftovers", left)) if r["status"] == "FAIL"]
    if review_problems(root, cfg, c, "HEAD"):
        failed.append("security review")
    if c.quick and quick_fit(root, cfg, c, "HEAD")["problems"]:
        failed.append("the quick lane's limits")
    if migration_problem(root, cfg, c.base, "HEAD"):
        failed.append("migrations")
    if failed:
        die(f"{c.name} stays building: the check fails now ({', '.join(failed)}). Run /mg-ship-kit:cto-check to see "
            "why.", 1)
    if c.removing:
        c.set_status("dropped")
        print(f"{c.name}: Status: dropped (its code is removed from {args.branch})")
    elif c.head:
        c.set_status("on-dev")
        print(f"{c.name}: Status: on-dev (a sub-piece of {c.head}; the chain goes on with its next sub-piece)")
    elif c.quick:
        c.set_status("on-dev")
        print(f"{c.name}: Status: on-dev (a quick fix: the owner checks it on {args.branch} and closes it with "
              "/mg-ship-kit:done; the next piece may start)")
    else:
        c.set_status("on-dev")
        print(f"{c.name}: Status: on-dev (the client tests it on {args.branch}; the next piece may start)")
    if c.head:
        sync_head_of(root, c)
    return 0


def sync_head_of(root: Path, sub: Contract) -> None:
    """After a sub-piece moved, move its head if the chain is complete, or say what holds it back."""
    cs = list_contracts(root)
    head = next((h for h in cs if h.is_head and h.name == sub.head), None)
    if head is None or head.status not in ("building", "on-dev"):
        return
    want, why = chain_state(head, subs_of(cs, head))
    if not move_head(head, want) and want is None and head.status == "building" and "dropped" in why:
        print(f"{head.name} stays building: {why}")


def cmd_done(args) -> int:
    root = Path(args.root).resolve()
    if not args.contract:
        # with a chain on dev, "done" means the head: its sub-pieces are on dev too, but the verdict is one
        on_dev = [c for c in list_contracts(root) if c.status == "on-dev"]
        heads = [c for c in on_dev if c.is_head]
        if len(heads) == 1 and all(c.is_head or c.head == heads[0].name for c in on_dev):
            args.contract = heads[0].name
    c = find_contract(root, args.contract, ("on-dev",), "mark done")
    if c.head:
        die(f"{c.name} is part of the chain {c.head}, and the client accepts the chain as a whole. Run "
            f"done --contract {c.head} once they accept it.", 1)
    if c.status != "on-dev":
        die(f"{c.name} can't be done: it's {c.status}. Only a piece that's on dev and accepted by the client can be "
            "done.", 1)
    subs = subs_of(list_contracts(root), c) if c.is_head else []
    if c.is_head:
        want, why = chain_state(c, subs)
        if want != "on-dev":
            die(f"{c.name} can't be done: {why}. The client accepts the whole chain, so every sub-piece must be "
                "on dev first.", 1)
    c.set_status("done")
    print(f"{c.name}: Status: done")
    for s in subs:
        if s.status == "on-dev":
            s.set_status("done")
            print(f"{s.name}: Status: done (with the head)")
    return 0


def dependents(root: Path, args, c: Contract) -> list[dict]:
    """Open rows that depend on this piece, or on the chain it belongs to (D93)."""
    if not args.rows:
        return []
    rows = load_rows(args.rows)
    targets = [c]
    if c.head:
        targets += [h for h in list_contracts(root) if h.is_head and h.name == c.head]
    hit, seen = [], set()
    for t in targets:
        tid = page_id(t.tracker)
        for i, r in enumerate(rows):
            if row_status(r) in ("done", "dropped") or i in seen or r["head"]:
                continue
            for d in r["depends"]:
                if (tid and page_id(d) == tid) or d.lower() == t.title.lower():
                    hit.append({**r, "on": t.title})
                    seen.add(i)
                    break
    return hit


def cmd_drop(args) -> int:
    root = Path(args.root).resolve()
    c = find_contract(root, args.contract, ("building", "on-dev"), "drop")
    deps = dependents(root, args, c)
    if deps:
        ways = []
        for r in deps:
            how = ("drop it first" if row_status(r) in ("building", "on dev")
                   else "change or cancel it in chat first")
            ways.append(f"{r['piece']} ({r['status']}) depends on {r['on']}: {how}")
        die(f"Nothing was dropped: other pieces depend on {c.title}. " + "; ".join(ways) + ".", 1)
    if c.is_head:
        return drop_head(root, c)
    if c.status in ("done", "dropped", "draft", "ready"):
        die(f"{c.name} can't be dropped: it's {c.status}. Only a piece that's building or on dev can be.", 1)
    if c.status == "building" and c.removing:
        die(f"{c.name} is already being removed. Delete its code, run /mg-ship-kit:cto-check, then push to dev.", 1)
    if c.status == "building":
        # never reached dev: its code must be gone from the working tree before the contract closes
        changed = [f for f in git_changes(root, c.base) if not f.startswith(CONTRACTS + "/")]
        if changed:
            die(f"Nothing was dropped: {c.name}'s code is still here ({len(changed)} files changed since it "
                f"started, like {changed[0]}). Delete that code first, then run drop again.", 1)
        c.set_status("dropped")
        print(f"{c.name}: Status: dropped (it never reached dev)")
        if c.head:
            sync_head_of(root, c)
        return 0
    others = building_pieces(list_contracts(root))
    if others:
        die(f"Nothing was dropped: {others[0].name} is building in this session. Push it to dev or drop it first, "
            f"or drop {c.name} from another session. (rule D93)", 1)
    head = git_out(root, "rev-parse", "--short=10", "HEAD")
    c.set_status("building", {"Base": head,
                              "Removing": f"{dt.date.today().isoformat()}, the client rejected it; built from {c.base}"})
    print(f"{c.name}: removing. Delete its code, run /mg-ship-kit:cto-check (nothing may be added), push to dev; "
          "it becomes dropped when the push lands.")
    return 0


def drop_head(root: Path, head: Contract) -> int:
    """Drop a chain whose sub-pieces hold no code: the head and every sub-piece become dropped. Once a sub-piece
    was built, the chain is dropped sub-piece by sub-piece, the last built first, and the head follows by itself."""
    subs = subs_of(list_contracts(root), head)
    built = [c for c in subs if c.status in ("building", "on-dev", "done")]
    if head.status not in ("building", "on-dev"):
        die(f"{head.name} can't be dropped: it's {head.status}. Only an open chain, or one on dev, can be.", 1)
    if built:
        die(f"Nothing was dropped: {head.name} has sub-pieces that were built "
            f"({', '.join(f'{c.name}, {c.status}' for c in built)}). Drop them one at a time, the last one first. "
            "Each one on dev becomes a removal, and the head is dropped with the last one.", 1)
    changed = [f for f in git_changes(root, head.base) if not f.startswith(CONTRACTS + "/")]
    if changed:
        die(f"Nothing was dropped: code was written after {head.name} was picked up ({len(changed)} files, like "
            f"{changed[0]}), though no sub-piece was building. Delete that code first, then run drop again.", 1)
    for c in subs:
        if c.status != "dropped":
            c.set_status("dropped")
    head.set_status("dropped")
    print(f"{head.name}: Status: dropped, with its {len(subs)} sub-pieces (nothing was built)")
    return 0


# ---------------------------------------------------------------- the security review (D66)
REVIEWS = CONTRACTS + "/reviews"  # one file per piece; a subfolder, so list_contracts never reads it as a contract
SEVERITIES = ("critical", "major", "minor")
BLOCKING = ("critical", "major")
FINDING_STATES = ("unchecked", "open", "fixed", "waived", "not reproduced")
SPEND_LEVELS = ("lean", "standard", "deep")
DEFAULT_SPEND = "standard"
# Paths whose names say they hold login, secrets, uploads, config or the database's shape: risky in any folder.
RISKY_NAME_RE = re.compile(r"(auth|login|logout|signin|signup|register|passw|token|jwt|oauth|session|permission|"
                           r"role|acl|secur|crypt|secret|upload|config|settings|middleware|migration|alembic)", re.I)
DEP_FILE_RE = re.compile(r"(^|/)(requirements[^/]*\.txt|pyproject\.toml|poetry\.lock|Pipfile(\.lock)?|package\.json|"
                         r"package-lock\.json|yarn\.lock|pnpm-lock\.yaml)$")
INFRA_FILE_RE = re.compile(r"(^|/)(Dockerfile[^/]*|docker-compose[^/]*\.ya?ml|compose\.ya?ml|Procfile|railway\.(json|toml)|"
                           r"nixpacks\.toml|vercel\.json|netlify\.toml|wrangler\.toml|nginx[^/]*\.conf|"
                           r"\.env\.(example|sample|template))$", re.I)
# Backend code that reads requests, the database, the environment or the shell. Checked on the whole file: a
# change anywhere in a file that serves routes can open a hole in them.
PY_RISKY = (
    ("routes", re.compile(r"@\w+\.(get|post|put|patch|delete|api_route|websocket)\(|\bAPIRouter\(|\bFastAPI\(")),
    ("database or SQL", re.compile(r"\.execute\(|\btext\(\s*[f\"']|\bcreate_engine\(|\bSession\b|\bselect\(|"
                                   r"[\"'](\s*)(SELECT|INSERT|UPDATE|DELETE)\s", re.I)),
    ("login and permissions", re.compile(r"\bDepends\(|\bSecurity\(|OAuth2|HTTPBearer|\bjwt\b|passlib|bcrypt|"
                                         r"\bcurrent_user\b|\bpermission", re.I)),
    ("file uploads", re.compile(r"\bUploadFile\b|\bFile\(|\bForm\(|multipart")),
    ("config and env", re.compile(r"os\.environ|os\.getenv|\bBaseSettings\b|load_dotenv|CORSMiddleware")),
    ("shell, eval or unsafe loading", re.compile(r"\bsubprocess\b|os\.system\(|\beval\(|\bexec\(|\bpickle\b|"
                                                 r"yaml\.load\(|\bmarshal\b")),
    ("outgoing requests", re.compile(r"\brequests\.(get|post|put|delete|request)\(|\bhttpx\.|urllib\.request")),
)
# Frontend lines that handle tokens, cookies or raw HTML. Checked on the piece's added lines only: the words are
# common enough that a whole-file check would flag every screen.
FE_RISKY = (
    ("tokens and browser storage", re.compile(r"localStorage|sessionStorage|document\.cookie|\btoken\b|"
                                              r"Authorization|password", re.I)),
    ("raw HTML or eval", re.compile(r"dangerouslySetInnerHTML|\.innerHTML\s*=|\beval\(|new Function\(|"
                                    r"\bv-html\b|postMessage\(")),
)
FINDING_RE = re.compile(r"^###\s+(F\d+)\s*·\s*(\w+)\s*·\s*(.+?)\s*$")


def review_path(root: Path, c: Contract) -> Path:
    return root / REVIEWS / f"{c.name}.md"


def git_blob(root: Path, ref: str, f: str) -> str:
    """The blob id of f at ref, or 'deleted'."""
    return git_out(root, "rev-parse", "--verify", "--quiet", f"{ref}:{f}") or "deleted"


def piece_files(root: Path, cfg: dict, c: Contract, ref: str | None) -> dict[str, str]:
    """Product files the piece changed since its base, with each file's blob id. ref None reads the working tree
    (untracked files included), which is what a review sees before the commit; ref 'HEAD' reads the commit, which
    is what the gate and GitHub see. A clean tree gives both the same answer."""
    if ref:
        files = [f for f in git_out(root, "diff", "--name-only", "--no-renames", c.base, ref).splitlines() if f]
        return {f: git_blob(root, ref, f) for f in sorted(files) if not is_bookkeeping(f, cfg)}
    tracked = git_out(root, "diff", "--name-only", "--no-renames", c.base).splitlines()
    untracked = [f for f in git_out(root, "ls-files", "--others", "--exclude-standard").splitlines()
                 if not any(part in SKIP_DIRS for part in f.split("/")[:-1])]
    files = sorted({f for f in tracked + untracked if f and not is_bookkeeping(f, cfg)})
    present = [f for f in files if (root / f).is_file()]
    blobs: dict[str, str] = {f: "deleted" for f in files}
    if present:
        r = subprocess.run(["git", "hash-object", "--stdin-paths"], cwd=root, input="\n".join(present) + "\n",
                           text=True, capture_output=True)
        if r.returncode != 0:
            die(f"git hash-object failed: {r.stderr.strip()}")
        blobs.update(dict(zip(present, r.stdout.split())))
    return blobs


def review_stamp(root: Path, c: Contract, ref: str | None) -> str:
    """One short id for exactly this code: any change to a file the piece touched gives a new stamp. It leaves out
    only the kit's own bookkeeping, never the owner's list in ship.json: review-write reads the working tree's
    ship.json, the gate origin/dev's and GitHub the last passed commit's, so a stamp that hung on that list could
    pass one and fail another (issue #40)."""
    blobs = piece_files(root, None, c, ref)
    text = "\n".join(f"{f} {b}" for f, b in sorted(blobs.items()))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def added_lines(root: Path, base: str, ref: str | None, f: str) -> list[str]:
    """The lines a file gained since base (all of it when new)."""
    args = ["diff", "--no-color", "--unified=0", base] + ([ref] if ref else []) + ["--", f]
    out = git_out(root, *args)
    if not out and not ref and (root / f).is_file() and git_out(root, "ls-files", "--", f) == "":
        return (root / f).read_text(encoding="utf-8", errors="ignore").splitlines()  # untracked: all of it
    return [l[1:] for l in out.splitlines() if l.startswith("+") and not l.startswith("+++")]


def file_text(root: Path, ref: str | None, f: str) -> str:
    if ref:
        r = sh(["git", "show", f"{ref}:{f}"], cwd=root)
        return r.stdout if r.returncode == 0 else ""
    p = root / f
    return p.read_text(encoding="utf-8", errors="ignore") if p.is_file() and p.stat().st_size < 2_000_000 else ""


def review_scope(root: Path, cfg: dict, c: Contract, blobs: dict[str, str], ref: str | None) -> list[str]:
    """Why this piece needs a review: one line per risky file, empty when nothing risky changed (D66). The script
    decides, never Claude. `review_all: true` in ship.json reviews every piece with code; `review_paths` adds globs
    (a path the list missed, added once)."""
    py, nd = cfg.get("python_dir"), cfg.get("node_dir")
    extra = cfg.get("review_paths", [])
    why: list[str] = []
    for f, blob in blobs.items():
        reasons: list[str] = []
        if blob == "deleted":
            continue
        if cfg.get("review_all"):
            reasons.append("review_all is on")
        if any((p.endswith("/") and f.startswith(p)) or f == p or fnmatch.fnmatch(f, p) for p in extra):
            reasons.append("listed in review_paths")
        if DEP_FILE_RE.search(f):
            reasons.append("dependencies")
        if INFRA_FILE_RE.search(f):
            reasons.append("deploy or env config")
        if is_project_workflow(f):
            reasons.append("CI workflow: runs on the runner with the repo's secrets")
        if f.lower().endswith(".sql"):
            reasons.append("SQL")
        if not is_test_file(f) and RISKY_NAME_RE.search(f):
            reasons.append("its name")
        if not is_test_file(f) and in_dir(f, py) and f.endswith(".py"):
            text = file_text(root, ref, f)
            reasons += [label for label, rx in PY_RISKY if rx.search(text)]
        if not is_test_file(f) and in_dir(f, nd) and f.endswith((".ts", ".tsx", ".js", ".jsx", ".vue", ".svelte")):
            lines = "\n".join(added_lines(root, c.base, ref, f))
            reasons += [label for label, rx in FE_RISKY if rx.search(lines)]
        if reasons:
            why.append(f"{f} ({', '.join(dict.fromkeys(reasons))})")
    return why


class Review:
    """A piece's review file, contracts/reviews/<contract>.md. Written only by the script (review-write,
    review-skip, review-waive); the gate reads it."""

    def __init__(self, text: str):
        self.text = text
        self.stamp = field(text, "Stamp") or ""
        self.scope = (field(text, "Scope") or "").lower()
        self.spend = field(text, "Spend") or ""
        self.findings: list[dict] = []
        self.errors: list[str] = []
        cur: dict | None = None
        for line in text.splitlines():
            m = FINDING_RE.match(line)
            if m:
                cur = {"id": m.group(1), "severity": m.group(2).lower(), "status": m.group(3).lower(),
                       "what": "", "where": "", "proof": "", "waiver": ""}
                if cur["severity"] not in SEVERITIES:
                    self.errors.append(f"{cur['id']}: unknown severity {cur['severity']!r}")
                if cur["status"] not in FINDING_STATES:
                    self.errors.append(f"{cur['id']}: unknown status {cur['status']!r}")
                self.findings.append(cur)
                continue
            k = re.match(r"^(What|Where|Proof|Waiver):\s*(.*)$", line)
            if k and cur is not None:
                cur[k.group(1).lower()] = k.group(2).strip()
        if not re.fullmatch(r"[0-9a-f]{16}", self.stamp):
            self.errors.append("no valid Stamp line")
        if not (self.scope.startswith("reviewed") or self.scope.startswith("skipped")):
            self.errors.append("the Scope line must say reviewed or skipped")

    @property
    def skipped(self) -> bool:
        return self.scope.startswith("skipped")

    def blocking(self) -> list[dict]:
        return [f for f in self.findings if f["severity"] in BLOCKING and f["status"] in ("open", "unchecked")]

    def summary(self) -> str:
        """The tracker's Security line (D66)."""
        if self.skipped:
            return "skipped: no risky files"
        found = [f for f in self.findings if f["status"] != "not reproduced"]
        if not found:
            return "reviewed: nothing found"
        n = {s: sum(1 for f in found if f["status"] == s) for s in ("fixed", "waived", "open", "unchecked")}
        parts = [f"{len(found)} found"] + [f"{v} {k}" for k, v in n.items() if v]
        return ", ".join(parts)


def load_review(root: Path, c: Contract) -> Review | None:
    p = review_path(root, c)
    return Review(p.read_text(encoding="utf-8")) if p.exists() else None


def review_problems(root: Path, cfg: dict, c: Contract, ref: str | None) -> list[str]:
    """Why the piece may not reach dev on the review's account (D66): no review, a review of other code, a skip note
    on a risky piece, a finding that blocks. A removal adds nothing and needs no review."""
    if c.removing:
        return []
    blobs = piece_files(root, cfg, c, ref)
    if not blobs:
        return []
    r = load_review(root, c)
    rel = f"{REVIEWS}/{c.name}.md"
    if r is None:
        return [f"no security review for {c.name} ({rel} is missing). Run /mg-ship-kit:cto-check: it runs the review "
                "(or writes the skip note when no risky file changed). Commit the file with the piece."]
    if r.errors:
        return [f"{rel} can't be read: {'; '.join(r.errors)}. Only the kit writes it: run review-write or review-skip "
                "again."]
    out = []
    if r.stamp != review_stamp(root, c, ref):
        out.append(f"the code changed after the security review ({rel} reviewed older code). Run the review "
                   "again: after a fix, the checker reruns the proofs and review-write stamps the new code.")
    why = review_scope(root, cfg, c, blobs, ref)
    if r.skipped and why:
        out.append(f"{rel} skipped the review, but the piece touches risky files ({short_list(why, 5)}). Run the "
                   "review.")
    for f in r.blocking():
        out.append(f"{f['id']} ({f['severity']}, {f['status']}): {f['what'] or '(no text)'} → fix it until its "
                   "proof passes, or the owner waives it in one line")
    for f in r.findings:
        if f["status"] == "waived" and not is_approval(f["waiver"]):
            out.append(f"{f['id']} is waived but has no Waiver line with the date, the owner's name and the reason.")
        if f["status"] in ("open", "fixed") and not f["proof"]:
            out.append(f"{f['id']} is {f['status']} but has no Proof line. Only findings that were reproduced count.")
    return out


def print_review_verdict(problems: list[str]) -> str:
    if not problems:
        print("SECURITY   PASS")
        return "PASS"
    print(f"SECURITY   FAIL  {len(problems)} to settle")
    for p in problems:
        print(f"  {p}")
    return "FAIL"


def spend_models(cfg: dict) -> tuple[str, dict]:
    level = cfg.get("spend", DEFAULT_SPEND)
    if level not in SPEND_LEVELS:
        die(f"ship.json has spend {level!r}; it must be one of {', '.join(SPEND_LEVELS)}.")
    f = kit_root() / "reference" / "spend.json"
    models = json.loads(f.read_text())["levels"][level] if f.exists() else {}
    return level, models


def render_review(c: Contract, stamp: str, scope: str, spend: str, findings: list[dict]) -> str:
    out = [f"# Security review: {c.name}",
           "<!-- Written by the Ship kit (review-write, review-skip, review-waive). Don't edit it by hand. -->",
           f"Contract: {c.name}", f"Stamp: {stamp}", f"Scope: {scope}", f"Spend: {spend}",
           f"Date: {dt.date.today().isoformat()}", "", "## Findings"]
    if not findings:
        out.append("None." if scope.startswith("reviewed") else "Not reviewed: no risky file changed.")
    for f in findings:
        out += ["", f"### {f['id']} · {f['severity']} · {f['status']}", f"What: {f.get('what', '')}",
                f"Where: {f.get('where', '')}", f"Proof: {f.get('proof', '')}"]
        if f.get("waiver"):
            out.append(f"Waiver: {f['waiver']}")
    return "\n".join(out) + "\n"


def write_review(root: Path, c: Contract, text: str) -> Path:
    p = review_path(root, c)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def review_target(root: Path, args) -> tuple[dict, Contract]:
    cfg = load_config(root)
    c = active_contract(root, getattr(args, "contract", None))
    if not c:
        die("Nothing to review: no piece is building.", 3)
    if c.is_head:
        die(f"{c.name} is a chain head and has no code. Each sub-piece is reviewed on its own.")
    return cfg, c


def cmd_review_plan(args) -> int:
    """What the review needs: the scope, the spend level and its models, and the diff for the reviewer."""
    root = Path(args.root).resolve()
    cfg, c = review_target(root, args)
    blobs = piece_files(root, cfg, c, None)
    why = review_scope(root, cfg, c, blobs, None)
    level, models = spend_models(cfg)
    diff = root / ".ship" / "review" / f"{c.name}.diff"
    diff.parent.mkdir(parents=True, exist_ok=True)
    parts = []
    for f, blob in blobs.items():
        if git_out(root, "ls-files", "--", f):
            parts.append(sh(["git", "diff", "--no-color", c.base, "--", f], cwd=root).stdout)
        else:  # untracked: git diff --no-index exits 1 when the files differ, which they always do here
            parts.append(sh(["git", "diff", "--no-color", "--no-index", "/dev/null", f], cwd=root).stdout)
    diff.write_text("".join(parts), encoding="utf-8")
    plan = {"contract": c.name, "contract_file": str(c.path.relative_to(root)), "removal": bool(c.removing),
            "files": len(blobs), "risky": why, "spend": level, "models": models,
            "diff": str(diff.relative_to(root)), "review_file": f"{REVIEWS}/{c.name}.md",
            "stamp": review_stamp(root, c, None)}
    print(json.dumps(plan, indent=2))
    return 0


def cmd_review_skip(args) -> int:
    root = Path(args.root).resolve()
    cfg, c = review_target(root, args)
    blobs = piece_files(root, cfg, c, None)
    why = review_scope(root, cfg, c, blobs, None)
    if why:
        die(f"This piece touches risky files ({short_list(why, 5)}), so it needs the security review. A skip note "
            "isn't enough.", 1)
    p = write_review(root, c, render_review(c, review_stamp(root, c, None), "skipped: no risky files", "none", []))
    print(f"wrote {p.relative_to(root)}: skipped, no risky file changed. Commit it with the piece.")
    return 0


def cmd_review_write(args) -> int:
    """Save the review from the checker's JSON: {"findings": [{"id", "severity", "status", "what", "where",
    "proof"}]}. A waiver already in the file stays while its finding is still open. Stamps the code as it is now."""
    root = Path(args.root).resolve()
    cfg, c = review_target(root, args)
    try:
        data = json.loads(Path(args.findings).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        die(f"can't read {args.findings}: {e}")
    old = load_review(root, c)
    waived = {f["id"]: f["waiver"] for f in (old.findings if old else []) if f["status"] == "waived" and f["waiver"]}
    findings, seen = [], set()
    for i, f in enumerate(data.get("findings", []), 1):
        fid = str(f.get("id") or f"F{i}")
        sev, status = str(f.get("severity", "")).lower(), str(f.get("status", "")).lower()
        if not re.fullmatch(r"F\d+", fid) or fid in seen:
            die(f"finding {fid!r}: ids are F1, F2 … and each is used once")
        seen.add(fid)
        if sev not in SEVERITIES:
            die(f"{fid}: severity must be one of {', '.join(SEVERITIES)}")
        if status == "waived" and fid not in waived:
            die(f"{fid}: only the owner waives a finding (review-waive), never the checker")
        if status not in FINDING_STATES:
            die(f"{fid}: status must be one of {', '.join(s for s in FINDING_STATES if s != 'waived')}")
        if status in ("open", "fixed") and not str(f.get("proof", "")).strip():
            die(f"{fid}: an {status} finding needs a proof (a failing test or a request that shows it)")
        row = {"id": fid, "severity": sev, "status": status, "what": " ".join(str(f.get("what", "")).split()),
               "where": str(f.get("where", "")).strip(), "proof": str(f.get("proof", "")).strip()}
        if fid in waived and status in ("open", "waived"):
            row["status"], row["waiver"] = "waived", waived[fid]
        findings.append(row)
    level, models = spend_models(cfg)
    spend = f"{level} (reviewer {models.get('reviewer', '?')}, checker {models.get('checker', '?')})"
    p = write_review(root, c, render_review(c, review_stamp(root, c, None), "reviewed", spend, findings))
    r = Review(p.read_text(encoding="utf-8"))
    print(f"wrote {p.relative_to(root)}: {r.summary()}")
    for f in r.blocking():
        print(f"  blocks: {f['id']} · {f['severity']} · {f['status']}: {f['what']}")
    return 1 if r.blocking() else 0


def cmd_review_waive(args) -> int:
    """The owner's one-line waiver of a finding, in their words (D66). Doesn't change the stamp."""
    root = Path(args.root).resolve()
    cfg, c = review_target(root, args)
    r = load_review(root, c)
    if r is None:
        die(f"{c.name} has no security review yet.")
    hit = next((f for f in r.findings if f["id"] == args.finding), None)
    if hit is None:
        die(f"{c.name}'s security review has no finding {args.finding}.")
    if hit["status"] not in ("open", "unchecked"):
        die(f"{args.finding} is {hit['status']}. Only an open finding can be waived.")
    if not args.by.strip() or not args.why.strip():
        die("A waiver needs the owner's name (--by) and their reason, in their own words (--why).")
    hit["status"], hit["waiver"] = "waived", f"{dt.date.today().isoformat()}, {args.by.strip()}: {' '.join(args.why.split())}"
    write_review(root, c, render_review(c, r.stamp, r.scope, r.spend, r.findings))
    print(f"{args.finding} waived by {args.by.strip()}. It shows on the tracker row and in the release note.")
    return 0


def cmd_review_status(args) -> int:
    root = Path(args.root).resolve()
    cfg = load_config(root)
    c = find_contract(root, args.contract, ("building", "on-dev"), "show") if args.contract else active_contract(root, None)
    if not c:
        die("No piece is building.", 3)
    r = load_review(root, c)
    line = r.summary() if r else "not reviewed yet"
    if args.line:
        print(f"Security: {line}")
        return 0
    print(f"{c.name} · Security: {line}")
    if c.status == "building":
        return 0 if print_review_verdict(review_problems(root, cfg, c, None)) == "PASS" else 1
    return 0


def release_waivers(root: Path, last_release: str | None = None) -> list[str]:
    """Waived findings in reviews that haven't reached main yet: the release note lists each one (D66). On GitHub's
    run for a push to main, origin/main is already the pushed commit, so the caller passes the commit main was at
    before the push."""
    if last_release and last_release != ZERO_SHA and is_commit(root, last_release):
        base = git_out(root, "merge-base", "HEAD", last_release)
    else:
        main = next((r for r in ("refs/remotes/origin/main", "refs/remotes/origin/master") if is_commit(root, r)), None)
        base = git_out(root, "merge-base", "HEAD", main) if main else ""
    if base:
        names = [f for f in git_out(root, "diff", "--name-only", base, "HEAD", "--", REVIEWS).splitlines() if f]
    else:
        names = [f.relative_to(root).as_posix() for f in sorted((root / REVIEWS).glob("*.md"))] \
            if (root / REVIEWS).exists() else []
    out = []
    for n in names:
        p = root / n
        if not p.is_file():
            continue
        for f in Review(p.read_text(encoding="utf-8")).findings:
            if f["status"] == "waived":
                out.append(f"{f['id']} {f['severity']}, {f['what']} ({Path(n).stem}; {f['waiver']})")
    return out


def cmd_review_waivers(args) -> int:
    w = release_waivers(Path(args.root).resolve())
    print(f"Waived: {len(w)}" + ("" if not w else "\n" + "\n".join(f"  {x}" for x in w)))
    return 0


# ---------------------------------------------------------------- the dev gate and the GitHub check
def is_commit(root: Path, ref: str | None) -> bool:
    return bool(ref) and sh(["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], cwd=root).returncode == 0


def rev(root: Path, ref: str) -> str:
    return git_out(root, "rev-parse", f"{ref}^{{commit}}")


def is_ancestor(root: Path, a: str, b: str) -> bool:
    """True when commit a is b or one of b's ancestors. The empty tree is nobody's ancestor."""
    return (a != EMPTY_TREE and is_commit(root, a) and is_commit(root, b)
            and sh(["git", "merge-base", "--is-ancestor", a, b], cwd=root).returncode == 0)


def product_files(root: Path, cfg: dict, a: str, b: str) -> list[str]:
    """Files that differ between a and b (a may be the empty tree) and aren't bookkeeping."""
    res = sh(["git", "diff", "--name-only", "--no-renames", a, b], cwd=root)
    if res.returncode != 0:
        die(f"git diff {a[:10]} {b[:10]} failed: {res.stderr.strip()}")
    return [f for f in res.stdout.splitlines() if f and not is_bookkeeping(f, cfg)]


def short_list(files: list[str], n: int = 8) -> str:
    return ", ".join(files[:n]) + (f" … ({len(files)} files)" if len(files) > n else "")


def cfg_at(root: Path, ref: str) -> dict | None:
    """ship.json as it was at a commit, or None."""
    if ref == EMPTY_TREE:
        return None
    r = sh(["git", "show", f"{ref}:{CONFIG}"], cwd=root)
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except ValueError:
        return None


def bad_bookkeeping(cfg: dict) -> list[str]:
    """`bookkeeping` patterns that would cover code in the backend or frontend folder. Bookkeeping may only name
    files outside the code, so a pattern can never wave product code past the check."""
    probes = []
    for key in ("python_dir", "node_dir"):
        d = cfg.get(key)
        if d is None:
            continue
        pre = "" if d in ("", ".") else d.strip("/") + "/"
        probes += [pre + p for p in ("main.py", "app/main.py", "src/App.tsx", "src/routes.ts", "package.json",
                                     "requirements.txt")]
    return [p for p in cfg.get("bookkeeping", [])
            if any((p.endswith("/") and f.startswith(p)) or f == p or fnmatch.fnmatch(f, p) for f in probes)]


def rules_since(root: Path, cfg: dict, since: str) -> tuple[dict, list[str]]:
    """The settings a push is judged by. Folders and the bookkeeping list come from ship.json as it was at `since`
    (the last passed point), so a push can't loosen its own check: a change to them takes effect from the next push.
    Returns (settings, notes)."""
    old = cfg_at(root, since)
    rules, notes = dict(cfg), []
    if old is None:  # ship.json is new in this push: no extra bookkeeping paths yet
        # ...but the cloudflare track's deploy files, which setup itself copies, come with that first push (D97)
        rules["bookkeeping"] = list(CF_BOOKKEEPING) if cfg.get("track") == "cloudflare" else []
        return rules, notes
    for key in ("python_dir", "node_dir", "bookkeeping", "review_all", "review_paths"):
        if key in old:
            rules[key] = old[key]
        else:
            rules.pop(key, None)
    if cfg.get("bookkeeping", []) != old.get("bookkeeping", []):
        notes.append("ship.json's bookkeeping list changed; it counts from the next push.")
    return rules, notes


def locked_ci_since(root: Path) -> str | None:
    """ci_since as setup first wrote it. A later edit doesn't move it, so it can't be pushed forward to hide code."""
    r = sh(["git", "log", "--reverse", "--format=%H", "-S", '"ci_since"', "--", CONFIG], cwd=root)
    first = r.stdout.split()[0] if r.returncode == 0 and r.stdout.split() else None
    old = cfg_at(root, first) if first else None
    return (old or {}).get("ci_since") or None


def fallback_since(root: Path, cfg: dict) -> tuple[str, str]:
    """Where checking starts when nothing newer is known to have passed: the newer of the commit recorded at
    setup (ci_since, as first written) and the last release (where HEAD meets origin/main). With neither, from
    nothing."""
    cands = []
    s = locked_ci_since(root)
    if s and is_ancestor(root, s, "HEAD"):
        cands.append((rev(root, s), "the commit recorded at setup"))
    for r in ("refs/remotes/origin/main", "refs/remotes/origin/master"):
        if is_commit(root, r):
            mb = git_out(root, "merge-base", "HEAD", r)
            if mb:
                cands.append((mb, "the last release"))
            break
    if not cands:
        return EMPTY_TREE, "no release and no setup commit yet"
    best = cands[0]
    for c in cands[1:]:
        if is_ancestor(root, best[0], c[0]):
            best = c
    return best


ADOPTED = CONTRACTS + "/adopted/commits.md"  # a subfolder, so list_contracts never reads it as a contract
ADOPT_RE = re.compile(r"^- ([0-9a-f]{40}) · (\d{4}-\d\d-\d\d) by (.+?): (.+)$")
ADOPT_HEAD = ("# Adopted commits\n\n<!-- Written by the Ship kit (adopt): the owner accepts code already on dev that no "
              "piece covers, and the dev check starts after it. Don't edit it by hand. -->\n")


def adoptions(text: str) -> list[dict]:
    out = []
    for line in text.splitlines():
        m = ADOPT_RE.match(line.strip())
        if m:
            out.append({"sha": m[1], "date": m[2], "by": m[3], "why": m[4]})
    return out


def adopted_start(root: Path, since: str, pushed: str | None, ref: str = "HEAD") -> dict | None:
    """The newest adopted commit between `since` and what dev already had before this push (`pushed`). Only code
    already on dev can be adopted, so a push can never adopt its own code. The list is read from `ref`, the pushed
    commit."""
    if not pushed:
        return None
    best = None
    for a in adoptions(sh(["git", "show", f"{ref}:{ADOPTED}"], cwd=root).stdout):
        sha = a["sha"]
        if sha == since or not is_ancestor(root, sha, pushed):
            continue
        if since != EMPTY_TREE and not is_ancestor(root, since, sha):
            continue
        if best is None or is_ancestor(root, best["sha"], sha):
            best = a
    return best


def push_start(root: Path, before: str) -> str | None:
    """What dev had before this push: GitHub's `before`, or where it meets HEAD after a force push."""
    if not before or before == ZERO_SHA or not is_commit(root, before):
        return None
    return rev(root, before) if is_ancestor(root, before, "HEAD") else (git_out(root, "merge-base", before, "HEAD") or None)


def dev_verdict(root: Path, cfg: dict, since: str, how: str, ci: bool = False, pushed: str | None = None) -> int:
    """May everything from `since` to HEAD reach dev? 0 yes · 1 no · 3 product code but no contract building.
    Bookkeeping alone always passes. Product code must come after the building contract's Base (code from before
    its pickup belongs to no piece), and the building piece must pass the CTO check."""
    short = "nothing" if since == EMPTY_TREE else since[:10]
    print(f"checking from {short} ({how}) to {rev(root, 'HEAD')[:10]}")
    env = env_files(root, "HEAD")
    if env:  # checked first: an env file fails even in a bookkeeping-only push
        print(f"an env file is in this commit: {short_list(env)}. {ENV_FIX}")
        return 1
    bad = bad_bookkeeping(cfg)
    if bad:
        print(f"ship.json's bookkeeping list covers code in the backend or frontend folder ({', '.join(bad)}). "
              "Bookkeeping may only name files outside the code: remove those patterns.")
        return 1
    a = adopted_start(root, since, pushed)
    if a:
        since, short = a["sha"], a["sha"][:10]
        print(f"note: starting after {short} instead: the owner adopted it on {a['date']} ({a['by']}: {a['why']}).")
    head_cfg = cfg
    cfg, notes = rules_since(root, head_cfg, since)
    for n in notes:
        print(f"note: {n}")
    code = product_files(root, cfg, since, "HEAD")
    old = cfg_at(root, since)
    if old is not None and any(old.get(k) != head_cfg.get(k) for k in ("python_dir", "node_dir")):
        # moving the folders changes what the check scans, so it rides with an approved piece like code does
        code.append(f"{CONFIG} (the backend or frontend folder changed)")
    if not code:
        print("bookkeeping only (contracts, ship.json, CLAUDE.md, .gitleaksignore, .claude/settings.json, the kit's CI files, "
              "readme): nothing to check.")
        return 0
    all_cs = list_contracts(root)
    building = building_pieces(all_cs)
    if len(building) > 1:
        print("more than one contract is building: " + ", ".join(c.name for c in building) +
              ". One piece per push: each session builds one piece (D93). If one came from dev, its session hasn't "
              "pushed its on-dev mark yet: wait for it, then sync again (sync-dev).")
        return 1
    if not building:
        heads = open_heads(all_cs)
        print(f"product code changed and no contract is building, so no check covers it: {short_list(code)}. "
              + (f"Chain {heads[0].name} is open but none of its sub-pieces is building: a sub-piece's code is "
                 "pushed while that sub-piece is building (/mg-ship-kit:chain)." if heads else
                 "Every change belongs to a piece (D1): pick one up with /mg-ship-kit:next, or remove the change."))
        return 3
    c = building[0]
    c.check_ready()
    if not is_ancestor(root, c.base, "HEAD"):
        print(f"{c.name}: its Base {c.base} isn't in this branch's history, so the check can't see what it added.")
        return 1
    if not is_ancestor(root, c.base, since):
        outside = product_files(root, cfg, since, c.base)
        if outside:
            print(f"code that belongs to no piece: these changed after {short} but before {c.name} was picked up, "
                  f"so no check covers them: {short_list(outside)}. Every change belongs to a piece: push a piece's "
                  "code while its contract is building. If that code is already on dev and the owner accepts it "
                  "without a piece, they adopt its newest commit in one line: `ship_check.py adopt <commit> --by "
                  "<owner> --why \"<their words>\"`, then push contracts/adopted/commits.md alone.")
            return 1
    size, stack = count_size(root, cfg, c), check_stack(root, cfg, c)
    left = check_leftovers(root, cfg, c, False)
    sec = review_problems(root, cfg, c, "HEAD")
    quick = quick_fit(root, cfg, c, "HEAD") if c.quick else None
    return 0 if print_report(c, size, stack, left, ci=ci, security=sec, lesson=lesson_problem(root, c),
                             quick=quick, migrations=migration_problem(root, cfg, since, "HEAD")) == "PASS" else 1


def cmd_gate_dev(args) -> int:
    """The push gate's rule for dev. Without --since it starts from what is already on origin/dev."""
    root = Path(args.root).resolve()
    cfg = load_config(root)
    if args.since:
        if args.since != EMPTY_TREE and not is_commit(root, args.since):
            die(f"--since {args.since!r} isn't a commit in this repo.")
        since, how = (args.since if args.since == EMPTY_TREE else rev(root, args.since)), "given with --since"
    elif is_commit(root, "refs/remotes/origin/dev"):
        since, how = rev(root, "refs/remotes/origin/dev"), "what is already on origin/dev"
    else:
        since, how = fallback_since(root, cfg)
    dev = "refs/remotes/origin/dev"
    return dev_verdict(root, cfg, since, how, pushed=rev(root, dev) if is_commit(root, dev) else None)


class GitHub:
    """The one API call the check needs: did the kit's workflow pass on a commit pushed to dev. Uses the workflow's
    token, which needs `actions: read`. Only runs of .github/workflows/ship-check.yml on push to dev count, and the
    newest one decides, so another workflow that borrows the name, or an old pass that a re-run failed, counts
    for nothing."""

    def __init__(self, offline: bool = False):
        env = {} if offline else os.environ
        self.token = env.get("GITHUB_TOKEN", "")
        self.repo = env.get("GITHUB_REPOSITORY", "")
        self.api = (env.get("GITHUB_API_URL") or "https://api.github.com").rstrip("/")
        self.run_id = env.get("GITHUB_RUN_ID", "")

    @property
    def ready(self) -> bool:
        return bool(self.token and self.repo)

    def workflow_runs(self, sha: str) -> list[dict]:
        q = urllib.parse.urlencode({"head_sha": sha, "branch": "dev", "event": "push", "per_page": 100})
        req = urllib.request.Request(f"{self.api}/repos/{self.repo}/actions/runs?{q}", headers={
            "Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "ship-kit"})
        err: Exception | None = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    return json.loads(r.read().decode())["workflow_runs"]
            except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as e:
                err = e
                time.sleep(2 * (attempt + 1))
        die(f"Couldn't ask GitHub which commits passed the check ({err}). The workflow needs "
            "`permissions: actions: read`: add it, then re-run the check.")
        return []

    def verdict(self, sha: str) -> str:
        """'passed', 'failed', 'running' or 'none' for the kit's check on a dev push of sha, leaving out this run."""
        runs = [r for r in self.workflow_runs(sha)
                if r.get("path", "").split("@")[0] == CI_WORKFLOW and r.get("event") == "push"
                and r.get("head_branch") == "dev" and r.get("head_sha") == sha and str(r.get("id")) != self.run_id]
        if not runs:
            return "none"
        newest = max(runs, key=lambda r: r.get("id", 0))
        if newest.get("status") != "completed":
            return "running"
        return "passed" if newest.get("conclusion") == "success" else "failed"


def in_actions() -> bool:
    return os.environ.get("GITHUB_ACTIONS") == "true"


def ci_since(root: Path, cfg: dict, before: str, gh: GitHub) -> tuple[str, str]:
    """For a push to dev: start from the newest commit the check passed on, so a red push can't hide under a
    later bookkeeping push. Walks back from the commit before this push; falls back to fallback_since."""
    start = push_start(root, before)
    if start and gh.ready:
        for sha in git_out(root, "rev-list", "--first-parent", "--max-count=50", start).split():
            if gh.verdict(sha) == "passed":
                return sha, "the newest commit the check passed on"
    elif start:
        if in_actions():
            die("There's no GITHUB_TOKEN, so the check can't tell which commits passed. Use the kit's workflow, "
                "which passes one.")
        return start, "the commit before this push (no token: not asking GitHub which commits passed)"
    return fallback_since(root, cfg)


def ci_release(root: Path, gh: GitHub, wait_s: int, before: str = "") -> int:
    """For a push to main: no env file, every piece has a verdict, the commit came through dev, and the check
    passed there."""
    env = env_files(root, "HEAD")
    if env:
        print(f"release blocked — an env file is in this commit: {short_list(env)}. {ENV_FIX}")
        return 1
    open_ = [f"{c.name} ({c.status})" for c in list_contracts(root) if c.status in ("building", "on-dev")]
    if open_:
        print(f"release blocked — still open: {', '.join(open_)}. Release only when no piece is half-built or "
              "waiting for the client's verdict.")
        return 1
    dev = "refs/remotes/origin/dev"
    if not is_commit(root, dev):
        print("release blocked — origin/dev not found. Everything reaches dev first.")
        return 1
    if not is_ancestor(root, "HEAD", dev):
        print("release blocked — this commit never reached dev. Push it to dev first (the check runs there), then "
              "release dev: `git push origin dev:main`.")
        return 1
    waivers = release_waivers(root, before)
    print(f"Waived: {len(waivers)}" + "".join(f"\n  {w}" for w in waivers))
    if not gh.ready:
        if in_actions():
            print("release blocked — no GITHUB_TOKEN, so the check can't confirm the dev check passed. Use the kit's "
                  "workflow, which passes it.")
            return 1
        print("every piece has a verdict and the commit came through dev (no token: the dev check wasn't asked).")
        return 0
    head, deadline = rev(root, "HEAD"), time.time() + wait_s
    at_dev_tip = head == rev(root, dev)  # a release right after the dev push: its check may not have started yet
    while True:
        v = gh.verdict(head)
        if v == "passed":
            print("every piece has a verdict, the commit came through dev, and the check passed on it there.")
            return 0
        if (v == "running" or (v == "none" and at_dev_tip)) and time.time() < deadline:
            time.sleep(15)
            continue
        print("release blocked — " + {
            "running": "the Ship check is still running on dev for this commit. Re-run this check when it finishes.",
            "failed": "the Ship check failed on this commit on dev. Fix it there first; nothing ships while a check "
                      "fails.",
        }.get(v, "the Ship check never ran on this commit on dev. Push it to dev, let the check pass, then release."))
        return 1


def cmd_ci(args) -> int:
    """The check GitHub runs on a push to dev, main or master. Exit 0 means the commit may deploy."""
    root = Path(args.root).resolve()
    cfg = load_config(root)
    branch = args.branch or os.environ.get("GITHUB_REF_NAME", "")
    after = args.after or os.environ.get("GITHUB_SHA", "") or "HEAD"
    if not is_commit(root, after) or rev(root, after) != rev(root, "HEAD"):
        die(f"Check out the pushed commit ({after[:10]}) first: the check reads the files on disk.")
    gh = GitHub(offline=args.offline)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print(f"Ship check · kit {KIT_VERSION} · {branch or '(no branch)'} · {rev(root, 'HEAD')[:10]}")
        if branch == "dev":
            before = args.before or os.environ.get("SHIP_BEFORE", "")
            if args.since:
                since, how = (args.since if args.since == EMPTY_TREE else rev(root, args.since)), "given with --since"
            else:
                since, how = ci_since(root, cfg, before, gh)
            code = dev_verdict(root, cfg, since, how, ci=True, pushed=push_start(root, before))
            # from the same point as the check, so commits of a red push are scanned again on the next one
            scan = new_commits(root, rev(root, "HEAD"), [since])
        elif branch in ("main", "master"):
            code = ci_release(root, gh, args.wait, args.before or os.environ.get("SHIP_BEFORE", ""))
            scan = ci_scan_range(root, branch, args.before or os.environ.get("SHIP_BEFORE", ""), rev(root, "HEAD"))
        else:
            print("not dev, main or master: nothing to check.")
            code, scan = 0, None
        if branch in ("dev", "main", "master"):
            s_code, found, note = scan_secrets(root, scan) if scan is not None else (2, [], "git couldn't list the new commits.")
            report_scan(s_code, found, note, "the commits since the last pass")
            if s_code:
                code = 1
        print("PASS: this commit may deploy." if code == 0 else "FAIL: nothing deploys from this commit. Fix the "
              "check first; nothing ships while a check fails.")
    text = buf.getvalue()
    sys.stdout.write(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("## Ship check\n\n```\n" + text + "```\n")
    return code


def cmd_ci_env(args) -> int:
    """`python_dir=…` and `node_dir=…` for the workflow: a folder that exists, or empty."""
    root = Path(args.root).resolve()
    cfg = load_config(root)
    for key in ("python_dir", "node_dir"):
        d = cfg.get(key)
        print(f"{key}={d if d is not None and dir_path(root, d).is_dir() else ''}")
    return 0


def kit_root() -> Path:
    return Path(__file__).resolve().parent.parent


def ci_files() -> list[tuple[Path, str]]:
    tpl = kit_root() / "templates" / "ci"
    return [(tpl / "ship-check.yml", CI_WORKFLOW), (Path(__file__).resolve(), CI_SCRIPT), (tpl / "README.md", CI_NOTES),
            (tpl / "ship-secrets.yml", SECRETS_WORKFLOW), (tpl / "gitleaks.toml", CI_GITLEAKS_CONFIG)]


def install_ci(root: Path) -> list[str]:
    """Copy the kit's CI files into the project; return the ones that changed. They're kit-owned: never edit them."""
    files = ci_files()
    if not files[0][0].exists():
        die("The CI templates aren't next to this script. Run setup from the plugin, not from the project's CI copy.")
    changed = []
    for src, rel in files:
        dst = root / rel
        if dst.exists() and dst.read_bytes().replace(b"\r\n", b"\n") == src.read_bytes().replace(b"\r\n", b"\n"):
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        changed.append(rel)
    return changed


def drop_plugin_declaration(root: Path) -> str:
    """Take the kit out of the project's .claude/settings.json (D65). The plugin now comes from the owner's claude.ai
    account, which keeps it current in chat and in Claude Code. A project-declared copy would outrank the account
    copy on every machine that trusts the repo and update on its own schedule. Removes only the kit's own entries;
    deletes the file if nothing else is left in it. Returns one line for setup's output."""
    path = root / CLOUD_SETTINGS
    if not path.exists():
        return "plugin: comes from your claude.ai account (Customize → Plugins); nothing declared in the repo."
    try:
        data = json.loads(path.read_text() or "{}")
    except json.JSONDecodeError:
        return (f"plugin: {CLOUD_SETTINGS} isn't valid JSON, so setup left it alone. If it names mg-ship-kit, "
                "delete those lines by hand: the plugin comes from your claude.ai account now.")
    if not isinstance(data, dict):
        return f"plugin: {CLOUD_SETTINGS} isn't a JSON object, so setup left it alone."
    before = json.dumps(data, sort_keys=True)
    markets = data.get("extraKnownMarketplaces")
    if isinstance(markets, dict):
        markets.pop(KIT_MARKETPLACE, None)
        if not markets:
            data.pop("extraKnownMarketplaces")
    plugins = data.get("enabledPlugins")
    if isinstance(plugins, dict):
        for k in [k for k in plugins if k.split("@")[-1] == KIT_MARKETPLACE]:
            plugins.pop(k)
        if not plugins:
            data.pop("enabledPlugins")
    if json.dumps(data, sort_keys=True) == before:
        return "plugin: comes from your claude.ai account (Customize → Plugins); nothing declared in the repo."
    if data:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        done = f"took the kit's lines out of {CLOUD_SETTINGS} (the rest stays)"
    else:
        path.unlink()
        done = f"deleted {CLOUD_SETTINGS}, which held only the kit's lines"
    return (f"plugin: {done}. The plugin comes from your claude.ai account now (D65); a copy declared in the repo "
            "would outrank it and update on its own. Commit the change.")


def local_install_note(home: Path) -> str | None:
    """A copy installed with /plugin on this machine outranks the account copy and doesn't update with it (D65)."""
    f = home / ".claude" / "plugins" / "installed_plugins.json"
    try:
        found = f.exists() and re.search(r'"mg-ship-kit@', f.read_text()) is not None
    except OSError:
        found = False
    if not found:
        return None
    return ("WARNING: mg-ship-kit is also installed on this machine with /plugin. That copy outranks the one on your "
            "claude.ai account and doesn't update with it. Remove it: /plugin uninstall mg-ship-kit@ship-kit, then "
            "/plugin marketplace remove ship-kit, then /reload-plugins.")


CLAUDE_POINTER = ("Ship's rules come from the mg-ship-kit plugin at session start, not from this file. "
                  "This file holds only what's true of this project.")
KIT_SECTION = "## How we build"  # the template's section that held only kit rules before D64


def kit_lines() -> set[str]:
    f = Path(__file__).resolve().parent.parent / "reference" / "claude-md-kit-lines.txt"
    if not f.exists():  # the project's CI copy has no reference/ folder; cleanup only runs from the plugin
        return set()
    return {l.strip() for l in f.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")}


def clean_claude_md(cm: Path) -> list[str]:
    """Take the kit's own rules out of a project's CLAUDE.md (D64): they come from the plugin now. Deletes only exact
    copies of lines the template once held, drops the kit's section when it ends up empty, and adds the pointer line
    once. Lines in the kit's section that don't match (edited by hand) stay and are listed. Returns setup's lines."""
    known = kit_lines()
    if not known:
        return ["CLAUDE.md: the plugin's list of kit lines is missing; left untouched."]
    text = cm.read_text(encoding="utf-8")
    lines = text.splitlines()
    removed = [l for l in lines if l.strip() in known]
    out = [l for l in lines if l.strip() not in known]
    edited: list[str] = []
    i = next((n for n, l in enumerate(out) if re.match(heading_re(KIT_SECTION.lstrip("# ")), l, re.I)), None)
    if i is not None:
        j = next((n for n in range(i + 1, len(out)) if out[n].startswith("## ")), len(out))
        body = [l for l in out[i + 1:j] if l.strip()]
        if not body:
            del out[i:j]
        else:
            edited = [l.strip() for l in body]
    if CLAUDE_POINTER not in out:
        h = next((n for n, l in enumerate(out) if l.startswith("# ")), None)
        if h is None:
            out[0:0] = [CLAUDE_POINTER, ""]
        else:  # right under the title, after the template's comment block if there is one
            at = h + 1
            while at < len(out):
                s = out[at].strip()
                if s.startswith("<!--"):
                    while at < len(out) and "-->" not in out[at]:
                        at += 1
                elif s:
                    break
                at += 1
            out[at:at] = ["", CLAUDE_POINTER, ""]
    new = re.sub(r"\n{3,}", "\n\n", "\n".join(out).strip("\n")) + "\n"
    if new == text:
        return ["CLAUDE.md: holds project facts only; Ship's rules come from the plugin."]
    cm.write_text(new, encoding="utf-8")
    msg = [f"CLAUDE.md: took out {len(removed)} kit line(s), now in the plugin's rules, and added the pointer line."
           if removed else "CLAUDE.md: added the pointer line; Ship's rules come from the plugin."]
    if edited:
        msg.append(f"CLAUDE.md: {len(edited)} line(s) under \"{KIT_SECTION}\" differ from any kit line, so they stay. "
                   "Show them to the owner; delete what the plugin's rules now cover, move the rest to "
                   "\"Rules the code can't show\":")
        msg += [f"  {l}" for l in edited]
    return msg


def cmd_kit_mark(args) -> int:
    """Record that the project page's Facts now say `Kit: mg-ship-kit <this version>` (D64)."""
    root = Path(args.root).resolve()
    cfg = load_config(root)
    if cfg.get("kit_line") == KIT_VERSION:
        print(f"Kit line already marked at {KIT_VERSION}.")
        return 0
    cfg["kit_line"] = KIT_VERSION
    save_config(root, cfg)
    print(f"marked: the project page says Kit: mg-ship-kit {KIT_VERSION}. Commit ship.json with your next commit.")
    return 0


def cmd_ci_install(args) -> int:
    root = Path(args.root).resolve()
    load_config(root)
    changed = install_ci(root)
    print("CI files: " + (f"wrote {', '.join(changed)}" if changed else "up to date") + f" (kit {KIT_VERSION})")
    return 0


def cmd_status(args) -> int:
    root = Path(args.root).resolve()
    def size_line(c: Contract) -> str:
        n = {k: c.size[k][0] for k in ("screens", "endpoints", "tables")}
        return " · ".join(f"{v} {k[:-1] if v == 1 else k}" for k, v in n.items())
    rows = [{"contract": c.name, "status": c.status, "removing": bool(c.removing), "tracker": c.tracker,
             "base": c.base, "size": size_line(c), "file": str(c.path.relative_to(root)),
             "kind": c.kind, "head": c.head, "repo": c.repo, "quick": c.quick, "depends": c.depends}
            for c in list_contracts(root)]
    if args.json:
        cfg = json.loads((root / CONFIG).read_text()) if (root / CONFIG).exists() else {}
        print(json.dumps({"repo": cfg.get("repo") or repo_name(root), "tracker": cfg.get("tracker"),
                          "contracts": rows}, indent=2))
        return 0
    if not rows:
        print("no contracts yet")
    for r in rows:
        tag = " (removing)" if r["removing"] else (" (head)" if r["kind"] == "head" else (f" (sub of {r['head']})" if r["head"] else ""))
        tag = (" (quick)" + tag) if r["quick"] else tag
        print(f"{r['contract']:40} {r['status'] + tag:30} {r['tracker'] or '(no tracker row)'}")
    return 0


def cmd_copy_check(args) -> int:
    root = Path(args.root).resolve()
    c = find_contract(root, args.contract, ("building", "on-dev"), "compare")  # any state when named
    notion = Path(args.notion).read_text(encoding="utf-8")
    theirs = claim_in(notion)
    if c.claim and theirs and theirs != c.claim:  # issue #30: never write over another session's pickup
        print(f"taken: the row's copy holds another session's Claim ({theirs}; this session's is {c.claim}). "
              "Write nothing to the row. At pickup, go on to the claim check; later, stop and ask the owner.")
        return TAKEN
    notion_h = copy_hash(notion)
    return copy_verdict(notion_h, copy_hash(c.text), load_sync(root).get(c.name))


def copy_verdict(notion_h: str, repo_h: str, stored: str | None) -> int:
    """Compare a Notion copy with the repo file and the last copy Claude Code wrote: 0 in step, 10 the repo moved,
    11 never written, 12 edited by hand."""
    if notion_h == repo_h:
        print("in-sync")
        return 0
    if stored is None:
        print("no-record: the Notion page doesn't hold a copy Claude Code wrote yet (first pickup, or a new page).")
        return 11
    if notion_h == stored:
        print("refresh: the repo file changed since the last copy; write the new copy.")
        return 10
    print("hand-edited: the Notion copy differs from the last copy Claude Code wrote. "
          "Stop and ask the owner before overwriting it.")
    return 12


def cmd_copy_render(args) -> int:
    root = Path(args.root).resolve()
    c = find_contract(root, args.contract, ("building", "on-dev"), "render")  # any state when named
    sys.stdout.write(render_notion_copy(c, root))
    return 0


def cmd_copy_mark(args) -> int:
    root = Path(args.root).resolve()
    c = find_contract(root, args.contract, ("building", "on-dev"), "mark")  # any state when named
    data = load_sync(root)
    data[c.name] = copy_hash(c.text)
    save_sync(root, data)
    print(f"{c.name}: tracker copy recorded")
    return 0

# ---------------------------------------------------------------- build map (D91)
MAP_FILE = CONTRACTS + "/map/build-map.md"  # a subfolder, so list_contracts never reads it as a contract
MAP_WRITTEN = "## Decisions and gaps"  # the one part Claude writes; everything above it is counted
MAP_WRITTEN_NOTE = "Written by Claude, not counted: the only part of this map that can be wrong."
MAP_MAX_WRITTEN = 10  # "a few lines": a long write-up goes unread and is where a confident wrong map comes from
MAP_REF = "origin/dev"  # the map describes what is on dev, never a half-built piece in the working tree
MAP_SYNC_KEY = "build-map"  # in .ship/notion-sync.json, next to the contracts' copies
FRESH_KEY = "Freshness:"
MAP_SIZE_LIMIT = 2_000_000
MAP_KEY_COLS = 8  # columns shown per table: keys and links first, then the rest up to this many
ALEMBIC_REV_RE = re.compile(r"^revision\s*(?::[^=\n]+)?=\s*[\"']([^\"']+)[\"']", re.M)
ALEMBIC_DOWN_RE = re.compile(r"^down_revision\s*(?::[^=\n]+)?=\s*(.+)$", re.M)
OP_CALL_RE = re.compile(r"\bop\.(create_table|drop_table|add_column|drop_column|rename_table)\(")
SQL_CREATE_RE = re.compile(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\"'`]?([\w.]+)[\"'`]?\s*\(", re.I)
SQL_DROP_RE = re.compile(r"DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?[\"'`]?([\w.]+)", re.I)
SQL_ALTER_RE = re.compile(r"ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:ONLY\s+)?[\"'`]?([\w.]+)[\"'`]?\s+"
                          r"(ADD|DROP)\s+(?:COLUMN\s+)?(?:IF\s+(?:NOT\s+)?EXISTS\s+)?[\"'`]?(\w+)", re.I)
SQL_RENAME_RE = re.compile(r"ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?[\"'`]?([\w.]+)[\"'`]?\s+RENAME\s+TO\s+[\"'`]?([\w.]+)", re.I)
SQL_NOT_COLUMN = ("CONSTRAINT", "PRIMARY", "FOREIGN", "UNIQUE", "CHECK", "INDEX", "KEY", "EXCLUDE", "LIKE")
STR_ARG_RE = re.compile(r"^[rbuRBU]?[\"']([^\"']+)[\"']")


def call_args(text: str, start: int) -> list[str]:
    """The top-level arguments of a call whose '(' ends just before start."""
    depth, i, quote, args, cur = 1, start, None, [], start
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "'\"`":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
            if depth == 0:
                args.append(text[cur:i])
                break
        elif ch == "," and depth == 1:
            args.append(text[cur:i])
            cur = i + 1
        i += 1
    return [a.strip() for a in args if a.strip()]


def str_arg(a: str) -> str | None:
    m = STR_ARG_RE.match(a.strip())
    return m.group(1) if m else None


def fk_table(target: str) -> str:
    """'orgs.id' → 'orgs'; 'public.orgs.id' → 'public.orgs'."""
    return target.rsplit(".", 1)[0].lower() if "." in target else target.lower()


class Schema:
    """Tables and their columns, replayed from the migrations in order: creates, adds, drops and renames."""

    def __init__(self):
        self.tables: dict[str, dict] = {}

    def create(self, name: str, f: str) -> dict:
        t = self.tables.setdefault(name.lower(), {"cols": [], "keys": set(), "links": {}, "file": f})
        return t

    def column(self, table: str, col: str, key: bool = False, link: str | None = None, f: str = "") -> None:
        t = self.create(table, f)
        if col not in t["cols"]:
            t["cols"].append(col)
        if key:
            t["keys"].add(col)
        if link:
            t["links"][col] = link

    def drop_column(self, table: str, col: str) -> None:
        t = self.tables.get(table.lower())
        if t and col in t["cols"]:
            t["cols"].remove(col)
            t["keys"].discard(col)
            t["links"].pop(col, None)

    def drop(self, table: str) -> None:
        self.tables.pop(table.lower(), None)

    def rename(self, old: str, new: str) -> None:
        if old.lower() in self.tables:
            self.tables[new.lower()] = self.tables.pop(old.lower())


def sa_column(schema: Schema, table: str, a: str, f: str) -> None:
    """One `sa.Column('name', …)` argument of an Alembic call."""
    m = re.match(r"(?:\w+\.)*Column\(", a)
    if not m:
        return
    inner = call_args(a, m.end())
    name = str_arg(inner[0]) if inner else None
    if not name:
        return
    fk = re.search(r"ForeignKey\(\s*[\"']([\w.]+)[\"']", a)
    schema.column(table, name, key=bool(re.search(r"primary_key\s*=\s*True", a)),
                  link=fk_table(fk.group(1)) if fk else None, f=f)


def replay_alembic(schema: Schema, text: str, f: str) -> None:
    for m in OP_CALL_RE.finditer(text):
        kind, args = m.group(1), call_args(text, m.end())
        first = str_arg(args[0]) if args else None
        if not first:
            continue
        if kind == "create_table":
            schema.create(first, f)
            for a in args[1:]:
                if re.match(r"(?:\w+\.)*PrimaryKeyConstraint\(", a):
                    for col in re.findall(r"[\"'](\w+)[\"']", a.split("name=")[0]):
                        schema.column(first, col, key=True, f=f)
                elif re.match(r"(?:\w+\.)*ForeignKeyConstraint\(", a):
                    lists = re.findall(r"\[([^\]]*)\]", a)
                    if len(lists) >= 2:
                        cols = re.findall(r"[\"'](\w+)[\"']", lists[0])
                        refs = re.findall(r"[\"']([\w.]+)[\"']", lists[1])
                        for col, ref in zip(cols, refs):
                            schema.column(first, col, link=fk_table(ref), f=f)
                else:
                    sa_column(schema, first, a, f)
        elif kind == "add_column" and len(args) > 1:
            sa_column(schema, first, args[1], f)
        elif kind == "drop_column" and len(args) > 1 and str_arg(args[1]):
            schema.drop_column(first, str_arg(args[1]))
        elif kind == "drop_table":
            schema.drop(first)
        elif kind == "rename_table" and len(args) > 1 and str_arg(args[1]):
            schema.rename(first, str_arg(args[1]))


def replay_sql(schema: Schema, text: str, f: str) -> None:
    events = []
    for m in SQL_CREATE_RE.finditer(text):
        events.append((m.start(), "create", m))
    for m in SQL_DROP_RE.finditer(text):
        events.append((m.start(), "drop", m))
    for m in SQL_RENAME_RE.finditer(text):
        events.append((m.start(), "rename", m))
    for m in SQL_ALTER_RE.finditer(text):
        events.append((m.start(), "alter", m))
    for _, kind, m in sorted(events, key=lambda e: e[0]):
        if kind == "create":
            table = m.group(1)
            schema.create(table, f)
            for item in call_args(text, m.end()):
                words = item.split()
                head = words[0].upper() if words else ""
                up = item.upper()
                if head in SQL_NOT_COLUMN:
                    cols = re.findall(r"\(([^)]*)\)", item)
                    names = [c.strip(" \"'`") for c in cols[0].split(",")] if cols else []
                    if "PRIMARY KEY" in up:
                        for c in names:
                            schema.column(table, c, key=True, f=f)
                    ref = re.search(r"REFERENCES\s+[\"'`]?([\w.]+)", item, re.I)
                    if "FOREIGN KEY" in up and ref:
                        for c in names:
                            schema.column(table, c, link=ref.group(1).lower(), f=f)
                    continue
                if not words:
                    continue
                ref = re.search(r"REFERENCES\s+[\"'`]?([\w.]+)", item, re.I)
                schema.column(table, words[0].strip("\"'`"), key="PRIMARY KEY" in up,
                              link=ref.group(1).lower() if ref else None, f=f)
        elif kind == "drop":
            schema.drop(m.group(1))
        elif kind == "rename":
            schema.rename(m.group(1), m.group(2))
        elif m.group(2).upper() == "ADD":
            rest = text[m.end():text.find(";", m.end()) if ";" in text[m.end():] else len(text)]
            ref = re.search(r"REFERENCES\s+[\"'`]?([\w.]+)", rest, re.I)
            schema.column(m.group(1), m.group(3), key="PRIMARY KEY" in rest.upper(),
                          link=ref.group(1).lower() if ref else None, f=f)
        else:
            schema.drop_column(m.group(1), m.group(3))


def upgrade_part(text: str) -> str:
    """An Alembic file's upgrade() only: its downgrade() undoes it and would erase the tables."""
    m = re.search(r"^def\s+upgrade\s*\(", text, re.M)
    if not m:
        return text
    d = re.search(r"^def\s+downgrade\s*\(", text[m.end():], re.M)
    return text[m.start(): m.end() + d.start()] if d else text[m.start():]


def migration_order(files: dict[str, str]) -> list[str]:
    """SQL and other files by path, then Alembic revisions along their chain (a merge counts after its parents)."""
    revs: dict[str, tuple[str, list[str]]] = {}
    plain = []
    for f, text in files.items():
        r = ALEMBIC_REV_RE.search(text)
        if f.endswith(".py") and r:
            d = ALEMBIC_DOWN_RE.search(text)
            downs = re.findall(r"[\"']([^\"']+)[\"']", d.group(1)) if d else []
            revs[r.group(1)] = (f, downs)
        else:
            plain.append(f)
    depth: dict[str, int] = {}

    def depth_of(rev: str, seen: frozenset = frozenset()) -> int:
        if rev in depth:
            return depth[rev]
        if rev not in revs or rev in seen:
            return 0
        d = 1 + max([depth_of(p, seen | {rev}) for p in revs[rev][1]] or [0])
        depth[rev] = d
        return d

    ordered = sorted(revs, key=lambda r: (depth_of(r), revs[r][0]))
    return sorted(plain) + [revs[r][0] for r in ordered]


def ref_files(root: Path, ref: str) -> dict[str, str]:
    """Every file at a commit that the size check reads: its text, by repo path."""
    res = sh(["git", "ls-tree", "-r", "-l", "-z", ref], cwd=root)
    if res.returncode != 0:
        die(f"can't list the files at {ref}: {res.stderr.strip()}")
    out = {}
    for entry in res.stdout.split("\0"):
        if not entry or "\t" not in entry:
            continue
        meta, f = entry.split("\t", 1)
        parts = meta.split()
        if len(parts) < 4 or parts[1] != "blob" or not parts[3].isdigit() or int(parts[3]) > MAP_SIZE_LIMIT:
            continue
        if not f.endswith((".py", ".sql", ".tsx", ".jsx", ".ts", ".js")) or \
                any(p in SKIP_DIRS for p in f.split("/")[:-1]):
            continue
        out[f] = ""
    if not out:
        return out
    names = sorted(out)
    res = subprocess.run(["git", "cat-file", "--batch"], cwd=str(root), capture_output=True,
                         input="".join(f"{ref}:{f}\n" for f in names).encode("utf-8"))
    data, pos = res.stdout, 0
    for f in names:  # each answer: "<sha> blob <size>\n<bytes>\n", or "<name> missing\n"
        nl = data.find(b"\n", pos)
        head = data[pos:nl].split()
        pos = nl + 1
        if len(head) == 3 and head[1] == b"blob":
            size = int(head[2])
            out[f] = data[pos:pos + size].decode("utf-8", errors="ignore")
            pos += size + 1
    return out


def map_contents(root: Path, cfg: dict, ref: str) -> dict:
    """What the build map holds, counted by the size check's code (D15) over every file on dev."""
    py, nd = cfg.get("python_dir"), cfg.get("node_dir")
    files = {f: t for f, t in ref_files(root, ref).items() if in_dir(f, py) or in_dir(f, nd)}
    seen: dict[str, dict[str, str]] = {"screens": {}, "endpoints": {}, "tables": {}}
    for f in sorted(files):
        scan_items(f, files[f], py, nd, seen)
    schema = Schema()
    migrations = {f: t for f, t in files.items() if in_dir(f, py) and not is_test_file(f) and
                  ((f.endswith(".sql") and "down" not in Path(f).name.lower()) or
                   (f.endswith(".py") and (OP_CALL_RE.search(t) or SQL_CREATE_RE.search(t))))}
    for f in migration_order(migrations):
        text = upgrade_part(migrations[f]) if f.endswith(".py") else migrations[f]
        if f.endswith(".py"):
            replay_alembic(schema, text, f)
        replay_sql(schema, text, f)
    tables = {}
    counted = {n for n in seen["tables"]}
    for name, t in schema.tables.items():
        tables[name] = t
    for name in counted:  # a table the count found and the replay couldn't name (create_table(var, …))
        if name.startswith("(unnamed") and name not in tables:
            tables[name] = {"cols": [], "keys": set(), "links": {}, "file": seen["tables"][name]}
    return {"tables": tables, "endpoints": seen["endpoints"], "screens": seen["screens"], "py": py, "nd": nd}


def table_line(name: str, t: dict) -> str:
    cols = t["cols"]
    first = [c for c in cols if c in t["keys"] or c in t["links"]]
    rest = [c for c in cols if c not in first]
    shown = (first + rest)[:max(MAP_KEY_COLS, len(first))]

    def label(c: str) -> str:
        bits = [c]
        if c in t["keys"]:
            bits.append("(key)")
        if c in t["links"]:
            bits.append(f"→ {t['links'][c]}")
        return " ".join(bits)

    more = len(cols) - len(shown)
    body = ", ".join(label(c) for c in shown) or "columns not read"
    return f"- {name}: {body}" + (f", +{more} more" if more > 0 else "")


def by_file(items: dict[str, str]) -> list[str]:
    groups: dict[str, list[str]] = {}
    for name, f in items.items():
        groups.setdefault(f, []).append(name)
    return [f"- {f}: {', '.join(sorted(names))}" for f, names in sorted(groups.items())]


def written_part(root: Path) -> list[str]:
    """The lines Claude wrote under 'Decisions and gaps' in the current map, kept across rebuilds."""
    p = root / MAP_FILE
    if not p.exists():
        return []
    text = p.read_text(encoding="utf-8")
    m = re.search(heading_re(MAP_WRITTEN.lstrip("# ")), text, re.M | re.I)
    if not m:
        return []
    lines = []
    for line in text[m.end():].splitlines():
        s = line.strip()
        if not s or s == MAP_WRITTEN_NOTE or s.lower() in ("- none yet", "- none written yet"):
            continue
        if s.startswith("#"):
            break
        lines.append(s)
    return lines


def written_problems(lines: list[str]) -> list[str]:
    out = []
    bad = [l for l in lines if not re.match(rf"^{BULLET}\s+\S", l)]
    if bad:
        out.append(f"{len(bad)} line(s) under '{MAP_WRITTEN}' aren't list items, like {bad[0][:60]!r}. Start each "
                   "with '- '")
    if len(lines) > MAP_MAX_WRITTEN:
        out.append(f"'{MAP_WRITTEN}' has {len(lines)} lines, and it holds at most {MAP_MAX_WRITTEN}. Merge "
                   "lines, or cut the least useful")
    if any(PLACEHOLDER_RE.search(l) for l in lines):
        out.append(f"a line under '{MAP_WRITTEN}' still has a placeholder in angle brackets. Replace it with real "
                   "text")
    return out


def render_map(root: Path, cfg: dict, ref: str, sha: str) -> str:
    m = map_contents(root, cfg, ref)
    date = git_out(root, "log", "-1", "--format=%cs", sha) or dt.date.today().isoformat()
    show = lambda d: "none" if d is None else ("the project root" if d == "." else f"{d}/")  # noqa: E731
    written = written_part(root)
    out = [f"# Build map: {cfg.get('repo') or repo_name(root) or root.name}", "",
           f"Map of: dev at {sha[:12]}, {date}",
           f"Counts: {len(m['tables'])} tables · {len(m['endpoints'])} endpoints · {len(m['screens'])} screens",
           f"Counted from: FastAPI routes and Alembic or SQL migrations in {show(m['py'])}, React Router routes "
           f"in {show(m['nd'])}, by the size check's own code (D15). Code it can't read isn't on this map.",
           "Claude Code rebuilds this file at every /mg-ship-kit:done. Never edit it by hand, here or in Notion.", "",
           "## Tables", ""]
    out += [table_line(n, m["tables"][n]) for n in sorted(m["tables"])] or ["- none"]
    out += ["", "## Endpoints", ""] + (by_file(m["endpoints"]) or ["- none"])
    out += ["", "## Screens", ""] + (by_file(m["screens"]) or ["- none"])
    out += ["", MAP_WRITTEN, "", MAP_WRITTEN_NOTE, ""] + (written or ["- none yet"])
    return "\n".join(out) + "\n"


def map_ref(root: Path, ref: str | None) -> tuple[str, str]:
    ref = ref or MAP_REF
    sha = git_out(root, "rev-parse", "--verify", f"{ref}^{{commit}}")
    if not sha:
        die(f"{ref} isn't here yet. Run `git fetch origin dev` first: the map describes dev, not your working copy.")
    return ref, sha


def map_stamp(text: str) -> str | None:
    m = re.search(r"^Map of: dev at ([0-9a-f]{7,40})\b", text, re.M)
    return m.group(1) if m else None


def cmd_map(args) -> int:
    root = Path(args.root).resolve()
    cfg = load_config(root)
    problems = written_problems(written_part(root))
    if problems:
        die("The build map wasn't written. Fix its written lines first:\n" + "\n".join(
            f"  {i}. {p}" for i, p in enumerate(problems, 1)), 1)
    ref, sha = map_ref(root, args.ref)
    text = render_map(root, cfg, ref, sha)
    p = root / MAP_FILE
    old = p.read_text(encoding="utf-8") if p.exists() else None
    if old == text:
        print(f"{MAP_FILE}: unchanged (dev at {sha[:12]})")
        return 0
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    counts = re.search(r"^Counts: (.*)$", text, re.M).group(1)
    print(f"wrote {MAP_FILE}: dev at {sha[:12]} · {counts} · {len(written_part(root))} written line(s)")
    return 0


def freshness(root: Path, cfg: dict, ref: str | None) -> tuple[int, str]:
    """(0 up to date | 1 stale | 3 no map, the line the Notion copy shows). Only product files count: the map's
    own commit, contract states and other bookkeeping don't make it stale."""
    p = root / MAP_FILE
    if not p.exists():
        return 3, f"{FRESH_KEY} no map yet: Claude Code writes it at setup or the next /mg-ship-kit:done."
    stamp = map_stamp(p.read_text(encoding="utf-8"))
    ref, sha = map_ref(root, ref)
    if not stamp or not is_commit(root, stamp):
        return 1, (f"{FRESH_KEY} unknown: the commit this map describes ({stamp or 'none'}) isn't here. "
                   "Treat it as stale.")
    changed = product_files(root, cfg, stamp, sha)
    if not changed:
        return 0, f"{FRESH_KEY} up to date with dev ({sha[:12]})."
    return 1, (f"{FRESH_KEY} stale. Dev has changed {len(changed)} product file(s) since this map "
               f"(dev at {sha[:12]}). It's rebuilt at the next /mg-ship-kit:done.")


def map_copy_text(root: Path, cfg: dict, ref: str | None) -> str:
    """The build map with its freshness line: what the Notion copy shows."""
    _, line = freshness(root, cfg, ref)
    text = (root / MAP_FILE).read_text(encoding="utf-8")
    return re.sub(r"^(Map of: .*)$", lambda m: f"{m.group(1)}\n{line}", text, count=1, flags=re.M)


def map_hash(text: str) -> str:
    """The copy's hash without its freshness line, which changes with every push to dev."""
    kept = [l for l in normalize_copy(text).splitlines() if not l.startswith(FRESH_KEY)]
    return hashlib.sha256("\n".join(kept).encode("utf-8")).hexdigest()[:16]


def fresh_line_of(text: str) -> str:
    for l in normalize_copy(text).splitlines():
        if l.startswith(FRESH_KEY):
            return l
    return ""


def need_map(root: Path) -> None:
    if not (root / MAP_FILE).exists():
        die(f"There's no build map yet. Run `map` first; it writes {MAP_FILE}.")


def cmd_map_status(args) -> int:
    root = Path(args.root).resolve()
    cfg = load_config(root)
    code, line = freshness(root, cfg, args.ref)
    print(line)
    if code == 3:
        return 3
    page = cfg.get("map_page")
    sync = load_sync(root)
    copy = map_copy_text(root, cfg, args.ref)
    if not page:
        print("copy: no Notion page linked yet → create the 'Build map' sub-page and run `link-map`")
    elif sync.get(MAP_SYNC_KEY) != map_hash(copy) or sync.get(MAP_SYNC_KEY + "-fresh") != fresh_line_of(copy):
        print("copy: refresh → write the Notion copy (map-copy-check, map-render, map-copy-mark)")
    else:
        print("copy: in step")
    return code


def cmd_map_render(args) -> int:
    root = Path(args.root).resolve()
    cfg = load_config(root)
    need_map(root)
    sys.stdout.write(render_copy(MAP_FILE, map_copy_text(root, cfg, args.ref),
                                 "Chat reads it before a spec; nobody edits it here."))
    return 0


def cmd_map_copy_check(args) -> int:
    root = Path(args.root).resolve()
    cfg = load_config(root)
    need_map(root)
    notion = Path(args.notion).read_text(encoding="utf-8")
    copy = map_copy_text(root, cfg, args.ref)
    sync = load_sync(root)
    code = copy_verdict(map_hash(notion), map_hash(copy), sync.get(MAP_SYNC_KEY))
    if code == 0 and fresh_line_of(notion) != fresh_line_of(copy):
        print("refresh: only the freshness line changed; write the new copy.")
        return 10
    return code


def cmd_map_copy_mark(args) -> int:
    root = Path(args.root).resolve()
    cfg = load_config(root)
    need_map(root)
    copy = map_copy_text(root, cfg, args.ref)
    data = load_sync(root)
    data[MAP_SYNC_KEY] = map_hash(copy)
    data[MAP_SYNC_KEY + "-fresh"] = fresh_line_of(copy)
    save_sync(root, data)
    print("build map: Notion copy recorded")
    return 0


def cmd_link_map(args) -> int:
    root = Path(args.root).resolve()
    cfg = load_config(root)
    if not re.match(r"^https://(www\.|app\.)?notion\.(so|com)/", args.page):
        die("--page must be the Notion link of the Build map sub-page.")
    if cfg.get("map_page") == args.page:
        print(f"build map page already linked: {args.page}")
        return 0
    cfg["map_page"] = args.page
    save_config(root, cfg)
    print(f"linked the build map page in {CONFIG}: {args.page}")
    return 0



def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ship_check.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".", help="project root (default: current directory)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("setup"); s.add_argument("--python-dir"); s.add_argument("--node-dir"); s.add_argument("--force", action="store_true")
    s.add_argument("--no-default-stack", action="store_true", help="don't fall back to the kit's default stack in an empty repo")
    s.add_argument("--track", choices=TRACKS + DROPPED_TRACKS, help="the project's track, from the Track line in its Facts")
    sub.add_parser("kit-mark", help="record that the project page's Kit line names this plugin version")
    p = sub.add_parser("link"); p.add_argument("--data-source", required=True); p.add_argument("--database"); p.add_argument("--page")
    p = sub.add_parser("gate-dev"); p.add_argument("--since", help="start from this commit (default: origin/dev)")
    p = sub.add_parser("ci"); p.add_argument("--branch"); p.add_argument("--after"); p.add_argument("--before")
    p.add_argument("--since", help="start from this commit instead of asking GitHub (dev only)")
    p.add_argument("--offline", action="store_true", help="don't call the GitHub API")
    p.add_argument("--wait", type=int, default=600, help="seconds a release waits for a running dev check")
    sub.add_parser("ci-env"); sub.add_parser("ci-install")
    p = sub.add_parser("pickup"); p.add_argument("--file", required=True); p.add_argument("--name"); p.add_argument("--tracker")
    p.add_argument("--repo", default="", help="the row's Repo column (D89): must name this repo")
    p.add_argument("--single-repo", action="store_true", help="the project page lists one repo: an empty Repo column passes")
    p.add_argument("--rows", help=f"the tracker's rows ({ROWS_FILE}): checks Depends on and numbers the contract (D93)")
    p.add_argument("--status", help="the row's Status, fetched just now: anything but Ready is refused (issue #30)")
    p = sub.add_parser("claim-check", help="read-back after pickup: does the row hold this session's Claim (issue #30)")
    p.add_argument("--contract"); p.add_argument("--notion", required=True, help="the row's page content, fetched back")
    p.add_argument("--status", help="the row's Status, fetched back (required unless --recheck)")
    p.add_argument("--recheck", action="store_true", help="before the push: is the row still this session's? removes nothing")
    p = sub.add_parser("next-pick", help="which Ready row of this repo may build now, from the tracker's rows (D93)")
    p.add_argument("--rows", default=ROWS_FILE); p.add_argument("--name", help="the row the owner named")
    p.add_argument("--skip", action="append", help="a row to pass over (pickup said it waits); repeatable")
    p.add_argument("--single-repo", action="store_true", help="the project page lists one repo: an empty Repo column passes")
    p = sub.add_parser("quick", help="write a quick fix's contract from the owner's own words (D92)")
    p.add_argument("--what", required=True, help="the change, in the owner's own words, one line")
    p.add_argument("--by", required=True, help="the owner's name")
    p.add_argument("--check", required=True, help="one line: When I … then I see …")
    p.add_argument("--rows", help=f"the tracker's rows ({ROWS_FILE}): numbers the contract after the tracker's (D93)")
    p.add_argument("--single-repo", action="store_true")
    p = sub.add_parser("split", help="save a head's sub-contracts as draft sub-pieces (the split stop)")
    p.add_argument("--head", help="the head contract (default: the only open one)")
    p.add_argument("--rows", help=f"the tracker's rows ({ROWS_FILE}): numbers the sub-contracts after the tracker's (D93)")
    p.add_argument("--single-repo", action="store_true")
    p.add_argument("files", nargs="+", help="the sub-contract files, in build order")
    p = sub.add_parser("go"); p.add_argument("--head")
    p = sub.add_parser("chain-next"); p.add_argument("--head")
    p.add_argument("--green", action="store_true", help="the owner says GitHub's check is green on dev: don't ask GitHub")
    p.add_argument("--timeout", type=int, default=900, help="seconds to wait for GitHub's check on dev (default 900)")
    p.add_argument("--poll", type=int, default=20)
    p = sub.add_parser("chain-sync"); p.add_argument("--head")
    p = sub.add_parser("chain-status"); p.add_argument("--head"); p.add_argument("--json", action="store_true")
    p = sub.add_parser("ci-wait"); p.add_argument("--sha", default="HEAD")
    p.add_argument("--timeout", type=int, default=900, help="seconds to wait for the check (default 900)")
    p.add_argument("--poll", type=int, default=20, help="seconds between asks (default 20)")
    p = sub.add_parser("set-tracker"); p.add_argument("--contract", required=True); p.add_argument("--tracker", required=True)
    p = sub.add_parser("ondev"); p.add_argument("--branch", default="dev"); p.add_argument("--quiet", action="store_true")
    p = sub.add_parser("sync-dev", help="rebase the building piece onto origin/dev and move its Base there (D93)")
    p.add_argument("--contract"); p.add_argument("--no-fetch", action="store_true", help="use origin/dev as fetched")
    p.add_argument("--owner-ok", action="store_true", help="the owner's word: go on past shared files, leave conflicts open")
    p.add_argument("--continue", dest="cont", action="store_true", help="after resolving: move the Base (owner-ok only)")
    p = sub.add_parser("drop"); p.add_argument("--contract")
    p.add_argument("--rows", help=f"the tracker's rows ({ROWS_FILE}): refuses while an open row depends on the piece (D93)")
    p = sub.add_parser("status"); p.add_argument("--json", action="store_true")
    p = sub.add_parser("copy-check"); p.add_argument("--contract"); p.add_argument("--notion", required=True)
    p = sub.add_parser("copy-mark"); p.add_argument("--contract")
    p = sub.add_parser("copy-render"); p.add_argument("--contract")
    for name in ("map", "map-status", "map-render", "map-copy-check", "map-copy-mark"):  # the build map (D91)
        p = sub.add_parser(name); p.add_argument("--ref", help=f"the commit the map describes (default: {MAP_REF})")
        if name == "map-copy-check":
            p.add_argument("--notion", required=True)
    p = sub.add_parser("link-map"); p.add_argument("--page", required=True)
    for name in ("check", "size", "leftovers"):
        p = sub.add_parser(name); p.add_argument("--contract"); p.add_argument("--json", action="store_true")
        if name == "leftovers":
            p.add_argument("--all", action="store_true", help="scan every file, not only the piece's")
    p = sub.add_parser("stack"); p.add_argument("--contract"); p.add_argument("--json", action="store_true")
    p = sub.add_parser("stack-add"); p.add_argument("side", choices=["python", "node"]); p.add_argument("name")
    p = sub.add_parser("done"); p.add_argument("--contract")
    p = sub.add_parser("review-plan"); p.add_argument("--contract")
    p = sub.add_parser("review-skip"); p.add_argument("--contract")
    p = sub.add_parser("review-write"); p.add_argument("--contract"); p.add_argument("--findings", required=True)
    p = sub.add_parser("review-waive"); p.add_argument("--contract"); p.add_argument("--finding", required=True)
    p.add_argument("--by", required=True); p.add_argument("--why", required=True)
    p = sub.add_parser("review-status"); p.add_argument("--contract"); p.add_argument("--line", action="store_true")
    sub.add_parser("review-waivers")
    p = sub.add_parser("env-check"); p.add_argument("--ref", default="HEAD", help="the commit to look in (default: HEAD)")
    p = sub.add_parser("secret-scan", help="scan new commits for secrets with gitleaks (D67)")
    p.add_argument("--ref", default="HEAD", help="what the push sends (default: HEAD); scans its commits not on any remote")
    p.add_argument("--history", action="store_true", help="scan the whole history and only report (setup runs it once)")
    p.add_argument("--ci", action="store_true", help="GitHub's run: the commits this push brought")
    p.add_argument("--branch"); p.add_argument("--before"); p.add_argument("--after")
    p = sub.add_parser("lesson", help="record what stops a fixed bug next time (D78)")
    p.add_argument("--contract", required=True); p.add_argument("--test"); p.add_argument("--fact"); p.add_argument("--kit")
    p = sub.add_parser("secret-allow", help="the owner clears a false alarm in one line (D68)")
    p.add_argument("fingerprint"); p.add_argument("--by", required=True); p.add_argument("--why", required=True)
    p = sub.add_parser("adopt", help="the owner accepts code already on dev that no piece covers (issue #40)")
    p.add_argument("commit"); p.add_argument("--by", required=True); p.add_argument("--why", required=True)
    args = ap.parse_args(argv)
    if args.cmd == "setup":
        return cmd_setup(args)
    if args.cmd in ("check", "size", "leftovers"):
        args.what = args.cmd
        return cmd_check(args)
    if args.cmd == "stack":
        return cmd_stack_only(args)
    if args.cmd == "stack-add":
        return cmd_stack_add(args)
    handlers = {"done": cmd_done, "link": cmd_link, "pickup": cmd_pickup, "quick": cmd_quick, "ondev": cmd_ondev, "drop": cmd_drop,
                "status": cmd_status, "copy-check": cmd_copy_check, "copy-mark": cmd_copy_mark,
                "copy-render": cmd_copy_render, "gate-dev": cmd_gate_dev, "ci": cmd_ci, "ci-env": cmd_ci_env,
                "ci-install": cmd_ci_install, "env-check": cmd_env_check, "split": cmd_split, "go": cmd_go,
                "chain-next": cmd_chain_next, "chain-sync": cmd_chain_sync, "chain-status": cmd_chain_status,
                "ci-wait": cmd_ci_wait, "set-tracker": cmd_set_tracker, "kit-mark": cmd_kit_mark,
                "review-plan": cmd_review_plan, "review-skip": cmd_review_skip, "review-write": cmd_review_write,
                "review-waive": cmd_review_waive, "review-status": cmd_review_status,
                "review-waivers": cmd_review_waivers, "secret-scan": cmd_secret_scan,
                "secret-allow": cmd_secret_allow, "adopt": cmd_adopt, "lesson": cmd_lesson, "map": cmd_map,
                "map-status": cmd_map_status, "map-render": cmd_map_render, "map-copy-check": cmd_map_copy_check,
                "map-copy-mark": cmd_map_copy_mark, "link-map": cmd_link_map, "next-pick": cmd_next_pick,
                "sync-dev": cmd_sync_dev, "claim-check": cmd_claim_check}
    if args.cmd in handlers:
        return handlers[args.cmd](args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
