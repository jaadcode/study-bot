import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import os
from dotenv import load_dotenv
import asyncio
import traceback

# ---- CONFIG ----
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

STUDY_ROLE_NAME = "Studying"

# ---- INTENTS ----
intents = discord.Intents.default()
intents.members = True
intents.voice_states = True  # Required for voice channel operations

STUDY_VOICE_CHANNEL = "Etude 🤓"

bot = commands.Bot(command_prefix="!", intents=intents)

# ---- SESSION STORAGE ----
# Structure: {user_id: {'task': asyncio.Task, 'guild_id': int, 'minutes': int, 'locked': bool}}
active_sessions: dict[int, dict] = {}


# ---- EVENTS ----
@bot.event
async def on_ready():
    print(f"✅ Connecté comme {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"✅ {len(synced)} commande(s) synchronisée(s)")
    except Exception as e:
        print(f"❌ Échec de la synchronisation: {e}")


# ---- HELPER FUNCTIONS ----
async def get_study_role(guild: discord.Guild) -> discord.Role | None:
    """Get the study role from the guild"""
    return discord.utils.get(guild.roles, name=STUDY_ROLE_NAME)


async def add_study_role(member: discord.Member) -> bool:
    """Add the study role to a member"""
    role = await get_study_role(member.guild)
    if not role:
        print(f"❌ Rôle '{STUDY_ROLE_NAME}' introuvable")
        return False
    
    try:
        await member.add_roles(role)
        print(f"✅ Rôle ajouté à {member.name}")
        return True
    except discord.Forbidden:
        print(f"❌ Permission refusée pour ajouter le rôle à {member.name}")
        return False
    except Exception as e:
        print(f"❌ Erreur lors de l'ajout du rôle: {e}")
        return False


async def remove_study_role(member: discord.Member) -> bool:
    """Remove the study role from a member"""
    role = await get_study_role(member.guild)
    if not role or role not in member.roles:
        return True
    
    try:
        await member.remove_roles(role)
        print(f"✅ Rôle retiré de {member.name}")
        return True
    except discord.Forbidden:
        print(f"❌ Permission refusée pour retirer le rôle de {member.name}")
        return False
    except Exception as e:
        print(f"❌ Erreur lors du retrait du rôle: {e}")
        return False


async def get_study_voice_channel(guild: discord.Guild) -> discord.VoiceChannel | None:
    """Get the study voice channel from the guild"""
    return discord.utils.get(guild.voice_channels, name=STUDY_VOICE_CHANNEL)


async def move_member_to_study_channel(member: discord.Member) -> bool:
    """Move a member to the study voice channel if they're in another VC"""
    study_vc = await get_study_voice_channel(member.guild)
    if not study_vc:
        print(f"❌ Salon vocal '{STUDY_VOICE_CHANNEL}' introuvable")
        return False
    
    # Check if user is in a voice channel but not the study one
    if member.voice and member.voice.channel and member.voice.channel != study_vc:
        try:
            await member.move_to(study_vc)
            print(f"✅ {member.name} déplacé vers {STUDY_VOICE_CHANNEL}")
            return True
        except discord.Forbidden:
            print(f"❌ Permission refusée pour déplacer {member.name}")
            return False
        except Exception as e:
            print(f"❌ Erreur lors du déplacement: {e}")
            return False
    
    return True


# ---- MODALS ----
class DurationModal(Modal, title="Durée de la session"):
    """Modal for entering custom study duration"""
    
    minutes_input = TextInput(
        label="Durée (en minutes)",
        placeholder="Ex: 25, 45, 90...",
        required=True,
        min_length=1,
        max_length=3
    )
    
    def __init__(self, lock_session: bool = False):
        super().__init__()
        self.lock_session = lock_session
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Parse and validate minutes
            minutes = int(self.minutes_input.value)
            
            if minutes < 1:
                await interaction.response.send_message(
                    "❌ La durée doit être au moins 1 minute.",
                    ephemeral=True
                )
                return
            
            if minutes > 300:  # Max 5 hours
                await interaction.response.send_message(
                    "❌ La durée maximale est de 300 minutes (5 heures).",
                    ephemeral=True
                )
                return
            
            # Start the session
            await self.start_session(interaction, minutes)
            
        except ValueError:
            await interaction.response.send_message(
                "❌ Veuillez entrer un nombre valide.",
                ephemeral=True
            )
    
    async def start_session(self, interaction: discord.Interaction, minutes: int):
        """Start the study session"""
        user_id = interaction.user.id
        guild = interaction.guild
        member = interaction.user
        
        print(f"📚 Durée sélectionnée: {minutes} min par {member.name} (verrouillée={self.lock_session})")
        
        # Check for existing session
        if user_id in active_sessions:
            await interaction.response.send_message(
                "⚠️ Tu as déjà une session en cours. Utilise `/stopstudy` pour l'arrêter.",
                ephemeral=True
            )
            return
        
        # Respond immediately
        lock_msg = "🔒 **Session verrouillée** - tu ne pourras pas l'arrêter avant la fin !" if self.lock_session else ""
        await interaction.response.send_message(
            f"📚 Session de **{minutes} minutes** lancée ! Bon courage 💪\n{lock_msg}",
            ephemeral=True
        )
        
        # Add study role
        await add_study_role(member)
        
        # Move to study channel if in another VC
        await move_member_to_study_channel(member)
        
        # Create study session task
        task = asyncio.create_task(
            run_study_session(guild.id, user_id, minutes)
        )
        
        # Store session
        active_sessions[user_id] = {
            'task': task,
            'guild_id': guild.id,
            'minutes': minutes,
            'locked': self.lock_session
        }
        
        print(f"✅ Session enregistrée pour {member.name}")
        print(f"   Sessions actives: {list(active_sessions.keys())}")


# ---- VIEWS ----
class LockWarningView(View):
    """View for confirming session lock"""
    
    def __init__(self):
        super().__init__(timeout=60)
    
    @discord.ui.button(label="✅ Oui, verrouiller", style=discord.ButtonStyle.danger, custom_id="lock_yes")
    async def btn_yes(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(DurationModal(lock_session=True))
    
    @discord.ui.button(label="❌ Non, laisser déverrouillé", style=discord.ButtonStyle.secondary, custom_id="lock_no")
    async def btn_no(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(DurationModal(lock_session=False))


# ---- SESSION LOGIC ----
async def run_study_session(guild_id: int, user_id: int, minutes: int):
    """Run the study session timer"""
    try:
        print(f"⏳ Timer de {minutes} min démarré pour user {user_id}")
        await asyncio.sleep(minutes * 60)
        print(f"✅ Timer terminé pour user {user_id}")
        
        # Session completed normally
        await end_session(guild_id, user_id, cancelled=False)
        
    except asyncio.CancelledError:
        print(f"⏹️ Timer annulé pour user {user_id}")
        # Session was cancelled
        await end_session(guild_id, user_id, cancelled=True)


async def end_session(guild_id: int, user_id: int, cancelled: bool = False):
    """End a study session and clean up"""
    print(f"🧹 Fin de session pour user {user_id} (annulée={cancelled})")
    
    # Get session data before removing
    session = active_sessions.pop(user_id, None)
    if not session:
        print(f"⚠️ Aucune session trouvée pour user {user_id}")
        return
    
    guild = bot.get_guild(guild_id)
    if not guild:
        print(f"❌ Serveur {guild_id} introuvable")
        return
    
    # Get member
    try:
        member = await guild.fetch_member(user_id)
    except discord.NotFound:
        print(f"❌ Membre {user_id} introuvable")
        return
    except discord.HTTPException as e:
        print(f"❌ Erreur lors de la récupération du membre: {e}")
        return
    
    # Remove study role
    await remove_study_role(member)
    
    # Send DM
    try:
        if cancelled:
            await member.send("⏹️ Session annulée. J'espère que t'as bien étudié mon mignon 📚")
        else:
            await member.send("✅ Ta session est terminée, bien ouej ! 🎉")
        print(f"✅ DM envoyé à {member.name}")
    except discord.Forbidden:
        print(f"❌ Impossible d'envoyer un DM à {member.name}")
    except discord.HTTPException as e:
        print(f"❌ Erreur lors de l'envoi du DM: {e}")


# ---- SLASH COMMANDS ----
@bot.tree.command(name="study", description="Démarre une session d'étude")
async def study(interaction: discord.Interaction):
    """Start a study session with custom duration"""
    try:
        user_id = interaction.user.id
        print(f"📖 /study utilisé par {interaction.user.name}")
        
        # Check for existing session
        if user_id in active_sessions:
            await interaction.response.send_message(
                "⚠️ Tu as déjà une session en cours. Utilise `/stopstudy` pour l'arrêter d'abord.",
                ephemeral=True
            )
            return
        
        # Show lock warning
        await interaction.response.send_message(
            "🔒 **Veux-tu verrouiller cette session ?**\n\n"
            "Si tu verrouilles, tu ne pourras **pas** utiliser `/stopstudy` pour l'arrêter avant la fin.\n"
            "Cela t'aidera à rester concentré sans tentation d'abandonner ! 💪",
            view=LockWarningView(),
            ephemeral=True
        )
        
    except Exception as e:
        print(f"❌ Erreur dans /study: {e}")
        traceback.print_exc()


@bot.tree.command(name="stopstudy", description="Arrête ta session d'étude en cours")
async def stopstudy(interaction: discord.Interaction):
    """Stop the current study session"""
    try:
        user_id = interaction.user.id
        print(f"🔍 /stopstudy par {interaction.user.name}")
        
        session = active_sessions.get(user_id)
        
        if not session:
            await interaction.response.send_message(
                "❌ Aucune session en cours.",
                ephemeral=True
            )
            return
        
        # Check if session is locked
        if session.get('locked', False):
            await interaction.response.send_message(
                "🔒 Cette session est verrouillée ! Tu dois attendre la fin du timer.\n"
                "Allez, tu peux le faire ! 💪",
                ephemeral=True
            )
            return
        
        # Cancel the task (this triggers end_session via CancelledError)
        if session.get('task'):
            session['task'].cancel()
        
        await interaction.response.send_message(
            "⏹️ Session annulée.",
            ephemeral=True
        )
        
    except Exception as e:
        print(f"❌ Erreur dans /stopstudy: {e}")
        traceback.print_exc()


@bot.tree.command(name="mystatus", description="Vérifie si tu as une session en cours")
async def mystatus(interaction: discord.Interaction):
    """Check your current study status"""
    try:
        session = active_sessions.get(interaction.user.id)
        
        if not session:
            await interaction.response.send_message(
                "📖 Tu n'as pas de session en cours.",
                ephemeral=True
            )
        else:
            minutes = session['minutes']
            locked_status = "🔒 Verrouillée" if session.get('locked', False) else "🔓 Déverrouillée"
            await interaction.response.send_message(
                f"📚 Session de **{minutes} minutes** en cours...\n{locked_status}",
                ephemeral=True
            )
            
    except Exception as e:
        print(f"❌ Erreur dans /mystatus: {e}")
        traceback.print_exc()


# ---- ERROR HANDLING ----
@bot.event
async def on_command_error(ctx, error):
    print(f"❌ Erreur de commande: {error}")
    traceback.print_exc()


# ---- RUN ----
if __name__ == "__main__":
    print("🚀 Démarrage du bot...")
    print(f"🎭 Rôle: {STUDY_ROLE_NAME}")
    print(f"🔊 Salon vocal: {STUDY_VOICE_CHANNEL}")
    bot.run(TOKEN)