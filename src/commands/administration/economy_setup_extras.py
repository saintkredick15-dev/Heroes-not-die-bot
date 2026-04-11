from __future__ import annotations

import time
import uuid

import discord

from commands.administration.economy_setup_shared import (
    CANONICAL_COIN,
    EMBED_COLOR,
    E_AUCTION,
    E_BOOST,
    E_CHECK,
    E_CLIPBOARD,
    E_CROSS,
    E_LEFT,
    E_MEDAL,
    E_ROLE,
    E_STAR,
    E_TROPHY,
    E_TRASH,
    db,
    build_category_embed,
    fmt_duration,
    get_eco,
    normalize_currency_emoji,
    parse_duration,
    save_eco,
)
from services.auction_manager import AUCTION_HISTORY, ACTIVE_AUCTIONS, setup_auction_manager
from services.auction_support import (
    get_auction_min_increment,
    get_auction_step_presets,
    lot_plain_label,
    lot_preview_text,
    lot_public_label,
    normalize_active_auction_doc,
    normalize_auction_lot,
    normalize_auction_queue,
)


def _setup_category_view(main_view, category: str):
    from commands.administration.economy_setup import SetupCategoryView

    return SetupCategoryView(main_view, category)


def _bid_source_label(source: str) -> str:
    return {
        "button": "кнопка",
        "custom": "власна ставка",
        "recover": "відновлення",
    }.get(source, source)


def _history_status_label(status: str) -> str:
    return {
        "finished": "Завершено",
        "force_finished": "Завершено достроково",
        "cancelled": "Скасовано",
    }.get(status, status)


class SeasonAnnounceChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, main_view, eco: dict):
        self.main_view = main_view
        cur = eco.get("season_announce_channel_id", 0)
        defaults = [discord.Object(id=cur)] if cur else []
        super().__init__(
            placeholder="Канал для анонсу кінця сезону...",
            channel_types=[discord.ChannelType.text],
            min_values=0,
            max_values=1,
            default_values=defaults,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        ch_id = self.values[0].id if self.values else 0
        await save_eco(interaction.guild.id, {"economy.season_announce_channel_id": ch_id})
        ctx = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
        self.main_view.eco = get_eco(ctx)
        await interaction.response.edit_message(
            embed=build_category_embed(self.main_view.eco, "season"),
            view=_setup_category_view(self.main_view, "season"),
        )


class SeasonRolePositionSelect(discord.ui.Select):
    def __init__(self, main_view, eco: dict):
        self.main_view = main_view
        self.eco = eco
        winner_roles = eco.get("season_winner_roles", {})
        opts = []
        labels = {
            "1": f"{E_TROPHY} 1 місце",
            "2": f"{E_MEDAL} 2 місце",
            "3": f"{E_STAR} 3 місце",
            "4": "4 місце",
            "5": "5 місце",
        }
        for pos, label in labels.items():
            rid = winner_roles.get(pos)
            desc = f"Роль: <@&{rid}>" if rid else "Не та встановлено"
            opts.append(discord.SelectOption(label=label, value=pos, description=desc[:50]))
        super().__init__(placeholder="Обери позицію для призначення ролі...", options=opts, row=1)

    async def callback(self, interaction: discord.Interaction):
        position = self.values[0]
        await interaction.response.edit_message(
            embed=discord.Embed(
                title=f"{E_TROPHY} Роль для {position} місця",
                description="Виберіть роль нижче. Натисніть 'Очистити' щоб прибрати роль.",
                color=EMBED_COLOR,
            ),
            view=SeasonRolePickerView(self.main_view, self.eco, position),
        )


class SeasonRolePickerView(discord.ui.View):
    def __init__(self, main_view, eco: dict, position: str):
        super().__init__(timeout=120)
        self.main_view = main_view
        self.eco = eco
        self.position = position
        self.add_item(SeasonRoleSelect(main_view, eco, position))

    @discord.ui.button(label="Назад", emoji=discord.PartialEmoji.from_str(E_LEFT), style=discord.ButtonStyle.secondary, row=1)
    async def back_btn(self, interaction: discord.Interaction, _):
        ctx = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
        self.main_view.eco = get_eco(ctx)
        await interaction.response.edit_message(
            embed=build_category_embed(self.main_view.eco, "season"),
            view=_setup_category_view(self.main_view, "season"),
        )

    @discord.ui.button(label="Очистити роль", emoji=discord.PartialEmoji.from_str(E_CROSS), style=discord.ButtonStyle.danger, row=1)
    async def clear_btn(self, interaction: discord.Interaction, _):
        winner_roles = self.eco.get("season_winner_roles", {})
        winner_roles.pop(self.position, None)
        await save_eco(interaction.guild.id, {"economy.season_winner_roles": winner_roles})
        ctx = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
        self.main_view.eco = get_eco(ctx)
        await interaction.response.edit_message(
            embed=build_category_embed(self.main_view.eco, "season"),
            view=_setup_category_view(self.main_view, "season"),
        )


class SeasonRoleSelect(discord.ui.RoleSelect):
    def __init__(self, main_view, eco: dict, position: str):
        self.main_view = main_view
        self.eco = eco
        self.position = position
        super().__init__(placeholder=f"Роль для {position} місця...", min_values=1, max_values=1, row=0)

    async def callback(self, interaction: discord.Interaction):
        winner_roles = self.eco.get("season_winner_roles", {})
        winner_roles[self.position] = self.values[0].id
        await save_eco(interaction.guild.id, {"economy.season_winner_roles": winner_roles})
        ctx = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
        self.main_view.eco = get_eco(ctx)
        await interaction.response.edit_message(
            embed=build_category_embed(self.main_view.eco, "season"),
            view=_setup_category_view(self.main_view, "season"),
        )


class AuctionChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, main_view):
        cur = main_view.eco.get("auction_channel_id", 0)
        defaults = [discord.Object(id=cur)] if cur else []
        super().__init__(
            placeholder="Виберіть канал для аукціону...",
            channel_types=[discord.ChannelType.text],
            min_values=0,
            max_values=1,
            default_values=defaults,
            row=0,
        )
        self.main_view = main_view

    async def callback(self, interaction: discord.Interaction):
        channel_id = self.values[0].id if self.values else 0
        await save_eco(interaction.guild.id, {"economy.auction_channel_id": channel_id})
        ctx = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
        self.main_view.eco = get_eco(ctx)
        await _render_auction_admin(interaction, self.main_view)


