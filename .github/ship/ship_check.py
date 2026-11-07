#!/usr/bin/env python3
"""Ship kit — the CTO check and its helpers.

Subcommands (run from the project root, or pass --root):
  setup       detect the backend and frontend folders, write ship.json, copy templates and the CI files
  link        store the project's Notion tracker in ship.json
  gate-dev    decide whether the commits since a ref may reach dev (the push gate and CI both use it)
  ci          the check GitHub runs on every push to dev and main, before any deploy
  ci-env      print the backend and frontend folders for the CI workflow
  ci-install  copy the CI workflow, this script and the deploy notes into .github/
  pickup      save a contract taken from the tracker as contracts/NNN-name.md, status building
  split       save the sub-contracts Claude wrote for a chain head as draft contracts, checked against the head
  go          the owner read the split: every draft sub-piece becomes ready, in build order
  chain-next  pick up the next ready sub-piece of a chain (status building)
  chain-sync  move a head to on-dev once every sub-piece is on dev, or to dropped once every one is dropped
  chain-status list a chain: its head and each sub-piece with its state
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
  env-check   exit 1 when a commit carries an env file (.env, .env.*; the example files are allowed)
  secret-scan  scan new commits for secrets with gitleaks: the push gate (every branch) and GitHub run it (D67–D70)
  secret-allow the owner's one-line clearing of a false alarm, written to .gitleaksignore (D68)
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
A chain (D61): one head contract from chat (`Chain: head`), split by Claude Code into sub-contracts (`Head: <name>`)
that build one after another. The head is picked up like a piece, the split is saved as draft sub-pieces, the owner's
"go" makes them ready, and each sub-piece then goes building → on-dev with the usual check and push. The head owns
no code itself: it moves to on-dev when every sub-piece is on dev, and the client's one verdict on the head closes
them all. A head that is building or on dev blocks release like any piece.
Exit codes: 0 pass · 1 fail · 2 usage, contract or tool error · 3 no contract building (and product code changed).
copy-check exit codes: 0 in-sync · 10 refresh · 11 no-record · 12 hand-edited.
Only python3 is required. vulture and knip are needed for `leftovers`; gitleaks 8 for `secret-scan` (every push).

ship.json folders: python_dir / node_dir are null (none), "." (the project root) or a subfolder.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
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

KIT_VERSION = "0.12.0"  # keep equal to plugins/mg-ship-kit/.claude-plugin/plugin.json
CONFIG = "ship.json"
CONTRACTS = "contracts"
SYNC_FILE = "notion-sync.json"  # in .ship/ (git-ignored): hash of the repo text last copied to the tracker
STATES = ("draft", "ready", "building", "on-dev", "done", "dropped")
BANNER_MARK = "Read-only copy of"  # first line of every tracker copy Claude Code writes
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "env", "dist", "build", "__pycache__", ".ship"}
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"  # git's empty tree: "since nothing"
ZERO_SHA = "0" * 40  # GitHub's `before` when a push creates the branch
TRACKS = ("devops", "railway", "cloudflare")  # D51: picked per project from the start questions
READY_TRACKS = ("devops", "railway")  # cloudflare needs its own stack list, size counts and deploy first
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
BOOKKEEPING_FILES = ("ship.json", "CLAUDE.md", ".gitignore", CLOUD_SETTINGS, GITLEAKS_IGNORE)
KIT_MARKETPLACE = "ship-kit"  # the name in .claude-plugin/marketplace.json
ENV_EXAMPLES = (".env.example", ".env.sample", ".env.template")  # env files that hold no secrets: these may be committed
GITIGNORE_ENV = [".env", ".env.*"] + [f"!{n}" for n in ENV_EXAMPLES]  # the lines setup adds to .gitignore
# The words line that opens a contract's body; its four labels follow the Backlog's Source (ship-spec). A chain's
# sub-piece opens with "From the head:" instead, since it traces to the head contract, not to the client (D61).
WORDS_LABEL_RE = re.compile(r"^\**(client['’]s words|from my notes on the client|users['’] words|owner['’]s words|from the head)\b", re.I)
HEADER_KEYS = ("Status", "Base", "Approved", "Tracker", "Removing", "Chain", "Head", "Lesson")  # the lines above a contract's body
GO_PENDING = "pending: the owner's go on the chain"  # a sub-piece's Approved line between the split and the go
MAX_SUBS = 6  # a chain is two to six sub-pieces; more is two chains
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
PY_STDLIB = set(getattr(sys, "stdlib_module_names", set())) | {"typing_extensions"}
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
        die(f"{CONFIG} not found in {root}. Run `/mg-ship-kit:setup` first.")
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


def field(text: str, key: str) -> str | None:
    m = re.search(rf"^\**{key}\**:\**[ \t]*(\S.*?)[ \t]*$", text, re.M)
    return m.group(1) if m else None


class Contract:
    def __init__(self, path: Path):
        self.path = path
        self.text = path.read_text(encoding="utf-8")
        self.name = path.stem
        self.status = (self._field("Status") or "draft").lower()
        if self.status not in STATES:
            die(f"contract {self.name}: unknown Status {self.status!r} (one of {', '.join(STATES)})")
        self.base = self._field("Base") or ""
        self.approved = self._field("Approved") or ""
        self.tracker = self._field("Tracker") or ""
        self.removing = self._field("Removing") or ""
        self.fixes = (self._field("Fixes") or "").strip()  # a bug fix: what broke, as the client said it (D77)
        self.lesson = (self._field("Lesson") or "").strip()  # what stops it next time (D78)
        self.is_head = (self._field("Chain") or "").strip().lower() == "head"  # a chain's head contract (D61)
        self.head = (self._field("Head") or "").strip()  # a sub-piece: the name of its head contract
        if self.is_head and self.head:
            die(f"contract {self.name}: a contract can't be both a chain head and a sub-piece")
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
        text = re.sub(r"^\**Status\**:\**[ \t]*.*$", lambda m: f"Status: {status}", self.text, count=1, flags=re.M)
        for key, val in (extra or {}).items():
            pat = re.compile(rf"^\**{key}\**:\**[ \t]*.*(?:\n|\Z)", re.M)
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
        sec = re.search(r"^#{1,4}\s*Size\s*$(.*?)(?=^#{1,4}\s|\Z)", self.text, re.M | re.S)
        if not sec:
            die(f"contract {self.name}: no `## Size` section")
        current = None
        for line in sec.group(1).splitlines():
            m = re.match(r"^\s*\**(Screens|Endpoints|Tables)\**\s*:\**\s*(\d+)", line, re.I)
            if m:
                current = m.group(1).lower()
                self.size[current] = (int(m.group(2)), [])
                continue
            if re.match(r"^\s*\**(Screens|Endpoints|Tables)\**\s*:", line, re.I):
                die(f"contract {self.name}: the count after `{line.strip().split(':')[0]}:` must be a number")
            b = re.match(r"^\s*[-*]\s+(.+?)\s*$", line)
            # Drop code and bold marks only: a lone `*` is a catch-all route, a real item
            item = re.sub(r"`|\*\*", "", b.group(1)).strip() if b else ""
            if b and current and item and not PLACEHOLDER_RE.fullmatch(item):
                self.size[current][1].append(item)
        missing = [k for k in ("screens", "endpoints", "tables") if k not in self.size]
        if missing:
            die(f"contract {self.name}: Size section lacks {', '.join(k.capitalize() + ': N' for k in missing)}")

    def check_ready(self) -> None:
        """A building contract must carry a base commit and a real approval line."""
        if self.status != "building":
            return
        if not self.base or PLACEHOLDER_RE.search(self.base):
            die(f"contract {self.name}: `Base:` must be the commit the piece starts from")
        if not is_approval(self.approved):
            die(f"contract {self.name}: `Approved:` must carry the date and the owner's name — "
                "a contract is building only after the owner approved it in one line")

    def count_problems(self) -> list[str]:
        """Where a count and its named items disagree, or an endpoint lacks its method. A chain splits by the
        names, so a head (and each sub-piece) must name every item it counts."""
        out = []
        for kind in ("screens", "endpoints", "tables"):
            n, items = self.size[kind]
            if n != len(items):
                out.append(f"{kind}: counts {n} but names {len(items)}")
            if kind == "endpoints":
                out += [f"endpoint {it} has no method (METHOD /path)" for it in items if not norm_endpoint(it)[0]]
        return out


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
    return out


def building_pieces(cs: list[Contract]) -> list[Contract]:
    """The contracts that own code right now: building, and not a chain head (a head never owns code itself)."""
    return [c for c in cs if c.status == "building" and not c.is_head]


def open_heads(cs: list[Contract]) -> list[Contract]:
    """Chain heads whose chain is still running: picked up, not yet on dev."""
    return [c for c in cs if c.is_head and c.status == "building"]


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
        die(f"contract {name!r} not found in {CONTRACTS}/")
    building = building_pieces(cs)
    if not building:
        return None
    if len(building) > 1:
        die("more than one contract is building: " + ", ".join(c.name for c in building) +
            ". One piece at a time: push the finished one to dev (it becomes on-dev) or drop it.")
    building[0].check_ready()
    return building[0]


def find_contract(root: Path, name: str | None, states: tuple[str, ...], what: str) -> Contract:
    """The contract named, or the only one in one of `states`."""
    cs = list_contracts(root)
    if name:
        for c in cs:
            if c.name == name or c.path.name == name or c.name.startswith(name):
                return c
        die(f"contract {name!r} not found in {CONTRACTS}/")
    hits = [c for c in cs if c.status in states]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        die(f"no contract is {' or '.join(states)}, so there is nothing to {what}.", 3)
    die(f"several contracts could be meant ({', '.join(c.name for c in hits)}): pass --contract <name>.")
    raise SystemExit  # unreachable


# ---------------------------------------------------------------- Notion text and the tracker copy
NOTION_TAG_RE = re.compile(r"</?(?:b|strong|i|em|u|s|code|span|mark)\b[^>]*>", re.I)
BLOCK_TAG_RE = re.compile(r"^\s*</?(?:callout|details|summary|columns?|toggle|empty-block|page|content)\b[^>]*>\s*$", re.I)


def notion_to_plain(text: str) -> str:
    """Undo what Notion does to plain markdown on a round trip: inline tags, escapes, entities."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)  # Notion joins lines of one block with <br />
    text = re.sub(r"<(mention-date|date)\s[^>]*?start=\"([^\"]*)\"[^>]*?(?:/>|>.*?</\1>)", r"\2", text)
    text = re.sub(r"<mention(?:-[a-z-]+)?\s[^>]*?url=\"([^\"]*)\"[^>]*>(.*?)</mention(?:-[a-z-]+)?>",
                  lambda m: m.group(2).strip() or m.group(1), text)
    text = re.sub(r"<mention(?:-[a-z-]+)?\s[^>]*?url=\"([^\"]*)\"[^>]*/>", r"\1", text)
    text = NOTION_TAG_RE.sub("", text)
    text = re.sub(r"\\([\\`*_{}\[\]()#+\-.!<>|~:\"'$=^])", r"\1", text)
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
        if re.match(r"^\**Tracker\**:", s):  # metadata Notion may turn into a mention; not part of the contract
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
    rel = c.path.relative_to(root).as_posix()
    out = ['<callout icon="📄" color="gray_bg">',
           f"\tRead-only copy of `{rel}`, written by Claude Code. Change the contract through Claude Code, not here.",
           "</callout>"]
    text = re.sub(r"<!--.*?-->", "", c.text, flags=re.S)
    prev_list = False
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", s)
        b = re.match(r"^[-*]\s+(.*)$", s)
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
        die(f"base commit {base!r} not found. Fetch more history or fix `Base:` in the contract.")
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


