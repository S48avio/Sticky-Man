# --- LIGHTWEIGHT PROCESS HANDOVER (Pure Python - No PyQt Imports here!) ---
import sys
import os
import socket
import argparse
import subprocess

PORT = 49152 # Dedicated local TCP port for StickyMan

def fast_get_primary_selection():
    try:
        result = subprocess.run(['wl-paste', '-p'], capture_output=True, text=True, timeout=0.1)
        if result.returncode == 0 and result.stdout.strip(): return result.stdout.strip()
    except: pass
    try:
        result = subprocess.run(['xclip', '-o', '-selection', 'primary'], capture_output=True, text=True, timeout=0.1)
        if result.returncode == 0 and result.stdout.strip(): return result.stdout.strip()
    except: pass
    return ""

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["text", "open"], default="text")
    args = parser.parse_args()

    # Fast check: If port is open, a primary instance is already running
    try:
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(0.1)
        client.connect(('127.0.0.1', PORT))
        
        payload = ""
        if args.mode == "text":
            payload = fast_get_primary_selection()
                
        message = f"{args.mode}|{payload}"
        client.sendall(message.encode('utf-8'))
        client.close()
        sys.exit(0) # Exit instantly! Loading took less than 15ms.
    except (ConnectionRefusedError, socket.timeout):
        pass # No primary instance running. Proceed to boot up.

# --- HEAVY IMPORTS (Only executed by the primary background instance) ---
import re
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLabel, QScrollArea, QStackedWidget, 
                             QListWidget, QListWidgetItem, QTextEdit, QFrame, 
                             QComboBox, QLineEdit, QCheckBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QPropertyAnimation, QPoint, QEasingCurve, QTimer, QEvent
from PyQt6.QtGui import QGuiApplication, QPixmap, QIcon

from backend import (get_primary_selection, ask_openrouter_stream, save_to_history, 
                     get_history, get_config, set_config, get_limit_string, get_latest_chat)

def markdown_to_html(text):
    """Converts common Markdown elements to PyQt RichText compatible HTML."""
    text = re.sub(r'^### (.*?)$', r'<h3>\1</h3>', text, flags=re.MULTILINE)
    text = re.sub(r'^## (.*?)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)
    text = re.sub(r'^# (.*?)$', r'<h1>\1</h1>', text, flags=re.MULTILINE)
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)
    text = re.sub(r'`(.*?)`', r'<code style="background-color: #2b2d30; padding: 2px; border-radius: 3px; font-family: monospace;">\1</code>', text)
    text = re.sub(r'^\* (.*?)$', r'<li>\1</li>', text, flags=re.MULTILINE)
    text = re.sub(r'^- (.*?)$', r'<li>\1</li>', text, flags=re.MULTILINE)
    text = text.replace('\n', '<br>')
    return text


