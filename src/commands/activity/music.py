import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp
import asyncio
from collections import deque
import datetime
from modules.db import get_database

db = get_database()

YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'extractaudio': True,
    'audioformat': 'mp3',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': False,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
}

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
            raise Exception(f"{e}")

        if 'entries' in data:
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
        self.history = deque(maxlen=20)
        self.next_event = asyncio.Event()

        self.current_track = None
        self.volume = 0.5
        self.loop = False
        
        self.bot.loop.create_task(self.player_loop())
        self.bot.loop.create_task(self.auto_disconnect_loop())

    async def auto_disconnect_loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            await asyncio.sleep(60)
            if self.guild.voice_client and self.guild.voice_client.is_connected():
                if len(self.guild.voice_client.channel.members) == 1:
                    await self.channel.send("👋 Я вийшов, бо нікого немає.", delete_after=30)
                    await self.guild.voice_client.disconnect()
                    self.cleanup()
                    return

    def cleanup(self):
        if self.guild.id in self.cog.players:
            del self.cog.players[self.guild.id]

    async def player_loop(self):
        await self.bot.wait_until_ready()

        while not self.bot.is_closed():
            self.next_event.clear()

            try:
                if not self.loop:
                    self.current_track = None

                if len(self.queue) == 0:
                    try:
                        await asyncio.wait_for(self.next_event.wait(), timeout=600)
                    except asyncio.TimeoutError:
                        if self.guild.voice_client:
                             await self.channel.send("😴 Черга пуста занадто довго. До побачення!", delete_after=30)
                             await self.guild.voice_client.disconnect()
                        self.cleanup()
                        return
                
                track_to_play = None
                
                if self.loop and self.current_track:
                    track_to_play = self.current_track
                elif len(self.queue) > 0:
                    track_to_play = self.queue.popleft()
                    self.current_track = track_to_play
                    self.history.append(track_to_play)
                
                if not track_to_play:
                    continue

                if self.guild.voice_client and self.guild.voice_client.is_connected():
                    try:
                        source = await YTDLSource.from_url(track_to_play['webpage_url'], loop=self.bot.loop, stream=True)
                        
                        # Fix: Ensure previous track is fully stopped
                        if self.guild.voice_client.is_playing():
                            self.guild.voice_client.stop()
                            await asyncio.sleep(0.5) # Short grace period

                        self.guild.voice_client.play(source, after=lambda _: self.bot.loop.call_soon_threadsafe(self.next_event.set))
                        
                        await self.send_now_playing(source)
                        await self.next_event.wait()
                    except Exception as e:
                        err_msg = str(e)
                        # Minimal error spam: delete_after=20
                        if "Sign in to confirm your age" in err_msg:
                            await self.channel.send(f"⚠️ Пропущено трек **{track_to_play.get('title')}**: Обмеження за віком (18+).", delete_after=20)
                        else:
                            clean_err = err_msg.replace("ERROR: [youtube] ", "")[:100]
                            await self.channel.send(f"⚠️ Пропущено трек **{track_to_play.get('title')}**: {clean_err}", delete_after=20)
                        self.next_event.set()
                    
            except Exception as e:
                self.next_event.set()

    async def send_now_playing(self, source):
        # Spotify-like clean embed
        embed = discord.Embed(color=0x1DB954) # Spotify Green
        embed.set_author(name="Зараз грає", icon_url="https://upload.wikimedia.org/wikipedia/commons/thumb/1/19/Spotify_logo_without_text.svg/2048px-Spotify_logo_without_text.svg.png")
        embed.title = source.title
        embed.url = source.webpage_url
        
        # Duration formatting
        duration = source.duration if hasattr(source, 'duration') else 0
        dur_str = str(datetime.timedelta(seconds=duration)) if duration else "Live"
        
        req_user = self.guild.get_member(source.data.get('requester'))
        req_name = req_user.display_name if req_user else "Unknown"

        embed.add_field(name="Тривалість", value=dur_str, inline=True)
        embed.add_field(name="Замовив", value=req_name, inline=True)
        
        if source.thumbnail:
            embed.set_thumbnail(url=source.thumbnail)
            
        view = PlayerView(self)
        
        # Avoid duplicates: try to delete the last message before sending a new one
        if hasattr(self, 'last_message') and self.last_message:
            try:
                await self.last_message.delete()
            except:
                pass
        
        try:
            self.last_message = await self.channel.send(embed=embed, view=view)
        except:
            pass