def count_size(root: Path, cfg: dict, c: Contract) -> dict:
    changes = git_changes(root, c.base)
    py, nd = cfg.get("python_dir"), cfg.get("node_dir")
    seen: dict[str, dict[str, str]] = {"screens": {}, "endpoints": {}, "tables": {}}
    for f, ch in changes.items():
        if is_test_file(f):
            continue
        text = ch.text
        keep = lambda m: line_of(text, m.start()) in ch.added  # noqa: E731
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
def detect_dir(root: Path, markers: tuple[str, ...], max_depth: int = 2) -> str | None:
    best = None
    for p in walk_files(root):
        rel = p.relative_to(root)
        if len(rel.parts) - 1 > max_depth:
            continue
        if p.name in markers:
            cand = str(rel.parent).replace("\\", "/")
            if best is None or len(cand) < len(best):
                best = cand
    return best


DEPLOY_NOTE = {
    "devops": "deploy: your devops connects the server's deploy to the Ship check, so nothing deploys unless it "
              f"passes. Give them {CI_NOTES} (section \"Your devops\").",
    "railway": f"deploy: set Railway up as {CI_NOTES} says (section \"Railway\"): dev → a staging environment, "
               "main → production, each with its own database, \"Wait for CI\" on.",
}


def cmd_setup(args) -> int:
    root = Path(args.root).resolve()
    cfg_path = root / CONFIG
    if args.track and args.track not in READY_TRACKS:
        die(f"the {args.track} track's kit pieces (its stack list, size counts and deploy) aren't built yet, so setup "
            "stops here; nothing was written. Keep filing requests in chat; setup works once they land.")
    if cfg_path.exists() and not args.force:
        cfg = json.loads(cfg_path.read_text())
        print(f"{CONFIG} exists; keeping it (use --force to rebuild).")
    else:
        tpl_dir = Path(__file__).resolve().parent.parent / "templates"
        py = args.python_dir if args.python_dir is not None else detect_dir(root, ("requirements.txt", "pyproject.toml"))
        nd = args.node_dir if args.node_dir is not None else detect_dir(root, ("package.json",))
        py = None if py in ("", "none") else py
        nd = None if nd in ("", "none") else nd
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
    track = cfg.get("track")
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
        die("--data-source must be the tracker's collection://… URL from a Notion fetch")
    cfg["tracker"] = {"page": args.page or "", "database": args.database or "", "data_source": args.data_source}
    save_config(root, cfg)
    print(f"linked the tracker in {CONFIG}: {args.data_source}")
    return 0


