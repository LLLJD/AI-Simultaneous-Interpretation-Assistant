# voice_recognition.py
import threading
import json
import logging
import uuid
import time
import struct

import websocket
import pyaudiowpatch as pyaudio
import audioop

from PyQt5.QtCore import QThread, pyqtSignal

import API
from config import API_RATE, CHUNK_MS, SILENCE_THRESHOLD, MAX_SILENCE_SEC
from audio_utils import rms_energy

logger = logging.getLogger(__name__)

class SpeechRecognitionThread(QThread):
    text_updated = pyqtSignal(str)
    final_text = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.ws_app = None
        self._is_running = True
        self.audio_thread = None

    def run(self):
        while self._is_running:
            uri = f"{API.URI}?sn={uuid.uuid1()}"
            logger.info(f"连接地址: {uri}")

            self.ws_app = websocket.WebSocketApp(
                uri,
                on_open=self.on_open,
                on_message=self.on_message,
                on_error=self.on_error,
                on_close=self.on_close
            )
            self.ws_app.run_forever()

            if self._is_running:
                logger.info("尝试在5秒后重连...")
                time.sleep(5)
            else:
                break
        logger.info("语音识别线程结束")

    def stop(self):
        self._is_running = False
        if self.ws_app and self.ws_app.sock:
            self.ws_app.close()
        self.quit()
        self.wait()

    def on_open(self, ws):
        start_req = {
            "type": "START",
            "data": {
                "appid": int(API.APPID),
                "appkey": API.APIKEY,
                "dev_pid": int(API.DEV_PID),
                "cuid": "pyqt_speaker_client",
                "sample": API_RATE,
                "format": "pcm"
            }
        }
        ws.send(json.dumps(start_req), websocket.ABNF.OPCODE_TEXT)
        logger.info("📤 已发送 START 指令")

        try:
            loopback_device = self.get_default_speaker_loopback()
        except Exception as e:
            logger.error(f"无法获取扬声器 Loopback 设备: {e}")
            ws.close()
            return

        if self.audio_thread and self.audio_thread.is_alive():
            self.audio_thread.join(timeout=2)
        self.audio_thread = threading.Thread(
            target=self.stream_speaker_audio,
            args=(ws, loopback_device),
            daemon=True
        )
        self.audio_thread.start()

    def on_message(self, ws, message):
        try:
            res = json.loads(message)
            msg_type = res.get("type")
            if msg_type == "MID_TEXT" and res.get("result"):
                self.text_updated.emit(res['result'])
            elif msg_type == "FIN_TEXT" and res.get("result"):
                final = res['result']
                self.final_text.emit(final)
                self.text_updated.emit(final)
            elif msg_type == "ERROR":
                logger.error(f"服务端错误: {res}")
            else:
                logger.debug(f"服务器消息: {res}")
        except Exception as e:
            logger.error(f"处理消息异常: {e}")

    def on_error(self, ws, error):
        logger.error(f"WebSocket 错误: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        logger.info(f"WebSocket 关闭: code={close_status_code}, msg={close_msg}")
        if self.audio_thread and self.audio_thread.is_alive():
            self.audio_thread.join(timeout=2)

    # ---------- 音频设备与采集 ----------
    def get_default_speaker_loopback(self):
        p = pyaudio.PyAudio()
        try:
            loopback_device = p.get_default_wasapi_loopback()
            if not loopback_device:
                raise RuntimeError("未找到默认的 WASAPI Loopback 设备")
            logger.info(f"扬声器 Loopback 设备: {loopback_device['name']} (ID={loopback_device['index']})")
            return loopback_device
        except Exception as e:
            logger.error(f"获取扬声器 Loopback 设备失败: {e}")
            raise
        finally:
            p.terminate()

    def stream_speaker_audio(self, ws, loopback_device):
        p = None
        stream = None
        silence_start = None
        try:
            p = pyaudio.PyAudio()
            original_rate = int(loopback_device["defaultSampleRate"])
            frames_per_buffer = int(original_rate * CHUNK_MS / 1000.0)
            frames_per_buffer = max(frames_per_buffer, 1)

            stream = p.open(
                format=pyaudio.paInt16,
                channels=loopback_device["maxInputChannels"],
                rate=original_rate,
                input=True,
                input_device_index=loopback_device["index"],
                frames_per_buffer=frames_per_buffer
            )
            logger.info(f"🎧 开始捕获扬声器音频 | 设备: {loopback_device['name']} | 采样率: {original_rate}Hz | 声道数: {loopback_device['maxInputChannels']} | 块大小: {frames_per_buffer}帧 ({CHUNK_MS}ms)")

            packet_count = 0
            interval = CHUNK_MS / 1000.0
            next_send = time.perf_counter()

            while ws.sock and ws.sock.connected:
                raw_data = stream.read(frames_per_buffer, exception_on_overflow=False)

                energy = rms_energy(raw_data)
                if energy < SILENCE_THRESHOLD:
                    if silence_start is None:
                        silence_start = time.time()
                    elif time.time() - silence_start > MAX_SILENCE_SEC:
                        logger.warning(f"长时间静音 ({MAX_SILENCE_SEC}秒)，发送人工静音包保持连接")
                        expected_len = int(API_RATE * CHUNK_MS / 1000) * 2
                        silence_data = b'\x00' * expected_len
                        ws.send(silence_data, websocket.ABNF.OPCODE_BINARY)
                        packet_count += 1
                        silence_start = time.time()
                        continue
                else:
                    silence_start = None
                    if packet_count % 100 == 0:
                        logger.debug(f"音频能量: {energy:.1f}")

                channels = loopback_device["maxInputChannels"]
                if channels > 1:
                    fmt = f"<{channels}h"
                    frame_size = struct.calcsize(fmt)
                    mono_data = bytearray()
                    for i in range(0, len(raw_data), frame_size):
                        frame = struct.unpack(fmt, raw_data[i:i+frame_size])
                        avg = int(sum(frame) / channels)
                        mono_data.extend(struct.pack("<h", avg))
                    raw_data = bytes(mono_data)

                if original_rate != API_RATE:
                    converted, _ = audioop.ratecv(raw_data, 2, 1, original_rate, API_RATE, None)
                else:
                    converted = raw_data

                expected_len = int(API_RATE * CHUNK_MS / 1000) * 2
                if len(converted) > expected_len:
                    converted = converted[:expected_len]
                elif len(converted) < expected_len:
                    converted += b'\x00' * (expected_len - len(converted))

                ws.send(converted, websocket.ABNF.OPCODE_BINARY)
                packet_count += 1
                if packet_count % 200 == 0:
                    logger.info(f"已发送 {packet_count} 个音频包")

                next_send += interval
                sleep_time = next_send - time.perf_counter()
                if sleep_time > 0:
                    time.sleep(sleep_time)

        except websocket.WebSocketConnectionClosedException:
            logger.warning("WebSocket 连接已关闭，音频线程退出")
        except Exception as e:
            logger.error(f"扬声器音频捕获异常: {e}", exc_info=True)
        finally:
            if stream:
                stream.stop_stream()
                stream.close()
            if p:
                p.terminate()
            logger.info("扬声器捕获线程已退出")