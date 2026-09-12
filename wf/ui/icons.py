"""Card-type icons, drawn from the same SVG paths the web builder used.

Rather than ship image files, the paths are parsed into QPainterPaths once and
stroked at whatever size and colour is asked for. That keeps the icons crisp on
a high-DPI display and keeps the accent colour a runtime argument, which is how
a module's own `accent` reaches its icon.

The parser handles exactly the subset these paths use: M, L, H, V, A and Z, in
absolute and relative form. It is not a general SVG implementation and does not
pretend to be - an unknown command raises rather than silently drawing nothing.
"""

import re

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (QColor, QGuiApplication, QIcon, QPainter, QPainterPath,
                           QPen, QPixmap)

# Viewbox for every path below.
VIEW = 16.0

PATHS = {
    'hash': 'M4 6h9M3 11h9M6 3l-1 11M11 3l-1 11',
    'columns': 'M3 12V6M6.5 12V3M10 12V8M13.5 12V5',
    'bar': 'M3 13V7M7 13V3M11 13V9M15 13v-2',
    'gauge': 'M2.5 12a5.5 5.5 0 1 1 11 0M8 12L11 7',
    'donut': 'M8 2a6 6 0 1 1-6 6 6 6 0 0 1 6-6zm0 3.6A2.4 2.4 0 1 0 10.4 8 2.4 2.4 0 0 0 8 5.6z',
    'list': 'M3 4h10M3 8h7M3 12h4',
    'line': 'M2 11l3.5-4 3 2.5L14 4',
    'table': 'M2 4h12v8H2zM2 7h12M6.5 4v8',
    'rows': 'M2 4h12M2 8h12M2 12h12',
    'text': 'M4 4h8M8 4v8M6 12h4',
    'heading': 'M3 8h3M11 8h2M7.5 4v8',
    # UI glyphs. Drawn rather than typed, because the obvious characters for
    # these (arrows, a sun, a padlock) are not in every Windows UI font and
    # come out as tofu boxes when they are missing.
    'undo': 'M3.2 8h6.3a3.2 3.2 0 0 1 0 6.4H6.5M3.2 8l3-3M3.2 8l3 3',
    'redo': 'M12.8 8H6.5a3.2 3.2 0 0 0 0 6.4h3M12.8 8l-3-3M12.8 8l-3 3',
    'moon': 'M13 9.2A5.4 5.4 0 0 1 6.8 3 5.6 5.6 0 1 0 13 9.2z',
    'sun': ('M8 3.2V1.6M8 14.4v-1.6M3.2 8H1.6M14.4 8h-1.6M4.6 4.6 3.5 3.5'
            'M12.5 12.5l-1.1-1.1M4.6 11.4l-1.1 1.1M12.5 3.5l-1.1 1.1'
            'M8 5.2A2.8 2.8 0 1 0 8 10.8 2.8 2.8 0 0 0 8 5.2z'),
    'lock': 'M5 7.4V5.4a3 3 0 0 1 6 0v2M3.9 7.4h8.2v6.1H3.9z',
}

_TOKEN = re.compile(r'([MmLlHhVvAaZz])|(-?\d*\.?\d+(?:e-?\d+)?)')

_cache = {}


def _numbers(spec):
    """Yield (command, [floats]) for each command in a path spec."""
    out = []
    cmd = None
    nums = []
    for m in _TOKEN.finditer(spec):
        if m.group(1):
            if cmd is not None:
                out.append((cmd, nums))
            cmd = m.group(1)
            nums = []
        else:
            nums.append(float(m.group(2)))
    if cmd is not None:
        out.append((cmd, nums))
    return out


