"""Any GitHub repo → a launch video script.

    cardbox repo owner/name --render
    cardbox repo https://github.com/owner/name --format landscape
    cardbox repo .                       your own project, before it's even pushed

Reads the repo's description, stars, topics and README, and writes a plain-text script (see script.py):
a hook from the tagline, a stars card, up to three feature beats, the install command and a closing
card. No AI is involved; it's a starting point you can edit. For a sharper script, ask your assistant
over MCP: `read_repo` gives it the same material.

A GitHub token in $GITHUB_TOKEN (or $GH_TOKEN) is used when present, for private repos and higher rate
limits. Nothing else is sent anywhere.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

UA = "cardbox (+https://github.com/aryainguz/cardbox)"
CREDIT = "Made with cardbox: github.com/Aryainguz/cardbox"

# Headings whose bullet lists describe what the project does, best first.
FEATURE_HEADINGS = re.compile(r"feature|highlight|why|what (it|makes|you)|different|benefit|overview|key", re.I)
SKIP_HEADINGS = re.compile(r"what'?s new|changelog|release|roadmap|todo|license|contribut|credit|sponsor|star history|"
                           r"contents|acknowledg|faq|support|community|author|thank", re.I)
INSTALL_HEADINGS = re.compile(r"install|quick ?start|getting started|setup|usage|try it", re.I)
INSTALL_CMD = re.compile(
    r"^(?:\$\s*)?((?:pipx|pip3?|uvx|uv (?:tool|add|pip)|npm|npx|pnpm|yarn|bun|bunx|brew|cargo (?:b?install|add)|go (?:install|get)|"
    r"gem|composer|dotnet|docker (?:run|pull)|apt(?:-get)?|winget|scoop|nix|curl)\b.*)$")
MAX_SAY_WORDS = 28
HOOK_WORDS = 20
# Install commands people recognise first, so the card shows the most familiar one the README offers.
INSTALL_RANK = ("brew", "pipx", "uvx", "pip", "npm", "npx", "cargo", "go ", "docker", "uv ", "pnpm", "yarn", "bun")


@dataclass
class Repo:
    owner: str
    name: str
    description: str = ""
    stars: int = 0
    language: str = ""
    topics: list[str] = field(default_factory=list)
    homepage: str = ""
    readme: str = ""

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.name}"

    @property
    def url(self) -> str:
        return f"https://github.com/{self.slug}"


# ---------- fetching ----------

def parse_ref(ref: str) -> tuple[str, str]:
    """'owner/name', 'github.com/owner/name', 'https://github.com/owner/name(.git)(/tree/...)', 'git@github.com:owner/name.git'."""
    s = ref.strip()
    m = re.search(r"github\.com[/:]([\w.-]+)/([\w.-]+?)(?:\.git)?(?:[/#?].*)?$", s) or re.fullmatch(r"([\w.-]+)/([\w.-]+)", s)
    if not m:
        raise ValueError(f"not a GitHub repo: {ref!r} (use owner/name or a github.com link)")
    return m.group(1), m.group(2)


def _get(url: str, raw: bool = False) -> bytes:
    headers = {"User-Agent": UA, "Accept": "application/vnd.github.raw" if raw else "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise FileNotFoundError(f"GitHub says not found: {url.split('/repos/')[-1]} (private? set GITHUB_TOKEN)") from e
        if e.code in (403, 429):
            raise RuntimeError("GitHub rate limit reached; set GITHUB_TOKEN and try again") from e
        raise RuntimeError(f"GitHub returned {e.code} for {url}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"couldn't reach GitHub: {e.reason}") from e


def fetch(ref: str) -> Repo:
    """A repo from GitHub, or from a local folder ('.', a path) using its README and git remote."""
    path = Path(ref).expanduser()
    if path.is_dir() and "github.com" not in ref:
        return _local(path)
    owner, name = parse_ref(ref)
    meta = json.loads(_get(f"https://api.github.com/repos/{owner}/{name}"))
    try:
        readme = _get(f"https://api.github.com/repos/{owner}/{name}/readme", raw=True).decode("utf-8", "replace")
    except FileNotFoundError:
        readme = ""
    return Repo(owner=meta["owner"]["login"], name=meta["name"], description=meta.get("description") or "",
                stars=meta.get("stargazers_count") or 0, language=meta.get("language") or "",
                topics=meta.get("topics") or [], homepage=meta.get("homepage") or "", readme=readme)


def _local(path: Path) -> Repo:
    path = path.resolve()
    readme = next((p for p in sorted(path.iterdir()) if p.name.lower() in ("readme.md", "readme.markdown", "readme")), None)
    owner, name = "", path.name
    try:
        remote = subprocess.run(["git", "-C", str(path), "remote", "get-url", "origin"],
                                capture_output=True, text=True, timeout=5).stdout.strip()
        owner, name = parse_ref(remote)
    except (ValueError, OSError, subprocess.SubprocessError):
        pass
    return Repo(owner=owner or "you", name=name, readme=readme.read_text(encoding="utf-8", errors="replace") if readme else "")


# ---------- reading the README ----------

def _strip_inline(s: str) -> str:
    """Markdown/HTML inline → plain words a voice can read."""
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", s)                 # images
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)              # links → their text
    s = re.sub(r"\[([^\]]*)\]\[[^\]]*\]", r"\1", s)             # reference links
    s = re.sub(r"`([^`]*)`", r"\1", s)
    s = re.sub(r"(\*\*|__|\*|_|~~)(?=\S)(.+?)(?<=\S)\1", r"\2", s)
    s = re.sub(r"[\U0001F000-\U0001FAFF☀-➿️‍]", "", s)  # emoji
    s = re.sub(r"&(nbsp|amp|lt|gt|quot);", lambda m: {"nbsp": " ", "amp": "&", "lt": "<", "gt": ">", "quot": '"'}[m.group(1)], s)
    return re.sub(r"\s+", " ", s).strip(" -–—:|")


@dataclass
class Section:
    heading: str
    lines: list[str] = field(default_factory=list)
    code: list[str] = field(default_factory=list)


def sections(md: str) -> list[Section]:
    """The README split by headings (the part before the first heading has heading '')."""
    out = [Section("")]
    in_code = False
    for ln in md.splitlines():
        if ln.lstrip().startswith(("```", "~~~")):
            in_code = not in_code
            continue
        if in_code:
            out[-1].code.append(ln.strip())
            continue
        h = re.match(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$", ln) or re.match(r"^\s*<h[1-6][^>]*>(.*?)</h[1-6]>", ln, re.I)
        if h:
            out.append(Section(_strip_inline(h.group(1))))
        else:
            out[-1].lines.append(ln)
    return out


def _bullets(sec: Section) -> list[str]:
    """Top-level list items, with wrapped continuation lines joined on."""
    items: list[str] = []
    open_item = False
    for ln in sec.lines:
        m = re.match(r"^\s{0,3}(?:[-*+]|\d+[.)])\s+(.*)", ln)
        if m:
            items.append(m.group(1))
            open_item = True
        elif not ln.strip():  # a blank line ends the item
            open_item = False
        elif open_item and not re.match(r"^\s*(?:[-*+]|\d+[.)])\s|^\s*[|<>]", ln):  # a wrapped line of the same item
            items[-1] += " " + ln.strip()
    return items


def _paragraphs(sec: Section) -> list[str]:
    paras, cur = [], []
    for ln in sec.lines + [""]:
        if not ln.strip() or re.match(r"^\s*(?:[-*+>|]|\d+[.)]|<p|<img|<a |\[!\[|---|===)", ln):
            if cur:
                paras.append(_strip_inline(" ".join(cur)))
                cur = []
            continue
        cur.append(ln.strip())
    return [p for p in paras if len(p.split()) >= 5]


def _sentence(text: str, limit: int = MAX_SAY_WORDS, more: bool = False) -> str:
    """The first sentence (with `more`, as many whole sentences as fit), within `limit` words, ending in
    a full stop. A sentence that's too long is cut back to its first clause, never mid-phrase."""
    sents = re.split(r"(?<=[.!?])\s+", text.strip())
    first = sents[0]
    if len(first.split()) > limit:
        cut = re.split(r"[,;:—–(]\s?", first)[0]
        first = cut if len(cut.split()) <= limit else " ".join(first.split()[:limit])
    out = first.rstrip(",;:—–( ")
    out = out if out.endswith((".", "!", "?")) else out + "."
    if more:
        for s in sents[1:]:
            if len((out + " " + s).split()) > limit:
                break
            out += " " + s
    return out


