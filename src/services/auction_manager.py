from __future__ import annotations

import asyncio
import re
import time

import discord
from pymongo.errors import DuplicateKeyError

from commands.administration.economy_setup_shared import get_eco, normalize_currency_emoji
from config.constants import Emojis
from modules.db import get_database, get_guild_settings, invalidate_user_data

db = get_database()

E_COIN = Emojis.COIN.value
E_AUCTION = Emojis.AUCTION.value
E_CLOCK = Emojis.CLOCK.value
E_CHECK = Emojis.CHECK.value
E_CROSS = Emojis.CANCEL.value
E_EDIT = Emojis.EDIT.value
E_WARN = Emojis.WARN.value

ACTIVE_AUCTIONS = db.active_auctions
ROLE_LOT_RE = re.compile(r"<@&(\d+)>")


def _curr(eco: dict) -> str:
    return normalize_currency_emoji(eco.get("currency_emoji") or Emojis.COIN.value)


async def _refund_reserved_bid(guild_id: int, user_id: int, amount: int) -> None:
    if not user_id or amount <= 0:
        return
    await db.users.update_one(
        {"guild_id": guild_id, "user_id": user_id},
        {"$inc": {"wallet": amount}},
    )
    await invalidate_user_data(guild_id, user_id)


async def _hold_bid_amount(guild_id: int, user_id: int, amount: int) -> bool:
    if amount <= 0:
        return False

    result = await db.users.find_one_and_update(
        {
            "guild_id": guild_id,
            "user_id": user_id,
            "$expr": {
                "$gte": [
                    {"$add": [{"$ifNull": ["$bank", 0]}, {"$ifNull": ["$wallet", 0]}]},
                    amount,
                ]
            },
        },
        [
            {
                "$set": {
                    "_bank_before": {"$ifNull": ["$bank", 0]},
                    "_wallet_before": {"$ifNull": ["$wallet", 0]},
                }
            },
            {
                "$set": {
                    "bank": {
                        "$cond": [
                            {"$gte": ["$_bank_before", amount]},
                            {"$subtract": ["$_bank_before", amount]},
                            0,
                        ]
                    },
                    "wallet": {
                        "$cond": [
                            {"$gte": ["$_bank_before", amount]},
                            "$_wallet_before",
                            {"$subtract": ["$_wallet_before", {"$subtract": [amount, "$_bank_before"]}]},
                        ]
                    },
                }
            },
            {"$unset": ["_bank_before", "_wallet_before"]},
        ],
    )

    if result is None:
        return False

    await invalidate_user_data(guild_id, user_id)
    return True


async def _award_lot(guild_id: int, guild: discord.Guild | None, lot: dict, winner_id: int, amount: int) -> str | None:
    role_match = ROLE_LOT_RE.search(lot["name"])
    if role_match:
        if guild is None:
            return f"{E_WARN} Не вдалося видати роль: сервер недоступний."

        role_id = int(role_match.group(1))
        member = guild.get_member(winner_id)
        role = guild.get_role(role_id)
        if member and role:
            try:
                await member.add_roles(role, reason="Виграш в аукціоні")
                return f"{E_CHECK} **Видано роль!**"
            except (discord.Forbidden, discord.HTTPException):
                return f"{E_WARN} Помилка видачі ролі (перевірте права бота)."
        return f"{E_WARN} Не вдалося видати роль переможцю."

    await db.inventory.update_one(
        {"guild_id": guild_id, "user_id": winner_id},
        {"$push": {"items": {"type": "auction_lot", "name": lot["name"], "purchased_for": amount}}},
        upsert=True,
    )
    return None


class CustomBidModal(discord.ui.Modal, title="Зробити свою ставку"):
    amount = discord.ui.TextInput(label="Сума ставки", max_length=15)

    def __init__(self, auction_view: "AuctionView"):
        super().__init__()
        self.auction_view = auction_view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            value = int(self.amount.value)
            if value <= 0:
                raise ValueError
        except ValueError:
            return await interaction.response.send_message(
                f"{E_CROSS} Введіть коректне число.",
                ephemeral=True,
            )

        await self.auction_view.process_bid(interaction, value)


