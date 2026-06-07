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
        # 音频设备选择：None 表示使用默认 Loopback
        self._audio_source_selection = None
        self._audio_source_lock = threading.Lock()
        self._reconnect_event = threading.Event()  # 触发重连信号
        self._force_stop_audio = threading.Event()  # 强制终止音频采集线程
        self._paused = True  # 初始为暂停状态，等用户手动开始

    def run(self):
        while self._is_running:
            # 暂停状态下等待恢复信号
            while self._is_running and self._paused:
                time.sleep(0.5)
            if not self._is_running:
                break

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
        self._reconnect_event.set()  # 唤醒可能等待的线程
        self._force_stop_audio.set()  # 强制终止音频线程
        if self.ws_app and self.ws_app.sock:
            self.ws_app.close()
        self.quit()
        self.wait()

    def pause(self):
        """暂停识别（断开 WebSocket，停止音频采集）"""
        if self._paused:
            return
        self._paused = True
        logger.info("⏸️ 暂停识别")
        self._force_stop_audio.set()
        if self.audio_thread and self.audio_thread.is_alive():
            self.audio_thread.join(timeout=2)
        if self.ws_app and self.ws_app.sock:
            self.ws_app.close()

    def resume(self):
        """恢复识别（触发重新连接）"""
        if not self._paused:
            return
        self._paused = False
        logger.info("▶️ 恢复识别")
        self._force_stop_audio.clear()
        # 关闭当前 ws 触发 run() 重连
        if self.ws_app and self.ws_app.sock:
            self.ws_app.close()
            self._reconnect_event.set()

    def is_paused(self):
        """返回当前是否暂停"""
        return self._paused

    def switch_audio_source(self, selection):
        """切换音频来源设备
        selection: {"type": "loopback", "device_index": int} 或
                   {"type": "microphone", "device_index": int}
        """
        with self._audio_source_lock:
            self._audio_source_selection = selection
        logger.info(f"音频来源切换为: {selection}")

        # 1. 强制终止旧音频采集线程
        self._force_stop_audio.set()
        if self.audio_thread and self.audio_thread.is_alive():
            logger.info("等待旧音频线程结束...")
            self.audio_thread.join(timeout=3)
            if self.audio_thread.is_alive():
                logger.warning("旧音频线程未在3秒内结束，继续执行")

        # 2. 关闭 WebSocket，触发 run() 中的 run_forever() 返回，自动重连
        if self.ws_app and self.ws_app.sock:
            self.ws_app.close()
            self._reconnect_event.set()
        logger.info("已触发重连，即将使用新设备重新开始")

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

        # 清除强制终止标志（新连接开始）
        self._force_stop_audio.clear()

        # 根据用户选择获取音频设备
        try:
            with self._audio_source_lock:
                selection = self._audio_source_selection
            if selection is None or selection.get("type") == "loopback":
                audio_device = self.get_loopback_device(
                    selection.get("device_index") if selection else None
                )
            else:
                audio_device = self.get_microphone_device(
                    selection.get("device_index")
                )
        except Exception as e:
            logger.error(f"无法获取音频设备: {e}")
            ws.close()
            return

        if self.audio_thread and self.audio_thread.is_alive():
            self.audio_thread.join(timeout=2)
        self.audio_thread = threading.Thread(
            target=self.stream_speaker_audio,
            args=(ws, audio_device),
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
                logger.info(f"服务器消息: {res}")
        except json.JSONDecodeError:
            logger.warning(f"收到非 JSON 消息: {message[:200]}")
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
        # 如果 close_msg 是 bytes，尝试解码
        if isinstance(close_msg, bytes) and close_msg:
            try:
                msg_str = close_msg.decode('utf-8')
                logger.info(f"WebSocket 关闭消息(解码): {msg_str}")
            except Exception:
                pass
        if self.audio_thread and self.audio_thread.is_alive():
            self.audio_thread.join(timeout=2)

    # ---------- 音频设备与采集 ----------
    @staticmethod
    def _is_loopback_device(dev_info):
        """判断设备是否为 WASAPI Loopback 设备"""
        name = dev_info.get('name', '')
        return 'loopback' in name.lower()

    def get_loopback_device(self, device_index=None):
        """获取 Loopback 设备信息
        device_index: 指定设备索引，None 则使用默认
        """
        p = pyaudio.PyAudio()
        try:
            if device_index is not None:
                # 使用指定索引的 Loopback 设备：遍历所有设备找到对应 Loopback
                for i in range(p.get_device_count()):
                    dev = p.get_device_info_by_index(i)
                    if dev['index'] == device_index and self._is_loopback_device(dev):
                        logger.info(f"扬声器 Loopback 设备: {dev['name']} (ID={dev['index']})")
                        return dev
                raise RuntimeError(f"未找到索引为 {device_index} 的 Loopback 设备")
            else:
                # 使用默认 Loopback
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

    def get_microphone_device(self, device_index):
        """获取麦克风设备信息"""
        p = pyaudio.PyAudio()
        try:
            dev_info = p.get_device_info_by_index(device_index)
            if dev_info.get('maxInputChannels', 0) == 0:
                raise RuntimeError(f"设备 {dev_info['name']} 不是输入设备")
            logger.info(f"麦克风设备: {dev_info['name']} (ID={device_index}, {int(dev_info['defaultSampleRate'])}Hz)")
            return dev_info
        except Exception as e:
            logger.error(f"获取麦克风设备失败: {e}")
            raise
        finally:
            p.terminate()

    def stream_speaker_audio(self, ws, audio_device):
        p = None
        stream = None
        keepalive_silence_start = None  # 长静音保活计时
        try:
            p = pyaudio.PyAudio()
            original_rate = int(audio_device["defaultSampleRate"])
            channels = audio_device["maxInputChannels"]
            frames_per_buffer = int(original_rate * CHUNK_MS / 1000.0)
            frames_per_buffer = max(frames_per_buffer, 1)

            stream = p.open(
                format=pyaudio.paInt16,
                channels=channels,
                rate=original_rate,
                input=True,
                input_device_index=audio_device["index"],
                frames_per_buffer=frames_per_buffer
            )
            logger.info(f"🎧 开始捕获音频 | 设备: {audio_device['name']} | 采样率: {original_rate}Hz | 声道数: {channels} | 块大小: {frames_per_buffer}帧 ({CHUNK_MS}ms)")

            packet_count = 0
            interval = CHUNK_MS / 1000.0
            next_send = time.perf_counter()

            while self._is_running:
                # 检查是否被强制终止（切换音频来源时）
                if self._force_stop_audio.is_set():
                    logger.info("收到强制终止信号，退出音频采集")
                    break

                if not ws.sock or not ws.sock.connected:
                    # WebSocket 已断开，等待重连或线程停止
                    time.sleep(0.5)
                    continue

                try:
                    raw_data = stream.read(frames_per_buffer, exception_on_overflow=False)
                except Exception:
                    continue

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
                        try:
                            ws.send(silence_data, websocket.ABNF.OPCODE_BINARY)
                        except Exception:
                            continue
                        packet_count += 1
                        keepalive_silence_start = now
                        continue

                    # 断句检测：0.5秒静音
                    if self._is_speaking:
                        if self._silence_start_time == 0.0:
                            self._silence_start_time = now
                        elif now - self._silence_start_time > SENTENCE_SILENCE_SEC:
                            # 静音超过0.5秒，发送断句信号
                            try:
                                self._send_sentence_end(ws)
                            except Exception:
                                pass
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
                        try:
                            self._send_sentence_end(ws)
                        except Exception:
                            pass
                        self._sentence_start_time = now
                        logger.debug(f"⏱️ 句子持续超过 {SENTENCE_MAX_DURATION}s，强制断句")

                    if packet_count % 100 == 0:
                        logger.debug(f"音频能量: {energy:.1f}")

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

                try:
                    ws.send(converted, websocket.ABNF.OPCODE_BINARY)
                except Exception:
                    continue
                packet_count += 1
                if packet_count % 200 == 0:
                    logger.info(f"已发送 {packet_count} 个音频包")

                next_send += interval
                sleep_time = next_send - time.perf_counter()
                if sleep_time > 0:
                    time.sleep(sleep_time)

        except websocket.WebSocketConnectionClosedException:
            logger.info("WebSocket 连接已关闭，等待重连...")
        except Exception as e:
            logger.error(f"扬声器音频捕获异常: {e}", exc_info=True)
        finally:
            if stream:
                stream.stop_stream()
                stream.close()
            if p:
                p.terminate()
            logger.info("扬声器捕获线程已退出")