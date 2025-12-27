import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp
import asyncio
import random
import re
import aiohttp
from collections import deque
import datetime
# db usage removed
# db = get_database()

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
    def __init__(self, bot, guild, channel, cog):
        self.bot = bot
        self.guild = guild
        self.channel = channel
        self.cog = cog

        self.queue = deque()
        self.history = deque(maxlen=20)
        self.next_event = asyncio.Event()

        self.current_track = None
        self.volume = 0.5
        self.loop = False
        
        self.bot.loop.create_task(self.player_loop())
        self.bot.loop.create_task(self.auto_disconnect_loop())
        
        # load_state removed to prevent ghost tracks
        # self.bot.loop.create_task(self.load_state())

    async def fetch_spotify_title(self, url):
        try:
             async with aiohttp.ClientSession() as session:
                 async with session.get(url) as resp:
                     if resp.status == 200:
                         text = await resp.text()
                         match = re.search(r'<title>(.*?)</title>', text)
                         if match:
                             title = match.group(1).replace(" | Spotify", "")
                             return title
        except:
             return None
        return None

    async def extract_tracks(self, query, source_type=None, interaction=None):
        """
        Універсальний метод для отримання треків.
        query: URL або пошуковий запит
        source_type: 'ytsearch', 'scsearch', 'spotify' або None
        interaction: для відправки статусних повідомлень (опціонально)
        """
        url = query
        search_prefix = "ytsearch"
        
        # Визначення префіксу пошуку
        if source_type:
            if source_type == "spotify" and not url.startswith("http"):
                 search_prefix = "ytsearch" # Spotify пошук текстом -> YouTube
            else:
                 search_prefix = source_type

        # Якщо це не посилання, додаємо префікс
        if not (url.startswith("http") or url.startswith("https")):
            url = f"{search_prefix}:{query}"
            if interaction:
                await self.cog.send_timed_msg(interaction, f"🔎 Шукаю: `{query}`...", delay=5)
        else:
             if interaction:
                await self.cog.send_timed_msg(interaction, f"🔎 Завантажую посилання...", delay=5)

        loop = self.bot.loop
        data = None
        
        try:
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))
        except Exception as e:
            err_str = str(e)
            if "DRM" in err_str or "spotify" in url.lower():
                 # Spotify Fallback Check
                 scraped_title = await self.fetch_spotify_title(url)
                 if scraped_title:
                     new_query = f"ytsearch:{scraped_title}"
                     try:
                         data = await loop.run_in_executor(None, lambda: ytdl.extract_info(new_query, download=False))
                     except Exception as e2:
                         raise Exception(f"Spotify Fallback Error: {e2}")
                 else:
                     raise Exception("Spotify DRM: Не вдалося отримати назву.")
            else:
                raise e

        if not data:
             return []

        tracks = []
        is_playlist = 'entries' in data
        
        if is_playlist:
            # Smart Playlist Logic
            # Convert entries to search queries to defer resolution and avoid DRM/Metadata issues
            # especially for Spotify/SoundCloud or non-YouTube playlists.
            
            origin_is_youtube = "youtube" in data.get('extractor', '').lower()
            
            for entry in data['entries']:
                if not entry: continue
                
                # If it's a YouTube playlist, valid URLs usually exist. 
                # But for everything else (or if title exists but no URL), use search.
                # User specifically requested: "search 30 song names on youtube... and export to queue"
                
                title = entry.get('title', '')
                artist = entry.get('artist', '')
                url = entry.get('url')
                
                # Effective query construction
                query_str = title
                if artist:
                    query_str = f"{artist} - {title}"
                
                # Heuristic: If it's NOT a direct YouTube video URL or we want to force search
                # We force search if:
                # 1. It's not from YouTube (origin_is_youtube False)
                # 2. Key metadata is missing
                # 3. Explicitly requested smart import for everything
                
                # For now, we trust YouTube URLs if they exist, otherwise search.
                if origin_is_youtube and url:
                     tracks.append(entry)
                else:
                     tracks.append({
                         'webpage_url': f"ytsearch:{query_str}",
                         'title': query_str,
                         'is_search': True,
                         'requester': interaction.user.id if interaction else None,
                         'playlist_origin': data.get('title', 'Unknown Playlist') # Mark as from playlist
                     })
        else:
            tracks.append(data)
            
        return tracks

    # load_state and save_state removed to prevent persistent queue issues
    # async def load_state(self): ...
    
    async def save_state(self):
        # Disabled persistence
        pass

    async def auto_disconnect_loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            await asyncio.sleep(60)
            if self.guild.voice_client and self.guild.voice_client.is_connected():
                if len(self.guild.voice_client.channel.members) == 1:
                    await self.channel.send("👋 Я вийшов, бо нікого немає.", delete_after=30)
                    if hasattr(self, 'last_message') and self.last_message:
                         try:
                             await self.last_message.delete()
                         except:
                             pass
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
                             if hasattr(self, 'last_message') and self.last_message:
                                 try:
                                     await self.last_message.delete()
                                 except:
                                     pass
                             await self.guild.voice_client.disconnect()
                        self.cleanup()
                        return
                
                track_to_play = None
                
                if self.loop and self.current_track:
                    track_to_play = self.current_track
                elif len(self.queue) > 0:
                    track_to_play = self.queue.popleft()
                    self.current_track = track_to_play
                    
                    url_to_check = track_to_play.get('webpage_url')
                    self.history = deque([t for t in self.history if t.get('webpage_url') != url_to_check], maxlen=None)
                    self.history.append(track_to_play)
                
                if not track_to_play:
                    continue

                if self.guild.voice_client and self.guild.voice_client.is_connected():
                    try:
                        # Lazy Search Resolution
                        # If the URL is a search query (starts with ytsearch:), resolution happens inside YTDLSource.from_url
                        # But we want to update the current_track info with the resolved video info.
                        
                        source = await YTDLSource.from_url(track_to_play['webpage_url'], loop=self.bot.loop, stream=True)
                        
                        if self.guild.voice_client.is_playing():
                            self.guild.voice_client.stop()
                            await asyncio.sleep(0.5) 
                        
                        # Update current_track with resolved metadata
                        self.current_track['title'] = source.title
                        self.current_track['webpage_url'] = source.webpage_url
                        self.current_track['duration'] = source.duration
                        self.current_track['thumbnail'] = source.thumbnail
                        
                        source.data['requester'] = track_to_play.get('requester')
                        source.data['requester_name'] = track_to_play.get('requester_name')
                        
                        self.guild.voice_client.play(source, after=lambda _: self.bot.loop.call_soon_threadsafe(self.next_event.set))
                        
                        await self.send_now_playing(source)
                        await self.next_event.wait()
                    except Exception as e:
                        err_msg = str(e)
                        if "Sign in to confirm your age" in err_msg:
                            await self.channel.send(f"⚠️ Пропущено трек **{track_to_play.get('title')}**: Обмеження за віком (18+).", delete_after=20)
                        else:
                            clean_err = err_msg.replace("ERROR: [youtube] ", "")[:100]
                            await self.channel.send(f"⚠️ Пропущено трек **{track_to_play.get('title')}**: {clean_err}", delete_after=20)
                        self.next_event.set()
                    
            except Exception as e:
                self.next_event.set()

    async def send_now_playing(self, source):
        embed = discord.Embed(color=0x1DB954) 
        embed.set_author(name="Зараз грає") 
        embed.title = source.title
        embed.url = source.webpage_url
        
        duration = source.duration if hasattr(source, 'duration') else 0
        dur_str = str(datetime.timedelta(seconds=duration)) if duration else "Live"
        
        req_name = source.data.get('requester_name', "Unknown")
        if req_name == "Unknown":
            req_user = self.guild.get_member(source.data.get('requester'))
            if req_user:
                req_name = req_user.display_name

        embed.add_field(name="Тривалість", value=dur_str, inline=True)
        embed.add_field(name="Замовив", value=req_name, inline=True)
        
        if source.thumbnail:
            embed.set_thumbnail(url=source.thumbnail)
            
        view = PlayerView(self)
        
        try:
            if hasattr(self, 'last_message') and self.last_message:
                try:
                    await self.last_message.delete()
                except:
                    pass
            
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
        
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.custom_id == "player_play_pause":
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
                
                if child.custom_id == "player_rewind":
                    child.disabled = (len(self.player.history) == 0)

    # Rewind button restored
    @discord.ui.button(emoji=discord.PartialEmoji.from_str("<:Rewind:1454135236689657977>"), style=discord.ButtonStyle.secondary, custom_id="player_rewind", row=0)
    async def rewind(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if not vc: 
            return await interaction.response.send_message("❌ Не підключено.", ephemeral=True, delete_after=5)
            
        if not self.player.history:
             return await interaction.response.send_message("❌ Історія пуста.", ephemeral=True, delete_after=5)

        if len(self.player.history) > 0:
            current_from_hist = self.player.history.pop()
        else:
            current_from_hist = None

        if len(self.player.history) > 0:
            previous_track = self.player.history.pop()
            
            if current_from_hist:
                 self.player.queue.appendleft(current_from_hist)
                 
            self.player.queue.appendleft(previous_track)
        else:
             if current_from_hist:
                 self.player.queue.appendleft(current_from_hist)
             else:
                 pass

        self.player.loop = False 
        vc.stop()
        await interaction.response.defer()

    @discord.ui.button(emoji=discord.PartialEmoji.from_str("<:pause:1454136275987861585>"), style=discord.ButtonStyle.secondary, custom_id="player_play_pause", row=0)
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
             await interaction.response.send_message("❌ Не грає.", ephemeral=True, delete_after=5)

    @discord.ui.button(emoji=discord.PartialEmoji.from_str("<:forward:1454135105097306133>"), style=discord.ButtonStyle.secondary, custom_id="player_skip", row=0)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            if self.player.loop:
                self.player.current_track = None 
            
            if len(self.player.queue) == 0:
                await interaction.response.send_message("⏭️ Пропущено. (Черга закінчилась)", ephemeral=True, delete_after=5)
            else:
                await interaction.response.send_message("⏭️ Пропущено.", ephemeral=True, delete_after=5)
                
            vc.stop()
        else:
            await interaction.response.send_message("❌ Нема що пропускати.", ephemeral=True, delete_after=5)

    @discord.ui.button(emoji=discord.PartialEmoji.from_str("<:shuffle:1454152407335309433>"), style=discord.ButtonStyle.secondary, custom_id="player_shuffle", row=0)
    async def shuffle_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if len(self.player.queue) < 2:
             await interaction.response.send_message("❌ Замало треків для перемішування.", ephemeral=True, delete_after=5)
             return
             
        temp_list = list(self.player.queue)
        random.shuffle(temp_list)
        self.player.queue = deque(temp_list)
        await interaction.response.send_message("🔀 Черга перемішана!", ephemeral=True, delete_after=5)

    @discord.ui.button(emoji=discord.PartialEmoji.from_str("<:repeat:1454136632197255220>"), style=discord.ButtonStyle.secondary, custom_id="player_loop", row=1)
    async def loop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.player.loop = not self.player.loop
        self.update_buttons()
        await interaction.response.edit_message(view=self)

    @discord.ui.button(emoji=discord.PartialEmoji.from_str("<:Queue:1454135859816173609>"), style=discord.ButtonStyle.secondary, custom_id="player_queue", row=1)
    async def queue_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Delete previous queue message if we can track it (optional optimization, user requested old one disappears)
        # Since queue messages are ephemeral, we can't delete them easily if they are from different interactions.
        # But if this button is clicked multiple times, we just send a new ephemeral.
        
        view = QueueView(self.player)
        embed = view.generate_embed()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class QueueView(discord.ui.View):
    def __init__(self, player):
        super().__init__(timeout=180)
        self.player = player
        self.update_select()

    def generate_embed(self):
        embed = discord.Embed(color=0x1DB954)
        embed.title = "📜 Черга відтворення"
        
        # --- Now Playing Section ---
        if self.player.current_track:
            title = self.player.current_track.get('title', 'Unknown')
            req = self.player.current_track.get('requester_name', 'Unknown')
            dur = str(datetime.timedelta(seconds=self.player.current_track.get('duration', 0)))
            
            embed.add_field(
                name="🎶 Зараз грає", 
                value=f"**{title}**\n⏱️ `{dur}` | 👤 {req}", 
                inline=False
            )
        else:
            embed.add_field(name="🎶 Зараз грає", value="*Нічого не грає*", inline=False)

        # --- Queue List Section ---
        if self.player.queue:
            q_list = ""
            for i, track in enumerate(self.player.queue, 1): 
                if i > 15: 
                    q_list += f"\n*...і ще {len(self.player.queue) - 15} треків*"
                    break
                
                t_title = track.get('title', 'Unknown')
                t_req = track.get('requester_name', 'Unknown')
                # If it's a smart playlist import
                origin = track.get('playlist_origin')
                if origin:
                     q_list += f"`{i}.` **{t_title}** *(📦 {origin})*\n"
                else:
                     q_list += f"`{i}.` {t_title} *({t_req})*\n"
            
            embed.add_field(name=f"⏳ Черга ({len(self.player.queue)})", value=q_list, inline=False)
        else:
             embed.add_field(name="⏳ Черга", value="*Пусто*", inline=False)

        return embed

    def update_select(self):
        for child in self.children:
             if isinstance(child, QueueRemoveSelect):
                 self.remove_item(child)
        
        if len(self.player.queue) > 0:
            self.add_item(QueueRemoveSelect(self.player))
            
        # HistoryRemoveSelect removed

        if len(self.player.queue) > 0:
            self.add_item(QueueRemoveSelect(self.player))
            
        # Playlist buttons removed

    # Save playlist button removed

    @discord.ui.button(emoji=discord.PartialEmoji.from_str("<:add:1454141315716612136>"), style=discord.ButtonStyle.success, row=2)
    async def add_url_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Opens the modal to add tracks
        await interaction.response.send_modal(AddURLModal(self.player, self))

    @discord.ui.button(style=discord.ButtonStyle.danger, emoji=discord.PartialEmoji.from_str("🗑️"), row=2)
    async def clear_q_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.player.queue.clear()
        await self.player.save_state()
        embed = self.generate_embed()
        self.update_select()
        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send("🗑️ Черга очищена.", ephemeral=True, delete_after=5)

# HistoryRemoveSelect class removed

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
            await interaction.response.send_message(f"🗑️ Видалено: **{removed.get('title')}**", ephemeral=True, delete_after=5)
            
            view = self.view
            view.update_select()
            embed = view.generate_embed()
            await interaction.message.edit(embed=embed, view=view)
        else:
            await interaction.response.send_message("❌ Помилка індексу.", ephemeral=True, delete_after=5)

# Playlist UI classes removed (SavePlaylistModal, PlaylistSelectView, DeletePlaylistSelectView, DeletePlaylistSelect, PlaylistSelect)

class MusicCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.players = {}

    async def send_timed_msg(self, interaction, content, delay=5, ephemeral=True):
        try:
            msg = await interaction.followup.send(content, ephemeral=ephemeral)
            if delay:
                await asyncio.sleep(delay)
                try:
                    await msg.delete()
                except:
                    pass
        except:
             pass

    def get_player(self, guild, channel):
        if guild.id not in self.players:
            self.players[guild.id] = MusicPlayer(self.bot, guild, channel, self)
        return self.players[guild.id]
    
    # Playlist slash commands removed per user request (UI only)
    
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
             await interaction.followup.send("❌ Ви маєте бути в голосовому каналі!", ephemeral=True, delete_after=5)
             return
        
        channel = interaction.user.voice.channel
        
        if not interaction.guild.voice_client:
            try:
                await channel.connect(self_deaf=True)
            except Exception as e:
                await self.send_timed_msg(interaction, f"❌ Не вдалося підключитися: {e}", delay=5)
                return
        
        player = self.get_player(interaction.guild, interaction.channel)
        
        try:
            tracks = await player.extract_tracks(query, source.value if source else None, interaction)
        except Exception as e:
            await self.send_timed_msg(interaction, f"❌ Помилка: {e}", delay=10)
            return

        added = 0
        req_name = interaction.user.display_name
        
        # Просто додаємо в чергу. Ніякого скидання поточних треків.
        for track in tracks:
             if track:
                track['requester'] = interaction.user.id
                track['requester_name'] = req_name
                player.queue.append(track)
                added += 1
                
        await player.save_state()

        if added == 1:
            track = tracks[0]
            await self.send_timed_msg(interaction, f"✅ Додано в чергу: **{track.get('title', 'Unknown')}**", delay=5)
        else:
            await self.send_timed_msg(interaction, f"✅ Додано {added} треків в чергу.", delay=5)
        
        # Сигнал плеєру, тільки якщо він чекає (не грає і не має треку)
        vc = interaction.guild.voice_client
        if vc and not (vc.is_playing() or vc.is_paused()) and not player.current_track:
             player.next_event.set()

class AddURLModal(discord.ui.Modal, title="Додати трек/плейлист"):
    url = discord.ui.TextInput(label="Посилання (YouTube/Spotify/SoundCloud)", placeholder="https://...", style=discord.TextStyle.short)

    def __init__(self, player, parent_view=None):
        super().__init__()
        self.player = player
        self.parent_view = parent_view # Reference to refresh the queue view if possible

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        url = self.url.value
        
        try:
            tracks = await self.player.extract_tracks(url, None, interaction)
        except Exception as e:
            await interaction.followup.send(f"❌ Помилка: {e}", ephemeral=True)
            return

        added = 0
        req_name = interaction.user.display_name
        
        for track in tracks:
            if track:
                track['requester'] = interaction.user.id
                track['requester_name'] = req_name
                self.player.queue.append(track)
                added += 1

        if added == 1:
            await interaction.followup.send(f"✅ Додано: **{tracks[0].get('title', 'Unknown')}**", ephemeral=True)
        else:
            pl_name = tracks[0].get('playlist_origin', 'Unknown Playlist')
            await interaction.followup.send(f"✅ Додано {added} треків з **{pl_name}**.", ephemeral=True)
            
        # Try to refresh the queue view if it was passed
        if self.parent_view:
             try:
                 new_embed = self.parent_view.generate_embed()
                 self.parent_view.update_select()
                 # We cannot edit the message directly easily because we don't have the message object 
                 # stored in the view reliably unless we passed it. 
                 # But we can try interaction.message if it was a button click? 
                 # Modal interaction is separate.
                 # The user wanted "old message disappears". 
                 # We can't delete the user's old ephemeral message. 
                 # But we can imply the user should just open the queue again or look at the updated one.
                 pass
             except:
                 pass
            
        vc = interaction.guild.voice_client
        # Якщо нічого не грає, запускаємо
        if vc and not (vc.is_playing() or vc.is_paused()) and not self.player.current_track:
             self.player.next_event.set()

async def setup(bot):
    await bot.add_cog(MusicCommands(bot))
