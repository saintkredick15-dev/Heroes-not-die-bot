from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from config.constants import Emojis as _E
from modules.db import get_database
from repositories.user import get_user
from utils.activity_config import (
    DEFAULT_ACTIVITY,
    migrate_activity_config,
    normalize_reward_rules,
    save_activity_updates,
    sync_member_reward_roles,
)
from utils.ui_contract import add_section, compact_kv, set_surface_footer, surface_embed

db = get_database()

E_STATS = _E.STATS.value
E_CHAT = _E.CHAT.value
E_STAR = _E.STAR.value
E_MICRO = _E.MICRO.value
E_NOTIF = _E.NOTIFICATION.value
E_NOTIF_OFF = _E.NOTIFICATION_OFF.value
E_CHECK = _E.CHECK.value
E_CROSS = _E.CROSS.value
E_ROLE = _E.ROLE.value
E_PLUS = _E.PLUS.value
E_RELOAD = _E.RELOAD.value


async def _load_activity(guild_id: int) -> dict:
    return await migrate_activity_config(guild_id)


def _status(enabled: bool) -> str:
    return f"{E_CHECK} Увімкнено" if enabled else f"{E_CROSS} Вимкнено"


def _reward_mode_label(mode: str) -> str:
    return "Лише найвища роль" if mode == "highest_only" else "Усі досягнуті ролі"


def _can_manage_role(guild: discord.Guild, role: discord.Role) -> bool:
    me = guild.me
    return me is not None and not role.managed and role < me.top_role


def _render_reward_lines(guild: discord.Guild, activity_config: dict, *, limit: int = 8) -> list[str]:
    rules = activity_config.get("reward_roles", [])
    if not rules:
        return ["Нагороди ще не налаштовані."]

    lines: list[str] = []
    for rule in rules[:limit]:
        role = guild.get_role(rule["role_id"])
        role_text = role.mention if role else f"`deleted:{rule['role_id']}`"
        lines.append(f"`Lv {rule['level']}` -> {role_text}")
    if len(rules) > limit:
        lines.append(f"+{len(rules) - limit} правил")
    return lines


def _build_main_embed(guild: discord.Guild, activity_config: dict) -> discord.Embed:
    channel_id = activity_config.get("levelup_channel_id")
    channel_text = f"<#{channel_id}>" if channel_id else f"{E_CROSS} Не вибрано"
    embed = surface_embed(
        "admin",
        title=f"{E_STATS} XP та активність",
        description="Єдиний центр керування XP, level-up повідомленнями та ролями-нагородами.",
    )
    add_section(
        embed,
        "XP ставки",
        [
            compact_kv("За повідомлення", f"`{activity_config['message_xp']}` XP"),
            compact_kv("За реакцію", f"`{activity_config['reaction_xp']}` XP"),
            compact_kv("За хвилину у войсі", f"`{activity_config['voice_xp_per_minute']}` XP"),
        ],
    )
    add_section(
        embed,
        "Level-up",
        [
            compact_kv("Канал", channel_text),
            compact_kv("Пінг користувача", _status(activity_config.get("levelup_ping_user", True))),
            compact_kv("Дозволити opt-out", _status(activity_config.get("levelup_allow_opt_out", True))),
        ],
    )
    add_section(
        embed,
        f"{E_ROLE} Нагороди за рівні",
        [
            compact_kv("Режим", _reward_mode_label(activity_config.get("reward_mode", DEFAULT_ACTIVITY["reward_mode"]))),
            *_render_reward_lines(guild, activity_config),
        ],
    )
    set_surface_footer(embed, "admin", "Окремо від економіки. Бот керує лише tracked XP-нагородами.")
    return embed


def _build_rewards_embed(guild: discord.Guild, activity_config: dict) -> discord.Embed:
    embed = surface_embed(
        "admin",
        title=f"{E_ROLE} Нагороди за рівні",
        description="Кожне правило складається з рівня та ролі. Режим визначає, чи лишається тільки найвища роль.",
    )
    add_section(embed, "Режим", compact_kv("Видача ролей", _reward_mode_label(activity_config.get("reward_mode", DEFAULT_ACTIVITY["reward_mode"]))), inline=False)
    add_section(embed, "Поточні правила", _render_reward_lines(guild, activity_config, limit=12), inline=False)
    set_surface_footer(embed, "admin", "highest_only прибирає нижчі tracked XP-роли, stack_all лишає всі.")
    return embed


