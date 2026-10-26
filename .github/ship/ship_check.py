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

A contract moves draft/ready → building → on-dev → done, or → dropped.
Exit codes: 0 pass · 1 fail · 2 usage, contract or tool error · 3 no contract building (and product code changed).
copy-check exit codes: 0 in-sync · 10 refresh · 11 no-record · 12 hand-edited.
Only python3 is required. vulture and knip are needed for `leftovers`.

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
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

KIT_VERSION = "0.3.2"  # keep equal to plugins/ship/.claude-plugin/plugin.json
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
BOOKKEEPING_FILES = ("ship.json", "CLAUDE.md", ".gitignore")
ENV_EXAMPLES = (".env.example", ".env.sample", ".env.template")  # env files that hold no secrets: these may be committed
GITIGNORE_ENV = [".env", ".env.*"] + [f"!{n}" for n in ENV_EXAMPLES]  # the lines setup adds to .gitignore
# The words line that opens a contract's body; its four labels follow the Backlog's Source (ship-spec).
WORDS_LABEL_RE = re.compile(r"^\**(client['’]s words|from my notes on the client|users['’] words|owner['’]s words)\b", re.I)
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
        die(f"{CONFIG} not found in {root}. Run `/ship:setup` first.")
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
        self.size: dict[str, tuple[int, list[str]]] = {}
        self._parse_size()

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
            item = re.sub(r"[`*]", "", b.group(1)).strip() if b else ""
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
        if not self.approved or PLACEHOLDER_RE.search(self.approved):
            die(f"contract {self.name}: `Approved:` must carry the date and the owner's name — "
                "a contract is building only after the owner approved it in one line")


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


def active_contract(root: Path, name: str | None) -> Contract | None:
    cs = list_contracts(root)
    if name:
        for c in cs:
            if c.name == name or c.path.name == name or c.name.startswith(name):
                c.check_ready()
                return c
        die(f"contract {name!r} not found in {CONTRACTS}/")
    building = [c for c in cs if c.status == "building"]
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
        print("CLAUDE.md exists; left untouched. Compare it with the kit template by hand.")
    for name, side, hint in (("vulture", "python_dir", "pip install vulture==2.16   (inside the backend's venv)"),
                             ("knip", "node_dir", "npm i -D knip           (inside the frontend)")):
        if cfg.get(side) is None:
            continue
        if not dir_path(root, cfg[side]).exists():
            print(f"{name}: needed once {cfg[side]}/ exists → {hint}")
            continue
        print(f"{name}: {'found' if find_tool(root, cfg, name) else 'MISSING → ' + hint}")
    changed = install_ci(root)
    print(f"CI: the Ship check runs on GitHub on every push to dev and main ({CI_WORKFLOW}); "
          + (f"wrote {', '.join(changed)}" if changed else "files up to date") + f" (kit {KIT_VERSION})")
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
def print_report(c: Contract, size: dict | None, stack: dict | None, left: dict | None, ci: bool = False) -> str:
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
    if overall == "PASS":
        lines.append("RESULT: PASS — the piece may reach dev." if ci else
                     "RESULT: PASS — the piece may reach dev. Propose CLAUDE.md edits now (D33).")
    elif ci:
        lines.append("RESULT: FAIL — nothing deploys from this commit. Run /ship:cto-check in Claude Code, take the "
                     "way out, push again.")
    else:
        lines.append("RESULT: FAIL — fix the check, then run /ship:cto-check again. Something extra: client asked? "
                     "→ owner approves a contract change in one line; else delete it.")
    print("\n".join(lines))
    return overall


