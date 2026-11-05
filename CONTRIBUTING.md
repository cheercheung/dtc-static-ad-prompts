# Contributing

Read the [usage guide](docs/usage.md) to understand the collection and the
[maintenance guide](docs/maintenance.md) before editing generated pages.

Report a problem through the appropriate issue form. Include the case number,
language edition, affected path, the exact issue, and the proposed correction.
Keep personal customer details and private campaign information out of reports.

Navigation and explanation improvements belong in the locale dictionaries or
usage guide. Prompt bodies are preserved exactly: do not rewrite a canonical
prompt to make a translation, correct a usage note, or demonstrate a new ad.
Describe proposed prompt changes for maintainer review before changing data.

For a local change, run both commands from the repository root:

```
python3 scripts/build_library.py
python3 scripts/verify_library.py
```

Include the checks performed and any unresolved problem in the pull request.
No public reuse license is granted by contributing instructions; read LICENSE
for the collection's current license status.