class XpRatesModal(discord.ui.Modal, title="XP ставки"):
    message_xp = discord.ui.TextInput(label="XP за повідомлення", max_length=4)
    reaction_xp = discord.ui.TextInput(label="XP за реакцію", max_length=4)
    voice_xp = discord.ui.TextInput(label="XP за хвилину у войсі", max_length=4)

    def __init__(self, activity_config: dict, message: discord.Message | None):
        super().__init__()
        self.panel_message = message
        self.message_xp.default = str(activity_config["message_xp"])
        self.reaction_xp.default = str(activity_config["reaction_xp"])
        self.voice_xp.default = str(activity_config["voice_xp_per_minute"])

    async def on_submit(self, interaction: discord.Interaction):
        try:
            patch = {
                "message_xp": max(0, int(self.message_xp.value.strip())),
                "reaction_xp": max(0, int(self.reaction_xp.value.strip())),
                "voice_xp_per_minute": max(0, int(self.voice_xp.value.strip())),
            }
        except ValueError:
            await interaction.response.send_message(f"{E_CROSS} Введіть цілі числа для XP.", ephemeral=True)
            return

        activity_config = await save_activity_updates(interaction.guild.id, patch)
        await interaction.response.send_message(f"{E_CHECK} XP ставки оновлено.", ephemeral=True)
        if self.panel_message is not None:
            view = XpSetupView(interaction.guild, activity_config)
            view.message = self.panel_message
            await self.panel_message.edit(embed=_build_main_embed(interaction.guild, activity_config), view=view)


class RewardLevelModal(discord.ui.Modal, title="Рівень для нагороди"):
    level = discord.ui.TextInput(label="Рівень", placeholder="Наприклад: 10", max_length=3)

    def __init__(self, role: discord.Role, activity_config: dict, message: discord.Message | None):
        super().__init__()
        self.role = role
        self.activity_config = activity_config
        self.panel_message = message

    async def on_submit(self, interaction: discord.Interaction):
        try:
            level = int(self.level.value.strip())
        except ValueError:
            await interaction.response.send_message(f"{E_CROSS} Рівень має бути цілим числом.", ephemeral=True)
            return

        if level <= 0:
            await interaction.response.send_message(f"{E_CROSS} Рівень має бути більшим за нуль.", ephemeral=True)
            return

        rules = normalize_reward_rules(self.activity_config.get("reward_roles", []))
        new_rule = {"level": level, "role_id": self.role.id}
        if new_rule in rules:
            await interaction.response.send_message(f"{E_CROSS} Таке правило вже існує.", ephemeral=True)
            return

        rules.append(new_rule)
        activity_config = await save_activity_updates(interaction.guild.id, {"reward_roles": rules})
        await interaction.response.send_message(f"{E_CHECK} Правило для {self.role.mention} збережено.", ephemeral=True)
        if self.panel_message is not None:
            view = RewardRulesView(interaction.guild, activity_config)
            view.message = self.panel_message
            await self.panel_message.edit(embed=_build_rewards_embed(interaction.guild, activity_config), view=view)


class LevelUpChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, activity_config: dict):
        current = activity_config.get("levelup_channel_id")
        defaults = [discord.Object(id=current)] if current else []
        super().__init__(
            placeholder="Канал для level-up повідомлень...",
            min_values=1,
            max_values=1,
            channel_types=[discord.ChannelType.text],
            row=0,
            default_values=defaults,
        )

    async def callback(self, interaction: discord.Interaction):
        activity_config = await save_activity_updates(interaction.guild.id, {"levelup_channel_id": self.values[0].id})
        view = XpSetupView(interaction.guild, activity_config)
        view.message = interaction.message
        await interaction.response.edit_message(embed=_build_main_embed(interaction.guild, activity_config), view=view)


