import sys
import threading
import pyaudio
import wave
import keyboard
import pyperclip
import pystray
from PIL import Image, ImageDraw
import win32gui
import win32con
import win32api
import groq
import tkinter as tk
from tkinter import ttk, simpledialog
import os
from dotenv import load_dotenv, set_key
import tempfile
import time

class DictationApp:
    def __init__(self):
        self.recording = False
        self.frames = []
        self.root = tk.Tk()
        self.root.withdraw()  # Hide the main window
        self.load_default_language()  # Load the default language
        self.setup_gui()
        self.setup_audio()
        self.setup_tray_icon()
        self.setup_hotkey()
        self.setup_groq_client()
        self.setup_custom_dictionary()
        self.temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
        self.target_window = None

    def load_default_language(self):
        load_dotenv()
        self.current_language = os.getenv('DEFAULT_LANGUAGE', 'english').lower()
        if self.current_language not in ["english", "spanish"]:
            self.current_language = "english"
        print(f"Loaded default language: {self.current_language}")

    def save_default_language(self):
        set_key('.env', 'DEFAULT_LANGUAGE', self.current_language)
        print(f"Default language saved: {self.current_language}")

    def setup_gui(self):
        self.overlay = tk.Toplevel(self.root)
        self.overlay.overrideredirect(True)
        self.overlay.attributes('-topmost', True)
        self.overlay.attributes('-alpha', 0.5)  # Set transparency

        # Position the overlay at the center bottom of the screen
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        overlay_width = 500
        overlay_height = 28
        x_position = (screen_width - overlay_width) // 2
        y_position = screen_height - overlay_height - 8  # 8 pixels from the bottom
        self.overlay.geometry(f'{overlay_width}x{overlay_height}+{x_position}+{y_position}')

        # Set the background color of the overlay
        self.overlay.configure(bg='black')

        # Use a slightly smaller, bold font for the text
        self.text_widget = ttk.Label(self.overlay, foreground='white', background='black',
                                     font=('Arial', 10, 'bold'), anchor='center')
        self.text_widget.pack(expand=True, fill='both')

        self.overlay.withdraw()

        # Apply rounded corners to the overlay
        self.overlay.update_idletasks()
        self.overlay.after(10, self.apply_rounded_corners)

    def apply_rounded_corners(self):
        hwnd = self.overlay.winfo_id()
        region = win32gui.CreateRoundRectRgn(0, 0, self.overlay.winfo_width(), self.overlay.winfo_height(), 10, 10)
        win32gui.SetWindowRgn(hwnd, region, True)

    def setup_audio(self):
        self.audio = pyaudio.PyAudio()
        self.stream = self.audio.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=1024)

    def setup_tray_icon(self):
        size = 64
        image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.ellipse([0, 0, size, size], fill='black')

        menu = pystray.Menu(
            pystray.MenuItem('Language', pystray.Menu(
                pystray.MenuItem('English', lambda: self.set_language("english"), checked=lambda item: self.current_language == "english"),
                pystray.MenuItem('Spanish', lambda: self.set_language("spanish"), checked=lambda item: self.current_language == "spanish")
            )),
            pystray.MenuItem('Set as Default', self.set_default_language),
            pystray.MenuItem('Exit', self.exit_app)
        )
        self.icon = pystray.Icon("dictation_app", image, "Dictation App", menu)
        threading.Thread(target=self.icon.run).start()

    def set_language(self, language):
        self.current_language = language
        print(f"Language set to: {language}")
        self.icon.update_menu()  # Update the menu to reflect the change

    def set_default_language(self):
        self.save_default_language()
        print(f"Default language set to: {self.current_language}")

    def exit_app(self):
        self.icon.stop()
        self.root.quit()
        os._exit(0)

    def setup_hotkey(self):
        keyboard.on_press_key('F3', self.start_recording, suppress=True)
        keyboard.on_release_key('F3', self.stop_recording, suppress=True)

    def setup_groq_client(self):
        load_dotenv()
        api_key = os.getenv('GROQ_API_KEY')

        if not api_key:
            api_key = simpledialog.askstring("Groq API Key", "Please enter your Groq API Key:", show='*')
            if api_key:
                os.environ['GROQ_API_KEY'] = api_key
                set_key('.env', 'GROQ_API_KEY', api_key)
            else:
                print("No API key provided. Exiting.")
                sys.exit(1)

        try:
            self.client = groq.Client(api_key=api_key)
        except groq.GroqError as e:
            print(f"Error initializing Groq client: {e}")
            sys.exit(1)

    def setup_custom_dictionary(self):
        self.custom_dictionary = {
            "english": set([
                "the", "be", "to", "of", "and", "a", "in", "that", "have", "I",
                "it", "for", "not", "on", "with", "he", "as", "you", "do", "CSAT",
                # Add more common English words as needed
            ]),
            "spanish": set([
                "el", "la", "de", "que", "y", "a", "en", "un", "ser", "porfa",
                "no", "haber", "por", "con", "su", "para", "como", "estar", "ratito", "CSAT",
                # Add more common Spanish words as needed
            ])
        }

    def start_recording(self, e):
        if not self.recording:
            self.recording = True
            self.frames = []
            self.target_window = win32gui.GetForegroundWindow()
            # Update to use a round green icon
            size = 64
            green_icon = Image.new('RGBA', (size, size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(green_icon)
            draw.ellipse([0, 0, size, size], fill='green')
            self.icon.icon = green_icon
            threading.Thread(target=self.record_audio).start()

    def stop_recording(self, e):
        if self.recording:
            self.recording = False
            # Update to use a round black icon
            size = 64
            black_icon = Image.new('RGBA', (size, size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(black_icon)
            draw.ellipse([0, 0, size, size], fill='black')
            self.icon.icon = black_icon
            self.transcribe_audio()

    def record_audio(self):
        while self.recording:
            data = self.stream.read(1024)
            self.frames.append(data)

    def transcribe_audio(self):
        audio_data = b''.join(self.frames)
        with wave.open(self.temp_file, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(self.audio.get_sample_size(pyaudio.paInt16))
            wf.setframerate(16000)
            wf.writeframes(audio_data)

        try:
            with open(self.temp_file, "rb") as audio_file:
                transcribed_text = self.client.audio.transcriptions.create(
                    model="whisper-large-v3-turbo",
                    file=audio_file,
                    response_format="text",
                    language="es" if self.current_language == "spanish" else "en"
                )

            # Apply custom dictionary
            transcribed_text = self.apply_custom_dictionary(transcribed_text)

            self.update_text(transcribed_text)
        except groq.GroqError as e:
            print(f"Error during transcription: {e}")
            self.show_error("Transcription failed. Please try again.")

    def apply_custom_dictionary(self, text):
        words = text.split()
        corrected_words = []
        for word in words:
            lower_word = word.lower()
            if lower_word in self.custom_dictionary[self.current_language]:
                corrected_words.append(lower_word)
            else:
                corrected_words.append(word)
        return ' '.join(corrected_words)

    def update_text(self, text):
        self.text_widget.config(text=text)
        self.overlay.deiconify()
        pyperclip.copy(text)
        self.paste_to_target_window(text)
        self.root.after(3000, self.hide_overlay)

    def show_error(self, message):
        self.text_widget.config(text=message)
        self.overlay.deiconify()
        self.root.after(3000, self.hide_overlay)

    def hide_overlay(self):
        self.overlay.withdraw()

    def paste_to_target_window(self, text):
        if self.target_window:
            win32gui.SetForegroundWindow(self.target_window)
            time.sleep(0.1)  # Give a moment for the window to come to the foreground
            keyboard.write(text)

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    app = DictationApp()
    app.run()
