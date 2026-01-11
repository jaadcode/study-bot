import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import asyncio
from discord.ui import View

# ---- CONFIG ----
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

STUDY_ROLE_NAME = "Studying"
STUDY_VOICE_CHANNEL_NAME = "Etude 🤓"

# ---- INTENTS ----
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)
active_sessions: dict[int, asyncio.Task] = {}

# ---- EVENTS ----
@bot.event
async def on_ready():
    print(f"✅ Connecté comme {bot.user}")
    # Synchronisation des slash commands
    try:
        await bot.tree.sync()
        print("✅ Slash commands synchronisées !")
    except Exception as e:
        print(f"⚠️ Erreur lors de la synchronisation des slash commands : {e}")

# ---- TEST COMMAND ----
@bot.command()
async def hello(ctx):
    await ctx.send(f"Salut {ctx.author.mention} ! Je suis bien en ligne 😎")

# ---- STUDY VIEW ----
class StudyView(View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(label="20 min", style=discord.ButtonStyle.primary, custom_id="study_20")
    async def study_20(self, interaction: discord.Interaction, button: Button):
        await self.start_session(interaction, 20)

    @discord.ui.button(label="40 min", style=discord.ButtonStyle.primary, custom_id="study_40")
    async def study_40(self, interaction: discord.Interaction, button: Button):
        await self.start_session(interaction, 40)

    @discord.ui.button(label="60 min", style=discord.ButtonStyle.primary, custom_id="study_60")
    async def study_60(self, interaction: discord.Interaction, button: Button):
        await self.start_session(interaction, 60)

    async def start_session(self, interaction: discord.Interaction, minutes: int):
        # defer l'interaction immédiatement
        await interaction.response.defer(ephemeral=True)

        user_id = interaction.user.id
        if user_id in active_sessions:
            await interaction.followup.send("⚠️ Tu as déjà une session en cours.", ephemeral=True)
            return

        # Désactiver les boutons
        for child in self.children:
            child.disabled = True
        try:
            await interaction.message.edit(view=self)
        except discord.HTTPException:
            pass  # Message peut être introuvable ou supprimé

        # Lancer la session
        task = asyncio.create_task(start_study(interaction, minutes))
        active_sessions[user_id] = task


# ---- STUDY LOGIC ----
async def start_study(interaction: discord.Interaction, minutes: int):
    guild = interaction.guild
    member = interaction.user

    # ---- ROLE CHECK ----
    role = discord.utils.get(guild.roles, name=STUDY_ROLE_NAME)
    if not role:
        try:
            await interaction.response.send_message(
                "❌ Le rôle **Studying** n'existe pas.",
                ephemeral=True
            )
        except discord.errors.InteractionAlreadyResponded:
            await interaction.followup.send(
                "❌ Le rôle **Studying** n'existe pas.",
                ephemeral=True
            )
        active_sessions.pop(member.id, None)
        return

    # ---- VOICE CHANNEL ----
    study_channel = discord.utils.get(
        guild.voice_channels,
        name=STUDY_VOICE_CHANNEL_NAME
    )
    if not study_channel:
        try:
            await interaction.response.send_message(
                "❌ Le salon vocal **Étude 🤓** est introuvable.",
                ephemeral=True
            )
        except discord.errors.InteractionAlreadyResponded:
            await interaction.followup.send(
                "❌ Le salon vocal **Étude 🤓** est introuvable.",
                ephemeral=True
            )
        active_sessions.pop(member.id, None)
        return

    should_mute = False

    # ---- SI DEJA EN VOCAL ----
    if member.voice and member.voice.channel:
        if member.voice.channel.id != study_channel.id:
            try:
                await member.move_to(study_channel)
            except discord.Forbidden:
                try:
                    await interaction.followup.send(
                        "⚠️ Je n’ai pas la permission de te déplacer.\n"
                        "Rejoins **Étude 🤓** manuellement.",
                        ephemeral=True
                    )
                except discord.errors.InteractionAlreadyResponded:
                    pass
            except discord.HTTPException:
                try:
                    await interaction.followup.send(
                        "⚠️ Impossible de te déplacer (salon plein ou indisponible).",
                        ephemeral=True
                    )
                except discord.errors.InteractionAlreadyResponded:
                    pass
        should_mute = True
    else:
        try:
            await interaction.response.send_message(
                "ℹ️ Rejoins le salon **Étude 🤓** pour être automatiquement mute.",
                ephemeral=True
            )
        except discord.errors.InteractionAlreadyResponded:
            await interaction.followup.send(
                "ℹ️ Rejoins le salon **Étude 🤓** pour être automatiquement mute.",
                ephemeral=True
            )

    # ---- ROLE ----
    await member.add_roles(role)

    # ---- MUTE (UNIQUEMENT SI EN VOCAL) ----
    if should_mute:
        try:
            await member.edit(mute=True)
        except discord.Forbidden:
            pass

    try:
        await interaction.followup.send(
            f"📚 **Session d’étude lancée pour {minutes} minutes. Bon focus !**",
            ephemeral=True
        )
    except discord.errors.InteractionAlreadyResponded:
        pass

    # ---- TIMER ----
    try:
        await asyncio.sleep(minutes * 60)
    except asyncio.CancelledError:
        await cleanup(member)
        active_sessions.pop(member.id, None)
        return

    await cleanup(member)
    active_sessions.pop(member.id, None)

    try:
        await member.send("✅ **Ta session d’étude est terminée ! Bien joué 💪**")
    except discord.Forbidden:
        pass

# ---- CLEANUP ----
async def cleanup(member: discord.Member):
    role = discord.utils.get(member.guild.roles, name=STUDY_ROLE_NAME)
    if role and role in member.roles:
        await member.remove_roles(role)

    if member.voice:
        try:
            await member.edit(mute=False)
            await asyncio.sleep(0.5)  # éviter le rate limit
        except discord.Forbidden:
            pass

# ---- AUTO MUTE ON JOIN ----
@bot.event
async def on_voice_state_update(member, before, after):
    if after.channel and after.channel.name == STUDY_VOICE_CHANNEL_NAME:
        role = discord.utils.get(member.guild.roles, name=STUDY_ROLE_NAME)
        if role and role in member.roles:
            try:
                await member.edit(mute=True)
            except discord.Forbidden:
                pass

# ---- SLASH COMMANDS ----
@bot.tree.command(name="study", description="Démarre une session d'étude")
async def study(interaction: discord.Interaction):
    try:
        await interaction.response.send_message(
            "⏱️ **Choisis la durée de ta session d’étude :**",
            view=StudyView(),
            ephemeral=True
        )
    except discord.errors.InteractionAlreadyResponded:
        await interaction.followup.send(
            "⏱️ **Choisis la durée de ta session d’étude :**",
            view=StudyView(),
            ephemeral=True
        )

@bot.tree.command(name="stopstudying", description="Arrête ta session d'étude en cours")
async def stopstudying(interaction: discord.Interaction):
    user_id = interaction.user.id
    task = active_sessions.get(user_id)

    if not task:
        try:
            await interaction.response.send_message(
                "❌ Tu n’as pas de session en cours.",
                ephemeral=True
            )
        except discord.errors.InteractionAlreadyResponded:
            await interaction.followup.send(
                "❌ Tu n’as pas de session en cours.",
                ephemeral=True
            )
        return

    # Annule la tâche et cleanup
    task.cancel()
    await cleanup(interaction.user)
    active_sessions.pop(user_id, None)

    try:
        await interaction.response.send_message(
            "⏹️ **Ta session d’étude a été annulée et tu as été démute.**",
            ephemeral=True
        )
    except discord.errors.InteractionAlreadyResponded:
        await interaction.followup.send(
            "⏹️ **Ta session d’étude a été annulée et tu as été démute.**",
            ephemeral=True
        )

# ---- RUN BOT ----
bot.run(TOKEN)