# ---------------------------------------------------------------- report
def print_report(c: Contract, size: dict | None, stack: dict | None, left: dict | None, ci: bool = False,
                 security: list[str] | None = None, lesson: str | None | bool = False) -> str:
    lines = [f"Ship CTO check · contract {c.name} · base {c.base[:10]} · {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}"]
    overall = "PASS"
    if size:
        cats = size["categories"]
        lines.append(f"SIZE       {size['status']:4}  " + " · ".join(f"{k} {v['found']}/{v['declared']}" for k, v in cats.items()))
        for k, v in cats.items():
            if v["status"] != "FAIL":
                continue
            for it in v["extra"][:20]:
                lines.append(f"  extra {k[:-1]:9} {it}")
            if len(v["extra"]) > 20:
                lines.append(f"  … {len(v['extra']) - 20} more extra {k}")
            if not v["extra"]:
                lines.append(f"  {k}: {v['found']} built, {v['declared']} in the contract (all named ones match)")
        overall = "FAIL" if size["status"] == "FAIL" else overall
    if stack:
        np_, ui = stack["new_packages"], stack["unknown_imports"]
        lines.append(f"STACK      {stack['status']:4}  packages: {len(np_)} new · imports: {len(ui)} not in the stack")
        for p in np_:
            lines.append(f"  package   {p}   → owner approves in one line (stack-add) or remove it")
        for u in ui[:10]:
            lines.append(f"  import    {u}   → stack-add, an alias in ship.json, or remove it")
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
        overall = "FAIL" if left["status"] == "FAIL" else overall
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
        lines.append("RESULT: PASS — the piece may reach dev." if ci else
                     "RESULT: PASS — the piece may reach dev. Propose CLAUDE.md edits now (D33).")
    elif ci:
        lines.append("RESULT: FAIL — nothing deploys from this commit. Run /mg-ship-kit:cto-check in Claude Code, take the "
                     "way out, push again.")
    else:
        lines.append("RESULT: FAIL — fix the check, then run /mg-ship-kit:cto-check again. Something extra: client asked? "
                     "→ owner approves a contract change in one line; else delete it.")
    print("\n".join(lines))
    return overall


# ---------------------------------------------------------------- commands
def cmd_check(args) -> int:
    root = Path(args.root).resolve()
    cfg = load_config(root)
    c = active_contract(root, args.contract)
    if c and c.is_head:
        die(f"{c.name} is a chain head: it owns no code, so there is nothing to check on it. The check runs on "
            "its sub-pieces, one at a time (/mg-ship-kit:chain).", 2)
    if not c:
        heads = open_heads(list_contracts(root))
        if heads:
            print(f"ship: no piece is building. Chain {heads[0].name} is open: pick up its next sub-piece with "
                  "/mg-ship-kit:chain.", file=sys.stderr)
        else:
            print("ship: no contract is building (none with `Status: building` in contracts/). "
                  "Pick up the next Ready piece with /mg-ship-kit:next.", file=sys.stderr)
        return 3
    what = args.what
    size = count_size(root, cfg, c) if what in ("check", "size") else None
    stack = check_stack(root, cfg, c) if what in ("check", "stack") else None
    left = check_leftovers(root, cfg, c, getattr(args, "all", False)) if what in ("check", "leftovers") else None
    if args.json:
        print(json.dumps({"contract": c.name, "size": size, "stack": stack, "leftovers": left}, indent=2))
        return 1 if "FAIL" in [x["status"] for x in (size, stack, left) if x] else 0
    lesson = lesson_problem(root, c, None) if what == "check" else False
    return 0 if print_report(c, size, stack, left, lesson=lesson) == "PASS" else 1


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
    load_config(root)
    cs = list_contracts(root)
    busy = building_pieces(cs)
    if busy:
        die(f"{busy[0].name} is still building. One piece at a time: push it to dev (/mg-ship-kit:cto-check) "
            "or drop it before picking up the next.", 2)
    heads = open_heads(cs)
    if heads:
        die(f"chain {heads[0].name} is open (split, or building its sub-pieces). Finish it with /mg-ship-kit:chain, "
            "or drop it, before picking up another piece.", 2)
    head = git_out(root, "rev-parse", "--short=10", "HEAD")
    if not head:
        die("no commit yet. Make a first commit, then pick up the piece.")
    raw = notion_to_plain(Path(args.file).read_text(encoding="utf-8"))
    if field(raw, "Head"):
        die("this row is a chain's sub-piece (it has a `Head:` line). Sub-pieces are picked up by their chain "
            "(/mg-ship-kit:chain), never on their own.", 1)
    name, approved, body = contract_parts(raw, args.name)
    is_head = (field(raw, "Chain") or "").strip().lower() == "head"
    path = new_contract_path(root, name)
    header = [f"# Contract: {name}", "Status: building", f"Base: {head}", f"Approved: {approved}"]
    if is_head:
        header.append("Chain: head")
    if args.tracker:
        header.append(f"Tracker: {args.tracker}")
    path.write_text("\n".join(header) + "\n\n" + body, encoding="utf-8")
    try:
        c = Contract(path)
        c.check_ready()
        if is_head and c.count_problems():
            die("a chain head must name every item it counts, since the split goes by the names: " +
                "; ".join(c.count_problems()) + ". Fix the row in chat, then pick it up.", 1)
        reuse = reuse_lines(c.text)
        if c.is_head and c.fixes:
            die("a chain head can't carry a Fixes line: a bug fix is a piece, and its lesson rides with it (D77). "
                "Spec the fix as a piece in chat.", 1)
    except SystemExit:
        path.unlink(missing_ok=True)
        raise
    added = adopt_packages(root, reuse)
    print(f"saved {path.relative_to(root)} · Status: building · Base: {head}"
          + (" · a chain head: split it next (/mg-ship-kit:chain)" if is_head else ""))
    if reuse:
        print(f"reuse (D73): {sum(1 for r in reuse if r['verdict'] == 'adopt')} adopted, "
              f"{sum(1 for r in reuse if r['verdict'] == 'build')} to build"
              + (f"; added to the stack list in {CONFIG}: {', '.join(added)}. Commit {CONFIG} with the contract."
                 if added else "."))
    return 0