class PlayerView(discord.ui.View):
    def __init__(self, player):
        super().__init__(timeout=None)
        self.player = player
        self.update_buttons()

    def update_buttons(self):
        vc = self.player.guild.voice_client
        paused = vc and vc.is_paused()
        loop = self.player.loop
        
        # Iterate over buttons to update state visually
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.custom_id == "player_play_pause":
                    # Dynamic Play/Pause Logic
                    # If paused, show Play button (to resume). If playing, show Pause button (to pause).
                    if paused:
                        child.emoji = discord.PartialEmoji.from_str("<:play:1454136146421350481>")
                        child.style = discord.ButtonStyle.success
                    else:
                        child.emoji = discord.PartialEmoji.from_str("<:pause:1454136275987861585>")
                        child.style = discord.ButtonStyle.secondary
                
                if child.custom_id == "player_loop":
                     if loop:
                         child.style = discord.ButtonStyle.success
                     else:
                         child.style = discord.ButtonStyle.secondary
                
                # Disable Rewind if no history
                if child.custom_id == "player_rewind":
                    child.disabled = (len(self.player.history) == 0)

    @discord.ui.button(emoji=discord.PartialEmoji.from_str("<:Rewind:1454135236689657977>"), style=discord.ButtonStyle.secondary, custom_id="player_rewind")
    async def rewind(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Logic: Play previous track.
        # History contains [..., Prev, Current] (since current is added at start of play).
        
        vc = interaction.guild.voice_client
        if not vc: 
            return await interaction.response.send_message("❌ Не підключено.", ephemeral=True)
            
        if not self.player.history:
             return await interaction.response.send_message("❌ Історія пуста.", ephemeral=True)

        # We need to pop current first
        if len(self.player.history) > 0:
            current_from_hist = self.player.history.pop()
        else:
            current_from_hist = None

        if len(self.player.history) > 0:
            # We have a previous track
            previous_track = self.player.history.pop()
            
            # Put current back in queue
            if current_from_hist:
                 self.player.queue.appendleft(current_from_hist)
                 
            # Put previous in queue to play now
            self.player.queue.appendleft(previous_track)
        else:
             # Only current track was in history (or empty). Restart current.
             if current_from_hist:
                 self.player.queue.appendleft(current_from_hist)
             else:
                 # Should not happen if playing
                 pass

        self.player.loop = False 
        vc.stop()
        await interaction.response.defer()

    @discord.ui.button(emoji=discord.PartialEmoji.from_str("<:pause:1454136275987861585>"), style=discord.ButtonStyle.secondary, custom_id="player_play_pause")
    async def play_pause(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc:
            if vc.is_paused():
                vc.resume()
            else:
                vc.pause()
            
            self.update_buttons()
            await interaction.response.edit_message(view=self)
        else:
             await interaction.response.send_message("❌ Не грає.", ephemeral=True)

    @discord.ui.button(emoji=discord.PartialEmoji.from_str("<:forward:1454135105097306133>"), style=discord.ButtonStyle.secondary, custom_id="player_skip")
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            # If looping is enabled, 'vc.stop()' usually triggers playing the same song again if logic isn't 'skip' aware.
            # But here player_loop uses 'self.loop'.
            # If user explicit skips, they probably want to break loop for this track?
            # Or just skip to next iteration of loop (same song)? 
            # Usually Skip means "Next Song".
            
            # We temporarily disable loop to force next track from queue, unless queue is empty?
            # No, that's messy.
            # We can force current_track to None so logic picks from queue.
            
            # Logic adjustment: If Loop is ON, player_loop reuses current_track.
            # We must set current_track = None or handle skip logic in player_loop.
            
            # Easy fix: If Loop is ON, and we skip, we want to play the NEXT one, not current one.
            # So we toggled loop off temporarily? No, that's messy.
            # We can force current_track to None so logic picks from queue.
            
            if self.player.loop:
                # Force next logic
                self.player.current_track = None 
                # This prevents player_loop from reusing 'self.current_track' in the 'if self.loop' block.
            
            vc.stop()
            await interaction.response.defer()
        else:
            await interaction.response.send_message("❌ Нема що пропускати.", ephemeral=True)

    @discord.ui.button(emoji=discord.PartialEmoji.from_str("<:repeat:1454136632197255220>"), style=discord.ButtonStyle.secondary, custom_id="player_loop")
    async def loop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.player.loop = not self.player.loop
        self.update_buttons()
        await interaction.response.edit_message(view=self)

    @discord.ui.button(emoji=discord.PartialEmoji.from_str("<:Queue:1454135859816173609>"), style=discord.ButtonStyle.secondary, custom_id="player_queue")
    async def queue_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = QueueView(self.player)
        embed = view.generate_embed()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class QueueView(discord.ui.View):
    def __init__(self, player):
        super().__init__(timeout=180)
        self.player = player
        self.update_select()

    def generate_embed(self):
        embed = discord.Embed(title="Поточна черга", color=0x1DB954)
        
        full_list = []
        
        for track in self.player.history:
            full_list.append(f"• {track.get('title', 'Unknown')}")
            
        if self.player.current_track:
            full_list.append(f"▶️ **{self.player.current_track.get('title', 'Unknown')}**")
            
        for track in self.player.queue:
            full_list.append(f"WAIT: {track.get('title', 'Unknown')}")

        if not full_list:
            embed.description = "📭 Список пустий."
            return embed

        desc = ""
        for i, line in enumerate(full_list, 1):
            if line.startswith("WAIT: "):
                clean_line = line.replace("WAIT: ", "")
                desc += f"`{i}.` {clean_line}\n"
            else:
                 desc += f"`{i}.` {line}\n"
                 
            if len(desc) > 3500:
                desc += f"... і ще {len(full_list) - i} треків."
                break
        
        embed.description = desc
        
        if self.player.current_track:
             dur = str(datetime.timedelta(seconds=self.player.current_track.get('duration', 0)))
             embed.set_footer(text=f"Зараз грає: {self.player.current_track.get('title')} | Тривалість: {dur}")
             
        return embed

    def update_select(self):
        for child in self.children:
             if isinstance(child, QueueRemoveSelect):
                 self.remove_item(child)
        
        if len(self.player.queue) > 0:
            self.add_item(QueueRemoveSelect(self.player))

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji=discord.PartialEmoji.from_str("<:save:1454146266094243841>"))
    async def save_playlist(self, interaction: discord.Interaction, button: discord.ui.Button):
        tracks_to_save = []
        tracks_to_save.extend(self.player.history)
        if self.player.current_track:
            tracks_to_save.append(self.player.current_track)
        tracks_to_save.extend(self.player.queue)
        
        if not tracks_to_save:
            await interaction.response.send_message("❌ Нічого зберігати.", ephemeral=True)
            return
            
        # Immediate save
        user_id = interaction.user.id
        now_str = datetime.datetime.now().strftime("%d-%m-%Y %H:%M")
        playlist_name = f"Мій Плейлист {now_str}"
        
        playlist_data = {
            "user_id": user_id,
            "name": playlist_name,
            "tracks": [t.get('webpage_url') for t in tracks_to_save],
            "created_at": datetime.datetime.utcnow()
        }
        
        await db.playlists.insert_one(playlist_data)
        await interaction.response.send_message(f"✅ Плейлист **{playlist_name}** збережено ({len(tracks_to_save)} треків)!", ephemeral=True)

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji=discord.PartialEmoji.from_str("<:add:1454141315716612136>"))
    async def add_url_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddURLModal(self.player))

