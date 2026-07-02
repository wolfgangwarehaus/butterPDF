# butterPDF — TODO / handoff

## ▶ Wind-down 2026-07-02 — MVP v1 FEATURE-COMPLETE

butterPDF is the **first loaf** baked with dough — the dogfood that drove dough's
development. **All B milestones done + pushed** (`main` @ `92cf97b`, public at
github.com/wolfgangwarehaus/butterPDF, CI green, 131 tests):

- **B1 fill** — butterPDF's own rendered page view (`page_view.py`, exact coordinate
  mapping for overlays); 6 **document backgrounds** (Auto/White/Light-grey/Dark-grey/OLED/
  Transparent); **image-preserving smart dark mode** (`recolor` + pypdf image regions);
  editable AcroForm field overlays (`pdf_forms.py` + `form_layer.py`); non-modal live Settings.
- **B2 save/flatten** — `pdf_save.py`: pypdf fill w/ regenerated appearance streams (verified
  in Adobe/browser) → pikepdf finalize (sanitize + stamp) → atomic write. Menu Save/Save As/
  Flatten + Ctrl+S.
- **B3 Quick-sign** — `signature.py`/`sign_dialog.py`/`sign_overlay.py`: draw (pen thickness+
  colour) / type (script font) / import; place (drag/resize/delete); composited as an image
  XObject w/ SMask on save.
- **B4 converters** — `convert.py`: PDF→PNG/JPEG + images→PDF (img2pdf).
- **B5 safe-open** — `safety.py`: inspect (active-content/XFA notice bar) + sanitize output.

Deps: PySide6 + numpy + pypdf + pikepdf + img2pdf (installed here via `--break-system-packages`;
declared in pyproject).

**▶ Next session:** (1) the user's **thorough walkthrough + refinements** (known: signature
UX polish, checkbox indicator sizing, whatever the walkthrough surfaces); (2) **first real
release** through dough's Delivery matrix (Milestone C — needs dough's C1 Delivery helpers +
`v0.1.0`). Fast-follow per BRIEF: cryptographic Verifiable-sign (PAdES via pyHanko). Sample
form for smoke: `/tmp/butterpdf_sample_form.pdf` (regenerate if gone).

---

Original brief is `BRIEF.md`; the shared game plan lives in `../dough/docs/TODO.md`.

## The goal (settled 2026-07-02, with the user)

> Ship **butterPDF v1** to real users through dough's Delivery matrix — the frosted,
> fast, native Linux PDF tool that closes the whole arc **open → fill real AcroForm
> fields → sign → save correctly → done**, with no web server, no $69 watermark, no AGPL.

This arc is **interleaved and butterPDF-led**: every dough gap butterPDF hits gets fixed
*in dough* as it comes up (chrome-machinery, the fork-sync tool, Delivery helpers). See
`../dough/docs/TODO.md` for the dough-side tasks.

## Repo state
- Branch `main`, public at github.com/wolfgangwarehaus/butterPDF (CI green).
- Synced onto dough's current base via `dough-sync.toml` (synced_from `945a434`); pull future
  base updates with `python ../dough/dev/sync_loaf.py --loaf .`.
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
