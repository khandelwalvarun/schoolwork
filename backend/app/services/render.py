"""Three renderers over the same DigestData: text (Telegram-ish), HTML (email/web), web."""

from __future__ import annotations

import html as _html
from dataclasses import asdict
from typing import Any

from .briefing import DigestData, DigestAssignmentRow, DigestGradeTrend, DigestKidSection


def _kid_header(k: DigestKidSection) -> str:
    return f"{k.name}" + (f" · {k.class_section}" if k.class_section else "")


def _fmt_row_line(r: DigestAssignmentRow) -> str:
    subj = (r.subject or "").replace("|", "/").strip()
    title = (r.title or "").strip()
    return f"  • {subj:<18}  {title[:46]:<46}  due {r.due or '—'}"


def render_text(data: DigestData) -> str:
    """Plain-text / Telegram Markdown. Emoji headers; no HTML."""
    lines: list[str] = []
    lines.append(
        f"🏫 *VVS Daily Digest* — {data.generated_for}"
    )
    if data.preamble:
        lines.append("")
        lines.append(data.preamble)
    lines.append("")
    delta_str = ""
    if data.backlog_delta_48h is not None:
        if data.backlog_delta_48h > 0:
            delta_str = f" (+{data.backlog_delta_48h})"
        elif data.backlog_delta_48h < 0:
            delta_str = f" ({data.backlog_delta_48h})"
    lines.append(
        f"🚨 Overdue: *{data.totals['overdue']}*{delta_str}   "
        f"📌 Due today: *{data.totals['due_today']}*   "
        f"📅 Upcoming: *{data.totals['upcoming']}*"
    )

    for k in data.kids:
        lines.append("")
        lines.append("─" * 40)
        lines.append(f"*{_kid_header(k)}*")
        lines.append("─" * 40)

        if k.overdue:
            lines.append(f"🚨 *Overdue — {len(k.overdue)}*")
            for r in k.overdue:
                lines.append(_fmt_row_line(r))
        if k.due_today:
            lines.append("")
            lines.append(f"📌 *Due Today — {len(k.due_today)}*")
            for r in k.due_today:
                lines.append(_fmt_row_line(r))
        if k.upcoming:
            lines.append("")
            lines.append(f"📅 *Upcoming — {len(k.upcoming)}*")
            for r in k.upcoming[:20]:
                lines.append(_fmt_row_line(r))
        if k.overdue_by_subject:
            lines.append("")
            concen = ", ".join(
                f"{subj}: {n}" for subj, n in sorted(
                    k.overdue_by_subject.items(), key=lambda kv: -kv[1]
                )[:6]
            )
            lines.append(f"  Overdue by subject — {concen}")

        if k.grade_trends:
            lines.append("")
            lines.append(f"📊 *Grade trend*")
            for t in k.grade_trends:
                lines.append(
                    f"  {t.subject:<22} {t.sparkline:<10} {t.arrow}  "
                    f"latest {t.latest:.0f}%  avg {t.avg:.0f}%  (n={t.count})"
                )

    if data.messages_last_7d:
        lines.append("")
        lines.append("─" * 40)
        lines.append(f"📬 *School Messages (last 7 days) — {len(data.messages_last_7d)}*")
        for m in data.messages_last_7d[:10]:
            title = m.get("title") or m.get("subject") or ""
            date_s = m.get("due_or_date") or ""
            lines.append(f"  • {title[:60]}   {date_s}")

    return "\n".join(lines)


def _esc(s: str | None) -> str:
    return _html.escape(s or "")


