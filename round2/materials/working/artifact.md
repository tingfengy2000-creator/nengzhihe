# Official template execution contract

The three retained DOCX references and supplied guide are authoritative. Reference SHA-256 and all package-part hashes are in template_inventory.json. The first-round references are read-only.

Page system: one A4 portrait section per template, top/bottom 25.4 mm, left/right 31.75 mm, original header/footer distances and line grid preserved. Exact section XML is stored in the inventory. Page counts are unresolved until permitted rendering succeeds.

Typography: preserve original title font 方正小标宋简体 at 18 pt and original alignment. Preserve body 仿宋 14 pt and 1.5 line spacing in technical/commercial templates; brief table body mainly 仿宋 12 pt. Clone original paragraph and run properties only. Preserve source styles, embedded fonts, theme, footer PAGE fields, customXml shape data and all relationships byte-for-byte.

Tables: preserve the original brief 20-row merged table and its nested 5-column, 6-row metric table. Source atLeast row heights remain; no fixed row heights are introduced. Original column grids, merges, padding and border properties remain unchanged. New metric content uses all five official data rows.

Editable package parts: document.xml content slots; settings.xml updateFields only; docProps/core.xml, custom.xml and app.xml anonymous metadata/cached statistics. All other package parts and relationships are preserve-only. Core creators and custom properties are scrubbed; cached page/word statistics are reset until rendering. Draft marker replaces template marker under explicit user authorization. Identity fields stay visible as anonymous placeholders.

Slot map: brief original body table rows/cells (zero based) name 0/1, team 1/1, track 2/1, captain 3/1, phone 3/3, members 4/1, background 6/1, idea 8/1, solution 10/1, business 12/1, stage 13/2, advance 14/2, outputs 15/2, TRL 16/2 unchanged unselected, comparators 17/2, nested metrics 18/2, improvement 19/2. Technical original body indexes: marker 3, project title 4, rationale 6, innovation anchors 8/9/10, implementation 12, prospect anchor 13. Commercial original body indexes: marker 3, project title 4, overview 5, team 6, product 8/9, market 11/12/13, business 15/16/17/18, economics 19. Original headings remain unchanged.

Content flow: brief compresses problem, idea, solution and business; technical preserves four chapters and three original innovation subheadings; business preserves six chapters and all original subheadings. No new chapter or decorative design system is introduced. Body text and official metrics remain editable native Word text.

Fidelity gates: input references unchanged, preserve-only bytes unchanged, same section geometry, required headings present, draft marker present, all 14 capped sections pass, no identifiable team metadata, all declared numbers bound to actual aggregate output. DOCX rendering and page visual review remain a separate unfinished gate if the bundled renderer is unavailable. The explicit user request permits delivery of marked editable drafts without declaring them final submissions.
