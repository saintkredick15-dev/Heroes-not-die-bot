from __future__ import annotations

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


def _setup_category_view(main_view, category: str):
    from commands.administration.economy_setup import SetupCategoryView

    return SetupCategoryView(main_view, category)


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
        super().__init__(placeholder="Виберіть канал для аукціону...", channel_types=[discord.ChannelType.text])
        self.main_view = main_view

    async def callback(self, interaction: discord.Interaction):
        await save_eco(interaction.guild.id, {"economy.auction_channel_id": self.values[0].id})
        ctx = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
        self.main_view.eco = get_eco(ctx)
        await interaction.response.edit_message(
            embed=build_category_embed(self.main_view.eco, "auction"),
            view=_setup_category_view(self.main_view, "auction"),
        )


class AuctionConfigModal(discord.ui.Modal, title="Аукціон: антиснайп"):
    anti_snipe = discord.ui.TextInput(label="Захист від снайпу (секунди, 0=вимк)", max_length=4)

    def __init__(self, main_view, eco: dict):
        super().__init__()
        self.main_view = main_view
        self.anti_snipe.default = str(eco.get("auction_anti_snipe_seconds", 30))

    async def on_submit(self, interaction: discord.Interaction):
        try:
            value = max(0, int(self.anti_snipe.value))
        except ValueError:
            await interaction.response.send_message(f"{E_CROSS} Лише числа!", ephemeral=True)
            return
        await save_eco(interaction.guild.id, {"economy.auction_anti_snipe_seconds": value})
        ctx = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
        self.main_view.eco = get_eco(ctx)
        await interaction.response.edit_message(
            embed=build_category_embed(self.main_view.eco, "auction"),
            view=_setup_category_view(self.main_view, "auction"),
        )


class AuctionAddLotModal(discord.ui.Modal, title="Додати Лот до Черги"):
    lot_name = discord.ui.TextInput(label="Назва Лоту або Пінг Ролі (@Role / ID)", max_length=100)
    lot_desc = discord.ui.TextInput(label="Опис (що це таке)", style=discord.TextStyle.paragraph, max_length=500, required=False)
    start_bid = discord.ui.TextInput(label="Початкова ставка", max_length=15)
    duration = discord.ui.TextInput(label="Час Аукціону (напр. 30m, 1h, 120s)", max_length=10)

    def __init__(self, main_view):
        super().__init__()
        self.main_view = main_view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            bid = int(self.start_bid.value)
            dur = parse_duration(self.duration.value)
            if bid <= 0 or dur < 10:
                raise ValueError
        except ValueError:
            await interaction.response.send_message(f"{E_CROSS} Помилка! Ставка має бути > 0, Час > 10 секунд. Формат часу: 30m, 1h.", ephemeral=True)
            return

        new_lot = {
            "id": str(uuid.uuid4())[:8],
            "name": self.lot_name.value.strip(),
            "desc": self.lot_desc.value.strip() if self.lot_desc.value else "Опис відсутній.",
            "start_bid": bid,
            "duration": dur,
            "status": "queued",
        }

        from modules.db import invalidate_guild_settings

        await db.guild_settings.update_one({"_id": interaction.guild.id}, {"$push": {"auction_queue": new_lot}}, upsert=True)
        invalidate_guild_settings(interaction.guild.id)
        await interaction.response.send_message(
            f"{E_CHECK} Лот **{new_lot['name']}** додано до черги (Аукціон іде {fmt_duration(dur)}, старт: {bid:,})!",
            ephemeral=True,
        )


class AuctionManageSelect(discord.ui.Select):
    def __init__(self, main_view, queue: list):
        self.main_view = main_view
        self.queue = queue
        options = []
        for lot in queue[:25]:
            desc = lot.get("desc", "")[:50]
            options.append(discord.SelectOption(label=lot["name"][:100], value=lot["id"], description=f"Старт: {lot['start_bid']} | {fmt_duration(lot['duration'])} | {desc}"))
        super().__init__(placeholder="Виберіть лот для дій...", options=options)

    async def callback(self, interaction: discord.Interaction):
        lot_id = self.values[0]
        lot = next((item for item in self.queue if item["id"] == lot_id), None)
        if not lot:
            return await interaction.response.send_message("Лот не знайдено.", ephemeral=True)
        embed = discord.Embed(
            title=f"Лот: {lot['name']}",
            description=f"**Опис:** {lot.get('desc', 'Немає')}\n**Стартова ставка:** `{lot['start_bid']:,}` {normalize_currency_emoji(self.main_view.eco.get('currency_emoji'))}\n**Тривалість:** `{fmt_duration(lot['duration'])}`",
            color=discord.Color.gold(),
        )
        embed.set_footer(text=f"ID Лоту: {lot_id}")
        await interaction.response.edit_message(embed=embed, view=AuctionLotActionView(self.main_view, lot))


