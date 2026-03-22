"""
welcome.py
Адміністративна панель для налаштування системи привітань, прощань і boost-повідомлень.
"""
from __future__ import annotations

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from modules.db import get_database
from utils.image_generator import get_available_fonts
from utils.ui_contract import add_section, compact_kv, set_surface_footer, status_badge, surface_embed

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
        defaults = {
            "text": (
                "Ласкаво просимо {user_mention}!"
                if mode == "welcome"
                else (
                    "Бувай, {user_mention}!"
                    if mode == "goodbye"
                    else "Дякуємо за підняття сервера, {user_mention}!"
                )
            ),
            "image": True,
            "font_c": "#FFFFFF",
            "font_n": "ARIAL",
            "out_c": "#FF73FA" if mode == "boost" else "#5865F2",
            "bg_u": "",
            "bg_c": "#1A1A2E",
        }
        data[f"{mode}_channel_id"] = settings.get(f"{mode}_channel_id")
        data[f"{mode}_text"] = settings.get(f"{mode}_text", defaults["text"])
        data[f"{mode}_image_enabled"] = settings.get(f"{mode}_image_enabled", defaults["image"])
        data[f"{mode}_font_color"] = settings.get(f"{mode}_font_color", defaults["font_c"])
        data[f"{mode}_font_name"] = settings.get(f"{mode}_font_name", defaults["font_n"])
        data[f"{mode}_outline_color"] = settings.get(f"{mode}_outline_color", defaults["out_c"])
        data[f"{mode}_bg_url"] = settings.get(f"{mode}_bg_url", defaults["bg_u"])
        data[f"{mode}_bg_color"] = settings.get(f"{mode}_bg_color", defaults["bg_c"])

    data["boost_role_id"] = settings.get("boost_role_id")
    return data


async def update_settings(guild_id: int, data: dict) -> None:
    await _col.update_one({"_id": guild_id}, {"$set": data}, upsert=True)


class TextModal(discord.ui.Modal):
    def __init__(self, guild_id: int, mode: str, current_text: str, view: "DashboardView"):
        titles = {
            "welcome": "Текст привітання",
            "goodbye": "Текст прощання",
            "boost": "Текст для boost-повідомлення",
        }
        super().__init__(title=titles.get(mode, "Текст повідомлення"))
        self.guild_id = guild_id
        self.mode = mode
        self.view_ref = view
        self.text_input = discord.ui.TextInput(
            label="Доступні змінні: {user_mention}, {server_name}",
            style=discord.TextStyle.paragraph,
            placeholder="Введіть текст повідомлення...",
            default=current_text,
            max_length=2000,
            required=True,
        )
        self.add_item(self.text_input)

    async def on_submit(self, interaction: discord.Interaction):
        key = f"{self.mode}_text"
        new_text = self.text_input.value.strip()
        await update_settings(self.guild_id, {key: new_text})
        self.view_ref.settings[key] = new_text
        await interaction.response.edit_message(
            embed=_build_embed(self.view_ref.settings, self.mode),
            view=self.view_ref,
        )


class ColorModal(discord.ui.Modal):
    def __init__(self, guild_id: int, mode: str, color_type: str, current_color: str, view: "DashboardView"):
        titles = {
            "font": "Колір тексту",
            "bg": "Суцільний колір фону",
            "outline": "Колір рамки аватара",
        }
        super().__init__(title=titles.get(color_type, "Колір"))
        self.guild_id = guild_id
        self.mode = mode
        self.color_type = color_type
        self.view_ref = view
        self.color_input = discord.ui.TextInput(
            label="HEX-колір",
            placeholder="#FFFFFF",
            default=current_color,
            min_length=6,
            max_length=7,
            required=True,
        )
        self.add_item(self.color_input)

    async def on_submit(self, interaction: discord.Interaction):
        color = self.color_input.value.strip().upper()
        if not color.startswith("#"):
            color = f"#{color}"
        key = f"{self.mode}_{self.color_type}_color"
        await update_settings(self.guild_id, {key: color})
        self.view_ref.settings[key] = color
        await interaction.response.edit_message(
            embed=_build_embed(self.view_ref.settings, self.mode),
            view=self.view_ref,
        )


class UrlModal(discord.ui.Modal):
    def __init__(self, guild_id: int, mode: str, current_url: str, view: "DashboardView"):
        super().__init__(title="Фонове зображення")
        self.guild_id = guild_id
        self.mode = mode
        self.view_ref = view
        self.url_input = discord.ui.TextInput(
            label="Пряме посилання на зображення",
            placeholder="https://example.com/image.png",
            default=current_url,
            required=False,
            max_length=2000,
        )
        self.add_item(self.url_input)

    async def on_submit(self, interaction: discord.Interaction):
        key = f"{self.mode}_bg_url"
        new_url = self.url_input.value.strip()
        await update_settings(self.guild_id, {key: new_url})
        self.view_ref.settings[key] = new_url
        await interaction.response.edit_message(
            embed=_build_embed(self.view_ref.settings, self.mode),
            view=self.view_ref,
        )


