# OEDI/LBNL 物理实测子集

`mzvav2_1_physical_subset.csv` is a six-date subset of `MZVAV-2-1.csv` from the public [OEDI dataset entry](https://data.openei.org/submissions/910), DOI [10.25984/1824861](https://doi.org/10.25984/1824861). The underlying dataset is attributed to Guanjing Lin and Robin Mitchell / Lawrence Berkeley National Laboratory and is distributed under CC BY 4.0.

This repository keeps only the rows for 2007-08-28, 2007-08-29, 2007-08-30, 2008-08-19, 2008-08-25 and 2008-09-04. The subset is a modified selection; source file name, fault calendar and `Fault Detection Ground Truth` are excluded from diagnostic input and used only for post-run evaluation. The source hash and selection protocol are in `../../protocol/external_physical_source.json`.

The file contains a physical AHU experiment with minute samples and control commands. It does not contain zone-air temperature feedback, aligned energy metering or actual damper/valve positions, so the workbench refuses to use it as a counterfactual operation-planning score.