class AuctionManageView(discord.ui.View):
    def __init__(self, main_view, queue: list):
        super().__init__(timeout=900)
        self.main_view = main_view
        self.add_item(AuctionManageSelect(main_view, queue))
        back_btn = discord.ui.Button(label="Назад", style=discord.ButtonStyle.secondary, emoji=E_LEFT, row=3)
        back_btn.callback = self._back_cb
        self.add_item(back_btn)

    async def _back_cb(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            embed=build_category_embed(self.main_view.eco, "auction"),
            view=_setup_category_view(self.main_view, "auction"),
        )


class AuctionLotActionView(discord.ui.View):
    def __init__(self, main_view, lot: dict):
        super().__init__(timeout=900)
        self.main_view = main_view
        self.lot = lot
        start_btn = discord.ui.Button(label="Запустити Аукціон зараз", style=discord.ButtonStyle.success, emoji=discord.PartialEmoji.from_str(E_BOOST))
        start_btn.callback = self._start_cb
        self.add_item(start_btn)
        del_btn = discord.ui.Button(label="Видалити з черги", style=discord.ButtonStyle.danger, emoji=discord.PartialEmoji.from_str(E_TRASH))
        del_btn.callback = self._delete_cb
        self.add_item(del_btn)
        back_btn = discord.ui.Button(label="Список Лотів", style=discord.ButtonStyle.secondary, emoji=E_LEFT, row=3)
        back_btn.callback = self._back_list_cb
        self.add_item(back_btn)

    async def _delete_cb(self, interaction: discord.Interaction):
        from modules.db import invalidate_guild_settings

        await db.guild_settings.update_one({"_id": interaction.guild.id}, {"$pull": {"auction_queue": {"id": self.lot["id"]}}})
        invalidate_guild_settings(interaction.guild.id)
        await interaction.response.send_message(f"{E_CHECK} Лот видалено.", ephemeral=True)
        await self._back_list_cb(interaction, is_followup=True)

    async def _start_cb(self, interaction: discord.Interaction):
        from modules.db import invalidate_guild_settings
        from services.auction_manager import setup_auction_manager

        am = setup_auction_manager(interaction.client)
        channel_id = self.main_view.eco.get("auction_channel_id", 0)
        if channel_id == 0:
            return await interaction.response.send_message(f"{E_CROSS} Спершу налаштуйте канал в меню Аукціону!", ephemeral=True)
        channel = interaction.guild.get_channel(channel_id)
        if not channel:
            return await interaction.response.send_message(f"{E_CROSS} Канал аукціону не знайдено (можливо видалений).", ephemeral=True)

        await db.guild_settings.update_one({"_id": interaction.guild.id}, {"$pull": {"auction_queue": {"id": self.lot['id']}}})
        success, msg = await am.start_auction(interaction.guild.id, self.lot, channel, self.main_view.eco)
        if not success:
            await db.guild_settings.update_one({"_id": interaction.guild.id}, {"$push": {"auction_queue": self.lot}})
            invalidate_guild_settings(interaction.guild.id)
            return await interaction.response.send_message(f"{E_CROSS} Помилка: {msg}", ephemeral=True)

        await interaction.response.send_message(f"{E_CHECK} Аукціон на лот **{self.lot['name']}** успішно розпочато в каналі {channel.mention}!", ephemeral=True)
        await interaction.message.edit(embed=build_category_embed(self.main_view.eco, "auction"), view=_setup_category_view(self.main_view, "auction"))

    async def _back_list_cb(self, interaction: discord.Interaction, is_followup=False):
        ctx = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
        queue = ctx.get("auction_queue", [])
        if not queue:
            embed = build_category_embed(self.main_view.eco, "auction")
            view = _setup_category_view(self.main_view, "auction")
        else:
            embed = discord.Embed(
                title=f"{E_CLIPBOARD} Керування чергою Аукціону",
                description=f"В черзі зараз лотів: **{len(queue)}**\nВиберіть лот у списку нижче.",
                color=EMBED_COLOR,
            )
            view = AuctionManageView(self.main_view, queue)
        if is_followup:
            await interaction.message.edit(embed=embed, view=view)
        else:
            await interaction.response.edit_message(embed=embed, view=view)


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



