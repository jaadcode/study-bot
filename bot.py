import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import asyncio
from discord.ui import View, button
import traceback

# ---- CONFIG ----
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

STUDY_ROLE_NAME = "Studying"

# ---- INTENTS ----
intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
active_sessions: dict[int, dict] = {}

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
        super().__init__(timeout=None)

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
        try:
            user_id = interaction.user.id
            
            print(f"📚 Button clicked by user {user_id} for {minutes} min")

            # Check for existing session
            if user_id in active_sessions:
                await interaction.response.send_message(
                    "⚠️ Tu as déjà une session en cours. Utilise `/stopstudying` pour l'arrêter.",
                    ephemeral=True
                )
                return

            # Respond IMMEDIATELY (must be within 3 seconds)
            await interaction.response.send_message(
                f"📚 Session de **{minutes} minutes** lancée ! Je t'enverrai un message quand ce sera terminé.",
                ephemeral=True
            )
            
            print(f"✅ Response sent to user {user_id}")

            # Now do the slower operations
            # Add role
            role = discord.utils.get(interaction.guild.roles, name=STUDY_ROLE_NAME)
            if role:
                try:
                    await interaction.user.add_roles(role)
                    print(f"✅ Role added to user {user_id}")
                except discord.Forbidden:
                    print(f"❌ Cannot add role to {interaction.user.name}")
                except Exception as e:
                    print(f"❌ Error adding role: {e}")

            # Create and store session
            task = asyncio.create_task(
                start_study(interaction.guild.id, user_id, minutes)
            )
            
            active_sessions[user_id] = {
                'task': task,
                'guild_id': interaction.guild.id,
                'minutes': minutes
            }
            
            print(f"✅ Session stored for user {user_id}")
            print(f"   Active sessions: {list(active_sessions.keys())}")
            
        except discord.errors.NotFound as e:
            print(f"❌ Interaction expired: {e}")
        except Exception as e:
            print(f"❌ Error in button handler: {e}")
            traceback.print_exc()

# ---- STUDY LOGIC ----
async def start_study(guild_id: int, user_id: int, minutes: int):
    try:
        print(f"⏳ Starting {minutes} min timer for user {user_id}")
        await asyncio.sleep(minutes * 60)
        print(f"✅ Timer completed for user {user_id}")
        # Session completed normally
        await cleanup(guild_id, user_id, cancelled=False)
    except asyncio.CancelledError:
        print(f"⏹️ Timer cancelled for user {user_id}")
        # Session was cancelled
        await cleanup(guild_id, user_id, cancelled=True)
    finally:
        removed = active_sessions.pop(user_id, None)
        print(f"🗑️ Session removed for user {user_id}: {removed is not None}")

# ---- CLEANUP ----
async def cleanup(guild_id: int, user_id: int, cancelled: bool = False):
    print(f"🧹 Cleanup started for user {user_id} (cancelled={cancelled})")
    
    guild = bot.get_guild(guild_id)
    if not guild:
        print(f"❌ Guild {guild_id} not found")
        return

    # Get member
    try:
        member = await guild.fetch_member(user_id)
    except discord.NotFound:
        print(f"❌ Member {user_id} not found")
        return
    except discord.HTTPException as e:
        print(f"❌ Error fetching member: {e}")
        return

    # Remove role
    role = discord.utils.get(guild.roles, name=STUDY_ROLE_NAME)
    if role and role in member.roles:
        try:
            await member.remove_roles(role)
            print(f"✅ Role removed from user {user_id}")
        except discord.Forbidden:
            print(f"❌ Cannot remove role from {member.name}")
        except Exception as e:
            print(f"❌ Error removing role: {e}")

    # Send DM
    try:
        if cancelled:
            await member.send("⏹️ Ta session d'étude a été annulée.")
        else:
            await member.send("✅ Ta session d'étude est terminée ! Bien joué ! 🎉")
        print(f"✅ DM sent to user {user_id}")
    except discord.Forbidden:
        print(f"❌ Cannot DM {member.name} - DMs disabled")
    except discord.HTTPException as e:
        print(f"❌ Error sending DM: {e}")

# ---- SLASH COMMANDS ----
@bot.tree.command(name="study", description="Démarre une session d'étude")
async def study(interaction: discord.Interaction):
    """Start a study session with duration selection"""
    try:
        # DEFER IMMEDIATELY - this prevents timeout
        await interaction.response.defer(ephemeral=True)
        
        print(f"📖 /study command used by user {interaction.user.id}")
        
        # Check if user already has a session
        if interaction.user.id in active_sessions:
            await interaction.followup.send(
                "⚠️ Tu as déjà une session en cours. Utilise `/stopstudying` pour l'arrêter d'abord.",
                ephemeral=True
            )
            return
        
        # Send followup with view
        await interaction.followup.send(
            "⏱️ Choisis la durée de ta session :",
            view=StudyView(),
            ephemeral=True
        )
        print(f"✅ Study view sent to user {interaction.user.id}")
        
    except discord.errors.NotFound as e:
        print(f"❌ Interaction expired in /study: {e}")
    except Exception as e:
        print(f"❌ Error in /study command: {e}")
        traceback.print_exc()

@bot.tree.command(name="stopstudying", description="Arrête ta session d'étude en cours")
async def stopstudying(interaction: discord.Interaction):
    """Stop the current study session"""
    try:
        # DEFER IMMEDIATELY - this prevents timeout
        await interaction.response.defer(ephemeral=True)
        
        user_id = interaction.user.id
        session = active_sessions.get(user_id)
        
        print(f"🔍 /stopstudying request from user {user_id}")
        print(f"   Active sessions: {list(active_sessions.keys())}")
        print(f"   Session found: {session is not None}")

        if not session:
            await interaction.followup.send(
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

        # Send followup message
        await interaction.followup.send(
            "⏹️ Session annulée.", 
            ephemeral=True
        )
            
    except Exception as e:
        print(f"❌ Error in /stopstudying command: {e}")
        traceback.print_exc()

@bot.tree.command(name="mystatus", description="Vérifie si tu as une session en cours")
async def mystatus(interaction: discord.Interaction):
    """Check your current study status"""
    try:
        # DEFER IMMEDIATELY - this prevents timeout
        await interaction.response.defer(ephemeral=True)
        
        session = active_sessions.get(interaction.user.id)
        
        if not session:
            await interaction.followup.send(
                "📖 Tu n'as pas de session en cours.",
                ephemeral=True
            )
        else:
            minutes = session['minutes']
            await interaction.followup.send(
                f"📚 Session de **{minutes} minutes** en cours...",
                ephemeral=True
            )
    except Exception as e:
        print(f"❌ Error in /mystatus command: {e}")
        traceback.print_exc()

# ---- ERROR HANDLING ----
@bot.event
async def on_command_error(ctx, error):
    print(f"❌ Command error: {error}")
    traceback.print_exc()

# ---- RUN ----
if __name__ == "__main__":
    print("🚀 Starting bot...")
    bot.run(TOKEN)