def feature(item: str) -> tuple[str, str] | None:
    """(on-screen headline, spoken line) from one README bullet, or None if it isn't a usable feature."""
    bold = re.match(r"^\s*(?:[^\w*_`]*\s*)?(?:\*\*|__)(.+?)(?:\*\*|__)\s*[:.\-–—]?\s*(.*)", item)
    if bold:
        head, rest = _strip_inline(bold.group(1)).rstrip(".:"), _strip_inline(bold.group(2))
    else:
        text = _strip_inline(item)
        parts = re.split(r"\s[-–—:]\s|:\s", text, maxsplit=1)
        head, rest = (parts[0], parts[1]) if len(parts) == 2 and len(parts[0].split()) <= 7 else ("", text)
    if not head and not rest:
        return None
    say = _sentence(rest) if len(rest.split()) >= 4 else _sentence(head or rest)
    if len(say.split()) < 3:
        return None
    return head, say


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:] if s[:1].islower() and not re.match(r"^\S*[A-Z_.]", s) else s


def features(md: str, n: int = 3) -> list[tuple[str, str]]:
    """Up to n (headline, spoken line) pairs from the README's best feature list. A list under a
    heading like "Features" wins; otherwise only lists in the first half of the README count, since
    lists further down are usually options, legends or reference material."""
    secs = sections(md)
    half = max(2, len(secs) // 2)
    usable = [(i, s) for i, s in enumerate(secs) if len(_bullets(s)) >= 2 and not SKIP_HEADINGS.search(s.heading)
              and not INSTALL_HEADINGS.search(s.heading) and (FEATURE_HEADINGS.search(s.heading) or i < half)]
    ranked = [s for _, s in sorted(usable, key=lambda t: (not FEATURE_HEADINGS.search(t[1].heading),
                                                          INSTALL_HEADINGS.search(t[1].heading) is not None, t[0]))]
    for sec in ranked:
        # Option lists (`ansi`, `--flag`) and link lists aren't features: skip items that open with code or a link.
        items = [b for b in _bullets(sec) if not re.match(r"^\s*(`|\[[^\]]*\]\(|<a\s|https?://)", b)]
        got = [f for f in map(feature, items) if f]
        if len(got) >= 2 and sum(len(say.split()) for _, say in got) / len(got) >= 5:
            return [(_cap(h), _cap(say)) for h, say in got[:n]]
    return []


LIBRARY_HEADINGS = re.compile(r"python|javascript|typescript|node|sdk|librar|client|binding|api|develop|from (local )?source|build", re.I)


def install_command(md: str, name: str = "") -> str:
    """The most familiar short command that installs this project, or ''."""
    found: list[tuple[str, str]] = []
    for sec in sections(md):
        for ln in sec.code:
            m = INSTALL_CMD.match(ln)
            if not m:
                continue
            cmd = re.sub(r"\s+#.*$", "", m.group(1)).strip()
            if cmd.startswith("curl") and not re.search(r"install|\|\s*(ba|z)?sh\b", cmd):
                continue  # `curl` that calls an API or pipes elsewhere isn't an install
            if re.search(r"--path\s|\s\.(\s|$)", cmd):
                continue  # installs from a local checkout
            found.append((cmd, sec.heading))
    key = re.sub(r"[^a-z0-9]", "", name.lower())

    def rank(item: tuple[str, str]) -> int:
        cmd, heading = item
        i = next((i for i, k in enumerate(INSTALL_RANK) if cmd.startswith(k)), len(INSTALL_RANK) + 1)
        return (i
                + (30 if len(cmd) > 38 else 0)                                   # must fit the terminal card
                + (100 if LIBRARY_HEADINGS.search(heading) else 0)               # `pip install ollama` is its Python client
                + (200 if key and key not in re.sub(r"[^a-z0-9]", "", cmd.lower()) else 0))  # installs something else
    return min(found, key=rank)[0] if found else ""


def tagline(repo: Repo) -> str:
    if repo.description:
        return _cap(_strip_inline(repo.description))
    secs = sections(repo.readme)
    for sec in secs[:3]:
        paras = _paragraphs(sec)
        if paras:
            return paras[0]
    return ""


# ---------- the script ----------

def _title(name: str) -> str:
    return name if any(c.isupper() for c in name) else name.replace("-", " ").replace("_", " ").title().replace(" ", "")


def stars_label(n: int) -> str:
    return f"{n / 1000:.1f}k".replace(".0k", "k") if n >= 1000 else str(n)


def spoken_stars(n: int) -> str:
    """Rounded down so "more than" stays true: 214 → 200, 92,147 → 92,000, 1,240,000 → 1.2 million."""
    if n >= 1_000_000:
        return f"{n // 100_000 / 10:g} million"
    step = 1000 if n >= 10_000 else 100
    return f"{n // step * step:,}"


def script(repo: Repo, cta: str = "") -> str:
    """A plain-text cardbox script for the repo."""
    title = repo.name if repo.name.islower() and "-" not in repo.name else _title(repo.name)
    tag = tagline(repo)
    hook_say = f"Meet {title}. {_sentence(tag, HOOK_WORDS, more=True)}" if tag else f"Meet {title}."
    paras = [f"# {title}\n{hook_say}"]
    if repo.stars >= 100:
        paras.append(f"# {stars_label(repo.stars)} stars on GitHub\n"
                     f"More than {spoken_stars(repo.stars)} developers have starred it on GitHub.")
    for head, say in features(repo.readme):
        paras.append((f"# {head}\n" if head else "") + say)
    cmd = install_command(repo.readme, repo.name)
    if cmd:
        paras.append(f"# {cmd}\nGetting started takes one command.")
    end_say = cta or f"It's open source. Find {title} on GitHub, link in the caption."
    paras.append(f"# {repo.slug}\n{end_say}")
    return "\n\n".join(paras) + "\n"


def caption(repo: Repo, credit: bool = True) -> str:
    lines = [_sentence(tagline(repo), 40) if tagline(repo) else repo.name, "", repo.url]
    if repo.homepage and repo.homepage.rstrip("/") != repo.url:
        lines.append(repo.homepage)
    if credit:
        lines += ["", CREDIT]
    return "\n".join(lines)


def hashtags(repo: Repo) -> list[str]:
    tags = [re.sub(r"[^a-z0-9]", "", t.lower()) for t in repo.topics] + ([repo.language.lower()] if repo.language else [])
    out: list[str] = []
    for t in tags + ["opensource", "github"]:
        if t and t not in out:
            out.append(t)
    return out[:5]


def animate(reel, repo: Repo):  # noqa: ANN001, ANN201  (spec.Reel, kept lazy)
    """Upgrades the plain beats: the star count counts up, the install command types itself out in a
    terminal, and the hook gets an 'Open source · Rust' eyebrow."""
    from .spec import Hook, SceneBeat, Stat, Text

    cmd = install_command(repo.readme, repo.name)
    beats = []
    for b in reel.beats:
        if isinstance(b, Hook) and not b.eyebrow:
            b.eyebrow = "Open source" + (f" · {repo.language}" if repo.language else "")
        if isinstance(b, Stat) and b.label == "stars on GitHub" and repo.stars >= 100:
            big = repo.stars >= 1000
            to = round(repo.stars / 1000, 1) if big else repo.stars
            b = SceneBeat(scene="counter", say=b.say, pronounce=b.pronounce,
                          params={"to": to, "decimals": 1 if big and to % 1 else 0, "unit": "k" if big else "",
                                  "label": "stars on GitHub", "on": 0.05, "seconds": 1.4})
        elif isinstance(b, Text) and cmd and b.text == cmd:
            b = SceneBeat(scene="terminal", head="Get started", say=b.say, pronounce=b.pronounce,
                          params={"title": repo.name, "lines": [{"text": cmd, "on": 0.1}]})
        beats.append(b)
    reel.beats = beats
    return reel


def build(ref: str, name: str = "", credit: bool = True, **options: object) -> tuple[Repo, str, Path]:
    """Fetches the repo, writes script.txt and reel.yaml into the workspace, and returns
    (repo, script text, reel folder). `options` are top-level spec fields (format, theme, voice, ...)."""
    from . import spec
    from .script import from_text
    from .workspace import reel_dir

    repo = fetch(ref)
    text = script(repo)
    d = reel_dir(name or repo.name)
    reel = from_text(text, title=f"{repo.name}: {tagline(repo)}" if tagline(repo) else repo.name,
                     media_dir=d / "media", **options)
    animate(reel, repo)
    reel.caption = caption(repo, credit)
    reel.hashtags = hashtags(repo)
    (d / "script.txt").write_text(text, encoding="utf-8")
    (d / "reel.yaml").write_text(spec.dump(reel), encoding="utf-8")
    return repo, text, d