# ---------------------------------------------------------------- lessons (D76–D79)
KIT_REPO = "mgac-consulting/ship-kit"
KIT_ISSUE_RE = re.compile(rf"^https://github\.com/{re.escape(KIT_REPO)}/issues/\d+/?$")
LESSON_HOW = ("Ask \"what stops this next time?\" and record one answer with `ship_check.py lesson --contract <name>`: "
              "--test <a test file this piece adds or changes>, --fact \"<the exact CLAUDE.md line, on the owner's "
              "yes>\", or --kit <the link of a `lesson` issue on " + KIT_REPO + ">")


def claude_md_lines(root: Path, ref: str | None = "HEAD") -> set[str]:
    """CLAUDE.md's lines, list markers dropped: at a commit, or (ref None) as the file is on disk."""
    if ref is None:
        p = root / "CLAUDE.md"
        text = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
    else:
        r = sh(["git", "show", f"{ref}:CLAUDE.md"], cwd=root)
        text = r.stdout if r.returncode == 0 else ""
    return {re.sub(r"^\s*[-*]\s+", "", l).strip() for l in text.splitlines() if l.strip()}


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
        line = re.sub(r"^\s*[-*]\s+", "", value).strip()
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
        return f"this piece fixes a bug (\"{c.fixes}\") and has no Lesson line (D78). {LESSON_HOW}."
    kind, _, value = c.lesson.partition(" ")
    err = check_lesson(root, c, kind.lower(), value.strip(), ref)
    return f"Lesson: {err}. {LESSON_HOW}." if err else None


def cmd_lesson(args) -> int:
    """Record what stops a fixed bug next time (D76–D79), after checking it holds."""
    root = Path(args.root).resolve()
    c = find_contract(root, args.contract, ("building",), "building")
    if not c.fixes:
        die(f"{c.name} has no Fixes line: a lesson belongs to a bug fix (D77).")
    picked = [(k, v) for k, v in (("test", args.test), ("fact", args.fact), ("kit", args.kit)) if v]
    if len(picked) != 1:
        die("give exactly one of --test, --fact, --kit.")
    kind, value = picked[0][0], " ".join(picked[0][1].split())
    err = check_lesson(root, c, kind, value, None)
    if err:
        die(f"not recorded: {err}.", 1)
    c.set_status(c.status, {"Lesson": f"{kind} {value}"})
    print(f"{c.name}: Lesson: {kind} {value}. Commit the contract with the fix.")
    return 0


# ---------------------------------------------------------------- the reuse block (D73, D74)
REUSE_ADOPT_RE = re.compile(r"^(?P<cap>[^:]+?):\s*adopt\s+(?P<pkg>[A-Za-z0-9@][\w.@/-]*)\s*\(\s*(?P<side>python|node)\s*,"
                            r"\s*(?P<lic>[^)]+?)\s*\)\s*(?:[—–-]+\s*ok:\s*(?P<ok>.+))?$", re.I)
REUSE_BUILD_RE = re.compile(r"^(?P<cap>[^:]+?):\s*build\b\s*(?:[—–-]+\s*(?P<why>.+))?$", re.I)


def licence_key(lic: str) -> str:
    """'MIT License' → 'mit', 'Apache 2.0' → 'apache-2.0', 'BSD 3-Clause' → 'bsd-3-clause'."""
    s = re.sub(r"\b(license|licence)\b", "", lic.lower())
    return re.sub(r"[\s_]+", "-", s.strip()).strip("-")


def permissive_licences() -> set[str]:
    return {licence_key(x) for x in json.loads((kit_root() / "reference" / "licences.json").read_text())["permissive"]}


