import discord
from discord.ext import commands
from discord import app_commands
import os
from dotenv import load_dotenv
import asyncio  # Import asyncio pour le mute temporaire

# --- Configuration ---
load_dotenv()  # Charge les variables d'environnement depuis .env
TOKEN = os.getenv('DISCORD_TOKEN')
       
# Définition des intents nécessaires
intents = discord.Intents.default()
intents.members = True  # Nécessaire pour accéder à la liste des membres et les gérer
intents.message_content = True  # Nécessaire pour lire le contenu des messages

# Initialisation du bot avec le préfixe "?"
bot = commands.Bot(command_prefix='?', intents=intents)

# --- Événements ---
@bot.event
async def on_ready():
    """S'exécute lorsque le bot est prêt et connecté à Discord."""
    try:
        # Synchronise les commandes slash
        synced = await bot.tree.sync()
        print(f"Synchronisé {len(synced)} commande(s) slash.")
        print(f'{bot.user.name} est connecté et prêt !')
        print(f'ID du bot : {bot.user.id}')
    except Exception as e:
        print(f'Erreur lors de la synchronisation des commandes : {e}')
@bot.event
async def on_ready():
    """S'exécute lorsque le bot est connecté et prêt."""
    print(f'{bot.user.name} est connecté et prêt !')
    print(f'ID du bot : {bot.user.id}')
    try:
        # Synchronise les commandes slash (si tu en as)
        synced = await bot.tree.sync()
        print(f"Synchronisé {len(synced)} commande(s) slash.")
    except Exception as e:
        print(f"Erreur lors de la synchronisation des commandes slash : {e}")

