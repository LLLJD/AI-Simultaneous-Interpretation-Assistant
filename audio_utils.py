# audio_utils.py
import struct
import math

def rms_energy(data):
    """计算16位PCM数据的均方根能量（近似音量）"""
    if not data:
        return 0
    samples = struct.unpack(f"<{len(data)//2}h", data)
    energy = math.sqrt(sum(s**2 for s in samples) / len(samples))
    return energy