def reuse_lines(text: str) -> list[dict]:
    """The contract's `## Reuse` block, checked: each line adopts a package (python or node, with its licence) or
    says build. A licence that isn't on the kit's permissive list needs the owner's words (`— ok: <reason>`)."""
    sec = re.search(r"^#{1,4}\s*Reuse\s*$(.*?)(?=^#{1,4}\s|\Z)", text, re.M | re.S)
    if not sec:
        return []
    ok_list, out, problems = permissive_licences(), [], []
    for line in sec.group(1).splitlines():
        b = re.match(r"^\s*[-*]\s+(.+?)\s*$", line)
        if not b:
            continue
        item = re.sub(r"`|\*\*", "", b.group(1)).strip()
        if PLACEHOLDER_RE.search(item):  # the template's example line: no package name has <…>
            continue
        m = REUSE_ADOPT_RE.match(item)
        if m:
            lic, ok = m.group("lic").strip(), (m.group("ok") or "").strip()
            alts = [licence_key(x) for x in re.split(r"\s+or\s+|\s*/\s*", lic, flags=re.I) if x.strip()]
            if not any(k in ok_list for k in alts) and not ok:  # a dual licence passes when either side does
                problems.append(f"{m.group('pkg')} is under {lic}, which isn't on the kit's permissive list: it needs "
                                "the owner's words on its line (\"— ok: <reason>\")")
            out.append({"verdict": "adopt", "capability": m.group("cap").strip(), "package": m.group("pkg").lower(),
                        "side": m.group("side").lower(), "licence": lic, "ok": ok})
            continue
        m = REUSE_BUILD_RE.match(item)
        if m:
            out.append({"verdict": "build", "capability": m.group("cap").strip(), "why": (m.group("why") or "").strip()})
            continue
        problems.append(f"can't read the Reuse line {item!r}: write \"<capability>: adopt <package> (python|node, "
                        "<licence>)\" or \"<capability>: build — <why>\"")
    if problems:
        die("the contract's Reuse block (D73, D74): " + "; ".join(problems) + ". Fix the row in chat, then pick it "
            "up.", 1)
    return out


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
    m = re.search(r"^#\s*Contract:\s*(.+?)\s*$", raw, re.M)
    name = (name or (m.group(1) if m else "")).strip()
    if not name:
        die("the piece has no name: pass --name \"<piece>\" (the tracker row's title)")
    approved = (field(raw, "Approved") or "").strip()
    if need_approval and not is_approval(approved):
        die("the tracker row has no `Approved: <date> by <owner>` line. A piece is Ready only after the owner "
            "approved its contract in one line; fix the row in chat, then pick it up.", 1)
    body_lines, in_header = [], True
    header_re = re.compile(r"^\**(" + "|".join(HEADER_KEYS) + r")\**:")
    for line in raw.splitlines():
        s = line.strip()
        if BANNER_MARK.lower() in s.lower():
            continue
        if in_header and (s.startswith("## ") or WORDS_LABEL_RE.match(s)):
            in_header = False
        if in_header and (re.match(r"^#\s*Contract:", s) or header_re.match(s) or not s):
            continue
        body_lines.append(line)
    return name, approved, "\n".join(body_lines).strip() + "\n"


def new_contract_path(root: Path, name: str) -> Path:
    nums = [int(p.name[:3]) for p in contracts_dir(root).glob("[0-9][0-9][0-9]-*.md")]
    num = (max(nums) + 1) if nums else 1
    contracts_dir(root).mkdir(exist_ok=True)
    return contracts_dir(root) / f"{num:03d}-{slugify(name)}.md"


# ---------------------------------------------------------------- chains (D61)
def head_named(root: Path, name: str | None, what: str) -> tuple[Contract, list[Contract]]:
    """The head contract named, or the only open one, with its sub-pieces."""
    cs = list_contracts(root)
    if name:
        hits = [c for c in cs if c.name == name or c.path.name == name or c.name.startswith(name)]
        if not hits:
            die(f"contract {name!r} not found in {CONTRACTS}/")
        if not hits[0].is_head:
            die(f"{hits[0].name} is not a chain head (no `Chain: head` line).")
        return hits[0], subs_of(cs, hits[0])
    heads = open_heads(cs)
    if not heads:
        die(f"no chain is open (no head contract is building), so there is nothing to {what}. "
            "Pick a head up first: /mg-ship-kit:chain.", 3)
    if len(heads) > 1:
        die(f"several chains are open ({', '.join(c.name for c in heads)}): pass --head <name>.")
    return heads[0], subs_of(cs, heads[0])


def partition_problems(head: Contract, subs: list[tuple[str, Contract]]) -> list[str]:
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
                    problems.append(f"{label}: {kind[:-1]} {it} is " + ("already in another sub-piece" if taken else
                                                                         f"not in the head's Size list"))
                else:
                    free.remove(hit)
        for d in free:
            problems.append(f"{kind[:-1]} {d} is in the head's Size list but in no sub-piece")
        if total != head_n:
            problems.append(f"{kind}: the sub-pieces count {total}, the head counts {head_n}")
    return problems


def cmd_split(args) -> int:
    """Save the sub-contracts Claude wrote for a head as draft contracts, checked against the head (the split stop)."""
    root = Path(args.root).resolve()
    load_config(root)
    head, subs = head_named(root, args.head, "split")
    if head.status != "building":
        die(f"{head.name} is {head.status}; a head is split right after pickup, while it is building.", 1)
    if subs:
        die(f"{head.name} is already split into {len(subs)} sub-pieces ({', '.join(c.name for c in subs)}). "
            "To split it differently, drop the chain first.", 1)
    if not 2 <= len(args.files) <= MAX_SUBS:
        die(f"a chain is two to {MAX_SUBS} sub-pieces ({len(args.files)} given). One piece is just a piece; more than "
            f"{MAX_SUBS} is two chains: spec it as such in chat.", 1)
    written: list[Path] = []
    parsed: list[tuple[str, Contract]] = []
    names: set[str] = set()
    try:
        for f in args.files:
            p = Path(f)
            if not p.is_file():
                die(f"{f}: not a file")
            name, _, body = contract_parts(p.read_text(encoding="utf-8"), need_approval=False)
            if name.lower() in names:
                die(f"two sub-pieces are named {name!r}; names must differ.")
            names.add(name.lower())
            m = re.search(r"^#{1,4}\s*How to check it\s*$\s*\n\s*[-*]\s+(\S.*?)\s*$", body, re.M | re.I)
            if not m or PLACEHOLDER_RE.fullmatch(m.group(1).strip()):
                die(f"{name}: no `## How to check it` line. Each sub-piece needs at least one check the chain can "
                    "halt on.", 1)
            path = new_contract_path(root, name)
            header = [f"# Contract: {name}", "Status: draft", f"Head: {head.name}", f"Approved: {GO_PENDING}"]
            path.write_text("\n".join(header) + "\n\n" + body, encoding="utf-8")
            written.append(path)
            parsed.append((name, Contract(path)))
        problems = partition_problems(head, parsed)
        if problems:
            die(f"the split doesn't match the head {head.name}:\n  " + "\n  ".join(problems) +
                "\nFix the sub-contracts and split again. A sub-piece names only what the head names, each item once.", 1)
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
        die(f"{head.name} is {head.status}; the go belongs to a chain that is building.", 1)
    drafts = [c for c in subs if c.status == "draft"]
    if not subs:
        die(f"{head.name} isn't split yet. Split it first.", 1)
    if not drafts:
        die(f"{head.name}: every sub-piece is past the go already.", 1)
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
        die(f"{busy[0].name} is still building. One piece at a time: push it to dev (/mg-ship-kit:cto-check) "
            "or drop it, then continue the chain.", 2)
    if not subs:
        die(f"{head.name} isn't split yet. Split it first.", 1)
    if any(c.status == "draft" for c in subs):
        die(f"{head.name} waits for the owner's go: they read the sub-pieces, then `go --head {head.name}`.", 1)
    ready = [c for c in subs if c.status == "ready"]
    if not ready:
        return cmd_chain_sync(args)
    if any(c.status in ("on-dev", "done") for c in subs) and not args.green:
        dev = "refs/remotes/origin/dev"
        if not is_commit(root, dev):
            die("origin/dev not found, so the last sub-piece's check can't be confirmed. Fetch, then continue.", 2)
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
        die(f"{args.sha!r} is not a commit here")
    return wait_for_ci(root, sha, args.timeout, args.poll)