async def _load_auction_context(guild_id: int, eco: dict) -> tuple[list[dict], dict | None, list[dict]]:
    queue_doc = await db.guild_settings.find_one({"_id": guild_id}, {"auction_queue": 1}) or {}
    queue = normalize_auction_queue(queue_doc.get("auction_queue", []))
    active_raw = await ACTIVE_AUCTIONS.find_one({"_id": guild_id})
    active_doc = normalize_active_auction_doc(active_raw, eco) if active_raw else None
    history = await AUCTION_HISTORY.find({"guild_id": guild_id}).sort("ended_at", -1).limit(5).to_list(length=5)
    return queue, active_doc, history


def _build_auction_admin_embed(eco: dict, guild: discord.Guild, queue: list[dict], active_doc: dict | None, history: list[dict]) -> discord.Embed:
    curr = normalize_currency_emoji(eco.get("currency_emoji", CANONICAL_COIN))
    channel_id = eco.get("auction_channel_id", 0)
    channel_text = f"<#{channel_id}>" if channel_id else f"{E_CROSS} Не вибрано"
    anti_snipe = eco.get("auction_anti_snipe_seconds", 30)
    min_increment = get_auction_min_increment(eco)
    step_presets = ", ".join(f"`+{step:,}`" for step in get_auction_step_presets(eco))
    active_text = f"{E_CHECK} Йде live-аукціон" if active_doc else f"{E_CROSS} Активного аукціону немає"
    next_lot = queue[0] if queue else None
    next_text = lot_preview_text(next_lot, guild) if next_lot else "Черга порожня"

    embed = discord.Embed(
        title=f"{E_AUCTION} Аукціон",
        description=(
            "Це адмінська панель аукціону.\n"
            "Вибір каналу лише задає місце проведення торгів і **не публікує лот автоматично**."
        ),
        color=EMBED_COLOR,
    )
    embed.add_field(
        name="Поточний стан",
        value=(
            f"**Канал:** {channel_text}\n"
            f"**Статус:** {active_text}\n"
            f"**У черзі:** `{len(queue)}`\n"
            f"**Наступний лот:** {next_text}"
        ),
        inline=False,
    )
    embed.add_field(
        name="Політика ставок",
        value=(
            f"**Антиснайп:** `{anti_snipe}с`\n"
            f"**Мінімальний крок:** `{min_increment:,}` {curr}\n"
            f"**Кнопки підвищення:** {step_presets}"
        ),
        inline=False,
    )
    if active_doc:
        live_lot = active_doc["lot_snapshot"]
        leader_text = f"<@{active_doc['highest_bidder']}>" if active_doc.get("highest_bidder") else "Ще немає ставок"
        embed.add_field(
            name="Активний аукціон",
            value=(
                f"**Лот:** {lot_public_label(live_lot, guild)}\n"
                f"**Поточна ставка:** `{active_doc['current_bid']:,}` {curr}\n"
                f"**Лідер:** {leader_text}\n"
                f"**Залишилось:** <t:{int(active_doc['end_time'])}:R>"
            ),
            inline=False,
        )
    elif history:
        last = history[0]
        last_label = lot_plain_label(last.get("lot_snapshot", {}), guild)
        embed.add_field(
            name="Останній підсумок",
            value=(
                f"**Лот:** {last_label}\n"
                f"**Статус:** `{_history_status_label(last.get('status', 'finished'))}`\n"
                f"**Фінальна ставка:** `{last.get('final_price', 0):,}` {curr}\n"
                f"**Ставок:** `{last.get('bids_count', 0)}`"
            ),
            inline=False,
        )

    embed.set_footer(text="Додайте лот у чергу, потім вручну запустіть його через керування чергою.")
    return embed


