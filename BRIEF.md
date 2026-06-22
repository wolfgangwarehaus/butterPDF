# butterPDF — Ingredients brief

*The first app baked with **dough** (`../dough`). Frosted, fast, fork-and-own — build
anywhere, deliver everywhere.* Status: **Ingredients** (this is the planning brief; the
feature/stack sections fill in when the research sweep lands).

## The why (the pain)
Filling + signing a PDF quickly on Arch / CachyOS is a frustrating, clunky experience.
butterPDF is the slick, fast, frosted PDF tool that *should* exist on Linux — a daily
driver for view + edit + **fill + sign** — and the first real app built with dough, so
it deploys anywhere virtually possible.

## Identity
- name **butterPDF** · slug `butterpdf` · display **butterPDF** · org `wolfgangwarehaus`
- pitch *(draft):* "Open, fill, sign, done — a fast frosted PDF tool."
- brand: the wolfgang warehaus bakery family (dough → butter → jelly).
- **icon** *(first-pass draft at `butterpdf.svg`)*: a filled **butter-yellow document**,
  slightly rounded corners, a folded top-right corner (reads as a *document*), and a
  tiny white shine. Refine in Baking once it can be rendered.

## Look & theming (decided — use dough's base for v1)
butterPDF ships dough's **base look** unchanged for v1 (the theming is a core dough
selling point, proven in jellytoast):
- **Frosted + solid, in light + dark** — four variants (*frosted* = the translucent
  blurred surface; *solid* = an opaque version).
- A **safety fallback** for systems with no native blur → degrade to the solid look so
  it never breaks.