class AuctionView(discord.ui.View):
    def __init__(self, manager: "AuctionManager", guild_id: int, lot: dict, eco: dict, *, state: dict | None = None):
        super().__init__(timeout=None)
        self.manager = manager
        self.guild_id = guild_id
        self.lot = lot
        self.eco = eco
        self.lock = asyncio.Lock()

        self.current_bid = state.get("current_bid", lot["start_bid"]) if state else lot["start_bid"]
        self.highest_bidder = state.get("highest_bidder") if state else None
        self.end_time = state.get("end_time", time.time() + lot["duration"]) if state else time.time() + lot["duration"]
        self.anti_snipe = state.get("anti_snipe", eco.get("auction_anti_snipe_seconds", 30)) if state else eco.get("auction_anti_snipe_seconds", 30)

    async def process_bid(self, interaction: discord.Interaction, bid_amount: int):
        user_id = interaction.user.id

        async with self.lock:
            now = time.time()
            if now > self.end_time:
                return await interaction.response.send_message(f"{E_CROSS} Аукціон уже завершено!", ephemeral=True)

            if self.highest_bidder is None and bid_amount < self.current_bid:
                return await interaction.response.send_message(
                    f"{E_CROSS} Початкова ставка: `{self.current_bid:,}` {_curr(self.eco)}!",
                    ephemeral=True,
                )

            if self.highest_bidder is not None and bid_amount <= self.current_bid:
                return await interaction.response.send_message(
                    f"{E_CROSS} Ваша ставка має бути більшою за `{self.current_bid:,}` {_curr(self.eco)}!",
                    ephemeral=True,
                )

            if self.highest_bidder == user_id:
                return await interaction.response.send_message(f"{E_CROSS} Ваша ставка вже найвища!", ephemeral=True)

            user_doc = await db.users.find_one(
                {"guild_id": self.guild_id, "user_id": user_id},
                {"wallet": 1, "bank": 1},
            ) or {}
            bank = user_doc.get("bank", 0)
            wallet = user_doc.get("wallet", 0)
            if bank + wallet < bid_amount:
                return await interaction.response.send_message(
                    f"{E_CROSS} У вас недостатньо коштів! (Готівка + Банк: {bank + wallet:,})",
                    ephemeral=True,
                )

            if not await _hold_bid_amount(self.guild_id, user_id, bid_amount):
                return await interaction.response.send_message(
                    f"{E_CROSS} Не вдалося зафіксувати ставку. Баланс уже змінився або виконується інша транзакція.",
                    ephemeral=True,
                )

            previous_bidder = self.highest_bidder
            previous_bid = self.current_bid if previous_bidder else 0
            extended_end_time = self.end_time
            time_left = extended_end_time - now
            if time_left < self.anti_snipe and self.anti_snipe > 0:
                extended_end_time += self.anti_snipe

            try:
                updated = await self.manager.persist_bid_state(
                    self.guild_id,
                    bid_amount=bid_amount,
                    highest_bidder=user_id,
                    end_time=extended_end_time,
                )
            except Exception:
                updated = False

            if not updated:
                await _refund_reserved_bid(self.guild_id, user_id, bid_amount)
                return await interaction.response.send_message(
                    f"{E_CROSS} Не вдалося оновити стан аукціону. Ставку скасовано.",
                    ephemeral=True,
                )

            self.current_bid = bid_amount
            self.highest_bidder = user_id
            self.end_time = extended_end_time

            if previous_bidder:
                await _refund_reserved_bid(self.guild_id, previous_bidder, previous_bid)

        await interaction.response.send_message(
            f"{E_CHECK} Ви успішно поставили **{bid_amount:,}** {_curr(self.eco)}!",
            ephemeral=True,
        )

    @discord.ui.button(label="+100", style=discord.ButtonStyle.primary, custom_id="auc_plus_100")
    async def btn_plus_100(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self.process_bid(interaction, self.current_bid + 100)

    @discord.ui.button(label="+1,000", style=discord.ButtonStyle.primary, custom_id="auc_plus_1000")
    async def btn_plus_1000(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self.process_bid(interaction, self.current_bid + 1000)

    @discord.ui.button(label="+5,000", style=discord.ButtonStyle.primary, custom_id="auc_plus_5000")
    async def btn_plus_5000(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self.process_bid(interaction, self.current_bid + 5000)

    @discord.ui.button(
        label="Власна ставка",
        style=discord.ButtonStyle.success,
        emoji=discord.PartialEmoji.from_str(E_EDIT),
        custom_id="auc_custom",
    )
    async def btn_custom(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.send_modal(CustomBidModal(self))


class AuctionManager:
    def __init__(self, bot):
        self.bot = bot
        self.active_auctions: dict[int, dict] = {}
        self._initialized = False
        self._init_lock = asyncio.Lock()

    async def initialize(self) -> None:
        if self._initialized:
            return

        async with self._init_lock:
            if self._initialized:
                return

            await self._recover_active_auctions()
            self._initialized = True

    async def start_auction(self, guild_id: int, lot: dict, channel: discord.TextChannel, eco: dict):
        await self.initialize()

        if guild_id in self.active_auctions:
            return False, "На цьому сервері вже йде аукціон."

        if await ACTIVE_AUCTIONS.find_one({"_id": guild_id}):
            return False, "У базі вже є активний аукціон для цього сервера. Перезапустіть менеджер або дочекайтесь recovery."

        view = AuctionView(self, guild_id, lot, eco)
        embed = self._build_embed(lot, view, eco)
        message = await channel.send(embed=embed, view=view)

        try:
            await ACTIVE_AUCTIONS.insert_one(
                {
                    "_id": guild_id,
                    "guild_id": guild_id,
                    "lot": lot,
                    "channel_id": channel.id,
                    "message_id": message.id,
                    "current_bid": view.current_bid,
                    "highest_bidder": view.highest_bidder,
                    "end_time": view.end_time,
                    "anti_snipe": view.anti_snipe,
                    "started_at": int(time.time()),
                }
            )
        except DuplicateKeyError:
            try:
                await message.delete()
            except discord.HTTPException:
                pass
            return False, "Активний аукціон уже існує."

        self.bot.add_view(view, message_id=message.id)
        task = self.bot.loop.create_task(self._auction_loop(guild_id, message, view, eco))
        self.active_auctions[guild_id] = {
            "task": task,
            "message": message,
            "view": view,
        }
        return True, "Аукціон запущено."

    async def persist_bid_state(self, guild_id: int, *, bid_amount: int, highest_bidder: int, end_time: float) -> bool:
        result = await ACTIVE_AUCTIONS.update_one(
            {"_id": guild_id},
            {"$set": {"current_bid": bid_amount, "highest_bidder": highest_bidder, "end_time": end_time}},
        )
        return result.matched_count == 1

    def _build_embed(self, lot: dict, view: AuctionView, eco: dict) -> discord.Embed:
        curr = _curr(eco)
        embed = discord.Embed(
            title=f"{E_AUCTION} Аукціон: {lot['name']}",
            description=f"**Опис:**\n{lot.get('desc', 'Немає')}",
            color=0x1A1A2E,
        )
        embed.add_field(name="Лідируюча ставка", value=f"`{view.current_bid:,}` {curr}", inline=True)

        bidder_text = f"<@{view.highest_bidder}>" if view.highest_bidder else "*Немає ставок*"
        embed.add_field(name="Лідер", value=bidder_text, inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=False)
        embed.add_field(
            name=f"{E_CLOCK} Залишилось",
            value=f"<t:{int(view.end_time)}:R> (<t:{int(view.end_time)}:T>)",
            inline=True,
        )
        return embed

    async def _recover_active_auctions(self) -> None:
        docs = await ACTIVE_AUCTIONS.find({}).to_list(length=None)
        for doc in docs:
            await self._recover_single_auction(doc)

    async def _recover_single_auction(self, doc: dict) -> None:
        guild_id = doc["guild_id"]
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            await self._close_dangling_auction(doc, refund=True)
            return

        settings = await get_guild_settings(db, guild_id)
        eco = get_eco(settings)
        channel = guild.get_channel(doc["channel_id"])
        if channel is None or not isinstance(channel, discord.TextChannel):
            await self._close_dangling_auction(doc, refund=True)
            return

        try:
            message = await channel.fetch_message(doc["message_id"])
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            if doc["end_time"] <= time.time():
                await self._settle_without_message(guild, doc, eco)
            else:
                await self._close_dangling_auction(doc, refund=True)
            return

        view = AuctionView(self, guild_id, doc["lot"], eco, state=doc)
        self.bot.add_view(view, message_id=message.id)
        if doc["end_time"] <= time.time():
            task = self.bot.loop.create_task(self._finish_auction(guild_id, message, view, eco))
        else:
            task = self.bot.loop.create_task(self._auction_loop(guild_id, message, view, eco))

        self.active_auctions[guild_id] = {
            "task": task,
            "message": message,
            "view": view,
        }

    async def _close_dangling_auction(self, doc: dict, *, refund: bool) -> None:
        if refund and doc.get("highest_bidder") and doc.get("current_bid", 0) > 0:
            await _refund_reserved_bid(doc["guild_id"], doc["highest_bidder"], doc["current_bid"])
        await ACTIVE_AUCTIONS.delete_one({"_id": doc["_id"]})

    async def _settle_without_message(self, guild: discord.Guild, doc: dict, eco: dict) -> None:
        highest_bidder = doc.get("highest_bidder")
        current_bid = doc.get("current_bid", 0)
        lot = doc["lot"]

        if highest_bidder:
            summary = await _award_lot(doc["guild_id"], guild, lot, highest_bidder, current_bid)
            channel = guild.get_channel(doc["channel_id"])
            if isinstance(channel, discord.TextChannel):
                embed = discord.Embed(
                    title=f"{E_CHECK} Аукціон завершено: {lot['name']}",
                    description=(
                        f"<:celebration_Confetti:1485626240734855441> Переможець: <@{highest_bidder}>\n"
                        f"<:coins:1485612564619727011> Фінальна ставка: `{current_bid:,}` {_curr(eco)}"
                    ),
                    color=discord.Color.green(),
                )
                if summary:
                    embed.description += f"\n\n{summary}"
                try:
                    await channel.send(embed=embed)
                except (discord.Forbidden, discord.HTTPException):
                    pass

        await ACTIVE_AUCTIONS.delete_one({"_id": doc["_id"]})

    async def _auction_loop(self, guild_id: int, message: discord.Message, view: AuctionView, eco: dict):
        last_update = time.time()
        try:
            while time.time() < view.end_time:
                if time.time() - last_update >= 5:
                    try:
                        await message.edit(embed=self._build_embed(view.lot, view, eco), view=view)
                        last_update = time.time()
                    except discord.NotFound:
                        await self._close_dangling_auction(
                            {
                                "_id": guild_id,
                                "guild_id": guild_id,
                                "highest_bidder": view.highest_bidder,
                                "current_bid": view.current_bid,
                            },
                            refund=True,
                        )
                        return
                    except Exception:
                        pass
                await asyncio.sleep(1)

            await self._finish_auction(guild_id, message, view, eco)
        except asyncio.CancelledError:
            pass
        finally:
            self.active_auctions.pop(guild_id, None)

    async def _finish_auction(self, guild_id: int, message: discord.Message, view: AuctionView, eco: dict):
        try:
            for child in view.children:
                child.disabled = True

            embed = self._build_embed(view.lot, view, eco)
            embed.clear_fields()

            if view.highest_bidder:
                amount = view.current_bid
                embed.title = f"{E_CHECK} Аукціон завершено: {view.lot['name']}"
                embed.color = discord.Color.green()
                embed.description = (
                    f"<:celebration_Confetti:1485626240734855441> Переможець: <@{view.highest_bidder}>\n"
                    f"<:coins:1485612564619727011> Фінальна ставка: `{amount:,}` {_curr(eco)}\n\n"
                    "*Перевірте свій інвентар або ролі!*"
                )
                summary = await _award_lot(guild_id, message.guild, view.lot, view.highest_bidder, amount)
                if summary:
                    embed.description += f"\n\n{summary}"
            else:
                embed.title = f"{E_CROSS} Аукціон завершено: {view.lot['name']}"
                embed.color = discord.Color.red()
                embed.description = "Ставок не було. Лот ніхто не купив."

            await message.edit(embed=embed, view=view)
        except Exception:
            pass
        finally:
            await ACTIVE_AUCTIONS.delete_one({"_id": guild_id})


auction_manager = None


def setup_auction_manager(bot):
    global auction_manager
    if auction_manager is None:
        auction_manager = AuctionManager(bot)
    return auction_manager