class RewardRoleSelect(discord.ui.RoleSelect):
    def __init__(self, activity_config: dict):
        super().__init__(placeholder="Оберіть роль для XP-нагороди...", min_values=1, max_values=1, row=0)
        self.activity_config = activity_config

    async def callback(self, interaction: discord.Interaction):
        role = self.values[0]
        if not _can_manage_role(interaction.guild, role):
            await interaction.response.send_message(
                f"{E_CROSS} Бот не може керувати роллю {role.mention}. Підніміть роль бота або оберіть іншу роль.",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(RewardLevelModal(role, self.activity_config, self.view.message))


class RewardAddRoleView(discord.ui.View):
    def __init__(self, guild: discord.Guild, activity_config: dict):
        super().__init__(timeout=180)
        self.guild = guild
        self.activity_config = activity_config
        self.message: discord.Message | None = None
        self.add_item(RewardRoleSelect(activity_config))

    @discord.ui.button(label="← Назад", style=discord.ButtonStyle.secondary, row=1)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        activity_config = await _load_activity(interaction.guild.id)
        view = RewardRulesView(interaction.guild, activity_config)
        view.message = interaction.message
        await interaction.response.edit_message(embed=_build_rewards_embed(interaction.guild, activity_config), view=view)


class RewardRuleRemoveSelect(discord.ui.Select):
    def __init__(self, guild: discord.Guild, activity_config: dict):
        rules = activity_config.get("reward_roles", [])
        options = []
        for rule in rules[:25]:
            role = guild.get_role(rule["role_id"])
            role_name = role.name if role else f"deleted:{rule['role_id']}"
            options.append(
                discord.SelectOption(
                    label=f"Lv {rule['level']} -> {role_name}"[:100],
                    value=f"{rule['level']}:{rule['role_id']}",
                    description="Видалити це правило",
                )
            )
        if not options:
            options = [discord.SelectOption(label="Правил немає", value="__empty__", description="Спочатку додайте XP-нагороду.")]
        super().__init__(placeholder="Видалити правило...", options=options, row=1, disabled=options[0].value == "__empty__")

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "__empty__":
            await interaction.response.defer()
            return
        level_str, role_str = self.values[0].split(":", 1)
        level = int(level_str)
        role_id = int(role_str)
        activity_config = await _load_activity(interaction.guild.id)
        rules = [
            rule
            for rule in activity_config.get("reward_roles", [])
            if not (rule["level"] == level and rule["role_id"] == role_id)
        ]
        activity_config = await save_activity_updates(interaction.guild.id, {"reward_roles": rules})
        view = RewardRulesView(interaction.guild, activity_config)
        view.message = interaction.message
        await interaction.response.edit_message(embed=_build_rewards_embed(interaction.guild, activity_config), view=view)


async def _collect_members(guild: discord.Guild) -> list[discord.Member]:
    members = {member.id: member for member in guild.members if not member.bot}
    if guild.member_count and len(members) < guild.member_count:
        try:
            async for member in guild.fetch_members(limit=None):
                if not member.bot:
                    members[member.id] = member
        except (discord.Forbidden, discord.HTTPException):
            pass
    return list(members.values())


async def _sync_rewards(interaction: discord.Interaction, panel_message: discord.Message | None):
    await interaction.response.defer(ephemeral=True)
    activity_config = await _load_activity(interaction.guild.id)
    members = await _collect_members(interaction.guild)

    processed = 0
    changed = 0
    failed = 0
    for member in members:
        user_data = await get_user(db, interaction.guild.id, member.id)
        result = await sync_member_reward_roles(member, user_data.get("level", 1), activity_config)
        processed += 1
        if result["added"] or result["removed"]:
            changed += 1
        failed += result["failed"]

    if panel_message is not None:
        view = XpSetupView(interaction.guild, activity_config)
        view.message = panel_message
        await panel_message.edit(embed=_build_main_embed(interaction.guild, activity_config), view=view)

    await interaction.followup.send(
        f"{E_CHECK} Синхронізацію завершено: перевірено `{processed}` учасників, змінено `{changed}`, проблем `{failed}`.",
        ephemeral=True,
    )


class RewardRulesView(discord.ui.View):
    def __init__(self, guild: discord.Guild, activity_config: dict):
        super().__init__(timeout=180)
        self.guild = guild
        self.activity_config = activity_config
        self.message: discord.Message | None = None
        self.toggle_mode_btn.label = f"Режим: {activity_config.get('reward_mode', DEFAULT_ACTIVITY['reward_mode'])}"
        self.add_item(RewardRuleRemoveSelect(guild, activity_config))

    @discord.ui.button(label="Додати правило", style=discord.ButtonStyle.secondary, emoji=discord.PartialEmoji.from_str(E_PLUS), row=0)
    async def add_rule_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        activity_config = await _load_activity(interaction.guild.id)
        view = RewardAddRoleView(interaction.guild, activity_config)
        view.message = interaction.message
        embed = surface_embed("admin", f"{E_PLUS} Оберіть роль", "Спочатку виберіть роль, а потім вкажіть рівень для XP-нагороди.")
        set_surface_footer(embed, "admin", "Роль має бути нижче за найвищу роль бота.")
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="Режим: highest_only", style=discord.ButtonStyle.secondary, row=0)
    async def toggle_mode_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        activity_config = await _load_activity(interaction.guild.id)
        new_mode = "stack_all" if activity_config.get("reward_mode") == "highest_only" else "highest_only"
        activity_config = await save_activity_updates(interaction.guild.id, {"reward_mode": new_mode})
        view = RewardRulesView(interaction.guild, activity_config)
        view.message = interaction.message
        await interaction.response.edit_message(embed=_build_rewards_embed(interaction.guild, activity_config), view=view)

    @discord.ui.button(label="Синхронізувати ролі", style=discord.ButtonStyle.primary, emoji=discord.PartialEmoji.from_str(E_RELOAD), row=2)
    async def sync_rewards_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _sync_rewards(interaction, interaction.message)

    @discord.ui.button(label="← Назад", style=discord.ButtonStyle.secondary, row=2)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        activity_config = await _load_activity(interaction.guild.id)
        view = XpSetupView(interaction.guild, activity_config)
        view.message = interaction.message
        await interaction.response.edit_message(embed=_build_main_embed(interaction.guild, activity_config), view=view)

    async def on_timeout(self):
        if self.message is not None:
            try:
                await self.message.edit(view=None)
            except discord.HTTPException:
                pass


