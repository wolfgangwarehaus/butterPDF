"""SignatureDialog — create a signature by drawing, typing, or importing.

Returns a transparent-background :class:`QImage` (via :meth:`signature_image`) the
viewer then places on the page. Frameless + frosted to match the app.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from butterpdf import signature, ui_helpers
from butterpdf.design_tokens import BTN_PRIMARY, TYPE_BODY, button_qss, type_qss
from butterpdf.frosted_dialog import FrostedDialog
from butterpdf.selector import Selector, selector_qss

_INK = QColor(20, 24, 40)


class InkCanvas(QWidget):
    """A draw-your-signature surface. Free-hand strokes on a transparent image."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(520, 180)
        self._img = QImage(self.size(), QImage.Format.Format_ARGB32)
        self._img.fill(Qt.GlobalColor.transparent)
        self._last: QPoint | None = None
        self._drawn = False
        self._pen_width = 2.6
        self._ink = QColor(_INK)

    def set_pen_width(self, w: float) -> None:
        self._pen_width = max(0.5, float(w))

    def set_ink(self, color: QColor) -> None:
        self._ink = QColor(color)

    def resizeEvent(self, e) -> None:  # noqa: N802
        new = QImage(self.size(), QImage.Format.Format_ARGB32)
        new.fill(Qt.GlobalColor.transparent)
        p = QPainter(new)
        p.drawImage(0, 0, self._img)  # keep what's drawn
        p.end()
        self._img = new

    def mousePressEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            self._last = e.position().toPoint()

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        if self._last is None:
            return
        p = QPainter(self._img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(self._ink, self._pen_width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        now = e.position().toPoint()
        p.drawLine(self._last, now)
        p.end()
        self._last = now
        self._drawn = True
        self.update()

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        self._last = None

    def paintEvent(self, e) -> None:  # noqa: N802
        p = QPainter(self)
        # a subtle baseline + a soft frame so the canvas reads as a sign-here box
        p.fillRect(self.rect(), QColor(255, 255, 255, 235))
        p.setPen(QPen(QColor(0, 0, 0, 30)))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        y = int(self.height() * 0.72)
        p.setPen(QPen(QColor(0, 0, 0, 40)))
        p.drawLine(24, y, self.width() - 24, y)
        p.drawImage(0, 0, self._img)
        p.end()

    def clear(self) -> None:
        self._img.fill(Qt.GlobalColor.transparent)
        self._drawn = False
        self.update()

    def image(self) -> QImage | None:
        return signature.trim(self._img) if self._drawn else None


class SignatureDialog(FrostedDialog):
    """Create a signature (Draw / Type / Import). Read :meth:`signature_image`
    after ``exec()`` returns Accepted."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, title="Signature", icon_name="edit", min_width=560)
        self.setModal(True)
        self.setStyleSheet(self.styleSheet() + selector_qss())  # legible dropdowns
        self._result: QImage | None = None
        self._imported: QImage | None = None

        # mode switch
        modes = QHBoxLayout()
        self._stack = QStackedWidget()
        for i, name in enumerate(("Draw", "Type", "Import")):
            b = QPushButton(name)
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(self._mode_qss())
            b.clicked.connect(lambda _=False, idx=i: self._set_mode(idx))
            modes.addWidget(b)
            setattr(self, f"_mode_btn_{i}", b)
        modes.addStretch(1)
        self.content_layout.addLayout(modes)

        # Draw
        self._canvas = InkCanvas()
        draw = QWidget()
        dl = QVBoxLayout(draw)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.addWidget(self._canvas)

        # pen controls: thickness slider + colour swatches (+ custom) + Clear
        from PySide6.QtWidgets import QSlider

        row = QHBoxLayout()
        row.setSpacing(8)
        thin = QLabel("Pen")
        thin.setStyleSheet(f"color:{ui_helpers.TEXT}; {type_qss(TYPE_BODY)}")
        row.addWidget(thin)
        self._pen_slider = QSlider(Qt.Orientation.Horizontal)
        self._pen_slider.setRange(1, 12)
        self._pen_slider.setValue(3)
        self._pen_slider.setFixedWidth(120)
        self._pen_slider.valueChanged.connect(self._canvas.set_pen_width)
        row.addWidget(self._pen_slider)
        for hex_ in ("#141828", "#000000", "#1a4fd0", "#c62828", "#1b7f3b"):
            row.addWidget(self._colour_swatch(hex_))
        custom = QPushButton("…")
        custom.setToolTip("Custom colour")
        custom.setFixedSize(24, 24)
        custom.setStyleSheet(self._mode_qss())
        custom.setCursor(Qt.CursorShape.PointingHandCursor)
        custom.clicked.connect(self._pick_ink)
        row.addWidget(custom)
        row.addStretch(1)
        clear = QPushButton("Clear")
        clear.setStyleSheet(self._mode_qss())
        clear.setCursor(Qt.CursorShape.PointingHandCursor)
        clear.clicked.connect(self._canvas.clear)
        row.addWidget(clear)
        dl.addLayout(row)
        self._stack.addWidget(draw)

        # Type
        typ = QWidget()
        tl = QVBoxLayout(typ)
        tl.setContentsMargins(0, 0, 0, 0)
        self._type_edit = QLineEdit()
        self._type_edit.setPlaceholderText("Type your name")
        self._type_edit.setStyleSheet(
            f"QLineEdit{{background:rgba(255,255,255,0.94);border:1px solid {ui_helpers.ACCENT};"
            f"border-radius:4px;color:#111;padding:6px 8px;{type_qss(TYPE_BODY)}}}"
        )
        from PySide6.QtGui import QFont

        self._type_font = Selector()
        self._type_font.setFixedWidth(240)
        for fam in self._script_fonts():
            self._type_font.addItem(fam, fam, font=QFont(fam))  # preview in-face
        self._type_preview = QLabel()
        self._type_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._type_preview.setMinimumHeight(150)
        self._type_preview.setStyleSheet("background:rgba(255,255,255,0.94);border-radius:4px;")
        self._type_edit.textChanged.connect(self._update_type_preview)
        self._type_font.currentIndexChanged.connect(self._update_type_preview)
        tl.addWidget(self._type_edit)
        tl.addWidget(self._type_font)
        tl.addWidget(self._type_preview)
        self._stack.addWidget(typ)

        # Import
        imp = QWidget()
        il = QVBoxLayout(imp)
        il.setContentsMargins(0, 0, 0, 0)
        pick = QPushButton("Choose image…")
        pick.setStyleSheet(button_qss(BTN_PRIMARY))
        pick.setCursor(Qt.CursorShape.PointingHandCursor)
        pick.clicked.connect(self._pick_image)
        self._import_preview = QLabel("Pick a PNG/JPG of your signature.\nNear-white becomes transparent.")
        self._import_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._import_preview.setMinimumHeight(150)
        self._import_preview.setStyleSheet(
            f"background:rgba(255,255,255,0.94);border-radius:4px;color:#333;{type_qss(TYPE_BODY)}"
        )
        il.addWidget(pick)
        il.addWidget(self._import_preview)
        self._stack.addWidget(imp)

        self.content_layout.addWidget(self._stack)

        # actions
        actions = QHBoxLayout()
        actions.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.setStyleSheet(self._mode_qss())
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        use = QPushButton("Use signature")
        use.setStyleSheet(button_qss(BTN_PRIMARY))
        use.setCursor(Qt.CursorShape.PointingHandCursor)
        use.clicked.connect(self._accept)
        actions.addWidget(cancel)
        actions.addWidget(use)
        self.content_layout.addLayout(actions)

        self._set_mode(0)

    # ── public ────────────────────────────────────────────────────────────
    def signature_image(self) -> QImage | None:
        return self._result

    # ── modes ─────────────────────────────────────────────────────────────
    def _set_mode(self, idx: int) -> None:
        self._stack.setCurrentIndex(idx)
        for i in range(3):
            getattr(self, f"_mode_btn_{i}").setChecked(i == idx)

    def _current_image(self) -> QImage | None:
        idx = self._stack.currentIndex()
        if idx == 0:
            return self._canvas.image()
        if idx == 1:
            text = self._type_edit.text().strip()
            fam = self._type_font.currentData() or ""
            return signature.render_typed(text, font_family=fam) if text else None
        return self._imported

    def _accept(self) -> None:
        img = self._current_image()
        if img is not None and not img.isNull():
            self._result = img
            self.accept()

    # ── type ──────────────────────────────────────────────────────────────
    def _update_type_preview(self) -> None:
        from PySide6.QtGui import QPixmap

        text = self._type_edit.text().strip()
        if not text:
            self._type_preview.setPixmap(QPixmap())
            return
        fam = self._type_font.currentData() or ""
        img = signature.render_typed(text, font_family=fam)
        pm = QPixmap.fromImage(img).scaled(
            self._type_preview.width() - 16, self._type_preview.height() - 16,
            Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
        )
        self._type_preview.setPixmap(pm)

    @staticmethod
    def _script_fonts() -> list[str]:
        """Prefer installed cursive/script faces; always include a sensible fallback."""
        from PySide6.QtGui import QFontDatabase

        installed = set(QFontDatabase.families())
        wanted = [
            "Segoe Script", "Brush Script MT", "Lucida Handwriting", "Comic Sans MS",
            "URW Chancery L", "Z003", "Dancing Script", "Great Vibes", "Pacifico",
        ]
        found = [f for f in wanted if f in installed]
        # Fall back to any serif so Type always works; italic sells the signature look.
        return found or ["Z003", "DejaVu Serif", "Serif"]

    # ── draw controls ─────────────────────────────────────────────────────
    def _colour_swatch(self, hex_: str) -> QPushButton:
        b = QPushButton()
        b.setFixedSize(22, 22)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setToolTip(hex_)
        b.setStyleSheet(
            f"QPushButton{{background:{hex_};border:1px solid rgba(0,0,0,0.35);"
            f"border-radius:11px;}}QPushButton:hover{{border:2px solid {ui_helpers.ACCENT};}}"
        )
        b.clicked.connect(lambda _=False, h=hex_: self._canvas.set_ink(QColor(h)))
        return b

    def _pick_ink(self) -> None:
        from PySide6.QtWidgets import QColorDialog

        c = QColorDialog.getColor(self._canvas._ink, self, "Pen colour")
        if c.isValid():
            self._canvas.set_ink(c)

    # ── import ────────────────────────────────────────────────────────────
    def _pick_image(self) -> None:
        from PySide6.QtGui import QPixmap

        path, _ = QFileDialog.getOpenFileName(
            self, "Choose signature image", "", "Images (*.png *.jpg *.jpeg *.bmp)"
        )
        if not path:
            return
        img = signature.load_image(path)
        if img is None:
            return
        self._imported = signature.whiten_to_transparent(img)
        pm = QPixmap.fromImage(self._imported).scaled(
            self._import_preview.width() - 16, self._import_preview.height() - 16,
            Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
        )
        self._import_preview.setPixmap(pm)

    # ── styling ───────────────────────────────────────────────────────────
    @staticmethod
    def _mode_qss() -> str:
        a = ui_helpers.ACCENT
        return (
            f"QPushButton{{background:transparent;color:{ui_helpers.TEXT};border:1px solid {a};"
            f"border-radius:6px;padding:5px 14px;{type_qss(TYPE_BODY)}}}"
            f"QPushButton:checked{{background:{a};color:#fff;}}"
            f"QPushButton:hover{{background:rgba(255,255,255,0.10);}}"
            f"QComboBox{{background:rgba(255,255,255,0.94);color:#111;border:1px solid {a};"
            f"border-radius:4px;padding:4px 8px;}}"
        )
