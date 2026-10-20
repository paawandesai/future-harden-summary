"""Loads vocab.toml and matches its concepts against text, whole-word and case-insensitive."""

import re
import tomllib
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

VOCAB_PATH = Path(__file__).with_name("vocab.toml")

_QUOTES = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-"})


def normalize(text: str) -> str:
    return text.translate(_QUOTES).lower()


def _pattern(term: str) -> re.Pattern[str]:
    return re.compile(r"(?<![\w'])" + re.escape(normalize(term)) + r"(?![\w'])")


@dataclass(frozen=True)
class Concept:
    key: str
    terms: tuple[str, ...]
    exclude: tuple[str, ...] = ()
    _patterns: tuple[re.Pattern[str], ...] = field(init=False, repr=False, compare=False)
    _excludes: tuple[re.Pattern[str], ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        # Longest first, so "resting heart rate" is reported instead of "heart rate".
        ordered = sorted(set(self.terms), key=len, reverse=True)
        object.__setattr__(self, "_patterns", tuple(_pattern(t) for t in ordered))
        object.__setattr__(self, "_excludes", tuple(_pattern(t) for t in self.exclude))

    def strip_excluded(self, text: str) -> str:
        text = normalize(text)
        for pattern in self._excludes:
            text = pattern.sub(" ", text)
        return text

    def find(self, text: str) -> list[str]:
        """Every term of this concept found in text, longest match first, without overlaps."""
        text = self.strip_excluded(text)
        found: list[str] = []
        for pattern in self._patterns:
            if pattern.search(text):
                found.append(pattern.pattern)
                text = pattern.sub(" ", text)
        return [_unpattern(p) for p in found]

    def hits(self, text: str) -> bool:
        return bool(self.find(text))


def _unpattern(pattern: str) -> str:
    inner = pattern.removeprefix(r"(?<![\w'])").removesuffix(r"(?![\w'])")
    return re.sub(r"\\(.)", r"\1", inner)


@dataclass(frozen=True)
class Vocab:
    concepts: dict[str, Concept]
    review_status: str

    def __getitem__(self, key: str) -> Concept:
        return self.concepts[key]


def _walk(prefix: str, node: dict[str, object], out: dict[str, Concept]) -> None:
    if "terms" in node:
        terms = node["terms"]
        exclude = node.get("exclude", [])
        assert isinstance(terms, list) and isinstance(exclude, list), prefix
        out[prefix] = Concept(prefix, tuple(str(t) for t in terms), tuple(str(t) for t in exclude))
        return
    for key, child in node.items():
        if isinstance(child, dict):
            _walk(f"{prefix}.{key}" if prefix else key, child, out)  # pyright: ignore[reportUnknownArgumentType]


@cache
def load_vocab(path: Path = VOCAB_PATH) -> Vocab:
    data = tomllib.loads(path.read_text())
    review = data.pop("review", {})
    concepts: dict[str, Concept] = {}
    _walk("", data, concepts)
    return Vocab(concepts, str(review.get("status", "draft")))


def phrase(term: str) -> Concept:
    """A one-off concept for a term that comes from the trace, such as a lab test name."""
    return Concept(term, (term,))
