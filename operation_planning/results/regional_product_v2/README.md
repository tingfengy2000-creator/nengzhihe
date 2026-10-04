# Regional product v2 evidence

This directory contains a reproducible first-stage reference run, not a claim of measured-building accuracy.

- `summary.json` / `summary.csv`: 3 cities (Guangzhou, Beijing, Harbin) × 3 complete ERA5 reference years (2023–2025) × 3 public rated-point profiles. Each row keeps the weather hash, model source, electricity, sensible/latent cooling, capacity shortfall, unmet temperature/RH indicators and a 10-year cash-flow result under the same explicit user quote (`3000 CNY` equipment, `800 CNY` installation, `260 CNY/year` maintenance, `0.66 CNY/kWh`).
- `sensitivity.json`: controlled changes to temperature/RH target, ventilation and equipment count on Guangzhou 2024. These are mechanism checks, not independent building cases.

The model uses city-scale reanalysis, a bounded lumped room model and an explicit rated-point temperature adaptation. It has no site calibration, complete manufacturer part-load maps or building total-meter validation. A quote is a user scenario; it is not a procurement price.