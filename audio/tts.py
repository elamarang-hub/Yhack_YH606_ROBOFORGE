import asyncio,pyttsx3

class TTS:
    def __init__(self): self.engine=pyttsx3.init()

    def speak_blocking(self,text):
        self.engine.say(text); self.engine.runAndWait()

    async def speak(self,text):
        await asyncio.to_thread(self.speak_blocking,text)
