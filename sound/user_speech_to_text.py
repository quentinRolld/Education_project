# user speech --> user text

import cv2
import pyaudio
import threading
import wave
import speech_recognition as sr

# Audio params
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100
CHUNK = 1024
AUDIO_INPUT = "input_audio.wav"

# Video params
VIDEO_OUTPUT = "input_video.avi"
FPS = 30
FRAME_WIDTH = 640
FRAME_HEIGHT = 480


# Audio recording function
def record_audio():
    audio = pyaudio.PyAudio()
    stream = audio.open(format=FORMAT, channels=CHANNELS,
                        rate=RATE, input=True,
                        frames_per_buffer=CHUNK)
    frames = []
    for _ in range(0, int(RATE / CHUNK * 10)):  # 10 seconds
        data = stream.read(CHUNK)
        frames.append(data)
    stream.stop_stream()
    stream.close()
    audio.terminate()

    with wave.open(AUDIO_INPUT, 'wb') as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(audio.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(b''.join(frames))

# Video recording function
def record_video():
    cap = cv2.VideoCapture(0)
    fourcc = cv2.VideoWriter_fourcc(*'XVID')
    out = cv2.VideoWriter(VIDEO_OUTPUT, fourcc, FPS, (FRAME_WIDTH, FRAME_HEIGHT))
    for _ in range(FPS * 10):  # 10 seconds
        ret, frame = cap.read()
        if ret:
            out.write(frame)
        else:
            break
    cap.release()
    out.release()

# Run both recordings
audio_thread = threading.Thread(target=record_audio)
video_thread = threading.Thread(target=record_video)

audio_thread.start()
video_thread.start()

audio_thread.join()
video_thread.join()

print("Enregistrement terminé.")


def input_speech2text(input_audio_file):

    # Initialisation du recognizer
    recognizer = sr.Recognizer()

    with sr.AudioFile(input_audio_file) as source:
        print("Chargement de l'audio...")
        audio_data = recognizer.record(source)  # Capturer le contenu audio

    # Reconnaissance vocale via Google (connexion internet requise)
    try:
        print("Transcription en cours...")
        text = recognizer.recognize_google(audio_data, language="fr-FR")
        print("Texte transcrit :")
        print(text)
    except sr.UnknownValueError:
        print("Google Speech Recognition n'a pas compris l'audio.")
    except sr.RequestError as e:
        print(f"Erreur avec le service Google Speech Recognition : {e}")
    
    return