class BoostRoleModal(discord.ui.Modal, title="Роль за boost сервера"):
    role_input = discord.ui.TextInput(
        label="ID ролі",
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
                    label=font,
                    value=font,
                    default=(font == current_font),
                    emoji=discord.PartialEmoji.from_str(E_FONTS),
                )
                for font in fonts[:25]
            ]
        super().__init__(
            placeholder="Оберіть шрифт для картки",
            min_values=1,
            max_values=1,
            options=options,
            row=1,
            custom_id="font_select",
        )

    async def callback(self, interaction: discord.Interaction):
        view: DashboardView = self.view
        key = f"{view.mode}_font_name"
        selected_font = self.values[0]
        await update_settings(interaction.guild.id, {key: selected_font})
        view.settings[key] = selected_font
        for option in self.options:
            option.default = option.value == selected_font
        await interaction.response.edit_message(embed=_build_embed(view.settings, view.mode), view=view)


class DashboardView(discord.ui.View):
    def __init__(self, guild_id: int, mode: str, settings: dict):
        super().__init__(timeout=1800)
        self.guild_id = guild_id
        self.mode = mode
        self.settings = settings
        self.add_item(FontSelect(settings[f"{self.mode}_font_name"]))

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        placeholder="Оберіть канал для повідомлень",
        channel_types=[discord.ChannelType.text],
        row=0,
    )
    async def select_channel(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        channel = select.values[0]
        key = f"{self.mode}_channel_id"
        await update_settings(self.guild_id, {key: channel.id})
        self.settings[key] = channel.id
        await interaction.response.edit_message(embed=_build_embed(self.settings, self.mode), view=self)

    @discord.ui.button(label="Текст", style=discord.ButtonStyle.secondary, emoji=discord.PartialEmoji.from_str(E_TEXT), row=2)
    async def btn_edit_text(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TextModal(self.guild_id, self.mode, self.settings[f"{self.mode}_text"], self))

    @discord.ui.button(label="Фонове зображення", style=discord.ButtonStyle.secondary, emoji=discord.PartialEmoji.from_str(E_BG), row=2)
    async def btn_edit_bg(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(UrlModal(self.guild_id, self.mode, self.settings[f"{self.mode}_bg_url"], self))

    @discord.ui.button(label="Колір тексту", style=discord.ButtonStyle.secondary, emoji=discord.PartialEmoji.from_str(E_COLOR), row=3)
    async def btn_edit_font_color(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ColorModal(self.guild_id, self.mode, "font", self.settings[f"{self.mode}_font_color"], self))

    @discord.ui.button(label="Колір рамки", style=discord.ButtonStyle.secondary, emoji=discord.PartialEmoji.from_str(E_COLOR_OUTLINE), row=3)
    async def btn_edit_out_color(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ColorModal(self.guild_id, self.mode, "outline", self.settings[f"{self.mode}_outline_color"], self))

    @discord.ui.button(label="Колір фону", style=discord.ButtonStyle.secondary, emoji=discord.PartialEmoji.from_str(E_PALETTE), row=3)
    async def btn_edit_bg_color(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ColorModal(self.guild_id, self.mode, "bg", self.settings[f"{self.mode}_bg_color"], self))

    @discord.ui.button(label="Картка on/off", style=discord.ButtonStyle.primary, row=4)
    async def btn_toggle_image(self, interaction: discord.Interaction, button: discord.ui.Button):
        key = f"{self.mode}_image_enabled"
        new_value = not self.settings[key]
        await update_settings(self.guild_id, {key: new_value})
        self.settings[key] = new_value
        await interaction.response.edit_message(embed=_build_embed(self.settings, self.mode), view=self)

    @discord.ui.button(label="Роль за boost", style=discord.ButtonStyle.secondary, emoji="<:boost:1478073594247643377>", row=4)
    async def btn_boost_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.mode != "boost":
            return await interaction.response.send_message(f"{E_CROSS} Ця дія доступна лише в режимі boost.", ephemeral=True)
        await interaction.response.send_modal(BoostRoleModal(self))


def _build_embed(settings: dict, mode: str) -> discord.Embed:
    titles = {
        "welcome": f"{E_HI} Привітання",
        "goodbye": f"{E_BYE} Прощання",
        "boost": "<:boost:1478073594247643377> Boost-повідомлення",
    }
    descriptions = {
        "welcome": "Огляд каналу, тексту та візуальної картки для нових учасників.",
        "goodbye": "Огляд каналу, тексту та картки для прощальних повідомлень.",
        "boost": "Огляд повідомлення про boost і додаткової ролі для бустерів.",
    }
    embed = surface_embed("admin", titles.get(mode, "Повідомлення"), descriptions.get(mode))

    channel_id = settings[f"{mode}_channel_id"]
    bg_url = settings[f"{mode}_bg_url"]
    preview_text = settings[f"{mode}_text"]
    if len(preview_text) > 220:
        preview_text = preview_text[:217] + "..."

    add_section(
        embed,
        f"{E_LIST} Огляд",
        [
            compact_kv("Канал", f"<#{channel_id}>" if channel_id else f"{E_CROSS} не вибрано"),
            compact_kv("Картка", status_badge(settings[f"{mode}_image_enabled"])),
            compact_kv("Фон", f"{E_PHOTO} URL" if bg_url else settings[f"{mode}_bg_color"]),
        ],
    )
    add_section(
        embed,
        f"{E_FONTS} Стиль",
        [
            compact_kv("Шрифт", f"`{settings[f'{mode}_font_name']}`"),
            compact_kv("Колір тексту", settings[f"{mode}_font_color"]),
            compact_kv("Колір рамки", settings[f"{mode}_outline_color"]),
        ],
    )
    if mode == "boost":
        role_id = settings.get("boost_role_id")
        add_section(
            embed,
            "Boost-рівень",
            [compact_kv("Роль за boost", f"<@&{role_id}>" if role_id else f"{E_CROSS} не вибрано")],
        )
    add_section(
        embed,
        f"{E_TEXT} Текст",
        [
            preview_text,
            "Швидкі дії нижче відкривають модалки для тексту, кольорів і фону.",
        ],
    )
    if bg_url:
        embed.set_image(url=bg_url)
    set_surface_footer(embed, "admin", "Огляд -> швидкі дії -> детальне редагування в одній панелі.")
    return embed


class GreetingsSettings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="welcome", description="Панель налаштування привітань, прощань і boost-повідомлень")
    @app_commands.describe(mode="Оберіть режим для налаштування")
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="Привітання", value="welcome"),
            app_commands.Choice(name="Прощання", value="goodbye"),
            app_commands.Choice(name="Boost", value="boost"),
        ]
    )
    @app_commands.default_permissions(administrator=True)
    async def welcome_setup(self, interaction: discord.Interaction, mode: app_commands.Choice[str]):
        chosen_mode = mode.value
        settings = await get_greetings_settings(interaction.guild.id)
        await interaction.response.send_message(
            embed=_build_embed(settings, chosen_mode),
            view=DashboardView(interaction.guild.id, chosen_mode, settings),
            ephemeral=True,
        )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if not member.bot:
            await self._process_greeting(member, "welcome")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if not member.bot:
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
        if not channel_id:
            return

        channel = member.guild.get_channel(channel_id)
        if not channel:
            return

        raw_text = settings.get(f"{mode}_text")
        if not raw_text:
            raw_text = {
                "welcome": "Ласкаво просимо {user_mention} до **{server_name}**!",
                "goodbye": "Бувай, {user_mention}, сподіваємось, тобі тут сподобалось!",
                "boost": "Дякуємо за підняття сервера, {user_mention}!",
            }[mode]

        formatted_text = raw_text.replace("{user_mention}", member.mention).replace("{server_name}", member.guild.name)

        if settings.get(f"{mode}_image_enabled", True):
            from utils.image_generator import generate_welcome_card

            avatar_bytes = b""
            try:
                avatar_bytes = await member.display_avatar.replace(size=256, format="png").read()
            except Exception as exc:
                print(f"[Greetings] Failed to read avatar: {exc}")

            bg_bytes = None
            bg_url = settings.get(f"{mode}_bg_url")
            if bg_url:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(bg_url) as resp:
                            if resp.status == 200:
                                bg_bytes = await resp.read()
                except Exception as exc:
                    print(f"[Greetings] Failed to download bg image: {exc}")

            try:
                top_texts = {
                    "welcome": "ЛАСКАВО ПРОСИМО",
                    "goodbye": "ПРОЩАВАЙ",
                    "boost": "ДЯКУЄМО ЗА BOOST",
                }
                card_buffer = generate_welcome_card(
                    avatar_bytes=avatar_bytes,
                    username=member.display_name,
                    top_text=top_texts.get(mode, "ПОВІДОМЛЕННЯ"),
                    bg_bytes=bg_bytes,
                    bg_color_hex=settings.get(f"{mode}_bg_color", "#1A1A2E"),
                    font_name=settings.get(f"{mode}_font_name", "ARIAL"),
                    font_color_hex=settings.get(f"{mode}_font_color", "#FFFFFF"),
                    avatar_outline_color_hex=settings.get(f"{mode}_outline_color", "#5865F2"),
                )
                await channel.send(content=formatted_text, file=discord.File(fp=card_buffer, filename=f"{mode}_card.png"))
                return
            except Exception as exc:
                print(f"[Greetings] Failed to generate card: {exc}")

        await channel.send(content=formatted_text)


async def setup(bot):
    await bot.add_cog(GreetingsSettings(bot))
