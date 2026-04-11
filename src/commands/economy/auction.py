import discord
from discord import app_commands
from discord.ext import commands

from commands.administration.economy_setup_shared import fmt_duration, get_eco, normalize_currency_emoji
from modules.db import get_database, get_guild_settings
from services.auction_manager import ACTIVE_AUCTIONS
from services.auction_support import (
    get_auction_min_increment,
    lot_plain_label,
    lot_public_label,
    normalize_active_auction_doc,
    normalize_auction_queue,
)

db = get_database()

E_AUCTION = "<:hammer:1485606127696609412>"


class AuctionStatusView(discord.ui.View):
    def __init__(self, *, guild_id: int, channel_id: int, message_id: int | None = None):
        super().__init__(timeout=180)
        if channel_id:
            url = (
                f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"
                if message_id
                else f"https://discord.com/channels/{guild_id}/{channel_id}"
            )
            label = "Відкрити live-аукціон" if message_id else "Відкрити канал аукціону"
            self.add_item(discord.ui.Button(label=label, url=url))


class AuctionCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="auction", description="Показати активний аукціон або найближчий лот у черзі")
    async def auction_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        settings = await get_guild_settings(db, interaction.guild.id)
        eco = get_eco(settings)

        if not eco.get("enabled", True):
            return await interaction.followup.send("Економіка вимкнена.", ephemeral=True)

        channel_id = eco.get("auction_channel_id", 0)
        if channel_id == 0:
            return await interaction.followup.send(
                "Аукціон ще не налаштований адміністратором: канал проведення не вибраний.",
                ephemeral=True,
            )

        queue = normalize_auction_queue((await db.guild_settings.find_one({"_id": interaction.guild.id}, {"auction_queue": 1}) or {}).get("auction_queue", []))
        active_raw = await ACTIVE_AUCTIONS.find_one({"_id": interaction.guild.id})
        active_doc = normalize_active_auction_doc(active_raw, eco) if active_raw else None
        curr = normalize_currency_emoji(eco.get("currency_emoji"))
        view = None

        if active_doc:
            lot = active_doc["lot_snapshot"]
            leader = f"<@{active_doc['highest_bidder']}>" if active_doc.get("highest_bidder") else "Ще немає ставок"
            min_next = active_doc["current_bid"] if not active_doc.get("highest_bidder") else active_doc["current_bid"] + active_doc["min_increment"]
            next_lot = queue[0] if queue else None
            embed = discord.Embed(
                title=f"{E_AUCTION} Активний аукціон",
                description=(
                    f"**Лот:** {lot_public_label(lot, interaction.guild)}\n"
                    f"**Опис:** {lot.get('description', 'Опис відсутній.')}\n"
                    f"**Переможець отримає:** {lot_public_label(lot, interaction.guild)}"
                ),
                color=0x2B2D31,
            )
            embed.add_field(name="Поточна ставка", value=f"`{active_doc['current_bid']:,}` {curr}", inline=True)
            embed.add_field(name="Лідер", value=leader, inline=True)
            embed.add_field(name="Мін. наступна", value=f"`{min_next:,}` {curr}", inline=True)
            embed.add_field(name="Ставок", value=f"`{len(active_doc.get('bid_history', []))}`", inline=True)
            embed.add_field(name="Завершення", value=f"<t:{int(active_doc['end_time'])}:R> • <t:{int(active_doc['end_time'])}:T>", inline=True)
            embed.add_field(name="Канал", value=f"<#{channel_id}>", inline=True)
            if next_lot:
                embed.add_field(
                    name="Далі в черзі",
                    value=(
                        f"{lot_plain_label(next_lot, interaction.guild)}\n"
                        f"Старт `{next_lot['start_bid']:,}` {curr} • `{fmt_duration(next_lot['duration_seconds'])}`"
                    ),
                    inline=False,
                )
            embed.set_footer(text="Ставки робляться в live-повідомленні в аукціонному каналі.")
            view = AuctionStatusView(
                guild_id=interaction.guild.id,
                channel_id=active_doc.get("channel_id", channel_id),
                message_id=active_doc.get("message_id"),
            )
            return await interaction.followup.send(embed=embed, view=view, ephemeral=True)

        if queue:
            next_lot = queue[0]
            embed = discord.Embed(
                title=f"{E_AUCTION} Активного аукціону зараз немає",
                description=(
                    "Найближчий лот уже в черзі й чекатиме ручного запуску адміністратором.\n\n"
                    f"**Наступний лот:** {lot_public_label(next_lot, interaction.guild)}\n"
                    f"**Опис:** {next_lot.get('description', 'Опис відсутній.')}"
                ),
                color=0x2B2D31,
            )
            embed.add_field(name="Стартова ставка", value=f"`{next_lot['start_bid']:,}` {curr}", inline=True)
            embed.add_field(name="Тривалість", value=f"`{fmt_duration(next_lot['duration_seconds'])}`", inline=True)
            embed.add_field(name="Канал", value=f"<#{channel_id}>", inline=True)
            embed.add_field(name="Антиснайп", value=f"`{eco.get('auction_anti_snipe_seconds', 30)}с`", inline=True)
            embed.add_field(name="Мін. крок", value=f"`{get_auction_min_increment(eco):,}` {curr}", inline=True)
            embed.add_field(name="У черзі", value=f"`{len(queue)}`", inline=True)
            embed.set_footer(text="Аукціон запускається вручну з черги. Коли торги стартують, ставка йде вже в live-повідомленні.")
            view = AuctionStatusView(guild_id=interaction.guild.id, channel_id=channel_id)
            return await interaction.followup.send(embed=embed, view=view, ephemeral=True)

        embed = discord.Embed(
            title=f"{E_AUCTION} Аукціон",
            description=(
                "Зараз немає ні активного аукціону, ні лотів у черзі.\n"
                "Коли staff додасть і запустить лот, торги з’являться в аукціонному каналі."
            ),
            color=0x2B2D31,
        )
        embed.add_field(name="Канал", value=f"<#{channel_id}>", inline=False)
        embed.set_footer(text="Аукціонна система налаштована, але торги ще не запущені.")
        view = AuctionStatusView(guild_id=interaction.guild.id, channel_id=channel_id)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


async def setup(bot):
    await bot.add_cog(AuctionCommand(bot))
