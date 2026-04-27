import cv2
import numpy as np

class ColorFinder:
    """
    Minimal color mask helper.
    - color_type: 'HSV', 'BGR', 'LAB', 'YCB', 'GREY'
    - center: (A,B,C) channel center
    - tol: (A,B,C) tolerance (always enabled)
    """
    def __init__(self, color_type: str = "HSV"):
        self.color_type = color_type
        self.center = (120, 120, 120)
        self.tol = (0, 0, 0)

    def set_center(self, center):
        if isinstance(center, (list, tuple)):
            if len(center) == 3:
                self.center = (int(center[0]), int(center[1]), int(center[2]))
            else:
                v = int(center[0])
                self.center = (v, v, v)
        else:
            v = int(center)
            self.center = (v, v, v)

    def set_tolerance(self, tol):
        if isinstance(tol, (list, tuple)):
            if len(tol) == 3:
                self.tol = (int(tol[0]), int(tol[1]), int(tol[2]))
            else:
                v = int(tol[0])
                self.tol = (v, v, v)
        else:
            v = int(tol)
            self.tol = (v, v, v)

    def set_color_type(self, color_type: str):
        self.color_type = color_type

    def enable_tolerance(self, _enable: bool):
        return

    def caps(self):
        if self.color_type == "HSV":
            return (179, 255, 255)
        if self.color_type in ("BGR", "LAB", "YCB"):
            return (255, 255, 255)
        if self.color_type == "GREY":
            return (255, 0, 0)
        return (255, 255, 255)

    def bounds_from_center_tol(self):
        a, b, c = self.center
        ta, tb, tc = self.tol
        capA, capB, capC = self.caps()
        amin = max(0, a - ta)
        amax = min(capA, a + ta)
        bmin = max(0, b - tb)
        bmax = min(capB, b + tb)
        cmin = max(0, c - tc)
        cmax = min(capC, c + tc)
        return {"amin": amin, "bmin": bmin, "cmin": cmin, "amax": amax, "bmax": bmax, "cmax": cmax}

    def get_values(self):
        return self.bounds_from_center_tol()

    def update(self, img, color_type=None):
        if color_type is not None:
            self.color_type = color_type
        vals = self.bounds_from_center_tol()
        if self.color_type == "HSV":
            space = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            lower = np.array([vals["amin"], vals["bmin"], vals["cmin"]], dtype=np.uint8)
            upper = np.array([vals["amax"], vals["bmax"], vals["cmax"]], dtype=np.uint8)
            mask = cv2.inRange(space, lower, upper)
            out = cv2.bitwise_and(img, img, mask=mask)
            return out, mask
        if self.color_type == "BGR":
            lower = np.array([vals["amin"], vals["bmin"], vals["cmin"]], dtype=np.uint8)
            upper = np.array([vals["amax"], vals["bmax"], vals["cmax"]], dtype=np.uint8)
            mask = cv2.inRange(img, lower, upper)
            out = cv2.bitwise_and(img, img, mask=mask)
            return out, mask
        if self.color_type == "LAB":
            space = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
            lower = np.array([vals["amin"], vals["bmin"], vals["cmin"]], dtype=np.uint8)
            upper = np.array([vals["amax"], vals["bmax"], vals["cmax"]], dtype=np.uint8)
            mask = cv2.inRange(space, lower, upper)
            out = cv2.bitwise_and(img, img, mask=mask)
            return out, mask
        if self.color_type == "YCB":
            space = cv2.cvtColor(img, cv2.COLOR_BGR2YCrCb)
            lower = np.array([vals["amin"], vals["bmin"], vals["cmin"]], dtype=np.uint8)
            upper = np.array([vals["amax"], vals["bmax"], vals["cmax"]], dtype=np.uint8)
            mask = cv2.inRange(space, lower, upper)
            out = cv2.bitwise_and(img, img, mask=mask)
            return out, mask
        if self.color_type == "GREY":
            space = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            lower = np.array([vals["amin"]], dtype=np.uint8)
            upper = np.array([vals["amax"]], dtype=np.uint8)
            mask = cv2.inRange(space, lower, upper)
            out = cv2.bitwise_and(space, space, mask=mask)
            return out, mask
        raise Exception("Masked color invalid")

def caps_for_space(cs: str):
    if cs == "HSV":
        return (179, 255, 255)
    if cs in ("BGR", "LAB", "YCB"):
        return (255, 255, 255)
    if cs == "GREY":
        return (255, 0, 0)
    return (255, 255, 255)

def mask_values_from_center(center, tol_scalar, cs):
    capA, capB, capC = caps_for_space(cs)
    a, b, c = center
    tA = tB = tC = int(tol_scalar)
    vals = {
        "amin": int(max(0, a - tA)),
        "amax": int(min(capA, a + tA)),
        "bmin": int(max(0, b - tB)),
        "bmax": int(min(capB, b + tB)),
        "cmin": int(max(0, c - tC)),
        "cmax": int(min(capC, c + tC)),
    }
    return vals

