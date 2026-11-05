"""Phone-photo simulation.

All geometry (placement on the background, rotation, camera tilt / perspective, partial
cropping) is composed into ONE 3x3 homography H. The envelope sheet is warped with H via
cv2.warpPerspective and every label polygon is mapped with the very same H via
cv2.perspectiveTransform, so image and boxes cannot drift apart. Photometric effects
applied afterwards (lighting, blur, noise, JPEG) never move pixels.
"""
from __future__ import annotations

import cv2
import numpy as np

from . import noise as fastnoise
from .background import make_background


# --------------------------------------------------------------------------- geometry


def _rot(axis: str, deg: float) -> np.ndarray:
    a = np.deg2rad(deg)
    c, s = np.cos(a), np.sin(a)
    if axis == "x":
        return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])
    if axis == "y":
        return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def project_envelope(w: float, h: float, rot: float, tilt_x: float, tilt_y: float) -> np.ndarray:
    """Project the envelope rectangle through a pinhole camera; returns 4x2 (unscaled)."""
    pts = np.array([[-w / 2, -h / 2, 0], [w / 2, -h / 2, 0], [w / 2, h / 2, 0], [-w / 2, h / 2, 0]], float)
    R = _rot("z", rot) @ _rot("x", tilt_x) @ _rot("y", tilt_y)
    D = 1.8 * max(w, h)  # camera distance ~ phone held close
    P = pts @ R.T + np.array([0, 0, D])
    return (D * P[:, :2] / P[:, 2:3]).astype(np.float64)


def transform_points(H: np.ndarray, pts) -> np.ndarray:
    pts = np.asarray(pts, np.float64).reshape(-1, 1, 2)
    return cv2.perspectiveTransform(pts, H).reshape(-1, 2)


def rect_poly(r) -> np.ndarray:
    x0, y0, x1, y1 = r
    return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], np.float64)


def visible_fraction(poly: np.ndarray, W: int, H: int) -> float:
    img = np.array([[0, 0], [W, 0], [W, H], [0, H]], np.float32)
    p = np.asarray(poly, np.float32)
    area = abs(cv2.contourArea(p))
    if area < 1:
        return 0.0
    inter, _ = cv2.intersectConvexConvex(p, img)
    return float(min(1.0, inter / area))


def sample_geometry(env_quad: np.ndarray, preset: dict, rng, OW: int, OH: int,
                    required: list[np.ndarray], allow_crop: bool) -> tuple[np.ndarray, dict]:
    """Choose a homography mapping sheet coords -> photo coords.

    required: polygons (sheet coords) that must stay fully inside the frame.
    """
    w = float(np.linalg.norm(env_quad[1] - env_quad[0]))
    h = float(np.linalg.norm(env_quad[3] - env_quad[0]))
    rmax, tmax = float(preset.get("rotation_deg", 0)), float(preset.get("tilt_deg", 0))
    fill_lo, fill_hi = preset.get("fill", [0.85, 0.9])
    params: dict = {}
    for attempt in range(25):
        shrink = 1.0 if attempt < 15 else 0.5
        rot = rng.uniform(-rmax, rmax) * shrink
        tx, ty = rng.uniform(-tmax, tmax) * shrink, rng.uniform(-tmax, tmax) * shrink
        uv = project_envelope(w, h, rot, tx, ty)
        bw, bh = np.ptp(uv[:, 0]), np.ptp(uv[:, 1])
        fill = rng.uniform(fill_lo, fill_hi)
        s = fill * min(OW / bw, OH / bh)
        uv = (uv - uv.mean(0)) * s
        bw, bh = bw * s, bh * s
        slack_x, slack_y = max(0.0, (OW - bw) / 2), max(0.0, (OH - bh) / 2)
        off = np.array([rng.uniform(-slack_x, slack_x) * 0.8, rng.uniform(-slack_y, slack_y) * 0.8])
        cropped = False
        if allow_crop and attempt < 15 and rng.random() < preset.get("crop_prob", 0):
            frac = rng.uniform(0.3, 1.0) * preset.get("crop_frac", 0.1)
            side = int(rng.integers(4))
            # push one envelope edge `frac` of its size past the frame edge
            if side == 0:
                off[0] = bw / 2 - OW / 2 - frac * bw
            elif side == 1:
                off[0] = OW / 2 - bw / 2 + frac * bw
            elif side == 2:
                off[1] = bh / 2 - OH / 2 - frac * bh
            else:
                off[1] = OH / 2 - bh / 2 + frac * bh
            cropped = True
        dst = uv + np.array([OW / 2, OH / 2]) + off
        H = cv2.getPerspectiveTransform(env_quad.astype(np.float32), dst.astype(np.float32))
        ok = True
        for poly in required:
            p = transform_points(H, poly)
            if p[:, 0].min() < 2 or p[:, 1].min() < 2 or p[:, 0].max() > OW - 2 or p[:, 1].max() > OH - 2:
                ok = False
                break
        if ok:
            params = {"rotation_deg": round(float(rot), 2), "tilt_x_deg": round(float(tx), 2),
                      "tilt_y_deg": round(float(ty), 2), "fill": round(float(fill), 3), "cropped": cropped}
            return H, params
    # Fallback: centred, untilted, fits easily.
    uv = project_envelope(w, h, 0, 0, 0)
    s = 0.8 * min(OW / np.ptp(uv[:, 0]), OH / np.ptp(uv[:, 1]))
    dst = (uv - uv.mean(0)) * s + np.array([OW / 2, OH / 2])
    H = cv2.getPerspectiveTransform(env_quad.astype(np.float32), dst.astype(np.float32))
    return H, {"rotation_deg": 0.0, "tilt_x_deg": 0.0, "tilt_y_deg": 0.0, "fill": 0.8, "cropped": False,
               "fallback": True}


