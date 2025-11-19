# audio_compression.py
import soundfile as sf
import numpy as np


def compress_audio(input_path, output_path):
    try:
        data, samplerate = sf.read(input_path)

        # If stereo → use only first channel
        if len(data.shape) > 1:
            data = data[:, 0]

        # Delta encode and convert to 8-bit
        data_int = np.round(data * 127).astype(np.int8)
        delta = np.zeros_like(data_int)
        delta[0] = data_int[0]
        delta[1:] = np.diff(data_int)

        # Reconstruct (for saving as compressed)
        recon = np.cumsum(delta)
        recon_float = recon.astype(np.float32) / 127

        # Save compressed output
        sf.write(output_path, recon_float, samplerate, subtype='PCM_U8')

        # Stats
        original_bytes = data.shape[0] * 2   # 16-bit = 2 bytes per sample
        new_bytes = recon.shape[0]           # 8-bit = 1 byte per sample
        saved = original_bytes - new_bytes
        saved_percent = round((saved / original_bytes) * 100, 2)

        return {
            "success": True,
            "original_size": original_bytes,
            "compressed_size": new_bytes,
            "saved": saved,
            "saved_percent": saved_percent
        }
    except Exception as e:
        print("Audio compression error:", e)
        return {"success": False, "error": str(e)}