def is_bookkeeping(f: str, cfg: dict | None = None) -> bool:
    """Files that carry no product code: contract states, kit setup, rules, CI files, the readme, plus any
    paths the owner listed under `bookkeeping` in ship.json (a folder ends with '/'; globs allowed).
    The push gate and the GitHub check use this one list."""
    name = f.rsplit("/", 1)[-1].lower()
    if (f.startswith(CONTRACTS + "/") or f in BOOKKEEPING_FILES or f.startswith(".github/")
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
            die(f"{after[:10]} is not a commit here: check out with fetch-depth 0.")
        opts, what = ci_scan_range(root, branch, before, rev(root, after)), f"the commits pushed to {branch or 'this branch'}"
    else:
        if not is_commit(root, args.ref):
            die(f"{args.ref!r} is not a commit here")
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
        die("give the fingerprint exactly as the secret scan printed it (commit:file:rule:line).")
    if not who or not why:
        die("--by and --why are the owner's name and their words.")
    p = root / GITLEAKS_IGNORE
    lines = p.read_text(encoding="utf-8").splitlines() if p.exists() else []
    if fp in (l.strip() for l in lines):
        print(f"already allowed: {fp}")
        return 0
    lines += [f"{ALLOW_MARK}{dt.date.today().isoformat()} by {who}: {why}", fp]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"allowed: {fp}. Commit {GITLEAKS_IGNORE} with your next commit; the scan skips this finding from now on.")
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
        die(f"{ref} not found. Push to {args.branch} first (or `git fetch origin {args.branch}`).", 1)
    if sh(["git", "merge-base", "--is-ancestor", "HEAD", ref], cwd=root).returncode != 0:
        die(f"this commit isn't on origin/{args.branch} yet. Push it first; the push gate runs the check.", 1)
    porcelain = sh(["git", "status", "--porcelain"], cwd=root).stdout  # not stripped: column 1 matters
    dirty = [l[3:] for l in porcelain.splitlines() if len(l) > 3 and not l[3:].strip('"').startswith(CONTRACTS + "/")]
    if dirty:
        die(f"uncommitted changes ({', '.join(dirty[:5])}{' …' if len(dirty) > 5 else ''}) aren't on {args.branch}. "
            "Commit and push them, or remove them, then run ondev again.", 1)
    code = [f for f in git_out(root, "diff", "--name-only", c.base, "HEAD").splitlines() if f and not is_bookkeeping(f, cfg)]
    if not code:
        die(f"{c.name} has no product code on {args.branch} yet (only bookkeeping since its base), so it stays building.", 1)
    size, stack = count_size(root, cfg, c), check_stack(root, cfg, c)
    left = check_leftovers(root, cfg, c, False)
    failed = [n for n, r in (("size", size), ("stack", stack), ("leftovers", left)) if r["status"] == "FAIL"]
    if review_problems(root, cfg, c, "HEAD"):
        failed.append("security review")
    if failed:
        die(f"{c.name}: the check fails now ({', '.join(failed)}), so it stays building. Run /mg-ship-kit:cto-check.", 1)
    if c.removing:
        c.set_status("dropped")
        print(f"{c.name}: Status: dropped (its code is removed from {args.branch})")
    elif c.head:
        c.set_status("on-dev")
        print(f"{c.name}: Status: on-dev (a sub-piece of {c.head}; the chain goes on with its next sub-piece)")
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
        die(f"{c.name} is a sub-piece of {c.head}: the client's verdict is on the head, not on its parts. "
            f"Run done --contract {c.head} once the whole chain is accepted.", 1)
    if c.status != "on-dev":
        die(f"{c.name} is {c.status}. Only a piece on dev, accepted by the client, can be done.", 1)
    subs = subs_of(list_contracts(root), c) if c.is_head else []
    if c.is_head:
        want, why = chain_state(c, subs)
        if want != "on-dev":
            die(f"{c.name} can't be done: {why}. The verdict covers the whole chain, so every sub-piece must be "
                "on dev first.", 1)
    c.set_status("done")
    print(f"{c.name}: Status: done")
    for s in subs:
        if s.status == "on-dev":
            s.set_status("done")
            print(f"{s.name}: Status: done (with the head)")
    return 0


