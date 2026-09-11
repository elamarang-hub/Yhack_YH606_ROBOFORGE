import asyncio,pygame

class Player:
    def __init__(self): pygame.mixer.init()

    async def play(self,path):
        pygame.mixer.music.load(str(path))
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            await asyncio.sleep(.1)

    def stop(self): pygame.mixer.music.stop()
