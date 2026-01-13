import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import asyncio
from discord.ui import View, button

# ---- CONFIG ----
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

STUDY_ROLE_NAME = "Studying"

# ---- INTENTS ----
intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
active_sessions: dict[int, asyncio.Task] = {}

# ---- EVENTS ----
@bot.event
async def on_ready():
    print(f"✅ Connecté comme {bot.user}")
    await bot.tree.sync()

# ---- STUDY VIEW ----
class StudyView(View):
    def __init__(self):
        super().__init__(timeout=60)

    @button(label="20 min", style=discord.ButtonStyle.primary)
    async def study_20(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await self.start(interaction, 20)

    @button(label="40 min", style=discord.ButtonStyle.primary)
    async def study_40(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await self.start(interaction, 40)

    @button(label="60 min", style=discord.ButtonStyle.primary)
    async def study_60(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await self.start(interaction, 60)

    async def start(self, interaction: discord.Interaction, minutes: int):
        # ACK immédiat
        await interaction.response.defer(ephemeral=True)

        user_id = interaction.user.id

        if user_id in active_sessions:
            await interaction.followup.send(
                "⚠️ Tu as déjà une session en cours.", ephemeral=True
            )
            return

        role = discord.utils.get(
            interaction.guild.roles,
            name=STUDY_ROLE_NAME
        )
        if role:
            await interaction.user.add_roles(role)

        # Désactiver les boutons
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)

        task = asyncio.create_task(
            start_study(interaction.guild.id, user_id, minutes)
        )
        active_sessions[user_id] = task

        await interaction.followup.send(
            f"📚 Session de **{minutes} minutes** lancée.",
            ephemeral=True
        )

# ---- STUDY LOGIC ----
async def start_study(guild_id: int, user_id: int, minutes: int):
    try:
        await asyncio.sleep(minutes * 60)
    except asyncio.CancelledError:
        pass
    finally:
        await cleanup(guild_id, user_id)
        active_sessions.pop(user_id, None)

# ---- CLEANUP ----
async def cleanup(guild_id: int, user_id: int):
    guild = bot.get_guild(guild_id)
    if not guild:
        return

    try:
        member = await guild.fetch_member(user_id)
    except discord.NotFound:
        return

    role = discord.utils.get(guild.roles, name=STUDY_ROLE_NAME)
    if role and role in member.roles:
        await member.remove_roles(role)

    try:
        await member.send("✅ Ta session d’étude est terminée !")
    except discord.Forbidden:
        pass

# ---- SLASH COMMANDS ----
@bot.tree.command(name="study")
async def study(interaction: discord.Interaction):
    await interaction.response.send_message(
        "⏱️ Choisis la durée de ta session :",
        view=StudyView(),
        ephemeral=True
    )

@bot.tree.command(name="stopstudying")
async def stopstudying(interaction: discord.Interaction):
    task = active_sessions.pop(interaction.user.id, None)

    if not task:
        await interaction.response.send_message(
            "❌ Aucune session en cours.", ephemeral=True
        )
        return

    task.cancel()
    await cleanup(interaction.guild.id, interaction.user.id)

    await interaction.response.send_message(
        "⏹️ Session annulée.", ephemeral=True
    )

# ---- RUN ----
bot.run(TOKEN)