def _arc_to(path, rx, ry, rot, large, sweep, x, y):
    """Endpoint-parameterised arc, converted to Qt's centre form.

    Qt has no endpoint arc, so this is the standard W3C implementation note
    conversion. The icon paths only use circular arcs, but the elliptical case
    costs nothing extra and avoids a surprise later.
    """
    import math

    x0, y0 = path.currentPosition().x(), path.currentPosition().y()
    if rx == 0 or ry == 0 or (x0 == x and y0 == y):
        path.lineTo(x, y)
        return
    rx, ry = abs(rx), abs(ry)
    phi = math.radians(rot)
    cos_p, sin_p = math.cos(phi), math.sin(phi)

    dx2, dy2 = (x0 - x) / 2.0, (y0 - y) / 2.0
    x1 = cos_p * dx2 + sin_p * dy2
    y1 = -sin_p * dx2 + cos_p * dy2

    # Scale radii up if they are too small to span the endpoints.
    lam = (x1 * x1) / (rx * rx) + (y1 * y1) / (ry * ry)
    if lam > 1:
        s = math.sqrt(lam)
        rx *= s
        ry *= s

    num = rx * rx * ry * ry - rx * rx * y1 * y1 - ry * ry * x1 * x1
    den = rx * rx * y1 * y1 + ry * ry * x1 * x1
    factor = math.sqrt(max(0.0, num / den)) if den else 0.0
    if large == sweep:
        factor = -factor
    cx1 = factor * rx * y1 / ry
    cy1 = -factor * ry * x1 / rx

    cx = cos_p * cx1 - sin_p * cy1 + (x0 + x) / 2.0
    cy = sin_p * cx1 + cos_p * cy1 + (y0 + y) / 2.0

    def angle(ux, uy):
        return math.degrees(math.atan2(uy, ux))

    start = angle((x1 - cx1) / rx, (y1 - cy1) / ry)
    end = angle((-x1 - cx1) / rx, (-y1 - cy1) / ry)
    sweep_deg = end - start
    if sweep and sweep_deg < 0:
        sweep_deg += 360.0
    elif not sweep and sweep_deg > 0:
        sweep_deg -= 360.0

    # Qt measures angles counter-clockwise from 3 o'clock; SVG measures
    # clockwise from the same place. Hence the sign flips.
    rect = QRectF(cx - rx, cy - ry, rx * 2, ry * 2)
    path.arcTo(rect, -start, -sweep_deg)


def painter_path(name):
    """QPainterPath for an icon name, cached."""
    if name in _cache:
        return _cache[name]
    spec = PATHS.get(name) or PATHS['hash']
    path = QPainterPath()
    cx = cy = 0.0
    start = (0.0, 0.0)
    for cmd, nums in _numbers(spec):
        rel = cmd.islower()
        up = cmd.upper()
        i = 0
        if up == 'Z':
            path.closeSubpath()
            cx, cy = start
            continue
        while i < len(nums) or (up in 'MLHV' and i == 0 and not nums):
            if up == 'M':
                x, y = nums[i], nums[i + 1]
                i += 2
                if rel:
                    x, y = cx + x, cy + y
                path.moveTo(x, y)
                cx, cy = x, y
                start = (x, y)
                up = 'L'  # subsequent pairs after an M are implicit line-tos
            elif up == 'L':
                x, y = nums[i], nums[i + 1]
                i += 2
                if rel:
                    x, y = cx + x, cy + y
                path.lineTo(x, y)
                cx, cy = x, y
            elif up == 'H':
                x = nums[i]
                i += 1
                if rel:
                    x = cx + x
                path.lineTo(x, cy)
                cx = x
            elif up == 'V':
                y = nums[i]
                i += 1
                if rel:
                    y = cy + y
                path.lineTo(cx, y)
                cy = y
            elif up == 'A':
                rx, ry, rot, large, sweep, x, y = nums[i:i + 7]
                i += 7
                if rel:
                    x, y = cx + x, cy + y
                _arc_to(path, rx, ry, rot, int(large), int(sweep), x, y)
                cx, cy = x, y
            else:
                raise ValueError('icon path uses unsupported command %r' % cmd)
            if i >= len(nums):
                break
    _cache[name] = path
    return path


def pixmap(name, size, colour, stroke=1.6, dpr=1.0):
    """Stroke an icon into a transparent pixmap of `size` logical pixels.

    Setting the device pixel ratio on the pixmap already puts the painter into
    logical coordinates, so the scale factor must NOT include dpr again - doing
    both draws the icon at twice the intended size and clips it, on exactly the
    scaled displays the argument exists to support.
    """
    px = max(1, int(round(size * dpr)))
    pm = QPixmap(px, px)
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.scale(size / VIEW, size / VIEW)
    pen = QPen(QColor(colour))
    pen.setWidthF(stroke)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawPath(painter_path(name))
    p.end()
    return pm


def icon(name, size, colour, dpr=None):
    """A QIcon at the display's real pixel density.

    Without the device pixel ratio the glyph is rendered at 1x and stretched,
    which is visibly soft next to anything Qt draws itself on a 125% or 150%
    Windows display - the default for most current laptops.
    """
    if dpr is None:
        app = QGuiApplication.instance()
        dpr = app.devicePixelRatio() if app else 1.0
    ic = QIcon()
    ic.addPixmap(pixmap(name, size, colour, dpr=dpr))
    return ic


def draw(painter, name, rect, colour, stroke=1.6):
    """Stroke an icon directly into a rect of an existing painter."""
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.translate(rect.x(), rect.y())
    painter.scale(rect.width() / VIEW, rect.height() / VIEW)
    pen = QPen(QColor(colour))
    pen.setWidthF(stroke * VIEW / max(rect.width(), 1e-6))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawPath(painter_path(name))
    painter.restore()


def tint(hex_colour, alpha):
    c = QColor(hex_colour)
    c.setAlphaF(alpha)
    return c