async def _render_auction_admin(interaction: discord.Interaction, main_view, *, use_followup: bool = False):
    ctx = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
    main_view.eco = get_eco(ctx)
    queue, active_doc, history = await _load_auction_context(interaction.guild.id, main_view.eco)
    embed = _build_auction_admin_embed(main_view.eco, interaction.guild, queue, active_doc, history)
    view = _setup_category_view(main_view, "auction")
    if use_followup:
        await interaction.message.edit(embed=embed, view=view)
    else:
        await interaction.response.edit_message(embed=embed, view=view)


def _lot_detail_embed(lot: dict, eco: dict, guild: discord.Guild) -> discord.Embed:
    curr = normalize_currency_emoji(eco.get("currency_emoji", CANONICAL_COIN))
    label = lot_public_label(lot, guild)
    embed = discord.Embed(
        title=f"{E_AUCTION} Лот: {lot_plain_label(lot, guild)}",
        description=(
            f"**Що отримує переможець:** {label}\n"
            f"**Опис:** {lot.get('description', 'Опис відсутній.')}\n"
            f"**Стартова ставка:** `{lot['start_bid']:,}` {curr}\n"
            f"**Тривалість:** `{fmt_duration(lot['duration_seconds'])}`"
        ),
        color=EMBED_COLOR,
    )
    embed.set_footer(text=f"ID лота: {lot['id']}")
    return embed


def _build_queue_embed(eco: dict, guild: discord.Guild, queue: list[dict], active_doc: dict | None) -> discord.Embed:
    embed = discord.Embed(
        title=f"{E_CLIPBOARD} Черга лотів",
        description=(
            f"У черзі зараз: **{len(queue)}**\n"
            "Оберіть лот нижче, щоб запустити, видалити або переглянути деталі."
        ),
        color=EMBED_COLOR,
    )
    if active_doc:
        embed.add_field(
            name="Активний зараз",
            value=f"{lot_plain_label(active_doc['lot_snapshot'], guild)} • <t:{int(active_doc['end_time'])}:R>",
            inline=False,
        )
    return embed


def _build_audit_embed(eco: dict, guild: discord.Guild, active_doc: dict | None, history: list[dict]) -> discord.Embed:
    curr = normalize_currency_emoji(eco.get("currency_emoji", CANONICAL_COIN))
    embed = discord.Embed(
        title=f"{E_CLIPBOARD} Audit аукціону",
        description="Поточні ставки live-аукціону та останні завершені лоти.",
        color=EMBED_COLOR,
    )

    if active_doc:
        lines = []
        for entry in list(active_doc.get("bid_history", []))[-8:][::-1]:
            lines.append(
                f"<t:{int(entry.get('timestamp', 0))}:t> • <@{entry.get('user_id')}> • "
                f"`{entry.get('amount', 0):,}` {curr} • {_bid_source_label(str(entry.get('source', 'unknown')))}"
            )
        embed.add_field(
            name=f"Live: {lot_plain_label(active_doc['lot_snapshot'], guild)}",
            value="\n".join(lines) if lines else "Ставок ще не було.",
            inline=False,
        )
    else:
        embed.add_field(name="Live-аукціон", value="Зараз немає активних торгів.", inline=False)

    if history:
        recent_lines = []
        for item in history:
            lot = normalize_auction_lot(item.get("lot_snapshot"))
            winner = f"<@{item['winner_id']}>" if item.get("winner_id") else "без переможця"
            recent_lines.append(
                f"**{lot_plain_label(lot, guild)}** • `{_history_status_label(item.get('status', 'finished'))}` • "
                f"{winner} • `{item.get('final_price', 0):,}` {curr} • `{item.get('bids_count', 0)}` ставок"
            )
        embed.add_field(name="Останні підсумки", value="\n".join(recent_lines), inline=False)
    else:
        embed.add_field(name="Історія", value="Поки що немає завершених аукціонів.", inline=False)

    return embed


