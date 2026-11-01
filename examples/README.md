# Sample input and output (made-up numbers)

`sample-export.csv` is an invented Meta-style export of three campaigns. Everything else in this folder was
produced from it by Foundry, unedited:

```
python foundry.py setup init --client Example
python foundry.py campaigns import --client Example --file examples/sample-export.csv
python foundry.py account audit --client Example
python foundry.py account report --client Example --lang ar
python foundry.py account report --client Example --lang ar --format whatsapp
```

| File | What it is |
|---|---|
| `sample-audit.md` | The audit: score, per-campaign call, ranked fixes, honest limits |
| `sample-report-ar.md` | The client report in Arabic |
| `sample-whatsapp-ar.txt`, `sample-whatsapp-en.txt` | The short WhatsApp versions |

Note the audit marks Campaign B "Too early" (6 results, under the 10 needed to judge) and flags that Meta's
"Results" column counts a different thing per objective. Reports are drafts: a person reviews them before they
go to a client.
