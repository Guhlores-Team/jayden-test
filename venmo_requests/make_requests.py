#!/usr/bin/env python3
"""Turn a guest list into one-tap Venmo request links.

Venmo has no public API for creating requests, so this does the next best
thing: it reads a CSV of guests and writes an HTML page of pre-filled
"Request" buttons. Each tap opens Venmo with recipient, amount and note already
filled in; you just hit Send. Open the page on your phone for the smoothest flow.

CSV columns (header required):
    username            Venmo handle, with or without the leading @
    amount   (optional) per-person amount; falls back to --amount
    note     (optional) per-person note;   falls back to --note

Usage:
    python venmo_requests/make_requests.py guests.csv --amount 1 --note "Friday function" -o requests.html
    python venmo_requests/make_requests.py guests.csv --format csv      # plain list of links
"""
from __future__ import annotations

import argparse
import csv
import html
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlencode

WEB_BASE = "https://venmo.com/"
APP_BASE = "venmo://paycharge"


def build_link(username: str, amount: Decimal, note: str, app: bool = False) -> str:
    params = {
        "txn": "charge",
        "audience": "private",
        "recipients": username.lstrip("@"),
        "amount": f"{amount:.2f}",
        "note": note,
    }
    return (APP_BASE if app else WEB_BASE) + "?" + urlencode(params)


def read_guests(path: Path, default_amount: Decimal, default_note: str) -> list[dict]:
    guests = []
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames or "username" not in [f.strip().lower() for f in reader.fieldnames]:
            sys.exit("CSV needs a header row with a 'username' column")
        for lineno, row in enumerate(reader, start=2):
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            username = row.get("username", "").lstrip("@")
            if not username:
                continue
            raw_amount = row.get("amount") or str(default_amount)
            try:
                amount = Decimal(raw_amount)
            except InvalidOperation:
                sys.exit(f"line {lineno}: bad amount {raw_amount!r}")
            if amount <= 0:
                sys.exit(f"line {lineno}: amount must be positive")
            guests.append({
                "username": username,
                "amount": amount,
                "note": row.get("note") or default_note,
            })
    return guests


def render_html(guests: list[dict], title: str) -> str:
    rows = []
    for g in guests:
        u = html.escape(g["username"])
        rows.append(
            f'<li data-user="{u}">'
            f'<label><input type="checkbox" class="done"> <span class="who">@{u}</span>'
            f' <span class="amt">${g["amount"]:.2f}</span></label>'
            f'<a class="btn" href="{html.escape(build_link(g["username"], g["amount"], g["note"]))}"'
            f' target="_blank" rel="noopener">Request</a>'
            f'</li>'
        )
    total = sum(g["amount"] for g in guests)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
  :root {{ --bg:#fff; --fg:#111; --muted:#666; --line:#e5e5e5; --accent:#008cff; --done:#f3f3f3; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg:#111; --fg:#eee; --muted:#999; --line:#2a2a2a; --accent:#3ea6ff; --done:#1c1c1c; }}
  }}
  body {{ margin:0; padding:16px; font:16px/1.4 system-ui,sans-serif; background:var(--bg); color:var(--fg); }}
  h1 {{ font-size:20px; margin:0 0 4px; }}
  .summary {{ color:var(--muted); margin-bottom:12px; }}
  ul {{ list-style:none; padding:0; margin:0; }}
  li {{ display:flex; align-items:center; justify-content:space-between; gap:12px;
        padding:10px 0; border-bottom:1px solid var(--line); }}
  li.is-done {{ background:var(--done); opacity:.55; }}
  label {{ display:flex; align-items:center; gap:10px; flex:1; min-width:0; }}
  .who {{ overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
  .amt {{ color:var(--muted); }}
  .btn {{ background:var(--accent); color:#fff; text-decoration:none; padding:8px 14px;
          border-radius:999px; font-weight:600; white-space:nowrap; }}
  .btn:active {{ opacity:.8; }}
</style></head><body>
<h1>{html.escape(title)}</h1>
<div class="summary"><span id="count">0</span>/{len(guests)} sent &middot; ${total:.2f} total</div>
<ul id="list">
{chr(10).join(rows)}
</ul>
<script>
(function () {{
  var key = 'venmo-requests:' + location.pathname + ':' + document.title;
  var saved = {{}};
  try {{ saved = JSON.parse(localStorage.getItem(key) || '{{}}'); }} catch (e) {{}}
  var items = document.querySelectorAll('#list li');
  function refresh() {{
    var n = 0;
    items.forEach(function (li) {{
      var done = !!saved[li.dataset.user];
      li.classList.toggle('is-done', done);
      li.querySelector('.done').checked = done;
      if (done) n++;
    }});
    document.getElementById('count').textContent = n;
    try {{ localStorage.setItem(key, JSON.stringify(saved)); }} catch (e) {{}}
  }}
  items.forEach(function (li) {{
    var user = li.dataset.user;
    li.querySelector('.done').addEventListener('change', function (ev) {{
      saved[user] = ev.target.checked; refresh();
    }});
    // Tapping Request marks the row done; untick the box if you back out.
    li.querySelector('.btn').addEventListener('click', function () {{
      saved[user] = true; refresh();
    }});
  }});
  refresh();
}})();
</script>
</body></html>
"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", type=Path, help="guest list CSV")
    ap.add_argument("--amount", type=Decimal, default=Decimal("1"), help="default amount (default 1)")
    ap.add_argument("--note", default="Thanks for coming!", help="default request note")
    ap.add_argument("--title", default="Venmo requests", help="page title")
    ap.add_argument("--format", choices=["html", "csv"], default="html")
    ap.add_argument("--app-links", action="store_true", help="csv format: emit venmo:// app links instead of web links")
    ap.add_argument("-o", "--out", type=Path, help="output file (default: stdout)")
    args = ap.parse_args()

    guests = read_guests(args.csv, args.amount, args.note)
    if not guests:
        sys.exit("no guests found in CSV")

    if args.format == "html":
        text = render_html(guests, args.title)
    else:
        text = "username,amount,link\n" + "".join(
            f'{g["username"]},{g["amount"]:.2f},{build_link(g["username"], g["amount"], g["note"], app=args.app_links)}\n'
            for g in guests
        )

    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {len(guests)} requests to {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