class AuctionPolicyModal(discord.ui.Modal, title="Політика аукціону"):
    anti_snipe = discord.ui.TextInput(label="Антиснайп (секунди, 0=вимк)", max_length=4)
    min_increment = discord.ui.TextInput(label="Мінімальний крок ставки", max_length=10)
    step_presets = discord.ui.TextInput(label="Кнопки підвищення через кому", max_length=30, placeholder="100,1000,5000")

    def __init__(self, main_view, eco: dict):
        super().__init__()
        self.main_view = main_view
        self.anti_snipe.default = str(eco.get("auction_anti_snipe_seconds", 30))
        self.min_increment.default = str(get_auction_min_increment(eco))
        self.step_presets.default = ",".join(str(step) for step in get_auction_step_presets(eco))

    async def on_submit(self, interaction: discord.Interaction):
        try:
            anti_snipe = max(0, int(self.anti_snipe.value))
            min_increment = max(1, int(self.min_increment.value))
            step_values = []
            for chunk in self.step_presets.value.split(","):
                value = int(chunk.strip())
                if value > 0:
                    step_values.append(value)
            if not step_values:
                raise ValueError
            step_values = sorted(dict.fromkeys(step_values))[:3]
        except ValueError:
            await interaction.response.send_message(f"{E_CROSS} Вкажіть коректні числа для політики ставок.", ephemeral=True)
            return

        await save_eco(
            interaction.guild.id,
            {
                "economy.auction_anti_snipe_seconds": anti_snipe,
                "economy.auction_min_increment": min_increment,
                "economy.auction_step_presets": step_values,
            },
        )
        ctx = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
        self.main_view.eco = get_eco(ctx)
        await _render_auction_admin(interaction, self.main_view)


class AuctionBaseLotModal(discord.ui.Modal):
    lot_title = discord.ui.TextInput(label="Назва лота", max_length=100)
    lot_desc = discord.ui.TextInput(label="Опис лота", style=discord.TextStyle.paragraph, max_length=500, required=False)
    start_bid = discord.ui.TextInput(label="Початкова ставка", max_length=15)
    duration = discord.ui.TextInput(label="Тривалість (напр. 30m, 1h, 120s)", max_length=10)

    def __init__(self, main_view, *, title: str):
        super().__init__(title=title)
        self.main_view = main_view

    def _build_lot(self, interaction: discord.Interaction, *, lot_type: str, role_id: int | None = None) -> dict:
        return normalize_auction_lot(
            {
                "id": str(uuid.uuid4())[:8],
                "type": lot_type,
                "title": self.lot_title.value.strip(),
                "description": self.lot_desc.value.strip() if self.lot_desc.value else "Опис відсутній.",
                "start_bid": int(self.start_bid.value),
                "duration_seconds": parse_duration(self.duration.value),
                "status": "queued",
                "role_id": role_id,
                "display_label": f"<@&{role_id}>" if role_id else self.lot_title.value.strip(),
                "created_by": interaction.user.id,
                "created_at": int(time.time()),
            }
        )

    async def _save_lot(self, interaction: discord.Interaction, lot: dict):
        from modules.db import invalidate_guild_settings

        await db.guild_settings.update_one({"_id": interaction.guild.id}, {"$push": {"auction_queue": lot}}, upsert=True)
        invalidate_guild_settings(interaction.guild.id)
        await _render_auction_admin(interaction, self.main_view)
        await interaction.followup.send(
            (
                f"{E_CHECK} Лот **{lot['title']}** додано до черги.\n"
                f"У канал він ще **не опублікований**.\n"
                "Наступний крок: **Черга лотів -> виберіть лот -> Запустити зараз**."
            ),
            ephemeral=True,
        )


class AuctionTextLotModal(AuctionBaseLotModal):
    def __init__(self, main_view):
        super().__init__(main_view, title="Додати текстовий лот")

    async def on_submit(self, interaction: discord.Interaction):
        try:
            lot = self._build_lot(interaction, lot_type="text")
            if lot["start_bid"] <= 0 or lot["duration_seconds"] < 10:
                raise ValueError
        except ValueError:
            await interaction.response.send_message(f"{E_CROSS} Початкова ставка має бути > 0, а час — не менше 10 секунд.", ephemeral=True)
            return
        await self._save_lot(interaction, lot)