class QueueRemoveSelect(discord.ui.Select):
    def __init__(self, player):
        self.player = player
        options = []
        for i, track in enumerate(player.queue, 1):
            if i > 25: break
            title = track.get('title', 'Unknown')[:90]
            options.append(discord.SelectOption(label=f"{i}. {title}", value=str(i-1)))
            
        super().__init__(placeholder="Видалити трек...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        index = int(self.values[0])
        if 0 <= index < len(self.player.queue):
            removed = self.player.queue[index]
            del self.player.queue[index]
            await interaction.response.send_message(f"🗑️ Видалено: **{removed.get('title')}**", ephemeral=True)
            
            view = self.view
            view.update_select()
            embed = view.generate_embed()
            await interaction.message.edit(embed=embed, view=view)
        else:
            await interaction.response.send_message("❌ Помилка індексу.", ephemeral=True)

class SavePlaylistModal(discord.ui.Modal, title="Зберегти плейлист"):
    name = discord.ui.TextInput(label="Назва плейлиста", placeholder="Мій крутий мікс")

    def __init__(self, tracks):
        super().__init__()
        self.tracks = tracks

    async def on_submit(self, interaction: discord.Interaction):
        playlist_name = self.name.value
        user_id = interaction.user.id
        
        playlist_data = {
            "user_id": user_id,
            "name": playlist_name,
            "tracks": [t.get('webpage_url') for t in self.tracks],
            "created_at": datetime.datetime.utcnow()
        }
        
        await db.playlists.insert_one(playlist_data)
        await interaction.response.send_message(f"✅ Плейлист **{playlist_name}** збережено ({len(self.tracks)} треків)!", ephemeral=True)

class MusicCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.players = {}

    def get_player(self, ctx):
        if ctx.guild.id not in self.players:
            self.players[ctx.guild.id] = MusicPlayer(ctx)
        return self.players[ctx.guild.id]
    
    # --- Playlist Commands ---
    playlist_group = app_commands.Group(name="playlist", description="Керування плейлистами")
    
    async def playlist_autocomplete(self, interaction: discord.Interaction, current: str):
        user_id = interaction.user.id
        # Simple lookup
        playlists = await db.playlists.find({"user_id": user_id}).to_list(length=50)
        return [
            app_commands.Choice(name=p['name'], value=p['name'])
            for p in playlists if current.lower() in p['name'].lower()
        ]

    @playlist_group.command(name="list", description="Показати ваші плейлисти")
    async def playlist_list(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        playlists = await db.playlists.find({"user_id": user_id}).to_list(length=50)
        
        if not playlists:
            await interaction.response.send_message("📭 У вас немає збережених плейлистів.", ephemeral=True)
            return
            
        desc = ""
        for p in playlists:
            count = len(p.get('tracks', []))
            desc += f"• **{p['name']}** ({count} треків)\n"
            
        embed = discord.Embed(title="💾 Ваші плейлисти", description=desc, color=0x1DB954)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @playlist_group.command(name="load", description="Завантажити плейлист")
    @app_commands.describe(name="Назва плейлиста")
    @app_commands.autocomplete(name=playlist_autocomplete)
    async def playlist_load(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer(ephemeral=True)
        
        user_id = interaction.user.id
        playlist = await db.playlists.find_one({"user_id": user_id, "name": name})
        
        if not playlist:
            await interaction.followup.send(f"❌ Плейлист '{name}' не знайдено.", ephemeral=True)
            return

        tracks_urls = playlist.get('tracks', [])
        if not tracks_urls:
            await interaction.followup.send(f"❌ Плейлист пустий.", ephemeral=True)
            return
            
        # Check voice
        if not interaction.user.voice:
             await interaction.followup.send("❌ Ви маєте бути в голосовому каналі!", ephemeral=True)
             return
             
        channel = interaction.user.voice.channel
        if not interaction.guild.voice_client:
            try:
                await channel.connect(self_deaf=True)
            except:
                pass
                
        # Setup player
        ctx = await self.bot.get_context(interaction)
        class FakeContext:
            def __init__(self, bot, guild, channel, cog):
                self.bot = bot
                self.guild = guild
                self.channel = channel
                self.cog = cog
        
        fake_ctx = FakeContext(self.bot, interaction.guild, interaction.channel, self)
        player = self.get_player(fake_ctx)
        
        await interaction.followup.send(f"⏳ Завантажую {len(tracks_urls)} треків з **{name}**...", ephemeral=True)
        
        # We need to resolve URLs to playable data. 
        # Ideally we'd just queue them as "to be resolved" but our Main Loop expects resolved data right now for 'title' etc.
        # But wait, YTDLSource.from_url does resolving.
        # Queue items in our dictionary format.
        
        # Optimization: Don't resolve ALL at once blocking. 
        # Just resolve first one and add others as generic dicts to be resolved JIT? 
        # Our Logic: "source = await YTDLSource.from_url(track_to_play['webpage_url']...)" in loop.
        # So we just need minimal dicts in queue: {'webpage_url': url, 'title': 'Loading...', 'requester': user_id}
        
        added_count = 0
        for url in tracks_urls:
            player.queue.append({
                'webpage_url': url,
                'title': 'Завантаження...', 
                'requester': user_id,
                'url': url # Backup
            })
            added_count += 1
            
        if not player.current_track and len(player.queue) > 0 and not player.next_event.is_set():
             player.next_event.set()
             
        await interaction.followup.send(f"✅ Успішно додано {added_count} треків з **{name}**!", ephemeral=True)

    @playlist_group.command(name="delete", description="Видалити плейлист")
    @app_commands.describe(name="Назва плейлиста")
    @app_commands.autocomplete(name=playlist_autocomplete)
    async def playlist_delete(self, interaction: discord.Interaction, name: str):
        result = await db.playlists.delete_one({"user_id": interaction.user.id, "name": name})
        if result.deleted_count > 0:
            await interaction.response.send_message(f"🗑️ Плейлист **{name}** видалено.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Плейлист '{name}' не знайдено.", ephemeral=True)
    
    # --- End Playlist Commands ---

    @app_commands.command(name="play", description="Відтворити музику/Додати до черги")
    @app_commands.describe(query="Назва пісні або посилання", source="Де шукати (якщо не посилання)")
    @app_commands.choices(source=[
        app_commands.Choice(name="YouTube", value="ytsearch"),
        app_commands.Choice(name="SoundCloud", value="scsearch"),
        app_commands.Choice(name="Spotify", value="spotify")
    ])
    async def play(self, interaction: discord.Interaction, query: str, source: app_commands.Choice[str] = None):
        await interaction.response.defer(ephemeral=True)
        
        if not interaction.user.voice:
             await interaction.followup.send("❌ Ви маєте бути в голосовому каналі!", ephemeral=True)
             return
        
        channel = interaction.user.voice.channel
        
        if not interaction.guild.voice_client:
            try:
                await channel.connect(self_deaf=True)
            except Exception as e:
                await interaction.followup.send(f"❌ Не вдалося підключитися: {e}", ephemeral=True)
                return
        
        ctx = await self.bot.get_context(interaction)
        class FakeContext:
            def __init__(self, bot, guild, channel, cog):
                self.bot = bot
                self.guild = guild
                self.channel = channel
                self.cog = cog
        
        fake_ctx = FakeContext(self.bot, interaction.guild, interaction.channel, self)
        
        player = self.get_player(fake_ctx)
        
        url = query
        search_prefix = "ytsearch"
        
        if source:
            if source.value == "spotify" and not (url.startswith("http")):
                 search_prefix = "ytsearch"
            else:
                 search_prefix = source.value

        if not (url.startswith("http") or url.startswith("https")):
            url = f"{search_prefix}:{query}"
            await interaction.followup.send(f"🔎 Шукаю: `{query}` в {source.name if source else 'YouTube'}...", ephemeral=True)
        else:
             await interaction.followup.send(f"🔎 Завантажую посилання...", ephemeral=True)

        loop = self.bot.loop
        try:
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))
        except Exception as e:
            await interaction.followup.send(f"❌ Помилка пошуку: {e}", ephemeral=True)
            return

        tracks = []
        if 'entries' in data:
            if url.startswith("ytsearch") or url.startswith("scsearch"):
                 tracks.append(data['entries'][0])
            else:
                for entry in data['entries']:
                    tracks.append(entry)
        else:
            tracks.append(data)

        added = 0
        for track in tracks:
            if track:
                track['requester'] = interaction.user.id
                player.queue.append(track)
                added += 1
                


        if added == 1:
            track = tracks[0]
            await interaction.followup.send(f"✅ Додано в чергу: **{track.get('title', 'Unknown')}**", ephemeral=True)
        else:
            await interaction.followup.send(f"✅ Додано {added} треків в чергу.", ephemeral=True)
        
        # Robust check to prevent interrupting playing audio
        is_playing = interaction.guild.voice_client and (interaction.guild.voice_client.is_playing() or interaction.guild.voice_client.is_paused())
        
        if not is_playing and not player.current_track and len(player.queue) > 0 and not player.next_event.is_set():
             player.next_event.set()

class AddURLModal(discord.ui.Modal, title="Додати трек/плейлист"):
    url = discord.ui.TextInput(label="Посилання (YouTube/Spotify/SoundCloud)", placeholder="https://...")

    def __init__(self, player):
        super().__init__()
        self.player = player

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        url = self.url.value
        
        loop = interaction.client.loop
        try:
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))
        except Exception as e:
            await interaction.followup.send(f"❌ Помилка: {e}", ephemeral=True)
            return

        tracks = []
        if 'entries' in data:
            for entry in data['entries']:
                tracks.append(entry)
        else:
            tracks.append(data)

        added = 0
        for track in tracks:
            if track:
                track['requester'] = interaction.user.id
                self.player.queue.append(track)
                added += 1

        if added == 1:
            await interaction.followup.send(f"✅ Додано: **{tracks[0].get('title', 'Unknown')}**", ephemeral=True)
        else:
            await interaction.followup.send(f"✅ Додано {added} треків.", ephemeral=True)
            
        # Robust play check
        vc = interaction.guild.voice_client
        is_playing = vc and (vc.is_playing() or vc.is_paused())
        
        if not is_playing and not self.player.current_track and len(self.player.queue) > 0 and not self.player.next_event.is_set():
             self.player.next_event.set()

async def setup(bot):
    await bot.add_cog(MusicCommands(bot))
