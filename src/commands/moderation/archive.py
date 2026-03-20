"""
archive.py
Команда для перенесення повідомлень з одного каналу в інший (або гілку).
Використовує Webhooks для імітації авторів повідомлень (ніків та аватарок).
"""
from __future__ import annotations

import asyncio
import discord
from discord import app_commands
from discord.ext import commands

class ArchiveSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="export", description="Перенести історію (клонувати повідомлення та медіа) з одного чату в інший.")
    @app_commands.describe(
        from_channel="Канал, З якого копіюємо",
        to_channel="Канал або Гілка, КУДИ копіюємо",
        limit="Скільки останніх повідомлень скопіювати (макс 1000)"
    )
    @app_commands.default_permissions(administrator=True)
    async def export_chat(
        self, 
        interaction: discord.Interaction, 
        from_channel: discord.TextChannel | discord.Thread | discord.VoiceChannel,
        to_channel: discord.TextChannel | discord.Thread | discord.VoiceChannel,
        limit: int = 100
    ):
        if limit > 2000:
            await interaction.response.send_message("<:cutiex:1480246146076119132> Ліміт не може перевищувати 2000 повідомлень за раз (захист від спам-лімітів).", ephemeral=True)
            return
            
        if from_channel.id == to_channel.id:
            await interaction.response.send_message("<:cutiex:1480246146076119132> Канали джерела і призначення не можуть збігатися.", ephemeral=True)
            return

        # Валідація вебхуку (вебхуки створюються ТІЛЬКИ на TextChannel або NewsChannel)
        # Якщо to_channel це Thread - вебхук має бути на батьківському каналі, 
        # а надсилатися з параметром thread=...
        
        target_channel_for_webhook = to_channel
        target_thread = discord.utils.MISSING
        
        if isinstance(to_channel, discord.Thread):
            target_channel_for_webhook = to_channel.parent
            target_thread = to_channel
            
        if not isinstance(target_channel_for_webhook, discord.TextChannel):
            await interaction.response.send_message("<:cutiex:1480246146076119132> Вебхуки підтримуються тільки у текстових каналах або гілках текстових каналів.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        # 1. Знаходимо або створюємо Вебхук
        webhook = None
        webhooks = await target_channel_for_webhook.webhooks()
        for wh in webhooks:
            if wh.name == "Vangard Archiver":
                webhook = wh
                break
                
        if not webhook:
            try:
                webhook = await target_channel_for_webhook.create_webhook(name="Vangard Archiver", reason="Created for chat export")
            except discord.Forbidden:
                await interaction.followup.send("<:cutiex:1480246146076119132> У бота немає прав керувати вебхуками в цільовому каналі.", ephemeral=True)
                return
                
        # 2. Отримуємо історію повідомлень з from_channel
        await interaction.followup.send(f"🔄 Починаю завантаження останніх {limit} повідомлень з {from_channel.mention}...", ephemeral=True)
        
        messagesToExport = []
        try:
            # oldest_first=True, щоб при копіюванні вони йшли в правильному хронологічному порядку.
            # Якщо ми копіюємо limit=10, нам треба взяти 10 НАЙНОВІШИХ повідомлень, 
            # але відправити їх в хронологічному порядку (від старішого до нового).
            # Discord API: history(limit=limit) повертає Х найновіших від найновішого до найстарішого.
            history = [msg async for msg in from_channel.history(limit=limit)]
            messagesToExport = history[::-1] # Реверсуємо, щоб старіші були першими
        except discord.Forbidden:
            await interaction.followup.send("<:cutiex:1480246146076119132> У бота немає прав читати історію в початковому каналі.", ephemeral=True)
            return

        if not messagesToExport:
            await interaction.followup.send("<:cutiex:1480246146076119132> В цьому каналі немає жодного повідомлення.", ephemeral=True)
            return

        # Робимо прогрес-бар
        total = len(messagesToExport)
        progress_msg = await interaction.followup.send(f"<:Hourglass:1479950504321745026> Скопійовано: 0/{total}... (це може зайняти хвилину)", ephemeral=True, wait=True)
        
        success = 0
        failed = 0

        # 3. Ітеруємо і відправляємо
        for i, msg in enumerate(messagesToExport):
            # Підготовка контенту
            content = msg.content
            
            # Якщо є файли - ми не качаємо їх, а просто кидаємо посиланням в текст
            # Discord сам розгорне їх як фото/відео
            attached_urls = [a.url for a in msg.attachments]
            if attached_urls:
                content += "\n" + "\n".join(attached_urls)
                
            # Запобігання порожнім повідомленням (наприклад, системні або тільки стікери)
            if not content and not msg.embeds:
                if msg.system_content:
                    content = f"*[Системне повідомлення: {msg.system_content}]*"
                else:
                    content = "*[Повідомлення не підтримується для експорту]*"

            # Автор
            username = msg.author.display_name
            avatar_url = msg.author.display_avatar.url if msg.author.display_avatar else None

            # Відправляємо через вебхук
            try:
                await webhook.send(
                    content=content,
                    username=username,
                    avatar_url=avatar_url,
                    embeds=msg.embeds,
                    thread=target_thread
                )
                success += 1
            except Exception as e:
                print(f"[Archiver] Помилка копіювання MSG_ID {msg.id}: {e}")
                failed += 1

            # Кожні 10 повідомлень оновлюємо прогрес-бар (і робимо паузу від Rate Limits)
            # Discord Webhook має ліміт 5 req/2s. Дамо 0.6 сек на кожне = 1.6 req/s, дуже безпечно.
            await asyncio.sleep(0.6)
            
            if (i + 1) % 10 == 0:
                try:
                    await progress_msg.edit(content=f"<:Hourglass:1479950504321745026> Скопійовано: {i+1}/{total}...")
                except:
                    pass

        # 4. Фінал
        await progress_msg.edit(content=f"<:cutiecheckmark:1479120440734650389> Експорт завершено!\nУспішно: **{success}**\nПомилок: **{failed}**\nПеревірте канал {to_channel.mention}.")

async def setup(bot):
    await bot.add_cog(ArchiveSystem(bot))
