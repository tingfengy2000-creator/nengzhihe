# OpenEI submission 910 verification

Checked 2026-10-03 from the official OpenEI page:

- URL: https://data.openei.org/submissions/910
- DOI shown by the page: 10.25984/1824861
- Organisation: Lawrence Berkeley National Laboratory
- Stated license: Creative Commons (the page links the license icon; the inventory is also distributed in the downloaded package)
- Stated data nature: the page describes air-handling-unit and rooftop-unit data simulated with PNNL's large-office-building model. It is not a physical FLEXLAB experiment and is not an operational-building record.
- Page snapshot: `sources/openei_submission_910.html`, SHA-256 `716244dcb4795f0bb1540988a0c44515d61dde9f04b07eb7ca514bfc82c7b957`.
- Official data archive downloaded from `/files/910/Data Sets for AFDD Evauluation of Building FDD Algorithms.zip`: `sources/openei_910_data.zip`, SHA-256 `68c58568e3f0e4e7d0f0de3194a2ce7ca80703c057325ee402a94d3eab5a76c1`.
- Official inventory downloaded from `/files/910/lbnldatasynthesisinventory.pdf`: `sources/openei_910_inventory.pdf`, SHA-256 `0c241a4d1b125a54e8d73e29b59e316012aef722524c3ea531c2f71da79d7d4d`.

The archive contains `SZCAV.csv`, `SZVAV.csv`, `RTU.csv`, and MZVAV files. The page-level summary describes the collection as simulated, while the downloaded inventory's SZVAV section identifies the September 2017 FLEXLAB X3A controlled-test-cell experiments. We therefore use the file only with the narrower inventory-backed description: a public controlled test-cell record, not an operational-building record, and not a generic claim about the entire submission. The `SZVAV.csv` bytes are exactly identical to the previously retained FLEXLAB SZVAV file (`512992155cb43c576a3ba1e45b37f20966f42c5b05980428fec8008bd054ee93`; 1,207,524 bytes). This is a provenance confirmation, not a second independent dataset.

## Decision

OpenEI 910 is retained as the authoritative public download and provenance record for the selected SZVAV file. It is excluded from any claim of physical validation because the submission itself identifies the collection as simulated. The selected SZVAV file is treated as the FLEXLAB X3A controlled-test-cell dataset described by the accompanying inventory, with fault injection and ground-truth metadata kept outside diagnostic input. It is also excluded from any claim of operational-building deployment.

No alternative source is downloaded in this round: the official archive already contains the matching SZVAV bytes, and searching for another source would not change the physical-vs-simulated status without an independent event set.
