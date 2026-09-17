import speech_recognition as sr

recognizer = sr.Recognizer()

with sr.Microphone() as source:
    print("Adjusting for background noise...")
    recognizer.adjust_for_ambient_noise(source, duration=1)

    print("\nSay your wake word 10 times.")
    print("Press Ctrl+C to stop.\n")

    while True:
        try:
            audio = recognizer.listen(
                source,
                timeout=10,
                phrase_time_limit=3
            )

            try:
                text = recognizer.recognize_google(audio)
                print(f"You said:     {text}")

            except sr.UnknownValueError:
                print("Google STT:   [could not understand]")

            except sr.RequestError as e:
                print(f"Google STT error: {e}")

        except sr.WaitTimeoutError:
            print("No speech detected.")