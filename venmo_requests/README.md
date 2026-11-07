# Venmo request links

Venmo has no API for sending requests, and automating the app gets accounts
locked. This script does the next best thing for hosts who need to request a
lot of people: it turns a guest list into a page of one-tap, pre-filled
**Request** buttons. Each tap opens Venmo with the person, amount and note
already filled in. You only press Send.

```bash
# 1. Make a CSV of guests (see guests.example.csv). Only `username` is required.
# 2. Build the page:
python venmo_requests/make_requests.py guests.csv --amount 1 --note "Friday function" -o requests.html
# 3. Open requests.html on your phone (AirDrop it, email it to yourself, etc.)
#    and tap through the list. Rows are checked off as you go.
```

Per-person overrides: fill in the `amount` or `note` column for that row.
Want plain links instead of a page? `--format csv` (add `--app-links` for
`venmo://` links that open the app directly).

Progress is saved in the browser, so you can stop and pick it back up later.
