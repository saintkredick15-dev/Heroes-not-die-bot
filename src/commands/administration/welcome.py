"""
welcome.py
Адміністративна панель для налаштування системи привітань та прощань.
Використовує Dashboard UI з фіксованим режимом (передається аргментом команди).
"""
from __future__ import annotations

import discord
import aiohttp
from discord import app_commands
from discord.ext import commands
from modules.db import get_database
from utils.image_generator import get_available_fonts

db = get_database()
_col = db.guild_settings

E_HI = "<:hi:1476689510560567456>"
E_BYE = "<:bye:1476689667351904376>"
E_LIST = "<:list:1454151067989184562>"
E_PHOTO = "<:photo:1476690859029172456>"
E_FONTS = "<:fonts:1476682058309828681>"
E_PALETTE = "<:palette:1476576171427758080>"
E_TEXT = "<:text:1476691204543348746>"
E_CHECK = "<:check:1454140864627740834>"
E_COLOR_OUTLINE = "<:fontspallets:1476940986277167246>"
E_COLOR = "<:collor:1476941167986872473>"
E_BG = "<:background:1476941632560435322>"
E_CROSS = "<:krestik:1476693091355463842>"

async def get_greetings_settings(guild_id: int) -> dict:
    settings = await _col.find_one({"_id": guild_id}) or {}
    data = {}
    for mode in ("welcome", "goodbye", "boost"):
        defs = {
            "text": "Ласкаво просимо {user_mention}!" if mode=="welcome" else ("Бувай, {user_mention}!" if mode=="goodbye" else "🚀 Дякуємо за підняття сервера, {user_mention}!"),
            "image": True,
            "font_c": "#FFFFFF",
            "font_n": "ARIAL",
            "out_c": "#FF73FA" if mode=="boost" else "#5865F2",
            "bg_u": "",
            "bg_c": "#1A1A2E"
        }
        data[f"{mode}_channel_id"] = settings.get(f"{mode}_channel_id")
        data[f"{mode}_text"] = settings.get(f"{mode}_text", defs["text"])
        data[f"{mode}_image_enabled"] = settings.get(f"{mode}_image_enabled", defs["image"])
        data[f"{mode}_font_color"] = settings.get(f"{mode}_font_color", defs["font_c"])
        data[f"{mode}_font_name"] = settings.get(f"{mode}_font_name", defs["font_n"])
        data[f"{mode}_outline_color"] = settings.get(f"{mode}_outline_color", defs["out_c"])
        data[f"{mode}_bg_url"] = settings.get(f"{mode}_bg_url", defs["bg_u"])
        data[f"{mode}_bg_color"] = settings.get(f"{mode}_bg_color", defs["bg_c"])
    
    data["boost_role_id"] = settings.get("boost_role_id")
    return data

async def update_settings(guild_id: int, data: dict) -> None:
    await _col.update_one({"_id": guild_id}, {"$set": data}, upsert=True)

    def __init__(self, guild_id: int, mode: str, current_text: str, view: DashboardView):
        if mode == "welcome": title = "Текст Привітання"
        elif mode == "goodbye": title = "Текст Прощання"
        else: title = "Текст про Буст"
        super().__init__(title=title)
        self.guild_id = guild_id
        self.mode = mode
        self.view = view
        
        self.text_input = discord.ui.TextInput(
            label="Змінні: {user_mention}, {server_name}",
            style=discord.TextStyle.paragraph,
            placeholder="Введіть текст повідомлення...",
            default=current_text,
            max_length=2000,
            required=True
        )
        self.add_item(self.text_input)

    async def on_submit(self, interaction: discord.Interaction):
        new_text = self.text_input.value.strip()
        key = f"{self.mode}_text"
        await update_settings(self.guild_id, {key: new_text})
        self.view.settings[key] = new_text
        await interaction.response.edit_message(embed=_build_embed(self.view.settings, self.mode), view=self.view)

class ColorModal(discord.ui.Modal):
    def __init__(self, guild_id: int, mode: str, color_type: str, current_color: str, view: DashboardView):
        if color_type == "font": title = "Колір тексту"
        elif color_type == "bg": title = "Суцільний колір фону"
        else: title = "Колір рамки аватара"
        
        super().__init__(title=title)
        self.guild_id = guild_id
        self.mode = mode
        self.color_type = color_type
        self.view = view
        
        self.color_input = discord.ui.TextInput(
            label="HEX-колір (наприклад: #FFFFFF)",
            placeholder="#FFFFFF",
            default=current_color,
            min_length=6,
            max_length=7,
            required=True
        )
        self.add_item(self.color_input)

    async def on_submit(self, interaction: discord.Interaction):
        color = self.color_input.value.strip().upper()
        if not color.startswith("#"):
            color = f"#{color}"
            
        key = f"{self.mode}_{self.color_type}_color"
        await update_settings(self.guild_id, {key: color})
        self.view.settings[key] = color
        await interaction.response.edit_message(embed=_build_embed(self.view.settings, self.mode), view=self.view)

