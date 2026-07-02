# butterPDF — TODO / handoff

Status as of **2026-07-02**. butterPDF is the **first loaf** baked with dough — the
dogfood that drives dough's development. It has **MVP #1 (the QtPdf viewer)** + a deep
first-looks polish loop (which drove dough's design backport). The full brief is
`BRIEF.md`; the shared game plan lives in `../dough/docs/TODO.md`.

## The goal (settled 2026-07-02, with the user)

> Ship **butterPDF v1** to real users through dough's Delivery matrix — the frosted,
> fast, native Linux PDF tool that closes the whole arc **open → fill real AcroForm
> fields → sign → save correctly → done**, with no web server, no $69 watermark, no AGPL.

This arc is **interleaved and butterPDF-led**: every dough gap butterPDF hits gets fixed
*in dough* as it comes up (chrome-machinery, the fork-sync tool, Delivery helpers). See
`../dough/docs/TODO.md` for the dough-side tasks.

## Repo state
- Branch `master`, **no git remote yet** — first job is `gh repo create` + push (task A3).
- Forked from dough **2026-06-22, before the macOS absorption** → it's a diverged fork on
  an older base. It'll catch up via the new dough→loaf sync tool (task A4), *not* a re-fork.
- Source at `/home/august/Projects/butterPDF/butterpdf/`. Viewer is `viewer.py`.

## ▶ Pick up here: the MVP engine (net-new, the wedge)

Per `BRIEF.md` §"Recommended feature set". Build in order — each is a task in the tracker:

1. **B1 · AcroForm fill** (pypdf) — Qt overlay widgets from field rects; checkbox states
   matched to each widget's `/AP /N` export value; fills save INTO the doc. Add `pypdf`;
   re-enable QtPdf in the PyInstaller spec if still excluded.
2. **B2 · Correct save/flatten — the make-or-break** — regenerate appearance streams
   (`auto_regenerate=False`) + explicit "Flatten for sending." **TEST the Adobe + print
   round-trip.** `pikepdf` for structure/normalize. If this is wrong, butterPDF is "just
   another viewer."
3. **B3 · Quick-sign** — draw/type/import a reusable signature, composite onto the page
   (zero PKI in v1; store in OS keychain). Cryptographic PAdES is the fast-follow.
4. **B4 · Converters** — PDF→PNG/JPEG (QtPdf render) + JPEG/PNG→PDF (`img2pdf`, lossless).
5. **B5 · Safe-open + XFA decline** — pikepdf sanitize (strip `/OpenAction`, `/AA`,
   `/JavaScript`, `/Launch`, `/EmbeddedFiles`); malformed → toast, never a crash; detect
   XFA and notify (graceful-decline).

Then **C3 · first real release** through dough's Delivery matrix (uses dough's C1 helpers).

## Stack (decided — licensing-clean, no AGPL)
QtPdf (view) · pypdf (fill, BSD) · pikepdf (structure, MPL) · Qt ink→PNG→pikepdf
(quick-sign) · img2pdf/Pillow (convert). **Hard no** on PyMuPDF/fillpdf (AGPL) in a
frozen GPL binary. See `BRIEF.md` §"Recommended stack".

## Feature backlog (post-MVP)
- **Verifiable-sign** (fast-follow) — self-signed PAdES B-T via pyHanko, reusing the
  Quick-sign PNG; zero-openssl first-run identity wizard.
- **PDF dark mode** — invert bright pages to dark-grey/OLED-black, text re-colored;
  a setting **independent of the app chrome theme**.
- Tier-3 PKCS#11/QES · PAdES B-LT/B-LTA (LTV) · annotations · page organize · encryption.
