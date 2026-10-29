"""
photo.jpg -> photo_cropped.png  (run once, when the photo changes)

  - background removed with rembg (falls back to OpenCV GrabCut if rembg is not installed)
  - tight crop: starts at the top of the hair, ends at the bottom of the photo,
    centred on the head, so the ASCII portrait has no empty line above or below
  - output: grayscale + alpha (LA) PNG, transparent = background

Usage:  pip install rembg  &&  python crop_photo.py
"""
import cv2
import numpy as np
from PIL import Image

SOURCE, OUTPUT = "photo.jpg", "photo_cropped.png"
CROP_ASPECT = 0.75          # crop width / height


def remove_background(img):
    """Returns an alpha mask (0-255) for the person."""
    try:
        from rembg import remove
        cut = remove(img.convert("RGB"))
        return np.array(cut)[:, :, 3]
    except ImportError:
        print("rembg not installed: using OpenCV GrabCut instead")
    rgb = np.array(img.convert("RGB"))
    h, w = rgb.shape[:2]
    mask = np.full((h, w), cv2.GC_PR_BGD, np.uint8)
    mask[int(h * 0.02):, int(w * 0.10):int(w * 0.90)] = cv2.GC_PR_FGD          # head + shoulders area
    mask[int(h * 0.35):int(h * 0.80), int(w * 0.30):int(w * 0.70)] = cv2.GC_FGD  # sure: centre of the face
    mask[:, :3] = mask[:, -3:] = cv2.GC_BGD
    mask[:3, :] = cv2.GC_BGD
    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    cv2.grabCut(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), mask, None, bgd, fgd, 8, cv2.GC_INIT_WITH_MASK)
    fg = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    # keep the largest blob and fill small holes
    n, labels, stats, _ = cv2.connectedComponentsWithStats(fg)
    if n > 1:
        fg = np.where(labels == 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA]), 255, 0).astype(np.uint8)
    fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    return cv2.GaussianBlur(fg, (5, 5), 0)


def main():
    img = Image.open(SOURCE)
    alpha = remove_background(img)
    gray = np.array(img.convert("L"))
    h, w = gray.shape

    rows = np.where((alpha > 127).sum(axis=1) > w * 0.02)[0]
    cols = np.where((alpha > 127).sum(axis=0) > h * 0.02)[0]
    top, bottom = rows[0], rows[-1] + 1                   # hair top -> bottom of the subject
    cx = (cols[0] + cols[-1]) / 2
    crop_w = min(w, int((bottom - top) * CROP_ASPECT))
    left = int(np.clip(cx - crop_w / 2, 0, w - crop_w))

    g = np.where(alpha > 127, gray, 0)[top:bottom, left:left + crop_w]
    a = alpha[top:bottom, left:left + crop_w]
    Image.merge("LA", (Image.fromarray(g.astype(np.uint8)), Image.fromarray(a))).save(OUTPUT)
    print(f"{OUTPUT}: {crop_w}x{bottom - top}")


if __name__ == "__main__":
    main()