def cmd_drop(args) -> int:
    root = Path(args.root).resolve()
    c = find_contract(root, args.contract, ("building", "on-dev"), "drop")
    if c.is_head:
        return drop_head(root, c)
    if c.status in ("done", "dropped", "draft", "ready"):
        die(f"{c.name} is {c.status}; only a building or on-dev piece can be dropped.", 1)
    if c.status == "building" and c.removing:
        die(f"{c.name} is already being removed: delete its code, run /mg-ship-kit:cto-check, push to dev.", 1)
    if c.status == "building":
        # never reached dev: its code must be gone from the working tree before the contract closes
        changed = [f for f in git_changes(root, c.base) if not f.startswith(CONTRACTS + "/")]
        if changed:
            die(f"{c.name}'s code is still here ({len(changed)} files changed since its base, e.g. {changed[0]}). "
                "Delete it first, then run drop again.", 1)
        c.set_status("dropped")
        print(f"{c.name}: Status: dropped (it never reached dev)")
        if c.head:
            sync_head_of(root, c)
        return 0
    others = building_pieces(list_contracts(root))
    if others:
        die(f"{others[0].name} is building. Push it to dev or drop it first; one piece at a time.", 1)
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
        die(f"{head.name} is {head.status}; only an open or on-dev chain can be dropped.", 1)
    if built:
        die(f"{head.name} has built sub-pieces: {', '.join(f'{c.name} ({c.status})' for c in built)}. Drop them one "
            "at a time, the last one first (each on-dev one becomes a removal); the head becomes dropped when the "
            "last one does.", 1)
    changed = [f for f in git_changes(root, head.base) if not f.startswith(CONTRACTS + "/")]
    if changed:
        die(f"code was written since {head.name} was picked up ({len(changed)} files, e.g. {changed[0]}), though no "
            "sub-piece was building. Delete it first, then run drop again.", 1)
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


def review_stamp(blobs: dict[str, str]) -> str:
    """One short id for exactly this code: any change to a product file the piece touched gives a new stamp."""
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
    if r.stamp != review_stamp(blobs):
        out.append(f"the code changed after the security review ({rel} reviewed other code). Run the review again "
                   "(after a fix, the checker reruns the proofs and review-write stamps it).")
    why = review_scope(root, cfg, c, blobs, ref)
    if r.skipped and why:
        out.append(f"{rel} is a skip note, but the piece touches risky files: {short_list(why, 5)}. Run the review.")
    for f in r.blocking():
        out.append(f"{f['id']} · {f['severity']} · {f['status']}: {f['what'] or '(no text)'} → fix it until its proof "
                   "passes, or the owner waives it in one line")
    for f in r.findings:
        if f["status"] == "waived" and not is_approval(f["waiver"]):
            out.append(f"{f['id']} is waived with no Waiver line (date, the owner's name and why).")
        if f["status"] in ("open", "fixed") and not f["proof"]:
            out.append(f"{f['id']} is {f['status']} with no Proof line: only reproduced findings count.")
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
        die(f"ship.json spend {level!r} must be one of {', '.join(SPEND_LEVELS)}")
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
        die("no contract is building, so there is nothing to review.", 3)
    if c.is_head:
        die(f"{c.name} is a chain head: it owns no code. Each sub-piece is reviewed on its own.")
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
            "stamp": review_stamp(blobs)}
    print(json.dumps(plan, indent=2))
    return 0


def cmd_review_skip(args) -> int:
    root = Path(args.root).resolve()
    cfg, c = review_target(root, args)
    blobs = piece_files(root, cfg, c, None)
    why = review_scope(root, cfg, c, blobs, None)
    if why:
        die(f"this piece touches risky files, so it needs the review, not a skip note: {short_list(why, 5)}", 1)
    p = write_review(root, c, render_review(c, review_stamp(blobs), "skipped: no risky files", "none", []))
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
    blobs = piece_files(root, cfg, c, None)
    p = write_review(root, c, render_review(c, review_stamp(blobs), "reviewed", spend, findings))
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
        die(f"{c.name} has no review yet.")
    hit = next((f for f in r.findings if f["id"] == args.finding), None)
    if hit is None:
        die(f"{c.name}'s review has no finding {args.finding}.")
    if hit["status"] not in ("open", "unchecked"):
        die(f"{args.finding} is {hit['status']}; only an open finding can be waived.")
    if not args.by.strip() or not args.why.strip():
        die("a waiver needs the owner's name (--by) and their reason in their words (--why)")
    hit["status"], hit["waiver"] = "waived", f"{dt.date.today().isoformat()}, {args.by.strip()}: {' '.join(args.why.split())}"
    write_review(root, c, render_review(c, r.stamp, r.scope, r.spend, r.findings))
    print(f"{args.finding} waived by {args.by.strip()}. It shows on the tracker row and in the release note.")
    return 0


def cmd_review_status(args) -> int:
    root = Path(args.root).resolve()
    cfg = load_config(root)
    c = find_contract(root, args.contract, ("building", "on-dev"), "show") if args.contract else active_contract(root, None)
    if not c:
        die("no contract is building.", 3)
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
        rules["bookkeeping"] = []
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


def dev_verdict(root: Path, cfg: dict, since: str, how: str, ci: bool = False) -> int:
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
        print("bookkeeping only (contracts, ship.json, CLAUDE.md, .gitleaksignore, .claude/settings.json, CI files, readme): nothing to check.")
        return 0
    all_cs = list_contracts(root)
    building = building_pieces(all_cs)
    if len(building) > 1:
        print("more than one contract is building: " + ", ".join(c.name for c in building) +
              ". One piece at a time: drop the extra one.")
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
                  "code while its contract is building.")
            return 1
    size, stack = count_size(root, cfg, c), check_stack(root, cfg, c)
    left = check_leftovers(root, cfg, c, False)
    sec = review_problems(root, cfg, c, "HEAD")
    return 0 if print_report(c, size, stack, left, ci=ci, security=sec, lesson=lesson_problem(root, c)) == "PASS" else 1


