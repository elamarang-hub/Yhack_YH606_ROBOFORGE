import asyncio,subprocess
from pathlib import Path
from telegram import Update
from telegram.ext import Application,CommandHandler,MessageHandler,ContextTypes,filters

class TelegramService:
    def __init__(self,config,db,audio,esp32,queue):
        self.c=config; self.db=db; self.audio=audio; self.esp32=esp32; self.q=queue
        self.app=Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
        self.call_active=False
        self.recording_lock=asyncio.Lock()
        self.register()

    def allowed(self,update):
        if not self.c.TELEGRAM_CHAT_ID: return True
        return str(update.effective_chat.id)==str(self.c.TELEGRAM_CHAT_ID)

    async def start(self,u,ctx):
        if self.allowed(u):
            await u.message.reply_text(
                "🏠 Smart Door Security\n\n"
                "/test /alarm /mode /history /endcall"
            )

    async def test(self,u,ctx):
        if self.allowed(u): await u.message.reply_text("✅ Telegram communication is working!")

    async def alarm(self,u,ctx):
        if not self.allowed(u): return
        self.esp32.buzzer_on()
        await u.message.reply_text("🚨 Buzzer ON command sent to ESP32.")
        asyncio.create_task(self.off_later())

    async def off_later(self):
        await asyncio.sleep(5); self.esp32.buzzer_off()

    async def mode(self,u,ctx):
        if not self.allowed(u): return
        if not ctx.args:
            await u.message.reply_text(
                f"Mode: {self.q.mode}\n"
                "individual = 120cm / 2s\n"
                "apartment = 50cm / 3s"
            ); return
        m=ctx.args[0].lower()
        if m not in ("individual","apartment"):
            await u.message.reply_text("Use /mode individual or /mode apartment"); return
        self.q.mode=m
        await u.message.reply_text(f"✅ {m.upper()} mode enabled.")

    async def history(self,u,ctx):
        if not self.allowed(u): return
        es=self.db.recent_events(10)
        text="📋 Recent security events:\n\n"
        for e in es:
            icon="🟢" if e["classification"]=="OWNER" else "🔴"
            label=e["classification"] or "STRANGER"
            when=e["created_at"].split("T")[-1] if "T" in e["created_at"] else e["created_at"]
            text+=(f"{icon} {label}\n"
                   f"Distance: {e['distance_cm']:.0f} cm\n"
                   f"Dwell: {e['dwell_seconds']:.1f} sec\n"
                   f"Time: {when}\n\n")
        if not es:
            text+="No security events yet.\n"

        ps=self.db.recent_passive(5)
        if ps:
            text+="\n📝 Passive activity\n"
            for p in ps:
                d="N/A" if p["distance_cm"] is None else f"{p['distance_cm']:.0f}cm"
                text+=f"{d} | {p['note']}\n"

        await u.message.reply_text(text[:4000])

    async def endcall(self,u,ctx):
        if self.allowed(u):
            self.call_active=False
            await u.message.reply_text("☎️ Intercom ended.")

    async def voice(self,u,ctx):
        if not self.allowed(u): return
        ogg=Path(self.c.BASE_DIR)/"owner_voice.ogg"
        wav=Path(self.c.BASE_DIR)/"owner_voice.wav"
        f=await ctx.bot.get_file(u.message.voice.file_id)
        await f.download_to_drive(ogg)
        try:
            subprocess.run(["ffmpeg","-y","-i",str(ogg),"-ar","48000","-ac","1",str(wav)],
                           check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            await u.message.reply_text("🎤 Owner voice received. 🔊 Playing...")
            await self.audio.play_voice(wav)
            if self.call_active:
                asyncio.create_task(self.record_and_send_visitor())
        except Exception as e:
            print("VOICE ERROR:",e)
            await u.message.reply_text("❌ Voice playback failed. Check FFmpeg/audio.")

    async def text(self,u,ctx):
        if not self.allowed(u) or not u.message.text or u.message.text.startswith("/"): return
        await u.message.reply_text("🔊 Converting owner text to speech...")
        await self.audio.speak_text(u.message.text)
        if self.call_active:
            asyncio.create_task(self.record_and_send_visitor())

    async def record_and_send_visitor(self):
        if not self.call_active:
            return

        async with self.recording_lock:
            if not self.call_active:
                return

            path=Path(self.c.RECORDINGS_DIR)/(
                "visitor_" + str(int(asyncio.get_running_loop().time()*1000)) + ".wav"
            )

            await asyncio.to_thread(
                self.audio.record_visitor,
                path,
                self.c.VISITOR_RECORD_SECONDS
            )

            if not self.call_active:
                return

            with open(path,"rb") as v:
                await self.app.bot.send_voice(
                    chat_id=self.c.TELEGRAM_CHAT_ID,
                    voice=v,
                    caption="🎤 Visitor voice — intercom"
                )

            await self.app.bot.send_message(
                chat_id=self.c.TELEGRAM_CHAT_ID,
                text="☎️ Visitor can continue speaking. Reply with voice/text, or /endcall."
            )

    async def alert_worker(self):
        while True:
            e=await self.q.alerts.get()
            try: await self.send_alert(e)
            except Exception as x: print("ALERT ERROR:",x)
            self.q.alerts.task_done()

    async def send_alert(self,e):
        # User-facing message: only ever OWNER or STRANGER. No visitor IDs,
        # no event IDs -- those stay internal to the database (e['event_id']).
        if e["classification"]=="OWNER":
            msg=("🟢 OWNER detected at the door.\n\n"
                 f"Distance: {e['distance_cm']:.0f} cm\n"
                 f"Dwell time: {e['dwell_seconds']:.1f} sec")
        else:
            msg=("🔴 STRANGER detected at the door.\n\n"
                 f"Distance: {e['distance_cm']:.0f} cm\n"
                 f"Dwell time: {e['dwell_seconds']:.1f} sec")

        with open(e["photo_path"],"rb") as p:
            await self.app.bot.send_photo(chat_id=self.c.TELEGRAM_CHAT_ID,
                                          photo=p,caption=msg)

        self.esp32.buzzer_on()
        asyncio.create_task(self.off_later())
        await self.audio.greeting()

        self.call_active=True
        await self.record_and_send_visitor()

    def register(self):
        self.app.add_handler(CommandHandler("start",self.start))
        self.app.add_handler(CommandHandler("test",self.test))
        self.app.add_handler(CommandHandler("alarm",self.alarm))
        self.app.add_handler(CommandHandler("mode",self.mode))
        self.app.add_handler(CommandHandler("history",self.history))
        self.app.add_handler(CommandHandler("endcall",self.endcall))
        self.app.add_handler(MessageHandler(filters.VOICE,self.voice))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,self.text))