class AuctionRoleLotModal(AuctionBaseLotModal):
    def __init__(self, main_view, role: discord.Role):
        super().__init__(main_view, title="Додати role-лот")
        self.role = role
        self.lot_title.default = role.name
        self.lot_desc.placeholder = f"Що дає роль @{role.name}"

    async def on_submit(self, interaction: discord.Interaction):
        try:
            lot = self._build_lot(interaction, lot_type="role", role_id=self.role.id)
            if lot["start_bid"] <= 0 or lot["duration_seconds"] < 10:
                raise ValueError
        except ValueError:
            await interaction.response.send_message(f"{E_CROSS} Початкова ставка має бути > 0, а час — не менше 10 секунд.", ephemeral=True)
            return
        await self._save_lot(interaction, lot)


class AuctionRoleSelect(discord.ui.RoleSelect):
    def __init__(self, main_view):
        self.main_view = main_view
        super().__init__(placeholder="Оберіть роль для аукціону...", min_values=1, max_values=1, row=0)

    async def callback(self, interaction: discord.Interaction):
        role = self.values[0]
        await interaction.response.send_modal(AuctionRoleLotModal(self.main_view, role))


class AuctionRoleLotPickerView(discord.ui.View):
    def __init__(self, main_view):
        super().__init__(timeout=180)
        self.main_view = main_view
        self.add_item(AuctionRoleSelect(main_view))

    @discord.ui.button(label="Назад", style=discord.ButtonStyle.secondary, emoji=discord.PartialEmoji.from_str(E_LEFT), row=1)
    async def back_btn(self, interaction: discord.Interaction, _):
        await _render_auction_admin(interaction, self.main_view)


