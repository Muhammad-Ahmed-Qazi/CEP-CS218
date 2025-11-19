
import os
import time
import math
import numpy as np
from PIL import Image
from scipy.fftpack import dct, idct

# Standard JPEG luminance quant table
QY = np.array([
    [16,11,10,16,24,40,51,61],
    [12,12,14,19,26,58,60,55],
    [14,13,16,24,40,57,69,56],
    [14,17,22,29,51,87,80,62],
    [18,22,37,56,68,109,103,77],
    [24,35,55,64,81,104,113,92],
    [49,64,78,87,103,121,120,101],
    [72,92,95,98,112,100,103,99]
], dtype=np.float32)

# use same base for chroma (simplified)
QC = QY.copy()

def quality_scale_to_matrix(Q, quality):
    # JPEG-like scaling (1..100)
    q = max(1, min(100, int(quality)))
    if q < 50:
        scale = 5000.0 / q
    else:
        scale = 200.0 - 2.0 * q
    Qs = np.floor((Q * scale + 50.0) / 100.0)
    Qs[Qs == 0] = 1
    return Qs.astype(np.float32)

def rgb_to_ycbcr(img_arr):
    # img_arr: HxWx3 uint8 or float
    R = img_arr[...,0].astype(np.float32)
    G = img_arr[...,1].astype(np.float32)
    B = img_arr[...,2].astype(np.float32)
    Y  =  0.299   * R + 0.587   * G + 0.114   * B
    Cb = -0.168736* R - 0.331264* G + 0.5     * B + 128.0
    Cr =  0.5     * R - 0.418688* G - 0.081312* B + 128.0
    return Y, Cb, Cr

def ycbcr_to_rgb(Y, Cb, Cr):
    R = Y + 1.402   * (Cr - 128.0)
    G = Y - 0.344136* (Cb - 128.0) - 0.714136 * (Cr - 128.0)
    B = Y + 1.772   * (Cb - 128.0)
    out = np.stack([R,G,B], axis=-1)
    out = np.clip(out, 0, 255).astype(np.uint8)
    return out