# ---------------------------------------------------------------- commands
def cmd_check(args) -> int:
    root = Path(args.root).resolve()
    cfg = load_config(root)
    c = active_contract(root, args.contract)
    if not c:
        print("ship: no contract is building (none with `Status: building` in contracts/). "
              "Pick up the next Ready piece with /ship:next.", file=sys.stderr)
        return 3
    what = args.what
    size = count_size(root, cfg, c) if what in ("check", "size") else None
    stack = check_stack(root, cfg, c) if what in ("check", "stack") else None
    left = check_leftovers(root, cfg, c, getattr(args, "all", False)) if what in ("check", "leftovers") else None
    if args.json:
        print(json.dumps({"contract": c.name, "size": size, "stack": stack, "leftovers": left}, indent=2))
        return 1 if "FAIL" in [x["status"] for x in (size, stack, left) if x] else 0
    return 0 if print_report(c, size, stack, left) == "PASS" else 1


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
    busy = [c for c in cs if c.status == "building"]
    if busy:
        die(f"{busy[0].name} is still building. One piece at a time: push it to dev (/ship:cto-check) "
            "or drop it before picking up the next.", 2)
    head = git_out(root, "rev-parse", "--short=10", "HEAD")
    if not head:
        die("no commit yet. Make a first commit, then pick up the piece.")
    raw = notion_to_plain(Path(args.file).read_text(encoding="utf-8"))
    m = re.search(r"^#\s*Contract:\s*(.+?)\s*$", raw, re.M)
    name = (args.name or (m.group(1) if m else "")).strip()
    if not name:
        die("the piece has no name: pass --name \"<piece>\" (the tracker row's title)")
    approved = (field(raw, "Approved") or "").strip()
    if not approved or PLACEHOLDER_RE.search(approved):
        die("the tracker row has no `Approved: <date> by <owner>` line. A piece is Ready only after the owner "
            "approved its contract in one line; fix the row in chat, then pick it up.", 1)
    # body = everything after the header lines; drop the banner and any header the row carried
    body_lines, in_header = [], True
    for line in raw.splitlines():
        s = line.strip()
        if BANNER_MARK.lower() in s.lower():
            continue
        if in_header and (s.startswith("## ") or WORDS_LABEL_RE.match(s)):
            in_header = False
        if in_header and (re.match(r"^#\s*Contract:", s) or re.match(r"^\**(Status|Base|Approved|Tracker|Removing)\**:", s) or not s):
            continue
        body_lines.append(line)
    body = "\n".join(body_lines).strip() + "\n"
    nums = [int(p.name[:3]) for p in contracts_dir(root).glob("[0-9][0-9][0-9]-*.md")]
    num = (max(nums) + 1) if nums else 1
    contracts_dir(root).mkdir(exist_ok=True)
    path = contracts_dir(root) / f"{num:03d}-{slugify(name)}.md"
    header = [f"# Contract: {name}", "Status: building", f"Base: {head}", f"Approved: {approved}"]
    if args.tracker:
        header.append(f"Tracker: {args.tracker}")
    path.write_text("\n".join(header) + "\n\n" + body, encoding="utf-8")
    try:
        Contract(path).check_ready()
    except SystemExit:
        path.unlink(missing_ok=True)
        raise
    print(f"saved {path.relative_to(root)} · Status: building · Base: {head}")
    return 0


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
    if failed:
        die(f"{c.name}: the check fails now ({', '.join(failed)}), so it stays building. Run /ship:cto-check.", 1)
    if c.removing:
        c.set_status("dropped")
        print(f"{c.name}: Status: dropped (its code is removed from {args.branch})")
    else:
        c.set_status("on-dev")
        print(f"{c.name}: Status: on-dev (the client tests it on {args.branch}; the next piece may start)")
    return 0


def cmd_done(args) -> int:
    root = Path(args.root).resolve()
    c = find_contract(root, args.contract, ("on-dev",), "mark done")
    if c.status != "on-dev":
        die(f"{c.name} is {c.status}. Only a piece on dev, accepted by the client, can be done.", 1)
    c.set_status("done")
    print(f"{c.name}: Status: done")
    return 0


