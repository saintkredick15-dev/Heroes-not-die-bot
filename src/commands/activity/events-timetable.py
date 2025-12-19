import discord
from discord import app_commands
from discord.ext import commands

class ComplaintModal(discord.ui.Modal, title='Відправити жалобу'):
    complaint = discord.ui.TextInput(
        label='Опис ситуації',
        placeholder='Розкажіть нам про ситуацію максимально детально',
        style=discord.TextStyle.long,
        max_length=2000
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        # ID каналу для жалоб
        complaint_channel_id = 1403706530100023386
        complaint_channel = interaction.guild.get_channel(complaint_channel_id)
        
        if complaint_channel:
            embed = discord.Embed(
                title="Нова жалоба",
                description=self.complaint.value,
                color=0xff0000,
                timestamp=discord.utils.utcnow()
            )
            embed.set_author(name=f"{interaction.user.display_name} ({interaction.user.id})", 
                           icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
            
            await complaint_channel.send(embed=embed)
            await interaction.response.send_message("Вашу жалобу було надіслано!", ephemeral=True)
        else:
            await interaction.response.send_message("Помилка: не вдалося знайти канал для жалоб", ephemeral=True)

class EventButtons(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        # Додаємо URL кнопку через add_item
        join_button = discord.ui.Button(
            label='Приєднатись',
            emoji='<:plus:1420453103005859990>',
            style=discord.ButtonStyle.link,
            url='https://discord.com/channels/1386300362595504159/1401581412682960896'
        )
        self.add_item(join_button)
    
    @discord.ui.button(label='Відправити скаргу', emoji='<:megaphone3:1420458218131296413>', style=discord.ButtonStyle.secondary)
    async def complaint_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = ComplaintModal()
        await interaction.response.send_modal(modal)

class EventTimetable(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command(name="івенттайбл", aliases=["eventtimetable", "тайбл"])
    async def event_timetable(self, ctx):
        # Перший ембед з зображенням
        first_embed = discord.Embed(color=0x2b2d31)
        first_embed.set_image(url="https://i.imgur.com/ftmM1HG.png")
        
        # Другий ембед з інформацією про гру
        second_embed = discord.Embed(
            title="**Gartic Phone** — HEROES NOT DIE",
            description="Гра, що поєднує «зламаний телефон» і малювання, де гравці по черзі малюють та підписують малюнки, створюючи кумедний ланцюжок інтерпретаці.",
            color=0x2b2d31
        )
        
        # Додаємо поля з емодзі в одну лінію
        second_embed.add_field(
            name="<:zirka:1412519774780395631> Ведучий — <@kredick>",
            value="",
            inline=False
        )
        second_embed.add_field(
            name="<:cubok:1412519929726374109> Нагорода за перемогу — кастомна роль до слідуючого івенту",
            value="",
            inline=False
        )
        second_embed.add_field(
            name="<:kalendar:1412519787019501719> Початок івенту — 27 вересня 2025 р. 17:35",
            value="",
            inline=False
        )
        
        # Створюємо кнопки
        view = EventButtons()
        
        # Відправляємо пінг ролі та ембеди з кнопками
        await ctx.send("||<@&1412151154699145318>||", embeds=[first_embed, second_embed], view=view)

async def setup(bot):
    await bot.add_cog(EventTimetable(bot))