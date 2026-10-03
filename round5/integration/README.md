# Public physical case entry

This directory is a thin round5 adapter around the existing round4 workbench
concept. It does not modify the round4 server or front-end. The entry point
re-parses the retained public SZVAV source, recalibrates on the two frozen
normal development days, runs the professional APAR baseline and the response
evidence mechanism, then exports a readable HTML card and JSON trace.

```powershell
$py = 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $py round5/integration/run_public_case.py --case-id 19e3873d3c2f
```

Default outputs:

- `round5/integration/public_case_output/case_card.html`
- `round5/integration/public_case_output/case_card.json`

The default case is the development FLEXLAB outdoor-damper controlled-test
experiment. The card labels the source nature and command-versus-feedback
boundary, shows baseline and post-evidence states on the same screen, lists
the actual subsequent windows and next action, and recomputes when inputs or
the case id change. A case with no discriminating window remains unresolved.

