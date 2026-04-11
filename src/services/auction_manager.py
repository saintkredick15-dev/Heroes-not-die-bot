from __future__ import annotations

import asyncio
import time

import discord
from pymongo.errors import DuplicateKeyError

from commands.administration.economy_setup_shared import fmt_duration, get_eco, normalize_currency_emoji
from config.constants import Emojis
from modules.db import get_database, get_guild_settings, invalidate_user_data
from services.auction_support import (
    get_auction_min_increment,
    get_auction_step_presets,
    lot_plain_label,
    lot_public_label,
    normalize_active_auction_doc,
    normalize_auction_lot,
)

db = get_database()

E_COIN = Emojis.COIN.value
E_AUCTION = Emojis.AUCTION.value
E_CLOCK = Emojis.CLOCK.value
E_CHECK = Emojis.CHECK.value
E_CROSS = Emojis.CANCEL.value
E_EDIT = Emojis.EDIT.value
E_WARN = Emojis.WARN.value
E_CLIPBOARD = Emojis.CLIPBOARD.value

ACTIVE_AUCTIONS = db.active_auctions
AUCTION_HISTORY = db.auction_history


def _curr(eco: dict) -> str:
    return normalize_currency_emoji(eco.get("currency_emoji") or Emojis.COIN.value)


def _allowed_mentions() -> discord.AllowedMentions:
    return discord.AllowedMentions.none()


def _history_status_label(status: str) -> str:
    return {
        "finished": "Завершено",
        "force_finished": "Завершено достроково",
        "cancelled": "Скасовано",
    }.get(status, status)


def _bid_source_label(source: str) -> str:
    return {
        "button": "кнопка",
        "custom": "власна ставка",
        "recover": "recovery",
    }.get(source, source)


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
    lot = normalize_auction_lot(lot)

    if lot["type"] == "role" and lot.get("role_id"):
        if guild is None:
            return f"{E_WARN} Не вдалося видати роль: сервер недоступний."

        role = guild.get_role(lot["role_id"])
        member = guild.get_member(winner_id)
        if not role or not member:
            return f"{E_WARN} Не вдалося видати роль переможцю. Перевірте роль або учасника."
        try:
            await member.add_roles(role, reason="Виграш в аукціоні")
            return f"{E_CHECK} Лот видано: {role.mention}"
        except (discord.Forbidden, discord.HTTPException):
            return f"{E_WARN} Бот не зміг видати роль. Перевірте права та ієрархію ролей."

    await db.inventory.update_one(
        {"guild_id": guild_id, "user_id": winner_id},
        {"$push": {"items": {"type": "auction_lot", "name": lot["title"], "purchased_for": amount}}},
        upsert=True,
    )
    return None


class CustomBidModal(discord.ui.Modal, title="Власна ставка"):
    amount = discord.ui.TextInput(label="Сума ставки", max_length=15)

    def __init__(self, auction_view: "AuctionView"):
        super().__init__()
        self.auction_view = auction_view
        self.amount.placeholder = f"Мінімум {auction_view.min_valid_bid():,}"

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

        await self.auction_view.process_bid(interaction, value, source="custom")