class UrlModal(discord.ui.Modal):
    def __init__(self, guild_id: int, mode: str, current_url: str, view: DashboardView):
        super().__init__(title="Встановити фонове зображення")
        self.guild_id = guild_id
        self.mode = mode
        self.view = view
        
        self.url_input = discord.ui.TextInput(
            label="Пряме посилання на зображення (URL)",
            placeholder="https://example.com/image.png (залиште пустим для видалення)",
            default=current_url,
            required=False,
            max_length=2000
        )
        self.add_item(self.url_input)

    async def on_submit(self, interaction: discord.Interaction):
        new_url = self.url_input.value.strip()
        key = f"{self.mode}_bg_url"
        await update_settings(self.guild_id, {key: new_url})
        self.view.settings[key] = new_url
        await interaction.response.edit_message(embed=_build_embed(self.view.settings, self.mode), view=self.view)

class BoostRoleModal(discord.ui.Modal, title="Роль за буст сервера"):
    role_input = discord.ui.TextInput(
        label="ID ролі (залиште пустим для видалення)",
        placeholder="123456789012345678",
        required=False,
        max_length=25,
    )

    def __init__(self, view: "DashboardView"):
        super().__init__()
        self.dv = view
        current = view.settings.get("boost_role_id")
        if current:
            self.role_input.default = str(current)

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.role_input.value.strip()
        if not raw:
            role_id = None
        elif raw.isdigit():
            role_id = int(raw)
        else:
            return await interaction.response.send_message(f"{E_CROSS} Невірний ID ролі.", ephemeral=True)
        await update_settings(interaction.guild.id, {"boost_role_id": role_id})
        self.dv.settings["boost_role_id"] = role_id
        await interaction.response.edit_message(embed=_build_embed(self.dv.settings, self.dv.mode), view=self.dv)

class FontSelect(discord.ui.Select):
    def __init__(self, current_font: str):
        fonts = get_available_fonts()
        if not fonts:
            options = [discord.SelectOption(label="ARIAL", value="ARIAL", description="Стандартний шрифт")]
        else:
            options = [
                discord.SelectOption(
                    label=f, value=f, default=(f == current_font), emoji=discord.PartialEmoji.from_str(E_FONTS)
                ) for f in fonts[:25]
            ]
        super().__init__(placeholder="Оберіть шрифт для картинки", min_values=1, max_values=1, options=options, row=1, custom_id="font_select")

    async def callback(self, interaction: discord.Interaction):
        selected_font = self.values[0]
        view: DashboardView = self.view
        mode = view.mode
        key = f"{mode}_font_name"
        
        await update_settings(interaction.guild.id, {key: selected_font})
        view.settings[key] = selected_font
        
        for opt in self.options:
            opt.default = (opt.value == selected_font)
            
        await interaction.response.edit_message(embed=_build_embed(view.settings, mode), view=view)

