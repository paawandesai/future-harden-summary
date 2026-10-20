"""A one-page HTML view of a run, as a coach would see it: each draft with its decision, the reasons, and
the words that triggered each finding highlighted. Self-contained, no scripts from the network."""

import html
import re

from weekly_summary.models import Trace
from weekly_summary.pipeline import Detail

_ORDER = {"block": 0, "flag": 1, "pass": 2}

_STYLE = """
:root{--bg:#f7f7f5;--card:#fff;--text:#1d1d1b;--muted:#6b6b66;--line:#e3e2dd;--block:#b42318;--block-bg:#fdecea;
--flag:#9a6700;--flag-bg:#fff4d6;--pass:#1a7f37;--pass-bg:#e6f4ea;--mark:#ffe08a}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--card:#20201f;--text:#ecebe6;--muted:#a3a29c;--line:#34332f;
--block:#ff8a80;--block-bg:#3b1d1a;--flag:#f5c451;--flag-bg:#3a2f12;--pass:#7ad08f;--pass-bg:#16301d;--mark:#6b5512}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);
font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:880px;margin:0 auto;padding:24px 16px 64px}h1{font-size:22px;margin:0 0 4px}
.sub{color:var(--muted);margin:0 0 16px}.bar{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 20px}
.bar button{border:1px solid var(--line);background:var(--card);color:var(--text);border-radius:999px;
padding:6px 14px;font:inherit;cursor:pointer}.bar button[aria-pressed=true]{border-color:var(--text);font-weight:600}
article{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin:0 0 12px}
header{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}.badge{font-size:12px;font-weight:700;
text-transform:uppercase;letter-spacing:.04em;border-radius:6px;padding:2px 8px}
.block .badge{color:var(--block);background:var(--block-bg)}.flag .badge{color:var(--flag);background:var(--flag-bg)}
.pass .badge{color:var(--pass);background:var(--pass-bg)}.who{font-weight:600}.id{color:var(--muted);font-size:13px}
ul{margin:10px 0 0;padding-left:20px}li{margin:2px 0}.draft{white-space:pre-wrap;margin:12px 0 0;padding:12px;
border-left:3px solid var(--line);color:var(--text)}mark{background:var(--mark);color:inherit;border-radius:3px;padding:0 2px}
details{margin-top:10px;color:var(--muted);font-size:13px}code{font-size:12px}
"""

_SCRIPT = """
document.querySelectorAll('.bar button').forEach(b=>b.addEventListener('click',()=>{
document.querySelectorAll('.bar button').forEach(x=>x.setAttribute('aria-pressed',x===b));
document.querySelectorAll('article').forEach(a=>{a.hidden=b.dataset.show!=='all'&&!a.classList.contains(b.dataset.show)})}));
"""


def _highlight(draft: str, evidence: list[str]) -> str:
    """Escape the draft and mark each evidence phrase that appears in it (longest first, case-insensitive)."""
    phrases = sorted({e.strip() for item in evidence for e in item.split(", ") if len(e.strip()) > 1}, key=len)[::-1]
    spans: list[tuple[int, int]] = []
    for phrase in phrases:
        for match in re.finditer(re.escape(phrase), draft, re.I):
            if not any(s < match.end() and match.start() < e for s, e in spans):
                spans.append(match.span())
    out, last = [], 0
    for start, end in sorted(spans):
        out += [html.escape(draft[last:start]), f"<mark>{html.escape(draft[start:end])}</mark>"]
        last = end
    return "".join(out) + html.escape(draft[last:])


def render(details: list[Detail], traces: dict[str, Trace], title: str = "Weekly summaries for review") -> str:
    counts = {k: sum(d.decision == k for d in details) for k in _ORDER}
    cards = []
    for d in sorted(details, key=lambda d: (_ORDER[d.decision], d.trace_id)):
        trace = traces.get(d.trace_id)
        who = f"{trace.input.member.first_name} · coach {trace.input.member.coach_name}" if trace else ""
        reasons = "".join(f"<li>{html.escape(r)}</li>" for r in d.reasons)
        findings = "".join(
            f"<li><code>{html.escape(f.check)}</code> ({f.source}, {f.severity}): {html.escape(f.evidence[:120])}</li>"
            for f in d.findings
        )
        draft = _highlight(d.draft, [f.evidence for f in d.findings]) if d.draft else "<em>No draft.</em>"
        # The model rewrote its first draft once; the coach sees why and what it replaced.
        rewrite = (
            "<details><summary>Rewritten once because: "
            + html.escape(" ".join(d.repair_reasons) or "a code check failed")
            + f'</summary><div class="draft">{html.escape(d.first_draft or "")}</div></details>'
            if d.repaired
            else ""
        )
        cards.append(
            f'<article class="{d.decision}"><header><span class="badge">{d.decision}</span>'
            f'<span class="who">{html.escape(who)}</span><span class="id">{html.escape(d.trace_id)}</span></header>'
            + (f"<ul>{reasons}</ul>" if reasons else "")
            + f'<div class="draft">{draft}</div>'
            + rewrite
            + (f"<details><summary>All findings</summary><ul>{findings}</ul></details>" if findings else "")
            + "</article>"
        )
    buttons = "".join(
        f'<button data-show="{k}" aria-pressed="{str(k == "all").lower()}">{label}</button>'
        for k, label in [
            ("all", f"All {len(details)}"),
            ("block", f"Block {counts['block']}"),
            ("flag", f"Flag {counts['flag']}"),
            ("pass", f"Pass {counts['pass']}"),
        ]
    )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{html.escape(title)}</title><style>{_STYLE}</style></head><body><main>"
        f"<h1>{html.escape(title)}</h1><p class='sub'>Blocked drafts first, then flags. Highlighted words are what "
        f"each check matched.</p><div class='bar'>{buttons}</div>{''.join(cards)}</main>"
        f"<script>{_SCRIPT}</script></body></html>"
    )