class AuctionView(discord.ui.View):
    def __init__(self, manager: "AuctionManager", guild_id: int, lot: dict, eco: dict, *, state: dict | None = None):
        super().__init__(timeout=None)
        self.manager = manager
        self.guild_id = guild_id
        self.eco = eco
        self.lock = asyncio.Lock()
        self.closed = False

        normalized_state = normalize_active_auction_doc(state, eco) if state else None
        self.lot = normalize_auction_lot(normalized_state.get("lot_snapshot") if normalized_state else lot)
        self.current_bid = normalized_state.get("current_bid", self.lot["start_bid"]) if normalized_state else self.lot["start_bid"]
        self.highest_bidder = normalized_state.get("highest_bidder") if normalized_state else None
        self.end_time = normalized_state.get("end_time", time.time() + self.lot["duration_seconds"]) if normalized_state else time.time() + self.lot["duration_seconds"]
        self.anti_snipe = normalized_state.get("anti_snipe", eco.get("auction_anti_snipe_seconds", 30)) if normalized_state else eco.get("auction_anti_snipe_seconds", 30)
        self.min_increment = normalized_state.get("min_increment", get_auction_min_increment(eco)) if normalized_state else get_auction_min_increment(eco)
        self.started_at = normalized_state.get("started_at", int(time.time())) if normalized_state else int(time.time())
        self.started_by = normalized_state.get("started_by", 0) if normalized_state else 0
        self.bid_history = list(normalized_state.get("bid_history", [])) if normalized_state else []
        self.step_presets = get_auction_step_presets(eco)
        self._bind_buttons()

    def _bind_buttons(self) -> None:
        for index, step in enumerate(self.step_presets):
            button = discord.ui.Button(
                label=f"+{step:,}",
                style=discord.ButtonStyle.secondary,
                custom_id=f"auc_step_{index}",
            )

            async def _callback(interaction: discord.Interaction, amount: int = step):
                await self.process_bid(interaction, self.current_bid + amount, source="button")

            button.callback = _callback
            self.add_item(button)

        custom_button = discord.ui.Button(
            label="Власна ставка",
            style=discord.ButtonStyle.secondary,
            emoji=discord.PartialEmoji.from_str(E_EDIT),
            custom_id="auc_custom",
        )
        custom_button.callback = self.btn_custom
        self.add_item(custom_button)

    def min_valid_bid(self) -> int:
        return self.lot["start_bid"] if self.highest_bidder is None else self.current_bid + self.min_increment

    async def refresh_message(self) -> None:
        runtime = self.manager.active_auctions.get(self.guild_id)
        if not runtime:
            return
        try:
            await runtime["message"].edit(
                embed=self.manager.build_live_embed(self.lot, self, self.eco),
                view=self,
                allowed_mentions=_allowed_mentions(),
            )
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return

    async def process_bid(self, interaction: discord.Interaction, bid_amount: int, *, source: str):
        user_id = interaction.user.id

        async with self.lock:
            if self.closed:
                return await interaction.response.send_message(f"{E_CROSS} Аукціон уже завершено.", ephemeral=True)

            now = time.time()
            if now > self.end_time:
                return await interaction.response.send_message(f"{E_CROSS} Аукціон уже завершено.", ephemeral=True)

            min_valid = self.min_valid_bid()
            if bid_amount < min_valid:
                return await interaction.response.send_message(
                    f"{E_CROSS} Мінімальна допустима ставка зараз: `{min_valid:,}` {_curr(self.eco)}.",
                    ephemeral=True,
                )

            if self.highest_bidder == user_id:
                return await interaction.response.send_message(f"{E_CROSS} Ваша ставка вже найвища.", ephemeral=True)

            user_doc = await db.users.find_one(
                {"guild_id": self.guild_id, "user_id": user_id},
                {"wallet": 1, "bank": 1},
            ) or {}
            bank = user_doc.get("bank", 0)
            wallet = user_doc.get("wallet", 0)
            if bank + wallet < bid_amount:
                return await interaction.response.send_message(
                    f"{E_CROSS} Недостатньо коштів. Доступно: `{bank + wallet:,}` {_curr(self.eco)}.",
                    ephemeral=True,
                )

            if not await _hold_bid_amount(self.guild_id, user_id, bid_amount):
                return await interaction.response.send_message(
                    f"{E_CROSS} Не вдалося зафіксувати ставку. Баланс уже змінився або виконується інша операція.",
                    ephemeral=True,
                )

            previous_bidder = self.highest_bidder
            previous_bid = self.current_bid if previous_bidder else 0
            extended_end_time = self.end_time
            time_left = extended_end_time - now
            if self.anti_snipe > 0 and time_left < self.anti_snipe:
                extended_end_time += self.anti_snipe

            bid_entry = {
                "user_id": user_id,
                "amount": bid_amount,
                "timestamp": int(now),
                "source": source,
            }

            try:
                updated = await self.manager.persist_bid_state(
                    self.guild_id,
                    bid_amount=bid_amount,
                    highest_bidder=user_id,
                    end_time=extended_end_time,
                    bid_entry=bid_entry,
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
            self.bid_history.append(bid_entry)

            if previous_bidder:
                await _refund_reserved_bid(self.guild_id, previous_bidder, previous_bid)

        await interaction.response.send_message(
            f"{E_CHECK} Ставку ` {bid_amount:,} ` {_curr(self.eco)} зафіксовано. "
            f"Наступний мінімум: `{self.min_valid_bid():,}` {_curr(self.eco)}.",
            ephemeral=True,
        )
        await self.refresh_message()

    async def btn_custom(self, interaction: discord.Interaction):
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

    async def start_auction(self, guild_id: int, lot: dict, channel: discord.TextChannel, eco: dict, *, started_by: int = 0):
        await self.initialize()

        if guild_id in self.active_auctions:
            return False, "На цьому сервері вже йде аукціон."

        if await ACTIVE_AUCTIONS.find_one({"_id": guild_id}):
            return False, "У базі вже є активний аукціон для цього сервера. Дочекайтеся recovery."

        normalized_lot = normalize_auction_lot(lot)
        min_increment = get_auction_min_increment(eco)
        state = {
            "lot_snapshot": normalized_lot,
            "current_bid": normalized_lot["start_bid"],
            "highest_bidder": None,
            "end_time": time.time() + normalized_lot["duration_seconds"],
            "anti_snipe": eco.get("auction_anti_snipe_seconds", 30),
            "min_increment": min_increment,
            "started_at": int(time.time()),
            "started_by": started_by,
            "bid_history": [],
        }
        view = AuctionView(self, guild_id, normalized_lot, eco, state=state)
        embed = self.build_live_embed(normalized_lot, view, eco)
        message = await channel.send(embed=embed, view=view, allowed_mentions=_allowed_mentions())

        try:
            await ACTIVE_AUCTIONS.insert_one(
                {
                    "_id": guild_id,
                    "guild_id": guild_id,
                    "lot_snapshot": normalized_lot,
                    "channel_id": channel.id,
                    "message_id": message.id,
                    "current_bid": view.current_bid,
                    "highest_bidder": view.highest_bidder,
                    "end_time": view.end_time,
                    "anti_snipe": view.anti_snipe,
                    "min_increment": min_increment,
                    "bid_history": [],
                    "started_at": view.started_at,
                    "started_by": started_by,
                    "status": "live",
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
        self.active_auctions[guild_id] = {"task": task, "message": message, "view": view}
        return True, "Аукціон запущено."

    async def persist_bid_state(
        self,
        guild_id: int,
        *,
        bid_amount: int,
        highest_bidder: int,
        end_time: float,
        bid_entry: dict,
    ) -> bool:
        result = await ACTIVE_AUCTIONS.update_one(
            {"_id": guild_id},
            {
                "$set": {
                    "current_bid": bid_amount,
                    "highest_bidder": highest_bidder,
                    "end_time": end_time,
                },
                "$push": {"bid_history": bid_entry},
            },
        )
        return result.matched_count == 1

    def build_live_embed(self, lot: dict, view: AuctionView, eco: dict) -> discord.Embed:
        curr = _curr(eco)
        label = lot_public_label(lot)
        bidder_text = f"<@{view.highest_bidder}>" if view.highest_bidder else "Ще немає ставок"
        bids_count = len(view.bid_history)
        embed = discord.Embed(
            title=f"{E_AUCTION} Аукціон: {lot['title']}",
            description=(
                f"**Лот:** {label}\n"
                f"**Опис:** {lot.get('description', 'Опис відсутній.')}\n\n"
                f"Переможець отримає: {label}"
            ),
            color=0x2B2D31,
        )
        embed.add_field(name="Поточна ставка", value=f"`{view.current_bid:,}` {curr}", inline=True)
        embed.add_field(name="Лідер", value=bidder_text, inline=True)
        embed.add_field(name="Мін. наступна", value=f"`{view.min_valid_bid():,}` {curr}", inline=True)
        embed.add_field(name=f"{E_CLOCK} Залишилось", value=f"<t:{int(view.end_time)}:R> • <t:{int(view.end_time)}:T>", inline=True)
        embed.add_field(name="Ставок", value=f"`{bids_count}`", inline=True)
        embed.add_field(
            name="Крок ставки",
            value=f"мінімум `+{view.min_increment:,}` • кнопки {' / '.join(f'+{step:,}' for step in view.step_presets)}",
            inline=True,
        )
        embed.set_footer(text="Кнопки нижче підвищують ставку. Власна ставка дозволяє ввести суму вручну.")
        return embed

    def build_summary_embed(self, lot: dict, eco: dict, *, winner_id: int | None, final_price: int, bids_count: int, status: str, note: str | None = None) -> discord.Embed:
        curr = _curr(eco)
        label = lot_public_label(lot)
        if status == "cancelled":
            title = f"{E_CROSS} Аукціон скасовано: {lot['title']}"
            description = (
                f"**Лот:** {label}\n"
                "Торги зупинено адміністратором.\n"
                "Активну ставку повернуто, лот не видано."
            )
            color = discord.Color.orange()
        elif winner_id:
            title = f"{E_CHECK} Аукціон завершено: {lot['title']}"
            description = (
                f"**Лот:** {label}\n"
                f"**Переможець:** <@{winner_id}>\n"
                f"**Фінальна ставка:** `{final_price:,}` {curr}\n"
                f"**Ставок:** `{bids_count}`\n"
                f"**Статус:** {_history_status_label(status)}"
            )
            color = discord.Color.green()
        else:
            title = f"{E_CROSS} Аукціон завершено: {lot['title']}"
            description = (
                f"**Лот:** {label}\n"
                "Ставок не було. Лот залишився без переможця."
            )
            color = discord.Color.red()

        embed = discord.Embed(title=title, description=description, color=color)
        if note:
            embed.add_field(name="Підсумок", value=note, inline=False)
        embed.set_footer(text="Публічний підсумок аукціону")
        return embed

    async def fetch_active_doc(self, guild_id: int) -> dict | None:
        settings = await get_guild_settings(db, guild_id)
        eco = get_eco(settings)
        doc = await ACTIVE_AUCTIONS.find_one({"_id": guild_id})
        return normalize_active_auction_doc(doc, eco) if doc else None

    async def fetch_recent_history(self, guild_id: int, *, limit: int = 5) -> list[dict]:
        docs = await AUCTION_HISTORY.find({"guild_id": guild_id}).sort("ended_at", -1).limit(limit).to_list(length=limit)
        return docs

    async def cancel_auction(self, guild_id: int, *, cancelled_by: int) -> tuple[bool, str]:
        runtime, doc, eco = await self._ensure_runtime(guild_id)
        if not runtime or not doc:
            return False, "Активного аукціону зараз немає."

        runtime["task"].cancel()
        await self._finalize_auction(
            guild_id,
            runtime["message"],
            runtime["view"],
            eco,
            status="cancelled",
            actor_id=cancelled_by,
        )
        return True, "Аукціон скасовано."

    async def force_finish_auction(self, guild_id: int, *, forced_by: int) -> tuple[bool, str]:
        runtime, doc, eco = await self._ensure_runtime(guild_id)
        if not runtime or not doc:
            return False, "Активного аукціону зараз немає."
        if not runtime["view"].highest_bidder:
            return False, "Force finish недоступний, поки немає жодної ставки."

        runtime["task"].cancel()
        await self._finalize_auction(
            guild_id,
            runtime["message"],
            runtime["view"],
            eco,
            status="force_finished",
            actor_id=forced_by,
        )
        return True, "Аукціон завершено достроково."

    async def _ensure_runtime(self, guild_id: int) -> tuple[dict | None, dict | None, dict | None]:
        await self.initialize()
        runtime = self.active_auctions.get(guild_id)
        settings = await get_guild_settings(db, guild_id)
        eco = get_eco(settings)
        doc = await ACTIVE_AUCTIONS.find_one({"_id": guild_id})
        if doc and not runtime:
            await self._recover_single_auction(doc)
            runtime = self.active_auctions.get(guild_id)
        return runtime, normalize_active_auction_doc(doc, eco) if doc else None, eco

    async def _archive_history(self, history_doc: dict) -> None:
        await AUCTION_HISTORY.insert_one(history_doc)

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
        normalized_doc = normalize_active_auction_doc(doc, eco)
        channel = guild.get_channel(normalized_doc["channel_id"])
        if channel is None or not isinstance(channel, discord.TextChannel):
            await self._close_dangling_auction(normalized_doc, refund=True)
            return

        try:
            message = await channel.fetch_message(normalized_doc["message_id"])
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            if normalized_doc["end_time"] <= time.time():
                await self._settle_without_message(guild, normalized_doc, eco)
            else:
                await self._close_dangling_auction(normalized_doc, refund=True)
            return

        view = AuctionView(self, guild_id, normalized_doc["lot_snapshot"], eco, state=normalized_doc)
        self.bot.add_view(view, message_id=message.id)
        if normalized_doc["end_time"] <= time.time():
            task = self.bot.loop.create_task(self._finish_auction(guild_id, message, view, eco))
        else:
            task = self.bot.loop.create_task(self._auction_loop(guild_id, message, view, eco))

        self.active_auctions[guild_id] = {"task": task, "message": message, "view": view}

    async def _close_dangling_auction(self, doc: dict, *, refund: bool) -> None:
        if refund and doc.get("highest_bidder") and doc.get("current_bid", 0) > 0:
            await _refund_reserved_bid(doc["guild_id"], doc["highest_bidder"], doc["current_bid"])
        await ACTIVE_AUCTIONS.delete_one({"_id": doc["_id"]})

    async def _settle_without_message(self, guild: discord.Guild, doc: dict, eco: dict) -> None:
        winner_id = doc.get("highest_bidder")
        final_price = doc.get("current_bid", 0) if winner_id else 0
        note = None
        if winner_id:
            note = await _award_lot(doc["guild_id"], guild, doc["lot_snapshot"], winner_id, final_price)

        history_doc = {
            "guild_id": doc["guild_id"],
            "lot_snapshot": doc["lot_snapshot"],
            "status": "finished",
            "winner_id": winner_id,
            "final_price": final_price,
            "bids_count": len(doc.get("bid_history", [])),
            "bid_history": doc.get("bid_history", []),
            "started_at": doc.get("started_at", 0),
            "ended_at": int(time.time()),
            "channel_id": doc.get("channel_id"),
            "message_id": doc.get("message_id"),
            "started_by": doc.get("started_by", 0),
            "ended_by": 0,
            "min_increment": doc.get("min_increment", get_auction_min_increment(eco)),
            "anti_snipe": doc.get("anti_snipe", eco.get("auction_anti_snipe_seconds", 30)),
        }
        await self._archive_history(history_doc)

        channel = guild.get_channel(doc["channel_id"])
        if isinstance(channel, discord.TextChannel):
            embed = self.build_summary_embed(
                doc["lot_snapshot"],
                eco,
                winner_id=winner_id,
                final_price=final_price,
                bids_count=len(doc.get("bid_history", [])),
                status="finished",
                note=note,
            )
            try:
                await channel.send(embed=embed, allowed_mentions=_allowed_mentions())
            except (discord.Forbidden, discord.HTTPException):
                pass

        await ACTIVE_AUCTIONS.delete_one({"_id": doc["_id"]})

    async def _auction_loop(self, guild_id: int, message: discord.Message, view: AuctionView, eco: dict):
        last_update = time.time()
        try:
            while time.time() < view.end_time and not view.closed:
                if time.time() - last_update >= 5:
                    try:
                        await message.edit(
                            embed=self.build_live_embed(view.lot, view, eco),
                            view=view,
                            allowed_mentions=_allowed_mentions(),
                        )
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

            if not view.closed:
                await self._finish_auction(guild_id, message, view, eco)
        except asyncio.CancelledError:
            pass
        finally:
            self.active_auctions.pop(guild_id, None)

    async def _finalize_auction(
        self,
        guild_id: int,
        message: discord.Message,
        view: AuctionView,
        eco: dict,
        *,
        status: str,
        actor_id: int,
    ) -> None:
        if view.closed:
            return

        view.closed = True
        for child in view.children:
            child.disabled = True

        winner_id = view.highest_bidder if status in {"finished", "force_finished"} else None
        final_price = view.current_bid if winner_id else 0
        note = None

        if status == "cancelled" and view.highest_bidder:
            await _refund_reserved_bid(guild_id, view.highest_bidder, view.current_bid)
            note = "Останню активну ставку повернуто лідеру."
        elif winner_id:
            note = await _award_lot(guild_id, message.guild, view.lot, winner_id, final_price)

        history_doc = {
            "guild_id": guild_id,
            "lot_snapshot": view.lot,
            "status": status,
            "winner_id": winner_id,
            "final_price": final_price,
            "bids_count": len(view.bid_history),
            "bid_history": list(view.bid_history),
            "started_at": view.started_at,
            "ended_at": int(time.time()),
            "channel_id": message.channel.id,
            "message_id": message.id,
            "started_by": view.started_by,
            "ended_by": actor_id,
            "min_increment": view.min_increment,
            "anti_snipe": view.anti_snipe,
        }
        await self._archive_history(history_doc)

        embed = self.build_summary_embed(
            view.lot,
            eco,
            winner_id=winner_id,
            final_price=final_price,
            bids_count=len(view.bid_history),
            status=status,
            note=note,
        )

        try:
            await message.edit(embed=embed, view=view, allowed_mentions=_allowed_mentions())
        except Exception:
            pass
        finally:
            await ACTIVE_AUCTIONS.delete_one({"_id": guild_id})

    async def _finish_auction(self, guild_id: int, message: discord.Message, view: AuctionView, eco: dict):
        await self._finalize_auction(guild_id, message, view, eco, status="finished", actor_id=0)


auction_manager = None


def setup_auction_manager(bot):
    global auction_manager
    if auction_manager is None:
        auction_manager = AuctionManager(bot)
    return auction_manager
