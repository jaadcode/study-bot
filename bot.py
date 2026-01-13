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
active_sessions: dict[int, dict] = {}  # Store more info about sessions

# ---- EVENTS ----
@bot.event
async def on_ready():
    print(f"✅ Connecté comme {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

# ---- STUDY VIEW ----
class StudyView(View):
    def __init__(self):
        super().__init__(timeout=None)  # No timeout - we'll manage state differently

    @button(label="20 min", style=discord.ButtonStyle.primary, custom_id="study_20")
    async def study_20(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await self.start(interaction, 20)

    @button(label="40 min", style=discord.ButtonStyle.primary, custom_id="study_40")
    async def study_40(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await self.start(interaction, 40)

    @button(label="60 min", style=discord.ButtonStyle.primary, custom_id="study_60")
    async def study_60(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await self.start(interaction, 60)

    async def start(self, interaction: discord.Interaction, minutes: int):
        user_id = interaction.user.id

        # Check for existing session
        if user_id in active_sessions:
            await interaction.response.send_message(
                "⚠️ Tu as déjà une session en cours. Utilise `/stopstudying` pour l'arrêter.",
                ephemeral=True
            )
            return

        # Add role FIRST
        role = discord.utils.get(interaction.guild.roles, name=STUDY_ROLE_NAME)
        if role:
            try:
                await interaction.user.add_roles(role)
            except discord.Forbidden:
                print(f"Cannot add role to {interaction.user.name}")

        # Create and store session BEFORE responding
        task = asyncio.create_task(
            start_study(interaction.guild.id, user_id, minutes)
        )
        
        active_sessions[user_id] = {
            'task': task,
            'guild_id': interaction.guild.id,
            'minutes': minutes
        }
        
        print(f"✅ Session started for user {user_id} ({minutes} min)")

        # Respond last
        await interaction.response.send_message(
            f"📚 Session de **{minutes} minutes** lancée ! Je t'enverrai un message quand ce sera terminé.",
            ephemeral=True
        )

# ---- STUDY LOGIC ----
async def start_study(guild_id: int, user_id: int, minutes: int):
    try:
        await asyncio.sleep(minutes * 60)
        # Session completed normally
        await cleanup(guild_id, user_id, cancelled=False)
    except asyncio.CancelledError:
        # Session was cancelled
        await cleanup(guild_id, user_id, cancelled=True)
    finally:
        active_sessions.pop(user_id, None)

# ---- CLEANUP ----
async def cleanup(guild_id: int, user_id: int, cancelled: bool = False):
    guild = bot.get_guild(guild_id)
    if not guild:
        return

    # Get member
    try:
        member = await guild.fetch_member(user_id)
    except discord.NotFound:
        return
    except discord.HTTPException as e:
        print(f"Error fetching member: {e}")
        return

    # Remove role
    role = discord.utils.get(guild.roles, name=STUDY_ROLE_NAME)
    if role and role in member.roles:
        try:
            await member.remove_roles(role)
        except discord.Forbidden:
            print(f"Cannot remove role from {member.name}")

    # Send DM
    try:
        if cancelled:
            await member.send("⏹️ Ta session d'étude a été annulée.")
        else:
            await member.send("✅ Ta session d'étude est terminée ! Bien joué ! 🎉")
    except discord.Forbidden:
        print(f"Cannot DM {member.name}")
    except discord.HTTPException as e:
        print(f"Error sending DM: {e}")

# ---- SLASH COMMANDS ----
@bot.tree.command(name="study", description="Démarre une session d'étude")
async def study(interaction: discord.Interaction):
    """Start a study session with duration selection"""
    
    # Check if user already has a session
    if interaction.user.id in active_sessions:
        await interaction.response.send_message(
            "⚠️ Tu as déjà une session en cours. Utilise `/stopstudying` pour l'arrêter d'abord.",
            ephemeral=True
        )
        return
    
    await interaction.response.send_message(
        "⏱️ Choisis la durée de ta session :",
        view=StudyView(),
        ephemeral=True
    )

@bot.tree.command(name="stopstudying", description="Arrête ta session d'étude en cours")
async def stopstudying(interaction: discord.Interaction):
    """Stop the current study session"""
    
    user_id = interaction.user.id
    session = active_sessions.get(user_id)
    
    print(f"🔍 Stop request from user {user_id}")
    print(f"   Active sessions: {list(active_sessions.keys())}")
    print(f"   Session found: {session is not None}")

    if not session:
        await interaction.response.send_message(
            "❌ Aucune session en cours.", 
            ephemeral=True
        )
        return

    # Cancel the task
    try:
        session['task'].cancel()
        print(f"✅ Task cancelled for user {user_id}")
    except Exception as e:
        print(f"❌ Error cancelling task: {e}")
    
    # Respond immediately
    await interaction.response.send_message(
        "⏹️ Session annulée.", 
        ephemeral=True
    )

@bot.tree.command(name="mystatus", description="Vérifie si tu as une session en cours")
async def mystatus(interaction: discord.Interaction):
    """Check your current study status"""
    
    session = active_sessions.get(interaction.user.id)
    
    if not session:
        await interaction.response.send_message(
            "📖 Tu n'as pas de session en cours.",
            ephemeral=True
        )
    else:
        minutes = session['minutes']
        await interaction.response.send_message(
            f"📚 Session de **{minutes} minutes** en cours...",
            ephemeral=True
        )

# ---- ERROR HANDLING ----
@bot.event
async def on_command_error(ctx, error):
    print(f"Command error: {error}")

# ---- RUN ----
if __name__ == "__main__":
    bot.run(TOKEN)