def cmd_gate_dev(args) -> int:
    """The push gate's rule for dev. Without --since it starts from what is already on origin/dev."""
    root = Path(args.root).resolve()
    cfg = load_config(root)
    if args.since:
        if args.since != EMPTY_TREE and not is_commit(root, args.since):
            die(f"--since {args.since!r} is not a commit here")
        since, how = (args.since if args.since == EMPTY_TREE else rev(root, args.since)), "given with --since"
    elif is_commit(root, "refs/remotes/origin/dev"):
        since, how = rev(root, "refs/remotes/origin/dev"), "what is already on origin/dev"
    else:
        since, how = fallback_since(root, cfg)
    return dev_verdict(root, cfg, since, how)


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
        die(f"couldn't ask GitHub which commits passed the check ({err}). The workflow needs `permissions: "
            "actions: read`. Re-run the check.")
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
    start = None
    if before and before != ZERO_SHA and is_commit(root, before):
        start = rev(root, before) if is_ancestor(root, before, "HEAD") else git_out(root, "merge-base", before, "HEAD")
    if start and gh.ready:
        for sha in git_out(root, "rev-list", "--first-parent", "--max-count=50", start).split():
            if gh.verdict(sha) == "passed":
                return sha, "the newest commit the check passed on"
    elif start:
        if in_actions():
            die("no GITHUB_TOKEN, so the check can't tell which commits passed. Use the kit's workflow, which "
                "passes it.")
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
        die(f"check out the pushed commit ({after[:10]}) first; the check reads the working tree.")
    gh = GitHub(offline=args.offline)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print(f"Ship check · kit {KIT_VERSION} · {branch or '(no branch)'} · {rev(root, 'HEAD')[:10]}")
        if branch == "dev":
            if args.since:
                since, how = (args.since if args.since == EMPTY_TREE else rev(root, args.since)), "given with --since"
            else:
                since, how = ci_since(root, cfg, args.before or os.environ.get("SHIP_BEFORE", ""), gh)
            code = dev_verdict(root, cfg, since, how, ci=True)
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
        die("the CI templates aren't next to this script. Run setup from the plugin, not from the project's CI copy.")
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
    i = next((n for n, l in enumerate(out) if l.strip() == KIT_SECTION), None)
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
             "kind": c.kind, "head": c.head} for c in list_contracts(root)]
    if args.json:
        cfg = json.loads((root / CONFIG).read_text()) if (root / CONFIG).exists() else {}
        print(json.dumps({"tracker": cfg.get("tracker"), "contracts": rows}, indent=2))
        return 0
    if not rows:
        print("no contracts yet")
    for r in rows:
        tag = " (removing)" if r["removing"] else (" (head)" if r["kind"] == "head" else (f" (sub of {r['head']})" if r["head"] else ""))
        print(f"{r['contract']:40} {r['status'] + tag:30} {r['tracker'] or '(no tracker row)'}")
    return 0


def cmd_copy_check(args) -> int:
    root = Path(args.root).resolve()
    c = find_contract(root, args.contract, ("building", "on-dev"), "compare")  # any state when named
    notion_h = copy_hash(Path(args.notion).read_text(encoding="utf-8"))
    repo_h = copy_hash(c.text)
    stored = load_sync(root).get(c.name)
    if notion_h == repo_h:
        print("in-sync")
        return 0
    if stored is None:
        print("no-record: the tracker row doesn't hold a copy Claude Code wrote yet (first pickup).")
        return 11
    if notion_h == stored:
        print("refresh: the repo file changed since the last copy; write the new copy.")
        return 10
    print("hand-edited: the tracker's copy differs from the last copy Claude Code wrote. "
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ship_check.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".", help="project root (default: current directory)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("setup"); s.add_argument("--python-dir"); s.add_argument("--node-dir"); s.add_argument("--force", action="store_true")
    s.add_argument("--no-default-stack", action="store_true", help="don't fall back to the kit's default stack in an empty repo")
    s.add_argument("--track", choices=TRACKS, help="the project's track, from the Track line in its Facts")
    sub.add_parser("kit-mark", help="record that the project page's Kit line names this plugin version")
    p = sub.add_parser("link"); p.add_argument("--data-source", required=True); p.add_argument("--database"); p.add_argument("--page")
    p = sub.add_parser("gate-dev"); p.add_argument("--since", help="start from this commit (default: origin/dev)")
    p = sub.add_parser("ci"); p.add_argument("--branch"); p.add_argument("--after"); p.add_argument("--before")
    p.add_argument("--since", help="start from this commit instead of asking GitHub (dev only)")
    p.add_argument("--offline", action="store_true", help="don't call the GitHub API")
    p.add_argument("--wait", type=int, default=600, help="seconds a release waits for a running dev check")
    sub.add_parser("ci-env"); sub.add_parser("ci-install")
    p = sub.add_parser("pickup"); p.add_argument("--file", required=True); p.add_argument("--name"); p.add_argument("--tracker")
    p = sub.add_parser("split", help="save a head's sub-contracts as draft sub-pieces (the split stop)")
    p.add_argument("--head", help="the head contract (default: the only open one)")
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
    p = sub.add_parser("drop"); p.add_argument("--contract")
    p = sub.add_parser("status"); p.add_argument("--json", action="store_true")
    p = sub.add_parser("copy-check"); p.add_argument("--contract"); p.add_argument("--notion", required=True)
    p = sub.add_parser("copy-mark"); p.add_argument("--contract")
    p = sub.add_parser("copy-render"); p.add_argument("--contract")
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
    handlers = {"done": cmd_done, "link": cmd_link, "pickup": cmd_pickup, "ondev": cmd_ondev, "drop": cmd_drop,
                "status": cmd_status, "copy-check": cmd_copy_check, "copy-mark": cmd_copy_mark,
                "copy-render": cmd_copy_render, "gate-dev": cmd_gate_dev, "ci": cmd_ci, "ci-env": cmd_ci_env,
                "ci-install": cmd_ci_install, "env-check": cmd_env_check, "split": cmd_split, "go": cmd_go,
                "chain-next": cmd_chain_next, "chain-sync": cmd_chain_sync, "chain-status": cmd_chain_status,
                "ci-wait": cmd_ci_wait, "set-tracker": cmd_set_tracker, "kit-mark": cmd_kit_mark,
                "review-plan": cmd_review_plan, "review-skip": cmd_review_skip, "review-write": cmd_review_write,
                "review-waive": cmd_review_waive, "review-status": cmd_review_status,
                "review-waivers": cmd_review_waivers, "secret-scan": cmd_secret_scan,
                "secret-allow": cmd_secret_allow, "lesson": cmd_lesson}
    if args.cmd in handlers:
        return handlers[args.cmd](args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