def render_html(data: DigestData) -> str:
    """Full HTML for email + web. Uses a compact self-contained inline-style table."""
    parts: list[str] = []
    parts.append('<div style="font-family: ui-sans-serif, system-ui, -apple-system; max-width: 780px; line-height: 1.5;">')
    parts.append(f'<h2 style="margin-bottom:4px">VVS Daily Digest — {_esc(data.generated_for)}</h2>')
    if data.preamble:
        parts.append(f'<p style="color:#444;white-space:pre-wrap">{_esc(data.preamble)}</p>')

    delta = ""
    if data.backlog_delta_48h is not None:
        delta = f' <span style="color:{"#b00" if data.backlog_delta_48h > 0 else "#070"}">(Δ {data.backlog_delta_48h:+d})</span>'
    parts.append(
        f'<div style="margin:12px 0 18px">'
        f'<span style="background:#fee;color:#900;padding:3px 8px;border-radius:4px">🚨 Overdue: <b>{data.totals["overdue"]}</b>{delta}</span>&nbsp;'
        f'<span style="background:#fef5e6;color:#a60;padding:3px 8px;border-radius:4px">📌 Due today: <b>{data.totals["due_today"]}</b></span>&nbsp;'
        f'<span style="background:#eef;color:#036;padding:3px 8px;border-radius:4px">📅 Upcoming: <b>{data.totals["upcoming"]}</b></span>'
        f'</div>'
    )

    for k in data.kids:
        parts.append(f'<h3 style="border-bottom:1px solid #ddd;padding-bottom:4px;margin-top:24px">{_esc(_kid_header(k))}</h3>')

        def _tbl(title: str, rows: list[DigestAssignmentRow], color: str) -> None:
            if not rows:
                return
            parts.append(f'<h4 style="color:{color};margin:14px 0 4px">{title} — {len(rows)}</h4>')
            parts.append('<table style="border-collapse:collapse;width:100%;font-size:14px">')
            parts.append(
                '<thead><tr style="color:#777;text-align:left">'
                '<th style="padding:4px 8px">Subject</th>'
                '<th style="padding:4px 8px">Assignment</th>'
                '<th style="padding:4px 8px">Type</th>'
                '<th style="padding:4px 8px">Due</th>'
                '</tr></thead><tbody>'
            )
            for r in rows:
                parts.append(
                    '<tr style="border-top:1px solid #eee">'
                    f'<td style="padding:4px 8px;white-space:nowrap">{_esc(r.subject)}</td>'
                    f'<td style="padding:4px 8px">{_esc(r.title)}</td>'
                    f'<td style="padding:4px 8px;color:#555">{_esc(r.type)}</td>'
                    f'<td style="padding:4px 8px;white-space:nowrap">{_esc(r.due)}</td>'
                    '</tr>'
                )
            parts.append('</tbody></table>')

        _tbl("🚨 Overdue", k.overdue, "#b00")
        _tbl("📌 Due today", k.due_today, "#a60")
        _tbl("📅 Upcoming", k.upcoming[:20], "#036")

        if k.overdue_by_subject:
            concen = ", ".join(
                f"<b>{_esc(subj)}</b>: {n}" for subj, n in sorted(
                    k.overdue_by_subject.items(), key=lambda kv: -kv[1]
                )[:6]
            )
            parts.append(f'<p style="color:#555;margin-top:6px">Overdue by subject — {concen}</p>')

        if k.grade_trends:
            parts.append('<h4 style="color:#555;margin:14px 0 4px">📊 Grade trend</h4>')
            parts.append('<table style="border-collapse:collapse;width:100%;font-size:14px">')
            for t in k.grade_trends:
                arrow_color = "#070" if t.arrow == "↑" else "#b00" if t.arrow == "↓" else "#555"
                parts.append(
                    '<tr style="border-top:1px solid #eee">'
                    f'<td style="padding:4px 8px">{_esc(t.subject)}</td>'
                    f'<td style="padding:4px 8px;font-family:monospace">{_esc(t.sparkline)}</td>'
                    f'<td style="padding:4px 8px;color:{arrow_color};font-size:18px">{t.arrow}</td>'
                    f'<td style="padding:4px 8px">latest <b>{t.latest:.0f}%</b></td>'
                    f'<td style="padding:4px 8px;color:#555">avg {t.avg:.0f}% (n={t.count})</td>'
                    '</tr>'
                )
            parts.append('</table>')

    if data.messages_last_7d:
        parts.append('<h3 style="border-bottom:1px solid #ddd;padding-bottom:4px;margin-top:24px">📬 School Messages (last 7 days)</h3>')
        parts.append('<ul style="padding-left:18px">')
        for m in data.messages_last_7d[:15]:
            title = m.get("title") or m.get("subject") or ""
            date_s = m.get("due_or_date") or ""
            parts.append(
                f'<li style="margin:3px 0"><b>{_esc(title[:80])}</b> <span style="color:#777">{_esc(date_s)}</span></li>'
            )
        parts.append('</ul>')

    parts.append('</div>')
    return "".join(parts)


def render_for_digest(data: DigestData) -> dict[str, Any]:
    text = render_text(data)
    html = render_html(data)
    subject = f"VVS Daily Digest — {data.generated_for}"
    return {
        "text": text,
        "markdown": text,  # telegram markdown
        "telegram": text,
        "html": html,
        "subject": subject,
        "data": asdict(data),
    }