def local_scale(H: np.ndarray, pt) -> float:
    """Approximate vertical scale factor of H around a sheet point."""
    x, y = pt
    a = transform_points(H, [[x, y], [x, y + 10]])
    return float(np.linalg.norm(a[1] - a[0]) / 10)


# --------------------------------------------------------------------------- photometric


def _grid(H: int, W: int, f: int):
    """Coordinate grids at 1/f resolution, in full-resolution pixel units."""
    ys = (np.arange(H // f, dtype=np.float32) + 0.5) * f
    xs = (np.arange(W // f, dtype=np.float32) + 0.5) * f
    return np.meshgrid(ys, xs, indexing="ij")


def disk_kernel(r: float) -> np.ndarray:
    R = int(np.ceil(r))
    yy, xx = np.mgrid[-R:R + 1, -R:R + 1]
    k = np.clip(r + 0.5 - np.sqrt(xx ** 2 + yy ** 2), 0, 1).astype(np.float32)
    return k / k.sum()


def motion_kernel(length: float, angle: float) -> np.ndarray:
    L = max(3, int(round(length)) | 1)
    k = np.zeros((L, L), np.float32)
    k[L // 2, :] = 1
    k = cv2.warpAffine(k, cv2.getRotationMatrix2D((L / 2 - 0.5, L / 2 - 0.5), angle, 1.0), (L, L))
    return k / max(k.sum(), 1e-6)


def photograph(sheet: np.ndarray, env_quad: np.ndarray, preset: dict, rng, OW: int, OH: int,
               required: list[np.ndarray], allow_crop: bool = True, force: dict | None = None,
               readable_text: tuple | None = None):
    """Render the phone photo.

    sheet: HxWx4 uint8 (straight alpha). Returns (rgb uint8 image, H, applied list).
    `force` overrides individual effects (used for illegible heavy_blur / extreme_low_light).
    `readable_text` = ((x, y) sheet point, font px): random blur is capped relative to that
    text's on-photo size so samples that are meant to stay readable actually do.
    """
    force = force or {}
    applied: list[dict] = []

    def u(rng_range):
        lo, hi = rng_range
        return float(rng.uniform(lo, hi))

    H, gparams = sample_geometry(env_quad, preset, rng, OW, OH, required, allow_crop)
    if abs(gparams["rotation_deg"]) > 0.01:
        applied.append({"name": "rotation", "params": {"deg": gparams["rotation_deg"]}})
    if abs(gparams["tilt_x_deg"]) > 0.01 or abs(gparams["tilt_y_deg"]) > 0.01:
        applied.append({"name": "perspective", "params": {"tilt_x_deg": gparams["tilt_x_deg"],
                                                           "tilt_y_deg": gparams["tilt_y_deg"]}})
    applied.append({"name": "placement", "params": {"fill": gparams["fill"], **({"fallback": True} if gparams.get("fallback") else {})}})
    if gparams["cropped"]:
        applied.append({"name": "partial_crop", "params": {}})

    # ---- background (uint8)
    bg_kind = preset["background"][int(rng.integers(len(preset["background"])))]
    bg = make_background(bg_kind, rng, OH, OW)
    applied.append({"name": "background", "params": {"kind": bg_kind}})

    # ---- warp sheet (premultiplied alpha) and composite over the background with a soft drop shadow.
    # The photometric pipeline below runs in uint8 with OpenCV (memory-bound, ~4x faster than float).
    a8 = sheet[..., 3:4].astype(np.uint16)
    premul = np.concatenate([((sheet[..., :3].astype(np.uint16) * a8 + 127) // 255).astype(np.uint8),
                             sheet[..., 3:4]], axis=2)
    warped = cv2.warpPerspective(premul, H, (OW, OH), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT,
                                 borderValue=(0, 0, 0, 0))
    wa = warped[..., 3]
    ds = 4  # drop shadow built at 1/4 resolution
    small_a = cv2.resize(wa, (OW // ds, OH // ds), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
    sh_dx, sh_dy = rng.uniform(-12, 12), rng.uniform(4, 16)
    drop = cv2.warpAffine(small_a, np.float32([[1, 0, sh_dx / ds], [0, 1, sh_dy / ds]]), (OW // ds, OH // ds))
    drop = cv2.GaussianBlur(drop, (0, 0), rng.uniform(5, 14) / ds)
    drop = cv2.resize(drop, (OW, OH), interpolation=cv2.INTER_LINEAR)
    bgfac = (1.0 - rng.uniform(0.2, 0.45) * drop) * (255 - wa).astype(np.float32)   # 0..255
    bgfac = cv2.cvtColor(bgfac.astype(np.uint8), cv2.COLOR_GRAY2RGB)
    img = cv2.add(cv2.cvtColor(warped, cv2.COLOR_RGBA2RGB), cv2.multiply(bg, bgfac, scale=1 / 255.0))

    # ---- multiplicative light field (lighting gradient x cast shadow x exposure x white balance),
    # built at 1/8 resolution and applied in one pass.
    f = 8
    sw, shh = OW // f, OH // f
    light = np.ones((shh, sw), np.float32)
    if rng.random() < preset.get("p_lighting", 0):
        g = u(preset["lighting_strength"])
        ang = rng.uniform(0, 2 * np.pi)
        yy, xx = _grid(OH, OW, f)
        lin = ((xx - OW / 2) * np.cos(ang) + (yy - OH / 2) * np.sin(ang)) / (0.5 * np.hypot(OW, OH))
        r2 = ((xx - OW / 2) ** 2 + (yy - OH / 2) ** 2) / (0.25 * (OW ** 2 + OH ** 2))
        vig = rng.uniform(0, g)
        light *= (1 + g * lin - vig * r2).astype(np.float32)
        applied.append({"name": "uneven_lighting", "params": {"strength": round(g, 3), "vignette": round(float(vig), 3)}})

    if rng.random() < preset.get("p_shadow", 0):   # hand / phone shadow
        d = u(preset["shadow_strength"])
        mask = np.zeros((shh, sw), np.float32)
        if rng.random() < 0.5:
            c = (int(rng.uniform(0, sw)), int(rng.choice([rng.uniform(-shh * 0.2, shh * 0.1), rng.uniform(shh * 0.9, shh * 1.2)])))
            cv2.ellipse(mask, c, (int(rng.uniform(0.3, 0.6) * sw), int(rng.uniform(0.25, 0.45) * shh)),
                        rng.uniform(0, 180), 0, 360, 1.0, -1)
        else:
            p0 = rng.uniform(0, 1, 2) * [OW, OH]
            n = rng.normal(0, 1, 2)
            n /= np.linalg.norm(n) + 1e-9
            yy, xx = _grid(OH, OW, f)
            mask = (((xx - p0[0]) * n[0] + (yy - p0[1]) * n[1]) > 0).astype(np.float32)
        mask = cv2.GaussianBlur(mask, (0, 0), rng.uniform(25, 70) / f)
        light *= 1 - d * mask
        applied.append({"name": "shadow", "params": {"strength": round(d, 3)}})

    gain = None
    if "low_light_gain" in force:
        gain = force["low_light_gain"]
    elif rng.random() < preset.get("p_low_light", 0):
        gain = u(preset["low_light_gain"])
    wb = np.array([1 + rng.normal(0, 0.04), 1.0, 1 + rng.normal(0, 0.05)], np.float32)
    if gain is not None:
        warm = rng.uniform(0.0, 0.12)  # indoor tungsten tint in dim light
        wb *= np.array([1 + warm, 1.0, 1 - warm], np.float32)
        light *= gain
        applied.append({"name": "low_light", "params": {"gain": round(float(gain), 3)}})
    if preset.get("p_lighting", 0) > 0 or gain is not None:
        applied.append({"name": "white_balance", "params": {"r": round(float(wb[0]), 3), "b": round(float(wb[2]), 3)}})
    else:
        wb[:] = 1.0
    if not (np.allclose(light, 1.0) and np.allclose(wb, 1.0)):
        field = np.clip(light[..., None] * wb[None, None, :] * 127.5, 0, 255).astype(np.uint8)
        field = cv2.resize(field, (OW, OH), interpolation=cv2.INTER_LINEAR)
        img = cv2.multiply(img, field, scale=2 / 255.0)   # field 127.5 == x1.0
    if gain is not None:   # dim scenes: crushed shadows via gamma LUT
        gamma = float(rng.uniform(1.0, 1.25))
        lut = np.clip(((np.arange(256) / 255.0) ** gamma) * 255 + 0.5, 0, 255).astype(np.uint8)
        img = cv2.LUT(img, lut)

    # ---- blur (optics / hand shake)
    max_r = max_len = None
    if readable_text is not None:
        t_px = readable_text[1] * local_scale(H, readable_text[0])
        max_r, max_len = max(1.0, 0.16 * t_px), max(3.0, 0.5 * t_px)
    radius = force.get("defocus_radius")
    if radius is None and rng.random() < preset.get("p_defocus", 0):
        radius = u(preset["defocus_radius"])
        if max_r is not None:
            radius = min(radius, max_r)
    if radius:
        img = cv2.filter2D(img, -1, disk_kernel(radius), borderType=cv2.BORDER_REFLECT)
        applied.append({"name": "defocus_blur", "params": {"radius_px": round(float(radius), 2)}})
    length = force.get("motion_length")
    if length is None and rng.random() < preset.get("p_motion", 0):
        length = u(preset["motion_length"])
        if max_len is not None:
            length = min(length, max_len)
    if length:
        ang = rng.uniform(0, 180)
        img = cv2.filter2D(img, -1, motion_kernel(length, ang), borderType=cv2.BORDER_REFLECT)
        applied.append({"name": "motion_blur", "params": {"length_px": round(float(length), 2), "angle_deg": round(float(ang), 1)}})

    # ---- sensor noise (luma + weaker chroma, from a pre-generated tile)
    sigma = force.get("noise_sigma")
    if sigma is None and rng.random() < preset.get("p_noise", 0):
        sigma = u(preset["noise_sigma"])
        if gain is not None:
            sigma *= 1 + (1 - gain)
    if sigma:
        nz = fastnoise.sensor_noise(rng, OH, OW)          # int16, std = fastnoise.SCALE
        img = cv2.addWeighted(img, 1.0, nz, float(sigma) * 255.0 / fastnoise.SCALE, 0, dtype=cv2.CV_8U)
        applied.append({"name": "noise", "params": {"sigma": round(float(sigma), 4)}})

    out = img

    # ---- JPEG compression artifacts (an intermediate re-encode, e.g. messaging app)
    q = force.get("jpeg_quality")
    if q is None and rng.random() < preset.get("p_jpeg", 0):
        q = int(round(u(preset["jpeg_quality"])))
    if q:
        ok, enc = cv2.imencode(".jpg", out[..., ::-1], [cv2.IMWRITE_JPEG_QUALITY, int(q)])
        out = cv2.imdecode(enc, cv2.IMREAD_COLOR)[..., ::-1]
        applied.append({"name": "jpeg_compression", "params": {"quality": int(q)}})
    return np.ascontiguousarray(out), H, applied
