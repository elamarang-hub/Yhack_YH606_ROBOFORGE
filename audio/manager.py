from .player import Player
from .tts import TTS
from .recorder import Recorder

class AudioManager:
    def __init__(self,greeting):
        self.greeting_path=greeting
        self.player=Player()
        self.tts=TTS()
        self.recorder=Recorder()

    async def greeting(self):
        if self.greeting_path.exists():
            await self.player.play(self.greeting_path)
        else:
            await self.tts.speak("Hello. You are at the smart door. Please wait for the owner.")

    async def play_voice(self,path): await self.player.play(path)
    async def speak_text(self,text): await self.tts.speak(text)
    def record_visitor(self,path,seconds): self.recorder.record(path,seconds)
