# butterPDF — TODO / handoff

## ▶ Engine findings — AI stress-test 2026-07-07 (fix before or right after C3)

An adversarial stress pass (real APIs, outputs verified with pypdf+pikepdf+QtPdf+
poppler; repros in the session scratchpad `pdf-stress/`) found 3 open engine bugs.
Fixed same day: AES owner-password-only PDFs (the common "permissions-restricted"
file) used to silently lose the form and raise on save — `cryptography>=3.1` is
now a declared dependency and the case works end-to-end.

- **S1 (HIGH, data loss): hierarchical field values silently dropped on save** —
  a parent field carrying `/FT` with named widget kids (`/T person` + kid
  `/T first`, a common Acrobat shape): `read_fields` names it `person.first`,
  but pypdf matches such widgets by the PARENT's qualified name, so
  `save_filled` writes nothing — no /V, no error. Fill by `person` works
  (key-mismatch proven). Fix in the read/save key mapping.
- **S2 (HIGH): rotated pages (`/Rotate 90`) — signatures baked in the wrong
  place, field overlays misplaced on screen** — `pt_to_px`/`px_to_pt` use the
  rotation-applied `pagePointSize` with no rotation transform, while
  `_finalize` stamps in unrotated user space. A signature dropped at one corner
  renders at another, mostly off-page. Apply the `/Rotate` transform in the
  coordinate mapping + when baking.
- **S3 (MEDIUM): CJK/emoji fill values bake as literal `?` glyphs** in the
  regenerated appearance (WinAnsi/Helvetica); `/V` is correct but flatten makes
  the `?`s permanent. Embed a Unicode-capable font or warn instead of baking.
  (Umlauts, long strings, delimiter chars all round-trip fine.)

Everything else passed: radio groups, combo/list boxes, multi-page forms,
non-`/Yes` checkbox on-states, damaged-file handling (no hangs, atomic-tmp
clean), safety flagging (JS/AA/XFA/EmbeddedFiles + sanitize), signature edge
placement.

## ▶ Resume here (after 2026-07-07)

New machine (fresh CachyOS) fully set up; 180 tests, 3-OS CI green @ `c5f2575`;
`cryptography` is now a declared dep (see the stress findings above). The
walkthrough artifacts were regenerated on this machine (`/tmp/butterpdf_sample_form.pdf`,
`/tmp/walk_filled_v2.pdf`, `/tmp/walk_flattened_v2.pdf`). **Next: (1) pull dough's
rig/deliver fixes — `python ../dough/dev/sync_loaf.py --loaf . --apply` → test →
commit → `--record`; (2) fix S1 + S2 above (HIGH — S1 is silent data loss);
(3) the walkthrough's in-person tail — open `/tmp/walk_flattened_v2.pdf` in
Okular/Firefox (✕ visible, name baked, nothing editable) + drag/zoom/scroll feel
verdicts; (4) C3 ship — `butterpdf-deliver` walks it (PyPI name `butterpdf` is
FREE; dough publishes as `dough-base`, decided; needs dough's first tag).**

## ▶ Audit 2026-07-03 — CI was quietly red; fixed

Two CI defects found + fixed (details in `../dough/docs/TODO.md` §Audit 2026-07-03):
`macos.yml` failed GitHub's parse on every push (`secrets` in a step `if:` → env-gated
now), and `lint-and-smoke` was red since B1 (installed only `ruff PySide6` while the
smoke imports numpy/pypdf → now `pip install ruff -e .`). Local health: 131 passed,
ruff clean. The B1–B5 build list that used to sit below is done — see the wind-down.

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
- Branch `main`, public at github.com/wolfgangwarehaus/butterPDF (all workflows green
  as of the 2026-07-03 CI fix — when claiming green, check EVERY workflow, not just `CI`).
- Synced onto dough's current base via `dough-sync.toml` (synced_from `945a434`); pull future
  base updates with `python ../dough/dev/sync_loaf.py --loaf .`.
- Source at `/home/august/Projects/butterPDF/butterpdf/`. Viewer is `viewer.py`.

## ▶ Pick up here: ship it (Milestone C)

The MVP engine (B1–B5) is **done** — see the wind-down block at the top. What remains:

1. **The user's thorough walkthrough** (in person, real KDE Wayland) + whatever
   refinements it surfaces (known: signature UX polish, checkbox indicator sizing).
   **2026-07-03 — the RIGGED half is done** (AI-driven on the live desktop): all 5
   document backgrounds shot + reviewed (dark modes preserve images ✓), fill→save
   verified (values + 5/5 regenerated /AP), flatten + PDF⇄PNG round trip + safe-open
   all green via the real APIs.
   **2026-07-03 evening — August drove the hands-on pass; the findings below were
   FIXED live** (commits e075b26 + 354ac48): the ink rework (smooth quad paths,
   DPR-crisp, no joint smear, tap-dots, light-grey paper — August: "signature is
   better!"), R1 baked-✕ appearances (proven in the flattened render), R2 settled
   (bright fields on dark stay), R3 CLI front (argparse help/version/PDF-guard),
   R4 editable install run (README already documented it). STILL OPEN from the
   walkthrough: the cross-viewer check of the saved PDFs + general feel verdicts.
   **Original findings, for the record:**
   - **R1 (real edge): checkbox visual can silently vanish on save** — a form whose
     checkbox has NO usable on-state appearance stream (null /AP /N entries; the
     rigged sample repros it) saves /V=/Yes correctly but renders UNCHECKED in other
     viewers, while butterPDF's own ✕ overlay makes it look checked in-app. Fix idea:
     at save, bake an ✕ appearance for any checked box whose on-state stream is
     missing/empty (mirror the screen). Repro: /tmp/butterpdf_sample_form.pdf.
   - **R2 (judgment call): field fills stay LIGHT in the dark document modes** —
     bright blocks against an OLED page. Deliberate (editable = bright)? Or should
     fills follow the page? August decides on the hands-on pass.
   - pypdf's flatten leaves the 5 field objects in the AcroForm dict (appearance is
     baked; interactivity in Adobe = August's cross-viewer check, artifacts sent).
   - **R3: no CLI front** — `butterpdf --help` opens the app and treats `--help` as a
     file path. Add a tiny argparse (help/version/positional file) before release.
   - **R4 (maker experience)**: the checkout had no install story until the editable
     install landed 2026-07-03 (`pip install -e . --break-system-packages`) — running
     your own loaf should be step zero; fold a dev-install line into the README/AGENTS.
2. **C3 · first real release** through dough's Delivery matrix — needs dough's C1
   Delivery helpers + dough `v0.1.0`. See `../dough/docs/TODO.md` for the C plan.
3. Fast-follow per BRIEF: cryptographic Verifiable-sign (PAdES via pyHanko).

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
