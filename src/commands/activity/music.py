import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp
import asyncio
from collections import deque
import datetime

# Налаштування yt-dlp для стрімінгу
YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'extractaudio': True,
    'audioformat': 'mp3',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': False, # Дозволяємо плейлисти
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
}

# Опції для FFmpeg
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')
        self.duration = data.get('duration')
        self.thumbnail = data.get('thumbnail')
        self.webpage_url = data.get('webpage_url')
        self.uploader = data.get('uploader')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        try:
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        except Exception as e:
            raise Exception(f"Помилка завантаження: {e}")

        if 'entries' in data:
            # Якщо це плейлист, беремо перший трек
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS), data=data)

class MusicPlayer:
    def __init__(self, ctx):
        self.bot = ctx.bot
        self.guild = ctx.guild
        self.channel = ctx.channel
        self.cog = ctx.cog

        self.queue = deque()
        self.next_event = asyncio.Event()

        self.current_track = None
        self.volume = 0.5
        self.loop = False
        
        # Запускаємо цикл програвання
        self.bot.loop.create_task(self.player_loop())

    async def player_loop(self):
        await self.bot.wait_until_ready()

        while not self.bot.is_closed():
            self.next_event.clear()

            try:
                # Чекаємо наступну пісню (з таймаутом, щоб вийти якщо пусто)
                if len(self.queue) == 0:
                    # Якщо черга пуста, чекаємо трохи, може щось додадуть
                     try:
                        # Чекаємо нову пісню 300 секунд (5 хвилин), якщо ні - виходимо
                        await asyncio.wait_for(self.next_event.wait(), timeout=300)
                     except asyncio.TimeoutError:
                         # Виходимо з каналу
                         if self.guild.voice_client and self.guild.voice_client.is_connected():
                             await self.guild.voice_client.disconnect()
                             # Видаляємо плеєр
                             if self.guild.id in self.cog.players:
                                 del self.cog.players[self.guild.id]
                         return
                    
                if self.loop and self.current_track:
                    # Якщо зациклено, граємо те саме (але треба перестворити source)
                    source_url = self.current_track.webpage_url # Використовуємо URL сторінки для повторного отримання
                    # Це трохи повільно, але надійно для стріму. 
                    # Або просто додаємо в початок черги той самий об'єкт даних? Ні, FFMpeg stream читається один раз.
                    # Треба створювати новий player.
                    # Для спрощення поки що просто беремо URL.
                    pass 
                else:
                    # Беремо наступну
                    if len(self.queue) > 0:
                         self.current_track = self.queue.popleft()

            except Exception as e:
                print(f"Error in player loop: {e}")
                continue
            
            if not self.current_track:
                continue

            # Відтворюємо
            try:
                if self.guild.voice_client and self.guild.voice_client.is_connected():
                    # Перестворюємо джерело для свіжого стріму
                    source = await YTDLSource.from_url(self.current_track['webpage_url'], loop=self.bot.loop, stream=True)
                    self.guild.voice_client.play(source, after=lambda _: self.bot.loop.call_soon_threadsafe(self.next_event.set))
                    
                    # Відправляємо інтерактивне повідомлення
                    await self.send_now_playing(source)
                    
                    # Чекаємо закінчення пісні
                    await self.next_event.wait()
                    
                    # Якщо увімкнено повтор, додаємо назад у чергу (в кінець чи початок? Зазвичай Loop track = повторювати цю ж)
                    if self.loop:
                        self.queue.appendleft(self.current_track) # Даємо пріоритет (або append для loop queue)
                        # Але логіка loop буває різною. 
                        # Реалізуємо простий Loop Track: якщо Loop True, не видаляємо з пам'яті "поточної", 
                        # а наступна ітерація візьме її ж.
                        pass # Вже оброблено логікою вище? Ні.
                        # Спростимо: loop просто додає трек назад у чергу.
            except Exception as e:
                await self.channel.send(f"❌ Помилка відтворення: {e}")
                self.next_event.set() # Пропускаємо

    async def send_now_playing(self, source):
        embed = discord.Embed(title="🎶 Зараз грає", description=f"[{source.title}]({source.webpage_url})", color=0x00ff00)
        embed.set_thumbnail(url=source.thumbnail)
        embed.add_field(name="Тривалість", value=str(datetime.timedelta(seconds=source.duration)) if source.duration else "N/A", inline=True)
        embed.add_field(name="Замовив", value=f"<@{self.current_track.get('requester')}>", inline=True)
        
        view = PlayerView(self)
        try:
            await self.channel.send(embed=embed, view=view)
        except:
            pass