class DashboardView(discord.ui.View):
    def __init__(self, guild_id: int, mode: str, settings: dict):
        super().__init__(timeout=1800)
        self.guild_id = guild_id
        self.settings = settings
        self.mode = mode
        
        self.add_item(FontSelect(settings[f"{self.mode}_font_name"]))

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        placeholder="Обрати канал для повідомлень",
        channel_types=[discord.ChannelType.text],
        row=0
    )
    async def select_channel(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        channel = select.values[0]
        key = f"{self.mode}_channel_id"
        await update_settings(self.guild_id, {key: channel.id})
        self.settings[key] = channel.id
        await interaction.response.edit_message(embed=_build_embed(self.settings, self.mode), view=self)

    @discord.ui.button(label="Текст", style=discord.ButtonStyle.secondary, emoji=discord.PartialEmoji.from_str(E_TEXT), row=2)
    async def btn_edit_text(self, interaction: discord.Interaction, button: discord.ui.Button):
        current = self.settings[f"{self.mode}_text"]
        await interaction.response.send_modal(TextModal(self.guild_id, self.mode, current, self))

    @discord.ui.button(label="Фонове Зображення", style=discord.ButtonStyle.secondary, emoji=discord.PartialEmoji.from_str(E_BG), row=2)
    async def btn_edit_bg(self, interaction: discord.Interaction, button: discord.ui.Button):
        current = self.settings[f"{self.mode}_bg_url"]
        await interaction.response.send_modal(UrlModal(self.guild_id, self.mode, current, self))

    @discord.ui.button(label="Колір тексту", style=discord.ButtonStyle.secondary, emoji=discord.PartialEmoji.from_str(E_COLOR), row=3)
    async def btn_edit_font_color(self, interaction: discord.Interaction, button: discord.ui.Button):
        current = self.settings[f"{self.mode}_font_color"]
        await interaction.response.send_modal(ColorModal(self.guild_id, self.mode, "font", current, self))

    @discord.ui.button(label="Колір рамки", style=discord.ButtonStyle.secondary, emoji=discord.PartialEmoji.from_str(E_COLOR_OUTLINE), row=3)
    async def btn_edit_out_color(self, interaction: discord.Interaction, button: discord.ui.Button):
        current = self.settings[f"{self.mode}_outline_color"]
        await interaction.response.send_modal(ColorModal(self.guild_id, self.mode, "outline", current, self))
        
    @discord.ui.button(label="Колір фону", style=discord.ButtonStyle.secondary, emoji=discord.PartialEmoji.from_str(E_COLOR), row=3)
    async def btn_edit_bg_color(self, interaction: discord.Interaction, button: discord.ui.Button):
        current = self.settings[f"{self.mode}_bg_color"]
        await interaction.response.send_modal(ColorModal(self.guild_id, self.mode, "bg", current, self))

    @discord.ui.button(label="Увімк/Вимк Картинку", style=discord.ButtonStyle.primary, row=4)
    async def btn_toggle_image(self, interaction: discord.Interaction, button: discord.ui.Button):
        key = f"{self.mode}_image_enabled"
        current = self.settings[key]
        await update_settings(self.guild_id, {key: not current})
        self.settings[key] = not current
        await interaction.response.edit_message(embed=_build_embed(self.settings, self.mode), view=self)

    @discord.ui.button(label="Роль за буст", style=discord.ButtonStyle.secondary, emoji="<:boost:1478073594247643377>", row=4)
    async def btn_boost_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.mode != "boost":
            return await interaction.response.send_message(f"{E_CROSS} Ця кнопка доступна лише в режимі Boost.", ephemeral=True)
        await interaction.response.send_modal(BoostRoleModal(self))

def _build_embed(settings: dict, mode: str) -> discord.Embed:
    if mode == "welcome":
        title = f"{E_HI} Налаштування Привітань (Welcome)"
    elif mode == "goodbye":
        title = f"{E_BYE} Налаштування Прощань (Goodbye)"
    else:
        title = "<:boost:1478073594247643377> Налаштування Бустів Сервера (Boost)"
    
    desc = "Налаштуйте канал, текст та генерацію візуальної картки."
    
    embed = discord.Embed(title=title, description=desc, color=0x1a1a2e)
    
    ch_id = settings[f"{mode}_channel_id"]
    ch_display = f"<#{ch_id}>" if ch_id else f"{E_CROSS} Не встановлено"
    img_status = f"{E_CHECK} Увімкнено" if settings[f"{mode}_image_enabled"] else f"{E_CROSS} Вимкнено"
    
    bg_url = settings[f"{mode}_bg_url"]
    bg_status = f"{E_PHOTO} Встановлено URL" if bg_url else f"{E_COLOR} Колір: {settings[f'{mode}_bg_color']}"
    
    embed.add_field(name=f"{E_LIST} Канал", value=ch_display, inline=True)
    embed.add_field(name=f"{E_PHOTO} Картинка", value=img_status, inline=True)
    embed.add_field(name=f"{E_BG} Фон", value=bg_status, inline=True)
    
    embed.add_field(name=f"{E_FONTS} Шрифт", value=f"`{settings[f'{mode}_font_name']}`", inline=True)
    embed.add_field(name=f"{E_COLOR} Колір тексту", value=settings[f"{mode}_font_color"], inline=True)
    embed.add_field(name=f"{E_COLOR_OUTLINE} Колір рамки", value=settings[f"{mode}_outline_color"], inline=True)
    
    if mode == "boost":
        role_id = settings.get("boost_role_id")
        role_val = f"<@&{role_id}>" if role_id else f"{E_CROSS} Не встановлено"
        embed.add_field(name="<:boost:1478073594247643377> Роль за буст", value=role_val, inline=True)
    
    embed.add_field(name=f"{E_TEXT} Текст повідомлення", value=f"```{settings[f'{mode}_text']}```", inline=False)
    
    if bg_url:
        embed.set_image(url=bg_url)
    
    embed.set_footer(text="Використовуйте кнопки для налаштування")
    return embed

class GreetingsSettings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="welcome", description="Панель налаштування системи привітань та прощань")
    @app_commands.describe(mode="Оберіть режим для налаштування")
    @app_commands.choices(mode=[
        app_commands.Choice(name="👋 Привітання (Welcome)", value="welcome"),
        app_commands.Choice(name="🚪 Прощання (Goodbye)", value="goodbye"),
        app_commands.Choice(name="🚀 Бусти сервера (Boost)", value="boost")
    ])
    @app_commands.default_permissions(administrator=True)
    async def welcome_setup(self, interaction: discord.Interaction, mode: app_commands.Choice[str]):
        chosen_mode = mode.value
        settings = await get_greetings_settings(interaction.guild.id)
        embed = _build_embed(settings, chosen_mode)
        view = DashboardView(interaction.guild.id, chosen_mode, settings)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot: return
        await self._process_greeting(member, "welcome")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if member.bot: return
        await self._process_greeting(member, "goodbye")
        
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.premium_since is None and after.premium_since is not None:
            
            settings = await _col.find_one({"_id": after.guild.id}) or {}
            boost_role_id = settings.get("boost_role_id")
            if boost_role_id:
                role = after.guild.get_role(boost_role_id)
                if role:
                    try:
                        await after.add_roles(role, reason="Boost Reward")
                    except discord.Forbidden:
                        pass
            await self._process_greeting(after, "boost")
        
    async def _process_greeting(self, member: discord.Member, mode: str):
        settings = await get_greetings_settings(member.guild.id)
        channel_id = settings.get(f"{mode}_channel_id")
        if not channel_id: return
            
        channel = member.guild.get_channel(channel_id)
        if not channel: return

        raw_text = settings.get(f"{mode}_text")
        if not raw_text:
            if mode == 'welcome': raw_text = "Ласкаво просимо {user_mention} до **{server_name}**!"
            elif mode == 'goodbye': raw_text = "Бувай, {user_mention}, сподіваємось, тобі тут сподобалось! 👋"
            else: raw_text = "🚀 Дякуємо за підняття сервера, {user_mention}!"
            
        formatted_text = raw_text.replace("{user_mention}", member.mention).replace("{server_name}", member.guild.name)

        if settings.get(f"{mode}_image_enabled", True):
            from utils.image_generator import generate_welcome_card
            
            avatar_bytes = b""
            display_avatar = member.display_avatar.replace(size=256, format="png")
            try:
                avatar_bytes = await display_avatar.read()
            except Exception as e:
                print(f"[Greetings] Failed to read avatar: {e}")
                
            bg_bytes = None
            bg_url = settings.get(f"{mode}_bg_url")
            if bg_url:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(bg_url) as resp:
                            if resp.status == 200:
                                bg_bytes = await resp.read()
                except Exception as e:
                    print(f"[Greetings] Failed to download bg image: {e}")
                
            try:
                top_texts = {"welcome": "ЛАСКАВО ПРОСИМО", "goodbye": "ПРОЩАВАЙ", "boost": "ДЯКУЄМО ЗА БУСТ"}
                card_buffer = generate_welcome_card(
                    avatar_bytes=avatar_bytes,
                    username=member.display_name,
                    top_text=top_texts.get(mode, "ПОВІДОМЛЕННЯ"),
                    bg_bytes=bg_bytes,
                    bg_color_hex=settings.get(f"{mode}_bg_color", "#1A1A2E"),
                    font_name=settings.get(f"{mode}_font_name", "ARIAL"),
                    font_color_hex=settings.get(f"{mode}_font_color", "#FFFFFF"),
                    avatar_outline_color_hex=settings.get(f"{mode}_outline_color", "#5865F2")
                )
                
                file = discord.File(fp=card_buffer, filename=f"{mode}_card.png")
                await channel.send(content=formatted_text, file=file)
                return
            except Exception as e:
                print(f"[Greetings] Failed to generate card: {e}")

        await channel.send(content=formatted_text)

async def setup(bot):
    await bot.add_cog(GreetingsSettings(bot))