class XpSetupView(discord.ui.View):
    def __init__(self, guild: discord.Guild, activity_config: dict):
        super().__init__(timeout=180)
        self.guild = guild
        self.activity_config = activity_config
        self.message: discord.Message | None = None
        self.add_item(LevelUpChannelSelect(activity_config))
        self.toggle_ping_btn.label = f"Пінг: {'ВКЛ' if activity_config.get('levelup_ping_user', True) else 'ВИКЛ'}"
        self.toggle_ping_btn.emoji = discord.PartialEmoji.from_str(
            E_NOTIF if activity_config.get("levelup_ping_user", True) else E_NOTIF_OFF
        )
        self.toggle_opt_out_btn.label = f"Opt-out: {'ВКЛ' if activity_config.get('levelup_allow_opt_out', True) else 'ВИКЛ'}"

    @discord.ui.button(label="XP ставки", style=discord.ButtonStyle.secondary, emoji=discord.PartialEmoji.from_str(E_STATS), row=1)
    async def xp_rates_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(XpRatesModal(self.activity_config, interaction.message))

    @discord.ui.button(label="Пінг: ВКЛ", style=discord.ButtonStyle.secondary, emoji=discord.PartialEmoji.from_str(E_NOTIF), row=1)
    async def toggle_ping_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        activity_config = await _load_activity(interaction.guild.id)
        activity_config = await save_activity_updates(
            interaction.guild.id,
            {"levelup_ping_user": not activity_config.get("levelup_ping_user", True)},
        )
        view = XpSetupView(interaction.guild, activity_config)
        view.message = interaction.message
        await interaction.response.edit_message(embed=_build_main_embed(interaction.guild, activity_config), view=view)

    @discord.ui.button(label="Opt-out: ВКЛ", style=discord.ButtonStyle.secondary, row=1)
    async def toggle_opt_out_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        activity_config = await _load_activity(interaction.guild.id)
        activity_config = await save_activity_updates(
            interaction.guild.id,
            {"levelup_allow_opt_out": not activity_config.get("levelup_allow_opt_out", True)},
        )
        view = XpSetupView(interaction.guild, activity_config)
        view.message = interaction.message
        await interaction.response.edit_message(embed=_build_main_embed(interaction.guild, activity_config), view=view)

    @discord.ui.button(label="Вимкнути level-up", style=discord.ButtonStyle.danger, row=1)
    async def disable_channel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        activity_config = await save_activity_updates(interaction.guild.id, {"levelup_channel_id": None})
        view = XpSetupView(interaction.guild, activity_config)
        view.message = interaction.message
        await interaction.response.edit_message(embed=_build_main_embed(interaction.guild, activity_config), view=view)

    @discord.ui.button(label="Нагороди", style=discord.ButtonStyle.primary, emoji=discord.PartialEmoji.from_str(E_ROLE), row=2)
    async def rewards_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        activity_config = await _load_activity(interaction.guild.id)
        view = RewardRulesView(interaction.guild, activity_config)
        view.message = interaction.message
        await interaction.response.edit_message(embed=_build_rewards_embed(interaction.guild, activity_config), view=view)

    @discord.ui.button(label="Синхронізувати ролі", style=discord.ButtonStyle.secondary, emoji=discord.PartialEmoji.from_str(E_RELOAD), row=2)
    async def sync_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _sync_rewards(interaction, interaction.message)

    async def on_timeout(self):
        if self.message is not None:
            try:
                await self.message.edit(view=None)
            except discord.HTTPException:
                pass


class XpSetupCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="xp_setup", description="Налаштувати XP, level-up та ролі-нагороди")
    @app_commands.default_permissions(administrator=True)
    async def xp_setup_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        activity_config = await _load_activity(interaction.guild.id)
        view = XpSetupView(interaction.guild, activity_config)
        message = await interaction.followup.send(
            embed=_build_main_embed(interaction.guild, activity_config),
            view=view,
            ephemeral=True,
            wait=True,
        )
        view.message = message


async def setup(bot: commands.Bot):
    await bot.add_cog(XpSetupCog(bot))
