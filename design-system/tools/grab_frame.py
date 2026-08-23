"""mp4 から「一番デザインが読めるフレーム」を1枚選んで webp/jpg で保存する。

真っ暗な冒頭やトランジション中を避けるため、候補を等間隔でサンプルして
エッジ量（ラプラシアン分散）× 明度の広がり でスコアリングし最良を採る。
"""
import sys, os
import cv2
import numpy as np

def best_frame(path, samples=12, skip_head=0.10, skip_tail=0.05):
    cap = cv2.VideoCapture(path)
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if n <= 0:
        cap.release(); return None, {}
    lo, hi = int(n * skip_head), int(n * (1 - skip_tail))
    idxs = np.linspace(lo, max(lo + 1, hi - 1), samples).astype(int)
    best, best_score, meta = None, -1.0, {}
    for i in idxs:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(i))
        ok, f = cap.read()
        if not ok:
            continue
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        edge = cv2.Laplacian(g, cv2.CV_64F).var()      # 情報量
        spread = float(g.std())                         # のっぺり除け
        score = edge * (spread + 1)
        if score > best_score:
            best, best_score, meta = f, score, {"frame": int(i), "edge": round(edge, 1), "std": round(spread, 1)}
    cap.release()
    return best, meta

def main():
    src, out = sys.argv[1], sys.argv[2]
    img, meta = best_frame(src)
    if img is None:
        print(f"FAIL\t{os.path.basename(src)}\tno decodable frame"); return 1
    h, w = img.shape[:2]
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    ext = ".webp" if out.endswith(".webp") else ".jpg"
    params = [cv2.IMWRITE_WEBP_QUALITY, 92] if ext == ".webp" else [cv2.IMWRITE_JPEG_QUALITY, 92]
    # cv2.imwrite は非ASCIIパス（ドキュメント等）で無言失敗するのでバイト経由で書く
    ok, buf = cv2.imencode(ext, img, params)
    if not ok:
        print(f"FAIL	{os.path.basename(src)}	encode failed"); return 1
    with open(out, "wb") as fh:
        fh.write(buf.tobytes())
    print(f"OK\t{os.path.basename(src)}\t{w}x{h}\tframe={meta['frame']}\tedge={meta['edge']}\tstd={meta['std']}\t{os.path.getsize(out)//1024}KB")
    return 0

if __name__ == "__main__":
    sys.exit(main())
