import os
import subprocess
import time
import shutil

# Chemins pour les fichiers temporaires
AUDIO_FILE = "input.wav"
CONVERTED_FILE = "converted.wav"

def record_audio(duration=5):
    """Capture l'audio depuis le microphone I2S."""
    print("Enregistrement en cours...")
    os.system(f"arecord -D plughw:1,0 -r 16000 -f S16_LE -c 1 -d {duration} {AUDIO_FILE}")

def convert_audio():
    """Convertit l'audio pour le format compatible Whisper."""
    print("Conversion de l'audio...")
    os.system(f"ffmpeg -i {AUDIO_FILE} -ar 16000 -ac 1 {CONVERTED_FILE}")

def transcribe_audio():
    """Transcrit l'audio en texte avec Whisper."""
    print("Transcription en cours...")
    result = subprocess.run(
        ["whisper", CONVERTED_FILE, "--language", "French", "--fp16", "False"],
        capture_output=True, text=True
    )
    return result.stdout

def main():
    """Service continu de transcription."""
    try:
        while True:
            # Étape 1 : Capturer l'audio
            record_audio()

            # Étape 2 : Convertir l'audio
            convert_audio()

            # Étape 3 : Transcrire l'audio
            transcription = transcribe_audio()
            print("Texte transcrit :", transcription)

            # Optionnel : Ajouter une réaction en fonction de la transcription
            # Exemple : envoyer la transcription à un LLM pour obtenir une réponse
            # response = send_to_llm(transcription)
            # print("Réponse :", response)

            # Pause avant de recommencer
            time.sleep(1)  # Ajustez pour un comportement en continu
    except KeyboardInterrupt:
        print("\nService interrompu par l'utilisateur.")
    finally:
        # Nettoyage des fichiers temporaires
        if os.path.exists(AUDIO_FILE):
            os.remove(AUDIO_FILE)
        if os.path.exists(CONVERTED_FILE):
            os.remove(CONVERTED_FILE)

# Lancer le service
if __name__ == "__main__":
    main()
