# Official template execution contract

Reference files remain authoritative and unchanged. This is an internal generation contract, not a submission document.

Render status: unresolved. The official packaged renderer failed because no allowed LibreOffice executable is available. Page counts and visual template patterns are therefore unverified. DOCX creation is gated; text drafts are permitted.

Page system: one portrait A4 section per template; top/bottom margins 25.4 mm; left/right 31.75 mm. Exact section XML and package hashes are recorded in template_inventory.json.
Typography: preserve source properties. Original title predominantly FangZheng XiaoBiaoSong 18 pt centered; technical/commercial body FangSong 14 pt, 1.5 lines; brief table FangSong 12 pt. Do not substitute generic styles.
Tables: preserve all source grids, merges, row rules and nested table. Rows use atLeast height. Brief table has 20 rows and one nested 5-column metric table. Fonts are embedded in source package and remain byte-identical.
Recurring components: preserve original footer including drawing/text-box elements and two PAGE fields in AlternateContent branches; customXml contains WPS shape properties; no body content controls or revisions found. Footer appearance remains a render-gate uncertainty. Set updateFields=true in settings to request refresh on Word open; do not flatten page numbers or rewrite the footer.
Editable package parts: document.xml for listed slots; settings.xml only for updateFields; core/custom/app properties for anonymous metadata. Every other part is preserve-only and must keep its SHA-256. Blank creator/lastModifiedBy, tracking identifiers, application fingerprint, cached statistics are intentional anonymity/accuracy deviations.

Stable slot map
Template 1: word/document.xml / w:body / w:tbl[1], zero-based row/cell slots: name 0/1; team 1/1; track 2/1; captain 3/1; phone 3/3; members 4/1; background 6/1; idea 8/1; solution 10/1; business 12/1; stage 13/2; advancement 14/2; outputs 15/2; TRL 16/2; comparators 17/2; nested metrics 18/2; improvement 19/2. Keep captions and merged label cells unchanged.
Template 2: original direct w:body child indexes: 6 rationale slot; 8/9/10 innovation subhead anchors; 12 implementation slot; 13 prospect heading anchor. Paragraph 3 is a draft status marker. Preserve other headings. Clone source body paragraph properties when adding content.
Template 3: original direct body child anchors 5 overview; 6 team; 8/9 product subheads; 11/12/13 market subheads; 15/16/17/18 business subheads; 19 economics. Preserve headings and exact source styles.

Fidelity gates: reference SHA unchanged; same section geometry and package part set; preserve-only hashes unchanged; edits confined to mapped content and anonymous metadata; per-section character caps pass; no invented identity/performance; all final pages rendered and visually inspected.