- The **selectable accent color** (dough's existing feature).

Any visual changes *beyond* this base set are deferred to **Baking** (if wanted then).

## What it is (the vision, captured)
A clean, fast, **featured** PDF **viewer + editor** for Linux (CachyOS daily driver) that:
- looks slick, **opens fast**, integrates with the OS it's on;
- possibly works well with different **web browsers**;
- has a **super slick, easy signature system + form-filling system** — *the headline*;
- is **security-compliant + up to date with the best PDF standards**;
- has a light set of format options — **convert to/from JPEG / PNG**.

## Reuse from dough vs net-new
- **Reuse:** the frosted chrome, settings, single-instance, tray + notifications,
  autostart, and the whole Delivery channel matrix.
- **Net-new:** a **PDF engine** (Qt's `QtPdf` is currently *excluded* in dough's
  PyInstaller spec — re-enable or choose an engine; see research + the licensing note),
  the **fill/sign** system, and the **converters**.

## Delivery targets *(draft)*
Desktop-first: PyPI · `.deb` · AppImage · **Windows** · **macOS** · AUR. Built on
CachyOS, deployed everywhere.

## The differentiator (synthesized from the research sweep)

> **butterPDF is the first free, native, KDE-free Qt6 app that closes the whole loop —
> open → fill the real AcroForm fields → sign (slick reusable image *or* cryptographic
> PAdES, same gesture) → save with correct baked appearance streams → done — instantly
> and frosted, with no web server, no $69 watermark, and no AGPL in the binary.**

## Field & gap

No free Linux app closes the whole arc **open → fill the real fields → sign → save
correctly → done** in one fast, native app. Today a CachyOS user stitches together
**Okular** (annotate/sign — clunky, KDE-coupled, signing "needs a PhD"), **Xournal++**
(draws a *picture* of a signature, can't fill AcroForm fields), a **browser/pdf.js**
(fills, but the save/flatten step blanks the PDF), and **CLI** (merge). The only app
that does the whole job — **Master PDF Editor** — is proprietary, $69, and watermarks
every page. **Stirling-PDF** does everything but is a self-hosted Docker/JVM web
server — the wrong *shape* for "double-click a form and sign it."

**butterPDF's wedge is the whole-arc, single-app job:** drop file → fill the real
AcroForm fields → slick reusable signature → Save (correct in Adobe and print) → done.
Instant cold-open, OS file-association, **no KDE stack, no web server, no watermark, no
AGPL** — frosted Qt6 native on CachyOS.

## Recommended feature set (MVP + later)

> **MVP FINALIZED (2026-06-22): the 7 items below.** Quick-sign ships in v1;
> cryptographic Verifiable-sign is the **fast-follow** — so the MVP carries **zero PKI /
> cert dependency** (no pyHanko, no cert wizard), keeping the first loaf lean.

**MVP — the first loaf, prove the workflow:**
1. **Fast frosted viewer** — QtPdf/PDFium render, scroll, zoom, text-select, find; OS "Open with" integration.
2. **AcroForm fill that saves INTO the document** — Qt overlay widgets placed from field rects (read via pypdf); checkbox states matched to each widget's `/AP /N` export value.
3. **Correct save/flatten** (first-class, tested) — regenerate appearance streams (`auto_regenerate=False`) + explicit "Flatten for sending."
4. **Quick-sign — the v1 signature** — draw/type/import a signature, place it, save it for reuse ("sign in seconds" on repeat docs); composited into the page content (a valid everyday e-signature).
5. **Light converters** — PDF→PNG/JPEG (QtPdf render) and JPEG/PNG→PDF (img2pdf, lossless).
6. **Safe-open baseline** — no document JS execution; pikepdf sanitize pass; malformed PDFs fail to a toast, never a crash.
7. **XFA graceful-decline** — detect and notify, don't silently fill nothing.

**Fast-follow (the very next thing after v1):** **Verifiable-sign** — self-signed
**PAdES B-T** (signature + RFC-3161 timestamp) via **pyHanko**, reusing the *same*
Quick-sign PNG as the visible stamp; a **zero-openssl** first-run identity wizard. (The
make-or-break signing-onboarding UX risk lives here — which is exactly why it's a
focused fast-follow, not v1.)

**Later:** **PDF dark mode** — invert bright pages to dark-grey *or* OLED-black with text re-colored to match, a setting **independent of the app chrome theme** (light chrome + dark PDFs is valid); Tier 3 PKCS#11 smartcard/QES signing; PAdES B-LT/B-LTA (LTV); full annotation set; page organize (rotate/reorder/merge/split); signature validation panel; AES-256 encryption + PDF/A export; careful browser integration; preserve PDF/UA tags on edit.

## Recommended stack (with licenses)

A clean **two-engine split** — QtPdf renders but can't edit; pikepdf edits but can't render:

| Role | Library | License | Why |
|------|---------|---------|-----|
| View engine | **PySide6 QtPdf** (PDFium) | GPLv2/LGPLv3 + BSD-3 | Already in dough; fast viewer + text-select + find + render-to-image, zero new native dep. **Render-only.** |
| Forms (fill) | **pypdf** | BSD-3-Clause | Reads field rects, fills with `auto_regenerate=False` to bake real appearance streams. |
| Forms (structure) | **pikepdf** (QPDF) | MPL-2.0 | Repair/normalize AcroForm, flatten edge cases, robust linearized save, sanitize, encryption. |
| Easy sign | **Qt ink canvas → PNG → pikepdf** | MPL-2.0 / BSD | Composite a reusable signature onto the page; zero PKI, zero AGPL. |
| Crypto sign | **pyHanko** | MIT | PAdES B-B→B-LTA, RFC-3161 timestamps, self-signed→PKCS#12→PKCS#11; reuses the drawn PNG as the visible stamp. |
| Convert | **img2pdf** + **Pillow** | LGPLv3 / HPND | Lossless images→PDF; PDF→image via QtPdf `render()`. |

## OS + browser integration

Native desktop is the category advantage over Stirling-PDF: **instant cold-open**, real
**file-association / "Open with"**, no Docker/localhost/JVM. Store the user's signature(s)
and self-signed identity in the **OS keychain** for "sign in seconds." Browser
integration is **post-MVP** and must be careful — never proxy an untrusted PDF into a
JS-executing context.

## Standards & security

- **Forms:** AcroForm only (PDF 2.0). **XFA explicitly out of scope** — dead across the Python ecosystem; graceful-decline only.
- **Signing:** target **PAdES** (ETSI/EU). MVP ships **B-T** (signature + TSA timestamp); B-LT/B-LTA (LTV) post-MVP. Honest eIDAS ladder: Quick-sign = SES (everyday), Verifiable = AES-grade tamper-evidence, Certified (later) = AES/QES via smartcard.
- **Security:** PDFium **never executes document JavaScript** (advertisable). pikepdf **sanitize** strips `/OpenAction`, `/AA`, `/JavaScript`, `/Launch`, `/EmbeddedFiles`, warns on external URIs. **Treat all input as hostile** — auto-repair + try/except so booby-trapped PDFs degrade to an error, never code-exec/crash.

## Key risks & open decisions

- **AGPL trap (decided):** PyMuPDF + **fillpdf** (transitively PyMuPDF) are AGPL-3.0 — **hard no** for a frozen GPL-2.0-or-later binary. Reject python-poppler too (GPL, heavier, no edit advantage).
- **"or-later" is load-bearing:** keep SPDX `GPL-2.0-or-later`; it legally admits the LGPLv3 PySide6/img2pdf deps. Ship a **NOTICES/THIRD-PARTY-LICENSES** file; for LGPLv3 deps in frozen binaries, satisfy the relink obligation.
- **Save/flatten correctness** is make-or-break — regenerate appearance streams + **test the Adobe + print round-trip**, or butterPDF is "just another viewer."
- **Signing onboarding UX** must be truly zero-config (no openssl) or Tier 2 is dead on arrival — the concrete way to beat Okular.
- **Two-engine round-trip latency** (mutate via pypdf/pikepdf → reload in QtPdf) must stay invisible behind snappy Qt overlay editing.
- **Scope discipline:** XFA out; don't chase Master PDF Editor's full content-editing depth. The wedge is fill+sign+save without watermark/paywall/KDE-stack — not feature parity.
