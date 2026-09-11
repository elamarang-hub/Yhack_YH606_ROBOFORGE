import wave,pyaudio

class Recorder:
    def __init__(self):
        self.rate=16000; self.channels=1; self.chunk=1024
        self.audio=pyaudio.PyAudio()

    def record(self,path,seconds=5):
        stream=self.audio.open(format=pyaudio.paInt16,channels=self.channels,
                               rate=self.rate,input=True,frames_per_buffer=self.chunk)
        frames=[]
        for _ in range(int(self.rate/self.chunk*seconds)):
            frames.append(stream.read(self.chunk,exception_on_overflow=False))
        stream.stop_stream(); stream.close()
        with wave.open(str(path),"wb") as w:
            w.setnchannels(self.channels)
            w.setsampwidth(self.audio.get_sample_size(pyaudio.paInt16))
            w.setframerate(self.rate)
            w.writeframes(b"".join(frames))

    def close(self): self.audio.terminate()