class SocketListenerThread(QThread):
    """Pure-Python Socket server thread that runs inside the primary PyQt window."""
    trigger_received = pyqtSignal(str, str)

    def run(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server.bind(('127.0.0.1', PORT))
            server.listen(5)
            while True:
                conn, addr = server.accept()
                data = conn.recv(4096).decode('utf-8')
                if data and "|" in data:
                    mode, payload = data.split("|", 1)
                    self.trigger_received.emit(mode, payload)
                conn.close()
        except Exception as e:
            print(f"Socket server error: {e}")


class AIWorker(QThread):
    chunk_received = pyqtSignal(str)
    finished = pyqtSignal(str)

    def __init__(self, session_messages):
        super().__init__()
        self.session_messages = session_messages

    def run(self):
        try:
            stream = ask_openrouter_stream(self.session_messages)
            if not stream:
                self.finished.emit("Error: Stream initialization failed.")
                return

            full_response = ""
            for chunk in stream:
                if len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    
                    reasoning = getattr(delta, "reasoning", None) or getattr(delta, "reasoning_details", None)
                    if not reasoning and hasattr(delta, "model_extra") and delta.model_extra:
                        reasoning = delta.model_extra.get("reasoning") or delta.model_extra.get("reasoning_details")
                    
                    if reasoning:
                        full_response += f"<thought_chunk>{reasoning}</thought_chunk>"
                        self.chunk_received.emit(f"<thought_chunk>{reasoning}</thought_chunk>")
                    
                    content = delta.content or ""
                    if content:
                        full_response += content
                        self.chunk_received.emit(content)
                        
            self.finished.emit(full_response)
        except Exception as e:
            self.finished.emit(f"Error: {e}")


class CollapsibleThinkingWidget(QWidget):
    def __init__(self, thought_text):
        super().__init__()
        self.thought_text = thought_text
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 10)
        layout.setSpacing(4)

        self.frame = QFrame()
        self.frame.setStyleSheet("background-color: #1a1b1d; border-left: 3px solid #FFD700; border-radius: 4px;")
        frame_layout = QVBoxLayout(self.frame)
        frame_layout.setContentsMargins(8, 8, 8, 8)
        frame_layout.setSpacing(4)

        self.toggle_btn = QPushButton("▶ Thinking Process")
        self.toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_btn.setStyleSheet("color: #FFD700; font-size: 11px; text-align: left; font-weight: bold; background: transparent; border: none; padding: 0;")
        self.toggle_btn.clicked.connect(self.toggle_visibility)
        frame_layout.addWidget(self.toggle_btn)

        self.content_lbl = QLabel(markdown_to_html(self.thought_text))
        self.content_lbl.setWordWrap(True)
        self.content_lbl.setTextFormat(Qt.TextFormat.RichText)
        self.content_lbl.setStyleSheet("color: #a9b7c6; font-size: 11px; font-style: italic; border: none; background: transparent; padding-left: 10px;")
        self.content_lbl.setVisible(False)
        frame_layout.addWidget(self.content_lbl)

        layout.addWidget(self.frame)

    def toggle_visibility(self):
        is_visible = self.content_lbl.isVisible()
        self.content_lbl.setVisible(not is_visible)
        self.toggle_btn.setText("▼ Thinking Process" if not is_visible else "▶ Thinking Process")


class ThinkingLabel(QWidget):
    def __init__(self):
        super().__init__()
        self.dots = 1
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 10)
        
        header_row = QWidget()
        h_layout = QHBoxLayout(header_row)
        h_layout.setContentsMargins(0, 5, 0, 5)
        h_layout.setSpacing(6)
        
        logo_icon = QLabel()
        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")
        if os.path.exists(logo_path):
            logo_pix = QPixmap(logo_path).scaled(16, 16, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            logo_icon.setPixmap(logo_pix)
        
        name_lbl = QLabel("StickyMan")
        name_lbl.setStyleSheet("color: #FFD700; font-weight: bold; font-size: 13px;")
        
        h_layout.addWidget(logo_icon)
        h_layout.addWidget(name_lbl)
        h_layout.addStretch()
        layout.addWidget(header_row)
        
        self.text_label = QLabel("Thinking.")
        self.text_label.setStyleSheet("color: #e4e4e4; font-size: 13px;")
        layout.addWidget(self.text_label)
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_dots)
        self.timer.start(500)

    def update_dots(self):
        self.dots = (self.dots % 3) + 1
        self.text_label.setText("Thinking" + "." * self.dots)

    def stop(self):
        self.timer.stop()


class FloatingAIWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.session_messages = []
        self.is_active_visible = False
        self.current_thinking_widget = None
        self.drag_position = QPoint()
        
        # Real-time Stream tracking states
        self.is_streaming = False
        self.current_stream_text = ""
        self.current_stream_thoughts = ""
        self.current_followup_prompt = ""

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")
        if os.path.exists(logo_path):
            self.setWindowIcon(QIcon(logo_path))

        self.width, self.height = 360, 520
        self.resize(self.width, self.height)
        
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.target_x = screen.width() - self.width - 20
        self.target_y = screen.height() - self.height - 20
        self.start_y = screen.height() + 10 
        self.move(self.target_x, self.start_y)
        
        self.init_ui()
        
        self.inactivity_timer = QTimer(self)
        self.inactivity_timer.timeout.connect(self.animate_popdown)
        self.reset_inactivity_timer()
        
        QApplication.instance().installEventFilter(self)

    # --- DRAGGABLE WINDOW LOGIC ---
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            self.target_x = self.x()
            self.target_y = self.y()
            screen = QGuiApplication.primaryScreen().availableGeometry()
            self.start_y = screen.height() + 10
            event.accept()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        self.container = QFrame()
        self.container.setObjectName("container")
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(10, 10, 10, 10)

        # --- TOP HEADER ---
        header_layout = QHBoxLayout()
        
        self.logo_label = QLabel()
        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")
        if os.path.exists(logo_path):
            logo_pix = QPixmap(logo_path).scaled(24, 24, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.logo_label.setPixmap(logo_pix)
        header_layout.addWidget(self.logo_label)

        self.title_label = QLabel("StickyMan")
        self.title_label.setStyleSheet("font-weight: bold; font-size: 15px; color: #FFD700;")
        
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #a9b7c6; font-size: 11px;")
        
        self.settings_btn = QPushButton("⚙️")
        self.settings_btn.setToolTip("Settings")
        self.settings_btn.setFixedSize(26, 26)
        self.settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_btn.clicked.connect(self.toggle_settings)
        
        self.close_btn = QPushButton("❌")
        self.close_btn.setToolTip("Close")
        self.close_btn.setFixedSize(26, 26)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.clicked.connect(self.animate_popdown)

        header_layout.addWidget(self.title_label)
        header_layout.addWidget(self.status_label)
        header_layout.addStretch()
        header_layout.addWidget(self.settings_btn)
        header_layout.addWidget(self.close_btn)
        container_layout.addLayout(header_layout)

        # --- STACKED WIDGET ---
        self.stack = QStackedWidget()
        container_layout.addWidget(self.stack)

        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.chat_content = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_content)
        self.chat_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.chat_scroll.setWidget(self.chat_content)
        self.stack.addWidget(self.chat_scroll)

        self.history_list = QListWidget()
        self.history_list.itemClicked.connect(self.show_history_detail)
        self.stack.addWidget(self.history_list)

        self.history_detail_scroll = QScrollArea()
        self.history_detail_scroll.setWidgetResizable(True)
        self.history_detail_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.history_detail_content = QWidget()
        self.history_detail_layout = QVBoxLayout(self.history_detail_content)
        self.history_detail_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.history_detail_scroll.setWidget(self.history_detail_content)
        self.stack.addWidget(self.history_detail_scroll)
        
        self.init_settings_view()
        self.stack.addWidget(self.settings_widget)

        # --- CHAT INPUT BAR ---
        self.input_layout = QHBoxLayout()
        self.input_bar = QLineEdit()
        self.input_bar.setPlaceholderText("Ask subsequent question...")
        self.input_bar.setStyleSheet("background-color: #2b2d30; color: white; border: 1px solid #555; border-radius: 4px; padding: 6px;")
        self.input_bar.returnPressed.connect(self.send_followup)
        
        self.send_btn = QPushButton("➔")
        self.send_btn.setFixedSize(26, 26)
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.clicked.connect(self.send_followup)
        
        self.input_layout.addWidget(self.input_bar)
        self.input_layout.addWidget(self.send_btn)
        container_layout.addLayout(self.input_layout)

        # --- BOTTOM FOOTER ---
        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(0, 5, 0, 0)
        
        self.history_btn = QPushButton("🕒")
        self.history_btn.setToolTip("History")
        self.history_btn.setFixedSize(26, 26)
        self.history_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.history_btn.clicked.connect(self.toggle_history)
        
        self.model_limit_label = QLabel(get_limit_string())
        self.model_limit_label.setStyleSheet("color: #888; font-size: 10px;")
        self.model_limit_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        
        footer_layout.addWidget(self.history_btn)
        footer_layout.addStretch()
        footer_layout.addWidget(self.model_limit_label)
        container_layout.addLayout(footer_layout)

        main_layout.addWidget(self.container)

        self.setStyleSheet("""
            #container { background-color: #1e1f22; border: 1px solid #FFD700; border-radius: 12px; }
            QPushButton { background-color: transparent; border: none; font-size: 14px; }
            QPushButton:hover { background-color: #383a40; border-radius: 4px; }
            QListWidget { background-color: transparent; border: none; color: white; font-size: 13px; }
            QListWidget::item { padding: 8px; border-bottom: 1px solid #333; }
            QListWidget::item:hover { background-color: #2b2d30; }
            QScrollBar:vertical { background: #1e1f22; width: 6px; }
            QScrollBar::handle:vertical { background: #FFD700; border-radius: 3px; }
        """)

    def init_settings_view(self):
        self.settings_widget = QWidget()
        s_layout = QVBoxLayout(self.settings_widget)
        s_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        title = QLabel("⚙️ Settings")
        title.setStyleSheet("color: #FFD700; font-weight: bold; font-size: 16px; margin-bottom: 10px;")
        s_layout.addWidget(title)
        
        s_layout.addWidget(QLabel("Select Model:"))
        self.model_combo = QComboBox()
        models = [
            "openrouter/free",
            "tencent/hy3:free",
            "google/gemini-2.0-flash-exp:free",
            "meta-llama/llama-3.3-70b-instruct:free",
            "meta-llama/llama-3.2-11b-vision-instruct:free"
        ]
        self.model_combo.addItems(models)
        self.model_combo.setCurrentText(get_config("model"))
        self.model_combo.setStyleSheet("background: #2b2d30; color: white; padding: 5px; border: 1px solid #555; border-radius: 4px;")
        s_layout.addWidget(self.model_combo)
        
        s_layout.addWidget(QLabel("OpenRouter API Key:"))
        self.api_input = QLineEdit()
        self.api_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_input.setText(get_config("api_key"))
        self.api_input.setStyleSheet("background: #2b2d30; color: white; padding: 5px; border: 1px solid #555; border-radius: 4px;")
        s_layout.addWidget(self.api_input)
        
        s_layout.addWidget(QLabel("Inactivity Timeout (seconds):"))
        self.timeout_input = QLineEdit()
        self.timeout_input.setText(get_config("inactivity_timeout"))
        self.timeout_input.setStyleSheet("background: #2b2d30; color: white; padding: 5px; border: 1px solid #555; border-radius: 4px;")
        s_layout.addWidget(self.timeout_input)
        
        s_layout.addWidget(QLabel("System Prompt:"))
        self.system_prompt_input = QTextEdit()
        self.system_prompt_input.setPlainText(get_config("system_prompt"))
        self.system_prompt_input.setStyleSheet("background: #2b2d30; color: white; padding: 5px; border: 1px solid #555; border-radius: 4px; font-size: 11px;")
        self.system_prompt_input.setMaximumHeight(80)
        s_layout.addWidget(self.system_prompt_input)
        
        self.reasoning_checkbox = QCheckBox("Enable Deep Thinking (Reasoning)")
        self.reasoning_checkbox.setChecked(get_config("reasoning_enabled") == "1")
        self.reasoning_checkbox.setStyleSheet("color: white; margin-top: 10px; margin-bottom: 10px;")
        s_layout.addWidget(self.reasoning_checkbox)

        save_btn = QPushButton("Save Settings")
        save_btn.setStyleSheet("background-color: #FFD700; color: black; font-weight: bold; padding: 8px; border-radius: 5px; margin-top: 15px;")
        save_btn.clicked.connect(self.save_settings)
        s_layout.addWidget(save_btn)

    def save_settings(self):
        set_config("model", self.model_combo.currentText())
        set_config("api_key", self.api_input.text())
        set_config("inactivity_timeout", self.timeout_input.text())
        set_config("system_prompt", self.system_prompt_input.toPlainText().strip())
        set_config("reasoning_enabled", "1" if self.reasoning_checkbox.isChecked() else "0")
        self.model_limit_label.setText(get_limit_string())
        self.reset_inactivity_timer()
        self.stack.setCurrentIndex(0)
        self.status_label.setText("Saved!")

    # --- ACTIONS ---
    def handle_external_trigger(self, mode, payload):
        self.reset_inactivity_timer()
        
        if mode == "open":
            if self.is_active_visible:
                self.animate_popdown()
            else:
                self.load_latest_chat_and_show()
            return

        if not self.is_active_visible:
            self.animate_popup()

        self.stack.setCurrentIndex(0)
        
        if mode == "text":
            self.current_followup_prompt = payload
            self.session_messages = [{"role": "user", "content": payload}]
            self.clear_chat_layout(self.chat_layout)
            self.append_message_bubble("user", payload)

        self.append_thinking_indicator()

        self.worker = AIWorker(self.session_messages)
        self.worker.chunk_received.connect(self.handle_chunk)
        self.worker.finished.connect(self.handle_stream_finished)
        self.worker.start()

    def load_latest_chat_and_show(self):
        self.animate_popup()
        latest = get_latest_chat()
        if latest:
            prompt, response, image_path = latest
            self.session_messages = [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": response}
            ]
            self.clear_chat_layout(self.chat_layout)
            self.append_message_bubble("user", prompt)
            self.append_message_bubble("assistant", response)
        else:
            self.clear_chat_layout(self.chat_layout)
            self.append_message_bubble("assistant", "No prior history. Select text and press Ctrl+Alt+A!")

    # --- REAL-TIME STREAM HANDLERS ---
    def handle_chunk(self, chunk):
        self.reset_inactivity_timer()
        
        if not self.is_streaming:
            self.remove_thinking_indicator()
            self.is_streaming = True
            self.current_stream_text = ""
            self.current_stream_thoughts = ""
            
            # Inline Header setup
            header_widget = QWidget()
            h_layout = QHBoxLayout(header_widget)
            h_layout.setContentsMargins(0, 5, 0, 5)
            h_layout.setSpacing(6)
            
            logo_icon = QLabel()
            logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")
            if os.path.exists(logo_path):
                logo_pix = QPixmap(logo_path).scaled(16, 16, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                logo_icon.setPixmap(logo_pix)
                
            name_lbl = QLabel("StickyMan")
            name_lbl.setStyleSheet("color: #FFD700; font-weight: bold; font-size: 13px;")
            h_layout.addWidget(logo_icon)
            h_layout.addWidget(name_lbl)
            h_layout.addStretch()
            self.chat_layout.addWidget(header_widget)
            
            # Temporary stream display label
            self.current_stream_label = QLabel()
            self.current_stream_label.setWordWrap(True)
            self.current_stream_label.setTextFormat(Qt.TextFormat.RichText)
            self.current_stream_label.setStyleSheet("color: #e4e4e4; font-size: 13px; margin-bottom: 10px;")
            self.chat_layout.addWidget(self.current_stream_label)

        # Separate thought chunks from main response text
        if "<thought_chunk>" in chunk:
            raw_thought = chunk.replace("<thought_chunk>", "").replace("</thought_chunk>", "")
            self.current_stream_thoughts += raw_thought
        else:
            self.current_stream_text += chunk
            
        display_text = self.current_stream_text
        if self.current_stream_thoughts:
            display_text = f"💭 *[Thinking Process Running...]*\n\n" + display_text
            
        self.current_stream_label.setText(markdown_to_html(display_text))
        self.scroll_to_bottom()

    def handle_stream_finished(self, full_response):
        self.is_streaming = False
        self.remove_thinking_indicator()
        
        final_rendered_text = full_response
        if self.current_stream_thoughts:
            final_rendered_text = f"<thought>\n{self.current_stream_thoughts}\n</thought>\n\n{self.current_stream_text}"

        save_to_history(self.current_followup_prompt, final_rendered_text, "text")
        self.session_messages.append({"role": "user", "content": self.current_followup_prompt})
        self.session_messages.append({"role": "assistant", "content": final_rendered_text})
        
        self.clear_chat_layout(self.chat_layout)
        for msg in self.session_messages:
            sender = "user" if msg["role"] == "user" else "assistant"
            self.append_message_bubble(sender, msg["content"])
            
        self.model_limit_label.setText(get_limit_string())
        self.scroll_to_bottom()

    def send_followup(self):
        self.reset_inactivity_timer()
        user_prompt = self.input_bar.text().strip()
        if not user_prompt: return
        
        self.input_bar.clear()
        self.append_message_bubble("user", user_prompt)
        self.append_thinking_indicator()
        
        self.current_followup_prompt = user_prompt
        
        recent_context = self.session_messages[-5:] if len(self.session_messages) > 5 else self.session_messages
        recent_context.append({"role": "user", "content": user_prompt})
        
        self.worker = AIWorker(recent_context)
        self.worker.chunk_received.connect(self.handle_chunk)
        self.worker.finished.connect(self.handle_stream_finished)
        self.worker.start()

    def clear_chat_layout(self, layout):
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def append_message_bubble(self, sender, text, image_path=None):
        if sender == "user":
            bubble = QLabel(f"<span style='color: #FFD700;'><b>👤 You</b></span><br><br>{markdown_to_html(text)}")
            bubble.setWordWrap(True)
            bubble.setTextFormat(Qt.TextFormat.RichText)
            bubble.setStyleSheet("color: #e4e4e4; font-size: 13px; background: #2b2d30; padding: 10px; border-radius: 8px; margin-bottom: 10px;")
            self.chat_layout.addWidget(bubble)
        else:
            # Inline Header layout featuring custom logo.png
            header_widget = QWidget()
            h_layout = QHBoxLayout(header_widget)
            h_layout.setContentsMargins(0, 5, 0, 5)
            h_layout.setSpacing(6)
            
            logo_icon = QLabel()
            logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")
            if os.path.exists(logo_path):
                logo_pix = QPixmap(logo_path).scaled(16, 16, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                logo_icon.setPixmap(logo_pix)
                
            name_lbl = QLabel("StickyMan")
            name_lbl.setStyleSheet("color: #FFD700; font-weight: bold; font-size: 13px;")
            
            h_layout.addWidget(logo_icon)
            h_layout.addWidget(name_lbl)
            h_layout.addStretch()
            self.chat_layout.addWidget(header_widget)

            # --- PARSE REASONING PROCESS BLOCK ---
            thought_content = ""
            main_response = text
            if "<thought>" in text and "</thought>" in text:
                try:
                    parts = text.split("</thought>", 1)
                    thought_part = parts[0].split("<thought>", 1)[1]
                    thought_content = thought_part.strip()
                    main_response = parts[1].strip()
                except:
                    pass
            
            # Render Collapsible Thought block (Collapsed by default!)
            if thought_content:
                collapsible_thought = CollapsibleThinkingWidget(thought_content)
                self.chat_layout.addWidget(collapsible_thought)

            # Render standard response text (Converted to RichText HTML for Markdown support)
            parts = main_response.split("```")
            for i, part in enumerate(parts):
                if i % 2 == 0:
                    if part.strip():
                        lbl = QLabel(markdown_to_html(part.strip()))
                        lbl.setWordWrap(True)
                        lbl.setTextFormat(Qt.TextFormat.RichText)
                        lbl.setStyleSheet("color: #e4e4e4; font-size: 13px; margin-bottom: 10px;")
                        self.chat_layout.addWidget(lbl)
                else:
                    lines = part.split('\n', 1)
                    language = lines[0].strip() if len(lines) > 1 else ""
                    code_content = lines[1].strip() if len(lines) > 1 else lines[0].strip()
                    
                    code_container = QWidget()
                    code_container.setStyleSheet("background-color: #141517; border-radius: 6px; margin-bottom: 10px;")
                    c_layout = QVBoxLayout(code_container)
                    c_layout.setContentsMargins(5, 5, 5, 5)
                    
                    top_bar = QWidget()
                    top_layout = QHBoxLayout(top_bar)
                    top_layout.setContentsMargins(0, 0, 0, 0)
                    lang_lbl = QLabel(language.upper())
                    lang_lbl.setStyleSheet("color: #888; font-size: 10px; font-weight: bold;")
                    
                    copy_btn = QPushButton("📋 Copy")
                    copy_btn.setFixedSize(60, 22)
                    copy_btn.setStyleSheet("font-size: 10px; background-color: #383a40; color: white;")
                    copy_btn.clicked.connect(lambda checked, text_block=code_content: self.copy_specific_text(text_block))
                    
                    top_layout.addWidget(lang_lbl)
                    top_layout.addStretch()
                    top_layout.addWidget(copy_btn)
                    c_layout.addWidget(top_bar)
                    
                    code_display = QTextEdit()
                    code_display.setReadOnly(True)
                    code_display.setPlainText(code_content)
                    code_display.setStyleSheet("background: transparent; color: #a9b7c6; font-family: monospace; border: none;")
                    
                    doc_height = code_display.document().size().height()
                    code_display.setMinimumHeight(int(doc_height) + 15)
                    code_display.setMaximumHeight(300)
                    c_layout.addWidget(code_display)
                    self.chat_layout.addWidget(code_container)

        self.scroll_to_bottom()

    def append_thinking_indicator(self):
        self.remove_thinking_indicator()
        self.current_thinking_widget = ThinkingLabel()
        self.chat_layout.addWidget(self.current_thinking_widget)
        self.scroll_to_bottom()

    def remove_thinking_indicator(self):
        if self.current_thinking_widget:
            self.current_thinking_widget.stop()
            self.current_thinking_widget.setParent(None)
            self.current_thinking_widget = None

    def scroll_to_bottom(self):
        QTimer.singleShot(100, lambda: self.chat_scroll.verticalScrollBar().setValue(
            self.chat_scroll.verticalScrollBar().maximum()
        ))

    def reset_inactivity_timer(self):
        try:
            timeout_sec = int(get_config("inactivity_timeout"))
        except:
            timeout_sec = 20
        self.inactivity_timer.start(timeout_sec * 1000)

    def eventFilter(self, obj, event):
        if event.type() in [QEvent.Type.KeyPress, QEvent.Type.MouseButtonPress, QEvent.Type.MouseMove]:
            self.reset_inactivity_timer()
        return super().eventFilter(obj, event)

    def animate_popup(self):
        self.reset_inactivity_timer()
        self.show()
        self.animation = QPropertyAnimation(self, b"pos")
        self.animation.setDuration(400)
        self.animation.setStartValue(QPoint(self.target_x, self.start_y))
        self.animation.setEndValue(QPoint(self.target_x, self.target_y))
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.start()
        self.is_active_visible = True

    def animate_popdown(self):
        self.inactivity_timer.stop()
        self.animation = QPropertyAnimation(self, b"pos")
        self.animation.setDuration(400)
        self.animation.setStartValue(QPoint(self.target_x, self.target_y))
        self.animation.setEndValue(QPoint(self.target_x, self.start_y))
        self.animation.setEasingCurve(QEasingCurve.Type.InCubic)
        self.animation.finished.connect(self.hide)
        self.animation.start()
        self.is_active_visible = False

    def copy_specific_text(self, text):
        QApplication.clipboard().setText(text)
        self.status_label.setText("Copied!")

    def toggle_history(self):
        self.reset_inactivity_timer()
        if self.stack.currentIndex() == 1 or self.stack.currentIndex() == 2:
            self.stack.setCurrentIndex(0)
            self.status_label.setText("")
        else:
            self.status_label.setText("History")
            self.history_list.clear()
            for row in get_history():
                row_id, prompt, response, image_path = row
                preview = prompt[:40].replace('\n', ' ') + "..."
                item = QListWidgetItem(f"👤 {preview}")
                item.setData(Qt.ItemDataRole.UserRole, (prompt, response, image_path))
                self.history_list.addItem(item)
            self.stack.setCurrentIndex(1)

    def toggle_settings(self):
        self.reset_inactivity_timer()
        if self.stack.currentIndex() == 3:
            self.stack.setCurrentIndex(0)
        else:
            self.stack.setCurrentIndex(3)

    def show_history_detail(self, item):
        prompt, response, image_path = item.data(Qt.ItemDataRole.UserRole)
        self.clear_chat_layout(self.history_detail_layout)
        
        p_label = QLabel(f"<span style='color: #FFD700;'><b>👤 You</b></span><br><br>{markdown_to_html(prompt)}")
        p_label.setWordWrap(True)
        p_label.setTextFormat(Qt.TextFormat.RichText)
        p_label.setStyleSheet("color: #e4e4e4; font-size: 13px; background: #2b2d30; padding: 10px; border-radius: 8px; margin-bottom: 10px;")
        self.history_detail_layout.addWidget(p_label)
        
        header_widget = QWidget()
        h_layout = QHBoxLayout(header_widget)
        h_layout.setContentsMargins(0, 5, 0, 5)
        h_layout.setSpacing(6)
        
        logo_icon = QLabel()
        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")
        if os.path.exists(logo_path):
            logo_pix = QPixmap(logo_path).scaled(16, 16, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            logo_icon.setPixmap(logo_pix)
            
        name_lbl = QLabel("StickyMan")
        name_lbl.setStyleSheet("color: #FFD700; font-weight: bold; font-size: 13px;")
        
        h_layout.addWidget(logo_icon)
        h_layout.addWidget(name_lbl)
        h_layout.addStretch()
        self.history_detail_layout.addWidget(header_widget)
        
        # Parse thought blocks on historical responses too
        thought_content = ""
        main_response = response
        if "<thought>" in response and "</thought>" in response:
            try:
                parts = response.split("</thought>", 1)
                thought_part = parts[0].split("<thought>", 1)[1]
                thought_content = thought_part.strip()
                main_response = parts[1].strip()
            except:
                pass
                
        if thought_content:
            collapsible_thought = CollapsibleThinkingWidget(thought_content)
            self.history_detail_layout.addWidget(collapsible_thought)

        parts = main_response.split("```")
        for i, part in enumerate(parts):
            if i % 2 == 0:
                if part.strip():
                    lbl = QLabel(markdown_to_html(part.strip()))
                    lbl.setWordWrap(True)
                    lbl.setTextFormat(Qt.TextFormat.RichText)
                    lbl.setStyleSheet("color: #e4e4e4; font-size: 13px; margin-bottom: 10px;")
                    self.history_detail_layout.addWidget(lbl)
            else:
                lines = part.split('\n', 1)
                language = lines[0].strip() if len(lines) > 1 else ""
                code_content = lines[1].strip() if len(lines) > 1 else lines[0].strip()
                
                code_container = QWidget()
                code_container.setStyleSheet("background-color: #141517; border-radius: 6px; margin-bottom: 10px;")
                c_layout = QVBoxLayout(code_container)
                c_layout.setContentsMargins(5, 5, 5, 5)
                
                top_bar = QWidget()
                top_layout = QHBoxLayout(top_bar)
                top_layout.setContentsMargins(0, 0, 0, 0)
                lang_lbl = QLabel(language.upper())
                lang_lbl.setStyleSheet("color: #888; font-size: 10px; font-weight: bold;")
                
                copy_btn = QPushButton("📋 Copy")
                copy_btn.setFixedSize(60, 22)
                copy_btn.setStyleSheet("font-size: 10px; background-color: #383a40; color: white;")
                copy_btn.clicked.connect(lambda checked, text_block=code_content: self.copy_specific_text(text_block))
                
                top_layout.addWidget(lang_lbl)
                top_layout.addStretch()
                top_layout.addWidget(copy_btn)
                c_layout.addWidget(top_bar)
                
                code_display = QTextEdit()
                code_display.setReadOnly(True)
                code_display.setPlainText(code_content)
                code_display.setStyleSheet("background: transparent; color: #a9b7c6; font-family: monospace; border: none;")
                
                doc_height = code_display.document().size().height()
                code_display.setMinimumHeight(int(doc_height) + 15)
                code_display.setMaximumHeight(300)
                c_layout.addWidget(code_display)
                self.history_detail_layout.addWidget(code_container)

        self.history_detail_layout.addStretch()
        self.stack.setCurrentIndex(2)


if __name__ == '__main__':
    # Set the environment variable for XWayland compatibility
    os.environ["QT_QPA_PLATFORM"] = "xcb"
    
    app = QApplication(sys.argv)
    
    # Create the main window
    window = FloatingAIWindow()
    
    # Start the pure-python socket listener thread
    listener = SocketListenerThread()
    listener.trigger_received.connect(window.handle_external_trigger)
    listener.start()
    
    # Trigger the initial load for the process
    window.handle_external_trigger(args.mode, fast_get_primary_selection() if args.mode == "text" else "")
    
    sys.exit(app.exec())