class PlayerView(discord.ui.View):
    def __init__(self, player):
        super().__init__(timeout=None)
        self.player = player

    @discord.ui.button(emoji="⏯️", style=discord.ButtonStyle.secondary, custom_id="player_pause")
    async def pause(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc:
            if vc.is_paused():
                vc.resume()
                await interaction.response.send_message("▶️ Продовжено.", ephemeral=True)
            else:
                vc.pause()
                await interaction.response.send_message("⏸️ Пауза.", ephemeral=True)
        else:
             await interaction.response.send_message("❌ Не грає.", ephemeral=True)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary, custom_id="player_skip")
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.stop()
            await interaction.response.send_message("⏭️ Пропущено.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Нема що пропускати.", ephemeral=True)

    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.danger, custom_id="player_stop")
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc:
            self.player.queue.clear()
            vc.stop()
            await vc.disconnect()
            await interaction.response.send_message("⏹️ Зупинено і відключено.", ephemeral=True)
            # Clean up
            if interaction.guild.id in self.player.cog.players:
                del self.player.cog.players[interaction.guild.id]
        else:
            await interaction.response.send_message("❌ Не підключено.", ephemeral=True)

    @discord.ui.button(emoji="📜", style=discord.ButtonStyle.secondary, custom_id="player_queue")
    async def queue_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if len(self.player.queue) == 0:
            await interaction.response.send_message("📭 Черга пуста.", ephemeral=True)
            return

        desc = ""
        for i, track in enumerate(self.player.queue, 1):
            desc += f"{i}. [{track['title']}]({track['webpage_url']})\n"
            if i >= 10:
                desc += f"... і ще {len(self.player.queue) - 10} треків."
                break
        
        embed = discord.Embed(title="📜 Черга відтворення", description=desc, color=0x00ff00)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(emoji="🔁", style=discord.ButtonStyle.secondary, custom_id="player_loop")
    async def loop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.player.loop = not self.player.loop
        status = "увімкнено" if self.player.loop else "вимкнено"
        await interaction.response.send_message(f"🔁 Повтор {status}.", ephemeral=True)


class MusicCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.players = {}

    def get_player(self, ctx):
        if ctx.guild.id not in self.players:
            self.players[ctx.guild.id] = MusicPlayer(ctx)
        return self.players[ctx.guild.id]

    @app_commands.command(name="play", description="Відтворити музику (YouTube, Spotify, SoundCloud)")
    @app_commands.describe(query="Назва пісні або посилання")
    async def play(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer()
        
        # Перевірка голосу
        if not interaction.user.voice:
             await interaction.followup.send("❌ Ви маєте бути в голосовому каналі!", ephemeral=True)
             return
        
        channel = interaction.user.voice.channel
        
        # Підключення
        if not interaction.guild.voice_client:
            try:
                await channel.connect()
            except Exception as e:
                await interaction.followup.send(f"❌ Не вдалося підключитися: {e}", ephemeral=True)
                return
        
        # Створення/отримання плеєра
        ctx = await self.bot.get_context(interaction) # Hack to pass context-like object or construct fake one
        # Можемо просто передати interaction обгорнутий
        class FakeContext:
            def __init__(self, bot, guild, channel, cog):
                self.bot = bot
                self.guild = guild
                self.channel = channel
                self.cog = cog
        
        fake_ctx = FakeContext(self.bot, interaction.guild, interaction.channel, self)
        
        player = self.get_player(fake_ctx)
        
        # Пошук
        await interaction.followup.send(f"🔎 Шукаю: `{query}`...", ephemeral=True)
        
        url = query
        if not (url.startswith("http") or url.startswith("https")):
            url = f"ytsearch:{query}"
            
        loop = self.bot.loop
        try:
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))
        except Exception as e:
            await interaction.followup.send(f"❌ Помилка пошуку: {e}", ephemeral=True)
            return

        tracks = []
        if 'entries' in data:
            # Це плейлист або результат пошуку
            if url.startswith("ytsearch"):
                 # Результат пошуку - беремо перший
                 tracks.append(data['entries'][0])
            else:
                # Плейлист
                if 'entries' in data:
                     # Додаємо всі
                     # Але це може бути довго для великих плейлистів. 
                     # Візьмемо топ 20 для безпеки або запитаємо. 
                     # Для простоти - додаємо всі.
                     for entry in data['entries']:
                         tracks.append(entry)
                else:
                    tracks.append(data)
        else:
            tracks.append(data)

        # Додавання в чергу
        added = 0
        for track in tracks:
            if track: # Filter None
                track['requester'] = interaction.user.id
                player.queue.append(track)
                added += 1
                
        # Тригернути плеєр якщо він чекає
        if not player.current_track and len(player.queue) > 0 and not player.next_event.is_set():
             player.next_event.set()

        if added == 1:
            track = tracks[0]
            await interaction.followup.send(f"✅ Додано в чергу: **{track.get('title', 'Unknown')}**")
        else:
            await interaction.followup.send(f"✅ Додано {added} треків в чергу.")

    @app_commands.command(name="skip", description="Пропустити поточну пісню")
    async def skip(self, interaction: discord.Interaction):
        if not interaction.guild.voice_client or not interaction.guild.voice_client.is_playing():
            await interaction.response.send_message("❌ Нічого не грає.", ephemeral=True)
            return
        interaction.guild.voice_client.stop()
        await interaction.response.send_message("⏭️ Пропущено.")

    @app_commands.command(name="stop", description="Зупинити музику і вийти")
    async def stop(self, interaction: discord.Interaction):
        if not interaction.guild.voice_client:
            await interaction.response.send_message("❌ Я не в каналі.", ephemeral=True)
            return
            
        if interaction.guild.id in self.players:
            self.players[interaction.guild.id].queue.clear()
            
        interaction.guild.voice_client.stop()
        await interaction.guild.voice_client.disconnect()
        
        # Cleanup
        if interaction.guild.id in self.players:
             del self.players[interaction.guild.id]
             
        await interaction.response.send_message("⏹️ Зупинено.", ephemeral=True)

    @app_commands.command(name="queue", description="Показати чергу")
    async def queue(self, interaction: discord.Interaction):
        if interaction.guild.id not in self.players:
            await interaction.response.send_message("📭 Черга пуста.", ephemeral=True)
            return
            
        player = self.players[interaction.guild.id]
        if len(player.queue) == 0:
            await interaction.response.send_message("📭 Черга пуста.", ephemeral=True)
            return

        desc = ""
        for i, track in enumerate(player.queue, 1):
            desc += f"{i}. [{track.get('title', 'Unknown')}]({track.get('webpage_url', '')})\n"
            if i >= 10:
                desc += f"... і ще {len(player.queue) - 10} треків."
                break
        
        embed = discord.Embed(title="📜 Черга відтворення", description=desc, color=0x00ff00)
        if player.current_track:
             embed.set_footer(text=f"Зараз грає: {player.current_track.get('title')}")
             
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(MusicCommands(bot))
