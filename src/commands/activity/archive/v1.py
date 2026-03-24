import discord
from discord import app_commands
from discord.ext import commands
from modules.db import get_database
import math

db = get_database()

class LeaderboardView(discord.ui.View):
    def __init__(self, users, guild, current_user, page=0):
        super().__init__(timeout=300)
        self.users = users
        self.guild = guild
        self.current_user = current_user
        self.page = page
        self.per_page = 10
        self.max_pages = math.ceil(len(users) / self.per_page)
        
        self.update_buttons()
    
    def update_buttons(self):
        self.first_page.disabled = self.page == 0
        self.prev_page.disabled = self.page == 0
        self.next_page.disabled = self.page >= self.max_pages - 1
        self.last_page.disabled = self.page >= self.max_pages - 1
    
    def get_embed(self):
        start = self.page * self.per_page
        end = start + self.per_page
        page_users = self.users[start:end]
        
        embed = discord.Embed(
            title="<:trophytop1:1485625873880191067> ЛІДЕРБОРД СЕРВЕРА",
            color=0x2f3136,
            description="Найактивніші учасники спільноти"
        )
        
        leaderboard_text = ""
        user_position = None
        user_data = None
        
        medals = ["<:trophytop1:1485625873880191067>", "<:medal:1485625991274430574>", "<:medal:1485625991274430574>"]
        
        for i, data in enumerate(page_users):
            position = start + i + 1
            member = self.guild.get_member(data["user_id"])
            name = member.display_name if member else f"Користувач#{data['user_id']}"
            
            if len(name) > 15:
                name = name[:12] + "..."
            
            medal = medals[position - 1] if position <= 3 else f"`{position:2d}.`"
            level_bar = "▰" * min(data['level'], 10) + "▱" * max(0, 10 - data['level'])
            
            leaderboard_text += (
                f"{medal} **{name}**\n"
                f"└ `Рівень {data['level']:2d}` {level_bar} `{data['xp']:4d} XP`\n"
                f"└ `🎤 {data['voice_minutes']:3d} хв` • `❤️ {data['reactions']:3d} реакцій`\n\n"
            )
            
            if data["user_id"] == self.current_user.id:
                user_position = position
                user_data = data
        
        if not user_position:
            for i, data in enumerate(self.users):
                if data["user_id"] == self.current_user.id:
                    user_position = i + 1
                    user_data = data
                    break
        
        embed.description = leaderboard_text or "Немає даних для відображення"
        
        if user_data:
            embed.set_footer(
                text=f"Твоя позиція: #{user_position} • Рівень {user_data['level']} • {user_data['xp']} XP",
                icon_url=self.current_user.display_avatar.url
            )
        
        embed.add_field(
            name="📄 Сторінка",
            value=f"{self.page + 1} / {self.max_pages}",
            inline=True
        )
        
        embed.add_field(
            name="👥 Всього учасників",
            value=f"{len(self.users)}",
            inline=True
        )
        
        embed.set_thumbnail(url=self.guild.icon.url if self.guild.icon else None)
        
        return embed
    
    @discord.ui.button(emoji="⏪", style=discord.ButtonStyle.secondary)
    async def first_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = 0
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
    
    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.primary)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
    
    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.primary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
    
    @discord.ui.button(emoji="⏩", style=discord.ButtonStyle.secondary)
    async def last_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = self.max_pages - 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
    
    @discord.ui.button(emoji="🔄", style=discord.ButtonStyle.success)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        users = await db.users.find({"guild_id": interaction.guild.id}).to_list(None)
        self.users = sorted(users, key=lambda x: x["xp"] + x["level"] * 1000, reverse=True)
        self.max_pages = math.ceil(len(self.users) / self.per_page)
        if self.page >= self.max_pages:
            self.page = max(0, self.max_pages - 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

class LeaderboardCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="leaderboard", description="Показує топ користувачів сервера")
    async def leaderboard(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        
        users = await db.users.find({"guild_id": interaction.guild.id}).to_list(None)
        
        if not users:
            embed = discord.Embed(
                title="<:trophytop1:1485625873880191067> ЛІДЕРБОРД СЕРВЕРА",
                description="Поки що немає активних користувачів на сервері.",
                color=0xff6b6b
            )
            await interaction.followup.send(embed=embed)
            return
        
        sorted_users = sorted(users, key=lambda x: x["xp"] + x["level"] * 1000, reverse=True)
        
        view = LeaderboardView(sorted_users, interaction.guild, interaction.user)
        embed = view.get_embed()
        
        await interaction.followup.send(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(LeaderboardCommands(bot))