# --- Commandes Slash ---
@bot.tree.command(name="say", description="Fait dire quelque chose au bot.")
@app_commands.describe(message="Le message que le bot doit dire.")
async def say_command(interaction: discord.Interaction, message: str):
    """Commande slash pour faire dire un message au bot."""
    try:
        await interaction.response.send_message("Message envoyé !", ephemeral=True)  # Réponse éphémère à l'utilisateur
        await interaction.channel.send(message)  # Le bot envoie le message dans le canal
    except discord.errors.Forbidden:
        await interaction.followup.send("Je n'ai pas la permission d'envoyer des messages dans ce canal.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"Une erreur s'est produite : {e}", ephemeral=True)

# --- Commandes de Modération ---

@bot.command(name='ban')
@commands.has_permissions(ban_members=True)  # Vérifie si l'utilisateur a la permission de bannir
async def ban(ctx, member: discord.Member, *, reason=None):
    """Bannit un membre du serveur."""
    if member == ctx.author:
        await ctx.send('Vous ne pouvez pas vous bannir vous-même !')
        return
    if member.top_role >= ctx.author.top_role and ctx.author != bot.user:
        await ctx.send('Vous ne pouvez pas bannir une personne ayant un rôle supérieur ou égal au vôtre.')
        return

    try:
        await member.ban(reason=reason)
        await ctx.send(f'{member.mention} a été banni. Raison : {reason or "Non spécifiée"}')
        print(f'{ctx.author} a banni {member} pour la raison : {reason or "Non spécifiée"}')
    except discord.Forbidden:
        await ctx.send('Je n\'ai pas les permissions nécessaires pour bannir ce membre.')
    except Exception as e:
        await ctx.send(f'Une erreur est survenue lors du bannissement : {e}')

@bot.command(name='kick')
@commands.has_permissions(kick_members=True)  # Vérifie si l'utilisateur a la permission d'expulser
async def kick(ctx, member: discord.Member, *, reason=None):
    """Expulse un membre du serveur."""
    if member == ctx.author:
        await ctx.send('Vous ne pouvez pas vous expulser vous-même !')
        return
    if member.top_role >= ctx.author.top_role and ctx.author != bot.user:
        await ctx.send('Vous ne pouvez pas expulser une personne ayant un rôle supérieur ou égal au vôtre.')
        return

    try:
        await member.kick(reason=reason)
        await ctx.send(f'{member.mention} a été expulsé. Raison : {reason or "Non spécifiée"}')
        print(f'{ctx.author} a expulsé {member} pour la raison : {reason or "Non spécifiée"}')
    except discord.Forbidden:
        await ctx.send('Je n\'ai pas les permissions nécessaires pour expulser ce membre.')
    except Exception as e:
        await ctx.send(f'Une erreur est survenue lors de l\'expulsion : {e}')

@bot.command(name='mute')
@commands.has_permissions(manage_roles=True)  # Nécessite la permission de gérer les rôles
async def mute(ctx, member: discord.Member, duration: int, *, reason=None):
    """Mute un membre pendant une durée spécifiée (en minutes)."""
    guild = ctx.guild
    muted_role = discord.utils.get(guild.roles, name="Muted")

    if not muted_role:
        try:
            muted_role = await guild.create_role(name="Muted", reason="Rôle créé pour les mutes")
            for channel in guild.text_channels:
                await channel.set_permissions(muted_role, send_messages=False)
            for channel in guild.voice_channels:
                await channel.set_permissions(muted_role, speak=False, connect=False)
        except discord.Forbidden:
            await ctx.send("Je n'ai pas les permissions nécessaires pour créer le rôle Muted.")
            return

    if member == ctx.author:
        await ctx.send("Vous ne pouvez pas vous mute vous-même.")
        return
    if member.top_role >= ctx.author.top_role and ctx.author != bot.user:
        await ctx.send('Vous ne pouvez pas mute une personne ayant un rôle supérieur ou égal au vôtre.')
        return

    try:
        await member.add_roles(muted_role, reason=reason)
        await ctx.send(f"{member.mention} a été mute pendant {duration} minutes. Raison: {reason or 'Non spécifiée'}")
        print(f"{ctx.author} a mute {member} pendant {duration} minutes pour la raison: {reason or 'Non spécifiée'}")
    except discord.Forbidden:
        await ctx.send("Je n'ai pas les permissions nécessaires pour muter ce membre.")
        return
    except Exception as e:
        await ctx.send(f"Une erreur est survenue lors du mute : {e}")
        return

    # Démute après la durée spécifiée
    try:
        await asyncio.sleep(duration * 60)  # Convertit minutes en secondes
        await member.remove_roles(muted_role, reason="Durée du mute écoulée")
        await ctx.send(f"{member.mention} a été démute après {duration} minutes.")
        print(f"{member} a été démute après {duration} minutes.")
    except discord.NotFound:
        # Le membre a quitté le serveur pendant le mute
        print(f"Le membre {member} a quitté le serveur pendant le mute.")
    except Exception as e:
        await ctx.send(f"Une erreur est survenue lors du démute : {e}")
        print(f"Erreur lors du démute : {e}")

@bot.command(name='unban')
@commands.has_permissions(ban_members=True)
async def unban(ctx, user_id: int, *, reason=None):
    """Débannit un utilisateur du serveur en utilisant son ID."""
    try:
        user = await bot.fetch_user(user_id)
        if user is None:
            await ctx.send(f"Impossible de trouver l'utilisateur avec l'ID `{user_id}`.")
            return

        await ctx.guild.unban(user, reason=reason)
        await ctx.send(f'{user.mention} (ID: `{user_id}`) a été débanni. Raison : {reason or "Non spécifiée"}')
        print(f'{ctx.author} a débanni {user} (ID: {user_id}) pour la raison : {reason or "Non spécifiée"}')
    except discord.NotFound:
        await ctx.send(f'L\'utilisateur avec l\'ID `{user_id}` n\'est pas banni du serveur.')
    except discord.Forbidden:
        await ctx.send('Je n\'ai pas les permissions nécessaires pour débannir cet utilisateur.')
    except Exception as e:
        await ctx.send(f'Une erreur est survenue lors du débannissement : {e}')

# --- Lancement du bot ---
if TOKEN is None:
    print("Erreur : le token n'a pas été chargé. Vérifiez votre fichier .env.")
else:
    try:
        bot.run(TOKEN)
    except discord.errors.LoginFailure as e:
        if e.args[0] == 'Improper token has been passed.':
            print("Erreur : Token invalide. Vérifiez le token dans le fichier .env ou le portail des développeurs Discord.")
        else:
            print(f"Erreur de connexion : {e}")
    except Exception as e:
        print(f"Une erreur inattendue s'est produite : {e}")

        # Bot ready-up code
@bot.event # Decorator
async def on_ready():
    await bot.tree.sync() # Syncs the commands with Discord so that they can be displayed
    print(f"{bot.user} is online!") # Appears when the bot comes online

# Run the bot
bot.run(TOKEN) # This code uses your bot's token to run the bot