class AuctionLotTypeView(discord.ui.View):
    def __init__(self, main_view):
        super().__init__(timeout=180)
        self.main_view = main_view

    @discord.ui.button(label="Текстовий лот", style=discord.ButtonStyle.secondary, row=0)
    async def text_btn(self, interaction: discord.Interaction, _):
        await interaction.response.send_modal(AuctionTextLotModal(self.main_view))

    @discord.ui.button(label="Role-лот", style=discord.ButtonStyle.secondary, emoji=discord.PartialEmoji.from_str(E_ROLE), row=0)
    async def role_btn(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(
            embed=discord.Embed(
                title=f"{E_AUCTION} Role-лот",
                description="Оберіть роль нижче. Після цього відкриється форма для стартової ставки й опису.",
                color=EMBED_COLOR,
            ),
            view=AuctionRoleLotPickerView(self.main_view),
        )

    @discord.ui.button(label="Назад", style=discord.ButtonStyle.secondary, emoji=discord.PartialEmoji.from_str(E_LEFT), row=1)
    async def back_btn(self, interaction: discord.Interaction, _):
        await _render_auction_admin(interaction, self.main_view)


class AuctionManageSelect(discord.ui.Select):
    def __init__(self, main_view, queue: list[dict]):
        self.main_view = main_view
        self.queue = queue
        options = []
        for lot in queue[:25]:
            desc = (lot.get("description", "") or "").strip().replace("\n", " ")
            meta = f"Старт {lot['start_bid']:,} • {fmt_duration(lot['duration_seconds'])}"
            if desc:
                remaining = max(0, 100 - len(meta) - 3)
                desc = desc[:remaining].rstrip()
                description = f"{meta} • {desc}" if desc else meta
            else:
                description = meta
            options.append(
                discord.SelectOption(
                    label=lot_plain_label(lot)[:100],
                    value=lot["id"],
                    description=description[:100],
                )
            )
        super().__init__(placeholder="Виберіть лот для дій...", options=options)

    async def callback(self, interaction: discord.Interaction):
        lot_id = self.values[0]
        lot = next((item for item in self.queue if item["id"] == lot_id), None)
        if not lot:
            return await interaction.response.send_message("Лот не знайдено.", ephemeral=True)
        await interaction.response.edit_message(
            embed=_lot_detail_embed(lot, self.main_view.eco, interaction.guild),
            view=AuctionLotActionView(self.main_view, lot),
        )


class AuctionManageView(discord.ui.View):
    def __init__(self, main_view, queue: list[dict], active_doc: dict | None):
        super().__init__(timeout=900)
        self.main_view = main_view
        self.active_doc = active_doc
        self.add_item(AuctionManageSelect(main_view, queue))
        if active_doc:
            active_btn = discord.ui.Button(label="Активний аукціон", style=discord.ButtonStyle.secondary, emoji=discord.PartialEmoji.from_str(E_AUCTION), row=1)
            active_btn.callback = self._active_cb
            self.add_item(active_btn)
        audit_btn = discord.ui.Button(label="Історія / audit", style=discord.ButtonStyle.secondary, emoji=discord.PartialEmoji.from_str(E_CLIPBOARD), row=1)
        audit_btn.callback = self._audit_cb
        self.add_item(audit_btn)
        back_btn = discord.ui.Button(label="Назад", style=discord.ButtonStyle.secondary, emoji=E_LEFT, row=3)
        back_btn.callback = self._back_cb
        self.add_item(back_btn)

    async def _active_cb(self, interaction: discord.Interaction):
        await _show_active_admin_view(interaction, self.main_view)

    async def _audit_cb(self, interaction: discord.Interaction):
        _, active_doc, history = await _load_auction_context(interaction.guild.id, self.main_view.eco)
        await interaction.response.edit_message(
            embed=_build_audit_embed(self.main_view.eco, interaction.guild, active_doc, history),
            view=AuctionAuditView(self.main_view),
        )

    async def _back_cb(self, interaction: discord.Interaction):
        await _render_auction_admin(interaction, self.main_view)


class AuctionLotActionView(discord.ui.View):
    def __init__(self, main_view, lot: dict):
        super().__init__(timeout=900)
        self.main_view = main_view
        self.lot = lot
        start_btn = discord.ui.Button(label="Запустити зараз", style=discord.ButtonStyle.secondary, emoji=discord.PartialEmoji.from_str(E_BOOST))
        start_btn.callback = self._start_cb
        self.add_item(start_btn)
        del_btn = discord.ui.Button(label="Видалити з черги", style=discord.ButtonStyle.secondary, emoji=discord.PartialEmoji.from_str(E_TRASH))
        del_btn.callback = self._delete_cb
        self.add_item(del_btn)
        back_btn = discord.ui.Button(label="Список Лотів", style=discord.ButtonStyle.secondary, emoji=E_LEFT, row=3)
        back_btn.callback = self._back_list_cb
        self.add_item(back_btn)

    async def _delete_cb(self, interaction: discord.Interaction):
        from modules.db import invalidate_guild_settings

        await db.guild_settings.update_one({"_id": interaction.guild.id}, {"$pull": {"auction_queue": {"id": self.lot["id"]}}})
        invalidate_guild_settings(interaction.guild.id)
        await interaction.response.send_message(f"{E_CHECK} Лот видалено з черги.", ephemeral=True)
        await self._back_list_cb(interaction, is_followup=True)

    async def _start_cb(self, interaction: discord.Interaction):
        from modules.db import invalidate_guild_settings

        am = setup_auction_manager(interaction.client)
        channel_id = self.main_view.eco.get("auction_channel_id", 0)
        if channel_id == 0:
            return await interaction.response.send_message(f"{E_CROSS} Спершу налаштуйте канал в меню Аукціону!", ephemeral=True)
        channel = interaction.guild.get_channel(channel_id)
        if not channel:
            return await interaction.response.send_message(f"{E_CROSS} Канал аукціону не знайдено (можливо видалений).", ephemeral=True)

        success, msg = await am.start_auction(interaction.guild.id, self.lot, channel, self.main_view.eco, started_by=interaction.user.id)
        if not success:
            return await interaction.response.send_message(f"{E_CROSS} Помилка: {msg}", ephemeral=True)

        await db.guild_settings.update_one({"_id": interaction.guild.id}, {"$pull": {"auction_queue": {"id": self.lot['id']}}})
        invalidate_guild_settings(interaction.guild.id)
        await interaction.response.send_message(
            f"{E_CHECK} Аукціон на лот **{self.lot['title']}** запущено в каналі {channel.mention}.",
            ephemeral=True,
        )
        await _render_auction_admin(interaction, self.main_view, use_followup=True)

    async def _back_list_cb(self, interaction: discord.Interaction, is_followup=False):
        ctx = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
        queue = normalize_auction_queue(ctx.get("auction_queue", []))
        active_raw = await ACTIVE_AUCTIONS.find_one({"_id": interaction.guild.id})
        active_doc = normalize_active_auction_doc(active_raw, self.main_view.eco) if active_raw else None
        if not queue:
            embed = _build_auction_admin_embed(self.main_view.eco, interaction.guild, queue, active_doc, [])
            view = _setup_category_view(self.main_view, "auction")
        else:
            embed = _build_queue_embed(self.main_view.eco, interaction.guild, queue, active_doc)
            view = AuctionManageView(self.main_view, queue, active_doc)
        if is_followup:
            await interaction.message.edit(embed=embed, view=view)
        else:
            await interaction.response.edit_message(embed=embed, view=view)


class AuctionAuditView(discord.ui.View):
    def __init__(self, main_view):
        super().__init__(timeout=180)
        self.main_view = main_view

    @discord.ui.button(label="Назад", style=discord.ButtonStyle.secondary, emoji=discord.PartialEmoji.from_str(E_LEFT))
    async def back_btn(self, interaction: discord.Interaction, _):
        await _render_auction_admin(interaction, self.main_view)


class AuctionConfirmView(discord.ui.View):
    def __init__(self, main_view, action: str):
        super().__init__(timeout=180)
        self.main_view = main_view
        self.action = action

    @discord.ui.button(label="Підтвердити", style=discord.ButtonStyle.secondary, row=0)
    async def confirm_btn(self, interaction: discord.Interaction, _):
        manager = setup_auction_manager(interaction.client)
        if self.action == "cancel":
            success, msg = await manager.cancel_auction(interaction.guild.id, cancelled_by=interaction.user.id)
        else:
            success, msg = await manager.force_finish_auction(interaction.guild.id, forced_by=interaction.user.id)

        if not success:
            return await interaction.response.send_message(f"{E_CROSS} {msg}", ephemeral=True)
        await interaction.response.send_message(f"{E_CHECK} {msg}", ephemeral=True)
        await _render_auction_admin(interaction, self.main_view, use_followup=True)

    @discord.ui.button(label="Назад", style=discord.ButtonStyle.secondary, emoji=discord.PartialEmoji.from_str(E_LEFT), row=0)
    async def back_btn(self, interaction: discord.Interaction, _):
        await _show_active_admin_view(interaction, self.main_view)


class AuctionActiveAdminView(discord.ui.View):
    def __init__(self, main_view):
        super().__init__(timeout=180)
        self.main_view = main_view

    @discord.ui.button(label="Скасувати", style=discord.ButtonStyle.secondary, row=0)
    async def cancel_btn(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(
            embed=discord.Embed(
                title=f"{E_AUCTION} Скасувати аукціон",
                description="Лот не буде видано, останню активну ставку буде повернуто лідеру.",
                color=EMBED_COLOR,
            ),
            view=AuctionConfirmView(self.main_view, "cancel"),
        )

    @discord.ui.button(label="Force finish", style=discord.ButtonStyle.secondary, row=0)
    async def force_btn(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(
            embed=discord.Embed(
                title=f"{E_AUCTION} Force finish",
                description="Поточний лідер буде оголошений переможцем, якщо ставка вже є.",
                color=EMBED_COLOR,
            ),
            view=AuctionConfirmView(self.main_view, "force_finish"),
        )

    @discord.ui.button(label="Історія / audit", style=discord.ButtonStyle.secondary, emoji=discord.PartialEmoji.from_str(E_CLIPBOARD), row=1)
    async def audit_btn(self, interaction: discord.Interaction, _):
        _, active_doc, history = await _load_auction_context(interaction.guild.id, self.main_view.eco)
        await interaction.response.edit_message(
            embed=_build_audit_embed(self.main_view.eco, interaction.guild, active_doc, history),
            view=AuctionAuditView(self.main_view),
        )

    @discord.ui.button(label="Назад", style=discord.ButtonStyle.secondary, emoji=discord.PartialEmoji.from_str(E_LEFT), row=1)
    async def back_btn(self, interaction: discord.Interaction, _):
        await _render_auction_admin(interaction, self.main_view)


async def _show_active_admin_view(interaction: discord.Interaction, main_view):
    queue, active_doc, history = await _load_auction_context(interaction.guild.id, main_view.eco)
    if not active_doc:
        return await interaction.response.send_message(f"{E_CROSS} Активного аукціону зараз немає.", ephemeral=True)
    embed = _build_auction_admin_embed(main_view.eco, interaction.guild, queue, active_doc, history)
    embed.title = f"{E_AUCTION} Активний аукціон"
    await interaction.response.edit_message(embed=embed, view=AuctionActiveAdminView(main_view))


def build_shop_roles_embed(eco: dict, guild: discord.Guild) -> discord.Embed:
    curr = normalize_currency_emoji(eco.get("currency_emoji", CANONICAL_COIN))
    shop_roles = eco.get("shop_roles", [])
    embed = discord.Embed(
        title=f"{E_ROLE} Магазин: Кастомні ролі",
        description="Тут ви можете додати ролі для продажу або видалити існуючі.\n\n**Поточні ролі в продажу:**",
        color=EMBED_COLOR,
    )
    if not shop_roles:
        embed.description += "\n\n*Немає жодної ролі на продаж.*"
    else:
        lines = []
        for role_data in shop_roles:
            role_obj = guild.get_role(role_data["role_id"])
            role_name = role_obj.mention if role_obj else f"Невідома роль ({role_data['role_id']})"
            lines.append(f"• {role_name} — **{role_data['price']:,}** {curr}")
        embed.description += "\n\n" + "\n".join(lines)
    embed.set_footer(text="Використовуйте меню для додавання/видалення")
    return embed


class ShopAddRoleModal(discord.ui.Modal, title="Додати Роль в Магазин"):
    price = discord.ui.TextInput(label="Ціна ролі", max_length=10)

    def __init__(self, main_view, role_id: int, guild: discord.Guild):
        super().__init__()
        self.main_view = main_view
        self.role_id = role_id
        self.guild = guild

    async def on_submit(self, interaction: discord.Interaction):
        try:
            price_val = int(self.price.value)
            if price_val <= 0:
                raise ValueError
        except ValueError:
            await interaction.response.send_message(f"{E_CROSS} Некоректна ціна!", ephemeral=True)
            return

        shop_roles = self.main_view.eco.get("shop_roles", [])
        role_exists = False
        for role_data in shop_roles:
            if role_data["role_id"] == self.role_id:
                role_data["price"] = price_val
                role_exists = True
                break
        if not role_exists:
            shop_roles.append({"role_id": self.role_id, "price": price_val})

        await save_eco(interaction.guild.id, {"economy.shop_roles": shop_roles})
        ctx = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
        self.main_view.eco = get_eco(ctx)
        await interaction.response.edit_message(
            embed=build_shop_roles_embed(self.main_view.eco, self.guild),
            view=ShopRolesView(self.main_view, self.guild),
        )


class ShopAddRoleSelect(discord.ui.RoleSelect):
    def __init__(self, main_view, guild: discord.Guild):
        super().__init__(placeholder="Виберіть роль для додавання/редагування...")
        self.main_view = main_view
        self.guild = guild

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ShopAddRoleModal(self.main_view, self.values[0].id, self.guild))


class ShopRemoveRoleSelect(discord.ui.Select):
    def __init__(self, main_view, guild: discord.Guild, shop_roles: list):
        self.main_view = main_view
        self.guild = guild
        options = []
        for role_data in shop_roles:
            role_obj = guild.get_role(role_data["role_id"])
            name_str = role_obj.name if role_obj else f"ID: {role_data['role_id']}"
            options.append(discord.SelectOption(label=f"Видалити {name_str}", value=str(role_data["role_id"]), description=f"Ціна: {role_data['price']}"))
        super().__init__(placeholder="Виберіть роль для видалення з продажу...", options=options)

    async def callback(self, interaction: discord.Interaction):
        role_id = int(self.values[0])
        shop_roles = self.main_view.eco.get("shop_roles", [])
        new_shop_roles = [role_data for role_data in shop_roles if role_data["role_id"] != role_id]
        await save_eco(interaction.guild.id, {"economy.shop_roles": new_shop_roles})
        ctx = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
        self.main_view.eco = get_eco(ctx)
        await interaction.response.edit_message(
            embed=build_shop_roles_embed(self.main_view.eco, self.guild),
            view=ShopRolesView(self.main_view, self.guild),
        )


class ShopRolesView(discord.ui.View):
    def __init__(self, main_view, guild: discord.Guild):
        super().__init__(timeout=900)
        self.main_view = main_view
        self.guild = guild
        self.add_item(ShopAddRoleSelect(main_view, guild))
        shop_roles = main_view.eco.get("shop_roles", [])
        if shop_roles:
            self.add_item(ShopRemoveRoleSelect(main_view, guild, shop_roles[:25]))
        back_btn = discord.ui.Button(label="Назад до налаштувань Магазину", style=discord.ButtonStyle.secondary, emoji=E_LEFT, row=3)
        back_btn.callback = self._back_cb
        self.add_item(back_btn)

    async def _back_cb(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            embed=build_category_embed(self.main_view.eco, "shop"),
            view=_setup_category_view(self.main_view, "shop"),
        )