def pad_to_multiple(arr, m=8):
    h, w = arr.shape[:2]
    H = ((h + m - 1)//m) * m
    W = ((w + m - 1)//m) * m
    if arr.ndim == 2:
        out = np.zeros((H, W), dtype=arr.dtype)
        out[:h,:w] = arr
    else:
        out = np.zeros((H, W, arr.shape[2]), dtype=arr.dtype)
        out[:h,:w,:] = arr
    return out, h, w

def subsample_420(channel):
    # channel: HxW
    # assume even dims
    H, W = channel.shape
    # average each 2x2 block -> shape (H/2, W/2)
    c = channel.reshape(H//2, 2, W//2, 2).mean(axis=(1,3))
    return c

def upsample_420(channel_small):
    # repeat to 2x2
    return channel_small.repeat(2, axis=0).repeat(2, axis=1)

def block_view(arr, block_h=8, block_w=8):
    """Return view of arr as blocks: shape (n_vert_blocks, n_horiz_blocks, block_h, block_w)"""
    H, W = arr.shape
    nbh = H // block_h
    nbw = W // block_w
    return arr.reshape(nbh, block_h, nbw, block_w).swapaxes(1,2)

def blocks_to_image(blocks):
    # inverse of block_view reshape
    nbh, nbw, bh, bw = blocks.shape
    return blocks.swapaxes(1,2).reshape(nbh*bh, nbw*bw)

def dct2_blockwise(blocks):
    # blocks shape: (nbh, nbw, 8, 8)
    # apply dct along last axis then along axis -2
    # operate in float32 for speed
    x = blocks.astype(np.float32)
    # DCT along width (axis=3)
    x = dct(x, axis=3, norm='ortho')
    # DCT along height (axis=2)
    x = dct(x, axis=2, norm='ortho')
    return x

def idct2_blockwise(blocks):
    x = blocks.astype(np.float32)
    x = idct(x, axis=3, norm='ortho')
    x = idct(x, axis=2, norm='ortho')
    return x

def compress_reconstruct_color(image_path, output_path, quality=50, do_timing=True):
    t0 = time.time()
    pil = Image.open(image_path).convert('RGB')
    arr = np.array(pil)
    padded, h_orig, w_orig = pad_to_multiple(arr, 8)
    # Convert to YCbCr
    Y, Cb, Cr = rgb_to_ycbcr(padded)

    # Prepare chroma subsampling 4:2:0
    # Ensure even sizes for chroma subsampling
    H, W = Y.shape
    if H % 2 != 0:
        Y = np.vstack([Y, Y[-1:,:]])
        Cb = np.vstack([Cb, Cb[-1:,:]])
        Cr = np.vstack([Cr, Cr[-1:,:]])
        H += 1
    if W % 2 != 0:
        Y = np.hstack([Y, Y[:, -1:]])
        Cb = np.hstack([Cb, Cb[:, -1:]])
        Cr = np.hstack([Cr, Cr[:, -1:]])
        W += 1

    # Subsample chroma by averaging 2x2 blocks
    Cb_small = subsample_420(Cb)
    Cr_small = subsample_420(Cr)

    # subtract 128 shift for DCT (typical JPEG)
    Y_shift = Y - 128.0
    Cb_shift = Cb_small - 128.0
    Cr_shift = Cr_small - 128.0

    # pad channels to multiples of 8 (they should be already)
    Y_pad, _, _ = pad_to_multiple(Y_shift, 8)
    Cb_pad, _, _ = pad_to_multiple(Cb_shift, 8)
    Cr_pad, _, _ = pad_to_multiple(Cr_shift, 8)

    # View as blocks
    Y_blocks = block_view(Y_pad, 8, 8)   # shape (nbh, nbw, 8, 8)
    Cb_blocks = block_view(Cb_pad, 8, 8)
    Cr_blocks = block_view(Cr_pad, 8, 8)

    if do_timing:
        t1 = time.time()

    # DCT vectorized
    Y_dct = dct2_blockwise(Y_blocks)
    Cb_dct = dct2_blockwise(Cb_blocks)
    Cr_dct = dct2_blockwise(Cr_blocks)

    if do_timing:
        t2 = time.time()

    # Quantization tables
    Qy = quality_scale_to_matrix(QY, quality)
    Qc = quality_scale_to_matrix(QC, quality)

    # Quantize (broadcast over blocks)
    # Q shape (8,8) -> we need shape (1,1,8,8) to broadcast
    Qy_b = Qy.reshape((1,1,8,8))
    Qc_b = Qc.reshape((1,1,8,8))

    Y_q = np.round(Y_dct / Qy_b).astype(np.int32)
    Cb_q = np.round(Cb_dct / Qc_b).astype(np.int32)
    Cr_q = np.round(Cr_dct / Qc_b).astype(np.int32)

    if do_timing:
        t3 = time.time()

    # Dequantize
    Y_deq = (Y_q.astype(np.float32) * Qy_b)
    Cb_deq = (Cb_q.astype(np.float32) * Qc_b)
    Cr_deq = (Cr_q.astype(np.float32) * Qc_b)

    # IDCT (vectorized)
    Y_idct = idct2_blockwise(Y_deq)
    Cb_idct = idct2_blockwise(Cb_deq)
    Cr_idct = idct2_blockwise(Cr_deq)

    if do_timing:
        t4 = time.time()

    # Merge blocks back to full images
    Y_rec = blocks_to_image(Y_idct)
    Cb_rec_small = blocks_to_image(Cb_idct)
    Cr_rec_small = blocks_to_image(Cr_idct)

    # add 128 shift back
    Y_rec += 128.0
    Cb_rec_small += 128.0
    Cr_rec_small += 128.0

    # Upsample chroma
    Cb_rec = upsample_420(Cb_rec_small)[:Y_rec.shape[0], :Y_rec.shape[1]]
    Cr_rec = upsample_420(Cr_rec_small)[:Y_rec.shape[0], :Y_rec.shape[1]]

    # Crop to original image size
    Y_final = Y_rec[:h_orig, :w_orig]
    Cb_final = Cb_rec[:h_orig, :w_orig]
    Cr_final = Cr_rec[:h_orig, :w_orig]

    rgb_out = ycbcr_to_rgb(Y_final, Cb_final, Cr_final)
    Image.fromarray(rgb_out).save(output_path)

    if do_timing:
        t5 = time.time()
        print(f"Timings (s): load+prep {t1-t0:.3f}, DCT {t2-t1:.3f}, quant {t3-t2:.3f}, dequant+IDCT {t4-t3:.3f}, merge+save {t5-t4:.3f}")
        print(f"Total time: {t5-t0:.3f}s")
    orig = np.array(Image.open(image_path).convert('RGB')).astype(np.float32)
    mse = np.mean((orig - rgb_out.astype(np.float32))**2)
    psnr = 20.0 * math.log10(255.0 / math.sqrt(mse)) if mse != 0 else float('inf')
    return psnr

def compress_image(input_path, output_path, quality=50):
    try:
        compress_reconstruct_color(input_path, output_path, quality=quality)
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            return False
        return True
    except Exception as e:
        print("Compression error:", e)
        return False



if __name__ == "__main__":
    input_image = "input.jpg"
    output_image = "output.jpg"
    quality = 10

    compress_reconstruct_color(input_image, output_image, quality=quality)