def apply_center_change(color_finder: ColorFinder, color_space: str, color_center, which: str, delta: int):
    capA, capB, capC = caps_for_space(color_space)
    a, b, c = color_center
    if which == 'ALL':
        a = int(np.clip(a + delta, 0, capA))
        b = int(np.clip(b + delta, 0, capB))
        c = int(np.clip(c + delta, 0, capC))
    elif which == 'A':
        a = int(np.clip(a + delta, 0, capA))
    elif which == 'B':
        b = int(np.clip(b + delta, 0, capB))
    elif which == 'C':
        c = int(np.clip(c + delta, 0, capC))
    new_center = (a, b, c)
    color_finder.set_center(new_center)
    return new_center


def cycle_channel(current: str):
    order = ['ALL', 'A', 'B', 'C']
    if current not in order:
        return 'ALL'
    idx = order.index(current)
    return order[(idx + 1) % len(order)]


def bump_color_tolerance(color_finder: ColorFinder, color_tol: int, tol_step: int = 1):
    color_tol = (color_tol + tol_step) % 101
    t = (color_tol, color_tol, color_tol)
    color_finder.set_tolerance(t)
    return color_tol


def hue_gradient(width=360, height=18):
    w = max(180, int(width))
    hsv = np.zeros((height, w, 3), dtype=np.uint8)
    hsv[..., 0] = np.linspace(0, 179, w, dtype=np.uint8)
    hsv[..., 1] = 255
    hsv[..., 2] = 255
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)


def bar_channel(label, vmin, vmax, cap=255, width=360, height=10, color=(200, 200, 200)):
    w = max(180, int(width))
    bar = np.full((height, w, 3), 25, dtype=np.uint8)
    for x in range(0, w, 30):
        cv2.line(bar, (x, 0), (x, height - 1), (45, 45, 45), 1)
    lo = int(np.clip(vmin / cap * (w - 1), 0, w - 1))
    hi = int(np.clip(vmax / cap * (w - 1), 0, w - 1))
    if hi < lo:
        lo, hi = hi, lo
    cv2.rectangle(bar, (lo, 0), (hi, height - 1), color, thickness=-1)
    cv2.rectangle(bar, (0, 0), (w - 1, height - 1), (90, 90, 90), 1)
    lbl = np.full((height, 60, 3), 25, dtype=np.uint8)
    cv2.putText(lbl, label, (2, height - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (220, 220, 220), 1, cv2.LINE_AA)
    return np.hstack([lbl, bar])


def legend_block(color_space, vals, center=None, tol=None):
    pad = 6
    line_h = 18
    width = 420
    body = []
    header = np.full((line_h, width, 3), 15, dtype=np.uint8)
    hdr_txt = f"{color_space} mask"
    cv2.putText(header, hdr_txt, (8, 13), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    if center is not None and tol is not None:
        ct = f"C:({center[0]},{center[1]},{center[2]})  T:({tol[0]},{tol[1]},{tol[2]})"
        cv2.putText(header, ct, (160, 13), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1, cv2.LINE_AA)
    body.append(header)

    if color_space == "HSV":
        hue = hue_gradient(width - 60, 18)
        hue_lbl = np.full((18, 60, 3), 25, dtype=np.uint8)
        cv2.putText(hue_lbl, "Hue", (4, 13), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (220, 220, 220), 1, cv2.LINE_AA)
        body.append(np.hstack([hue_lbl, hue]))
        capA, capB, capC = 179, 255, 255
    else:
        capA = capB = capC = 255

    barA = bar_channel("A", vals["amin"], vals["amax"], capA, width - 60, 12, (120, 220, 220))
    barB = bar_channel("B", vals["bmin"], vals["bmax"], capB, width - 60, 12, (220, 220, 120))
    barC = bar_channel("C", vals["cmin"], vals["cmax"], capC, width - 60, 12, (220, 120, 220))
    body.extend([barA, barB, barC])

    h = sum(b.shape[0] for b in body) + pad * 2 + 2
    w = width + pad * 2
    canvas = np.full((h, w, 3), 10, dtype=np.uint8)
    y = pad
    for b in body:
        canvas[y:y + b.shape[0], pad:pad + b.shape[1]] = b
        y += b.shape[0]
    cv2.rectangle(canvas, (0, 0), (w - 1, h - 1), (60, 60, 60), 1)
    return canvas


def overlay_legend_on_frame(frame, legend, anchor="br", margin=8, alpha=0.9):
    if legend is None:
        return frame
    fh, fw = frame.shape[:2]
    lh, lw = legend.shape[:2]
    if lw > fw or lh > fh:
        scale = min((fw - 2 * margin) / lw, (fh - 2 * margin) / lh, 1.0)
        if scale < 1.0:
            legend = cv2.resize(legend, (int(lw * scale), int(lh * scale)), interpolation=cv2.INTER_AREA)
            lh, lw = legend.shape[:2]
    if anchor == "br":
        x0 = fw - lw - margin
        y0 = fh - lh - margin
    elif anchor == "tr":
        x0 = fw - lw - margin
        y0 = margin
    elif anchor == "bl":
        x0 = margin
        y0 = fh - lh - margin
    else:
        x0 = margin
        y0 = margin
    roi = frame[y0:y0 + lh, x0:x0 + lw]
    blended = cv2.addWeighted(roi, 1.0 - alpha, legend, alpha, 0)
    frame[y0:y0 + lh, x0:x0 + lw] = blended
    return frame