def cmd_drop(args) -> int:
    root = Path(args.root).resolve()
    c = find_contract(root, args.contract, ("building", "on-dev"), "drop")
    if c.status in ("done", "dropped", "draft", "ready"):
        die(f"{c.name} is {c.status}; only a building or on-dev piece can be dropped.", 1)
    if c.status == "building" and c.removing:
        die(f"{c.name} is already being removed: delete its code, run /ship:cto-check, push to dev.", 1)
    if c.status == "building":
        # never reached dev: its code must be gone from the working tree before the contract closes
        changed = [f for f in git_changes(root, c.base) if not f.startswith(CONTRACTS + "/")]
        if changed:
            die(f"{c.name}'s code is still here ({len(changed)} files changed since its base, e.g. {changed[0]}). "
                "Delete it first, then run drop again.", 1)
        c.set_status("dropped")
        print(f"{c.name}: Status: dropped (it never reached dev)")
        return 0
    others = [x for x in list_contracts(root) if x.status == "building"]
    if others:
        die(f"{others[0].name} is building. Push it to dev or drop it first; one piece at a time.", 1)
    head = git_out(root, "rev-parse", "--short=10", "HEAD")
    c.set_status("building", {"Base": head,
                              "Removing": f"{dt.date.today().isoformat()}, the client rejected it; built from {c.base}"})
    print(f"{c.name}: removing. Delete its code, run /ship:cto-check (nothing may be added), push to dev; "
          "it becomes dropped when the push lands.")
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
    for key in ("python_dir", "node_dir", "bookkeeping"):
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
        print("bookkeeping only (contracts, ship.json, CLAUDE.md, CI files, readme): nothing to check.")
        return 0
    building = [c for c in list_contracts(root) if c.status == "building"]
    if len(building) > 1:
        print("more than one contract is building: " + ", ".join(c.name for c in building) +
              ". One piece at a time: drop the extra one.")
        return 1
    if not building:
        print(f"product code changed and no contract is building, so no check covers it: {short_list(code)}. "
              "Every change belongs to a piece (D1): pick one up with /ship:next, or remove the change.")
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
    return 0 if print_report(c, size, stack, left, ci=ci) == "PASS" else 1


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


def ci_release(root: Path, gh: GitHub, wait_s: int) -> int:
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
        elif branch in ("main", "master"):
            code = ci_release(root, gh, args.wait)
        else:
            print("not dev, main or master: nothing to check.")
            code = 0
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
    return [(tpl / "ship-check.yml", CI_WORKFLOW), (Path(__file__).resolve(), CI_SCRIPT), (tpl / "README.md", CI_NOTES)]


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
             "base": c.base, "size": size_line(c), "file": str(c.path.relative_to(root))} for c in list_contracts(root)]
    if args.json:
        cfg = json.loads((root / CONFIG).read_text()) if (root / CONFIG).exists() else {}
        print(json.dumps({"tracker": cfg.get("tracker"), "contracts": rows}, indent=2))
        return 0
    if not rows:
        print("no contracts yet")
    for r in rows:
        print(f"{r['contract']:40} {r['status'] + (' (removing)' if r['removing'] else ''):20} {r['tracker'] or '(no tracker row)'}")
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
    p = sub.add_parser("link"); p.add_argument("--data-source", required=True); p.add_argument("--database"); p.add_argument("--page")
    p = sub.add_parser("gate-dev"); p.add_argument("--since", help="start from this commit (default: origin/dev)")
    p = sub.add_parser("ci"); p.add_argument("--branch"); p.add_argument("--after"); p.add_argument("--before")
    p.add_argument("--since", help="start from this commit instead of asking GitHub (dev only)")
    p.add_argument("--offline", action="store_true", help="don't call the GitHub API")
    p.add_argument("--wait", type=int, default=600, help="seconds a release waits for a running dev check")
    sub.add_parser("ci-env"); sub.add_parser("ci-install")
    p = sub.add_parser("pickup"); p.add_argument("--file", required=True); p.add_argument("--name"); p.add_argument("--tracker")
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
    p = sub.add_parser("env-check"); p.add_argument("--ref", default="HEAD", help="the commit to look in (default: HEAD)")
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
                "ci-install": cmd_ci_install, "env-check": cmd_env_check}
    if args.cmd in handlers:
        return handlers[args.cmd](args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
