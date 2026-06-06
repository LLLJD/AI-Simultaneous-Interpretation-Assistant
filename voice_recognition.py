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
from config import API_RATE, CHUNK_MS, SILENCE_THRESHOLD, MAX_SILENCE_SEC, SENTENCE_SILENCE_SEC, SENTENCE_MAX_DURATION
from audio_utils import rms_energy
from translation import translate_text

logger = logging.getLogger(__name__)

class SpeechRecognitionThread(QThread):
    text_updated = pyqtSignal(str)
    final_text = pyqtSignal(str)
    translation_ready = pyqtSignal(str, str, str, bool)  # (sentence_id, 原文, 译文, is_final)

    def __init__(self):
        super().__init__()
        self.ws_app = None
        self._is_running = True
        self.audio_thread = None
        # 断句状态
        self._sentence_start_time = 0.0  # 当前句子开始时间
        self._silence_start_time = 0.0   # 当前静音开始时间
        self._is_speaking = False        # 是否正在说话
        # 实时翻译追踪
        self._current_sentence_id = None  # 当前句子的唯一ID
        self._translation_lock = threading.Lock()  # 翻译去重锁

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
                mid_text = res['result']
                self.text_updated.emit(mid_text)
                # 如果是新句子，生成新ID
                if self._current_sentence_id is None:
                    self._start_new_sentence()
                # 异步触发临时翻译（防抖：如果翻译线程正在跑，跳过）
                threading.Thread(
                    target=self._translate_and_emit,
                    args=(self._current_sentence_id, mid_text, False),
                    daemon=True
                ).start()
            elif msg_type == "FIN_TEXT" and res.get("result"):
                final = res['result']
                self.final_text.emit(final)
                self.text_updated.emit(final)
                # 确保有 sentence_id
                if self._current_sentence_id is None:
                    self._start_new_sentence()
                sid = self._current_sentence_id
                # 异步最终翻译
                threading.Thread(
                    target=self._translate_and_emit,
                    args=(sid, final, True),
                    daemon=True
                ).start()
                self._current_sentence_id = None  # 重置，等待下一句
            elif msg_type == "ERROR":
                logger.error(f"服务端错误: {res}")
            else:
                logger.debug(f"服务器消息: {res}")
        except Exception as e:
            logger.error(f"处理消息异常: {e}")

    def _start_new_sentence(self):
        """新句子开始，生成短ID"""
        import uuid as _uuid
        self._current_sentence_id = str(_uuid.uuid4())[:8]

    def _translate_and_emit(self, sentence_id, text, is_final):
        """在后台线程中调用翻译 API，完成后发射信号"""
        # 中间结果去重：同一句子的中间翻译同时只跑一个
        if not is_final:
            if not self._translation_lock.acquire(blocking=False):
                return  # 上一轮中间翻译还没结束，跳过
        try:
            translated = translate_text(text)
            if translated:
                self.translation_ready.emit(sentence_id, text, translated, is_final)
        finally:
            if not is_final:
                self._translation_lock.release()

    def _send_sentence_end(self, ws):
        """发送断句信号（发送一个JSON格式的断句标记给百度API）"""
        try:
            end_req = {
                "type": "END",
            }
            ws.send(json.dumps(end_req), websocket.ABNF.OPCODE_TEXT)
        except Exception as e:
            logger.error(f"发送断句信号失败: {e}")

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
        keepalive_silence_start = None  # 长静音保活计时
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
                now = time.time()

                if energy < SILENCE_THRESHOLD:
                    # --- 静音检测 ---
                    # 长时间静音保活
                    if keepalive_silence_start is None:
                        keepalive_silence_start = now
                    elif now - keepalive_silence_start > MAX_SILENCE_SEC:
                        logger.warning(f"长时间静音 ({MAX_SILENCE_SEC}秒)，发送人工静音包保持连接")
                        expected_len = int(API_RATE * CHUNK_MS / 1000) * 2
                        silence_data = b'\x00' * expected_len
                        ws.send(silence_data, websocket.ABNF.OPCODE_BINARY)
                        packet_count += 1
                        keepalive_silence_start = now
                        continue

                    # 断句检测：0.5秒静音
                    if self._is_speaking:
                        if self._silence_start_time == 0.0:
                            self._silence_start_time = now
                        elif now - self._silence_start_time > SENTENCE_SILENCE_SEC:
                            # 静音超过0.5秒，发送断句信号
                            self._send_sentence_end(ws)
                            self._is_speaking = False
                            self._silence_start_time = 0.0
                            self._sentence_start_time = 0.0
                            logger.debug(f"🔇 静音 {SENTENCE_SILENCE_SEC}s，触发断句")
                else:
                    # --- 有声音 ---
                    keepalive_silence_start = None
                    self._silence_start_time = 0.0

                    if not self._is_speaking:
                        # 新句子开始
                        self._is_speaking = True
                        self._sentence_start_time = now
                        logger.debug("🎤 检测到语音，开始新句子")
                    elif now - self._sentence_start_time > SENTENCE_MAX_DURATION:
                        # 句子超过10秒，强制断句
                        self._send_sentence_end(ws)
                        self._sentence_start_time = now
                        logger.debug(f"⏱️ 句子持续超过 {SENTENCE_MAX_DURATION}s，强制断句")

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