import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import json
import asyncio
import aiohttp
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="?", intents=intents)

CONFIG_FILE = "tickets_config.json"
TICKETS_FILE = "tickets_data.json"

# ------------------ UTILITAIRES ------------------
def load_json(file):
    try:
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_json(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

# ------------------ STAFF LOGS ------------------
def get_staff_log_channel(guild: discord.Guild):
    return discord.utils.get(guild.text_channels, name="staff-logs")

async def send_staff_log(guild: discord.Guild, title: str, description: str, color=discord.Color.blue()):
    channel = get_staff_log_channel(guild)
    if not channel:
        return
    embed = discord.Embed(title=title, description=description, color=color, timestamp=discord.utils.utcnow())
    await channel.send(embed=embed)

# ------------------ TIME PARSER ------------------
def parse_time(timestr: str):
    if not timestr: return None
    unit = timestr[-1]
    try: amount = int(timestr[:-1])
    except: return None
    if unit == "s": return amount
    if unit == "m": return amount*60
    if unit == "h": return amount*3600
    if unit == "d": return amount*86400
    return None

async def get_or_create_mute_role(guild: discord.Guild):
    role = discord.utils.get(guild.roles, name="Muted")
    if not role:
        role = await guild.create_role(name="Muted", permissions=discord.Permissions(send_messages=False))
        for c in guild.channels:
            await c.set_permissions(role, send_messages=False, add_reactions=False)
    return role

# ------------------ SAY ------------------
@bot.tree.command(name="say", description="Faire parler le bot via modal")
@app_commands.describe(salon="Salon où envoyer le message")
@app_commands.checks.has_permissions(administrator=True)
async def say(interaction: discord.Interaction, salon: discord.TextChannel):
    class SayModal(discord.ui.Modal, title="Message à envoyer"):
        contenu = discord.ui.TextInput(label="Message", style=discord.TextStyle.paragraph, required=True)
        async def on_submit(self, inter: discord.Interaction):
            await salon.send(self.contenu.value)
            await inter.response.send_message(f"✅ Message envoyé dans {salon.mention}", ephemeral=True)
            await send_staff_log(interaction.guild, "💬 /say utilisé", f"Message envoyé par {interaction.user.mention} dans {salon.mention}:\n{self.contenu.value}")
    await interaction.response.send_modal(SayModal())

# ------------------ CREATE EMBED ------------------
@bot.tree.command(name="createembed", description="Créer un embed personnalisable")
@app_commands.describe(salon="Salon obligatoire", webhook="Webhook facultatif", mentions="Mentions facultatives")
@app_commands.checks.has_permissions(administrator=True)
async def createembed(interaction: discord.Interaction, salon: discord.TextChannel, webhook: str | None = None, mentions: str | None = None):
    class EmbedModal(discord.ui.Modal, title="Création d'Embed"):
        title_field = discord.ui.TextInput(label="Titre", required=True)
        description_field = discord.ui.TextInput(label="Description", style=discord.TextStyle.paragraph, required=True)
        footer_field = discord.ui.TextInput(label="Footer", required=False)
        image_field = discord.ui.TextInput(label="URL Image", required=False)
        thumbnail_field = discord.ui.TextInput(label="URL Thumbnail", required=False)
        color_field = discord.ui.TextInput(label="Couleur HEX (ex: #FF9900)", required=False)
        buttons_field = discord.ui.TextInput(label="Boutons (texte|URL, séparés par |)", required=False)
        async def on_submit(self, inter: discord.Interaction):
            color = discord.Color.default()
            if self.color_field.value:
                try: color = discord.Color(int(self.color_field.value.replace("#",""),16))
                except: await inter.response.send_message("❌ Couleur invalide.", ephemeral=True); return
            embed = discord.Embed(title=self.title_field.value, description=self.description_field.value, color=color)
            if self.footer_field.value: embed.set_footer(text=self.footer_field.value)
            if self.image_field.value: embed.set_image(url=self.image_field.value)
            if self.thumbnail_field.value: embed.set_thumbnail(url=self.thumbnail_field.value)
            if webhook:
                async with aiohttp.ClientSession() as session:
                    webhook_obj = discord.Webhook.from_url(webhook, session=session)
                    await webhook_obj.send(content=mentions or "", embed=embed)
                await inter.response.send_message(f"✅ Embed envoyé via webhook dans {salon.mention}", ephemeral=True)
            else:
                await salon.send(content=mentions or "", embed=embed)
                await inter.response.send_message(f"✅ Embed envoyé dans {salon.mention}", ephemeral=True)
            await send_staff_log(interaction.guild, "📄 Embed créé", f"Embed envoyé par {interaction.user.mention} dans {salon.mention}")
    await interaction.response.send_modal(EmbedModal())

    # ------------------ TICKETS PERSISTANTS ------------------
def load_ticket_settings():
    return load_json(CONFIG_FILE)

def save_ticket_settings(settings):
    save_json(CONFIG_FILE, settings)

def load_open_tickets():
    return load_json(TICKETS_FILE)

def save_open_tickets(data):
    save_json(TICKETS_FILE, data)

@bot.tree.command(name="ticketsconfig", description="Configurer le système de tickets")
@app_commands.describe(
    salon="Salon où mettre le message de ticket",
    titre="Titre",
    description="Description",
    bouton="Titre du bouton pour ouvrir le ticket",
    logs="Salon pour validation",
    category="Catégorie tickets"
)
@app_commands.checks.has_permissions(administrator=True)
async def ticketsconfig(interaction: discord.Interaction, salon: discord.TextChannel, titre: str, description: str, bouton: str, logs: discord.TextChannel, category: discord.CategoryChannel):
    settings = {"salon": salon.id, "titre": titre, "description": description, "bouton": bouton, "logs": logs.id, "category": category.id}
    save_ticket_settings(settings)

    class TicketButton(discord.ui.View):
        @discord.ui.button(label=bouton, style=discord.ButtonStyle.green)
        async def open_ticket(self, inter: discord.Interaction, button: discord.ui.Button):
            open_tickets = load_open_tickets()
            overwrites = {
                inter.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                inter.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                inter.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }
            ticket_channel = await inter.guild.create_text_channel(f"ticket-{inter.user.name}", category=category, overwrites=overwrites)
            await ticket_channel.send(f"🎫 Ticket ouvert pour {inter.user.mention}")
            open_tickets[str(ticket_channel.id)] = {"user": inter.user.id, "logs": logs.id}
            save_open_tickets(open_tickets)
            await inter.response.send_message(f"✅ Ticket créé : {ticket_channel.mention}", ephemeral=True)
            await send_staff_log(inter.guild, "🎫 Ticket créé", f"{inter.user.mention} a ouvert un ticket : {ticket_channel.mention}")

    embed = discord.Embed(title=titre, description=description, color=discord.Color.green())
    await salon.send(embed=embed, view=TicketButton())
    await interaction.response.send_message(f"✅ Configuration du ticket appliquée dans {salon.mention}", ephemeral=True)

# ------------------ FERMER UN TICKET ------------------
@bot.tree.command(name="close_ticket", description="Fermer un ticket")
@app_commands.checks.has_permissions(administrator=True)
async def close_ticket(interaction: discord.Interaction):
    open_tickets = load_open_tickets()
    channel_id = str(interaction.channel.id)
    if channel_id not in open_tickets:
        return await interaction.response.send_message("❌ Ce salon n'est pas un ticket.", ephemeral=True)
    ticket_info = open_tickets.pop(channel_id)
    save_open_tickets(open_tickets)
    await interaction.response.send_message("🔒 Ticket fermé. Suppression dans 5 secondes...", ephemeral=True)
    await send_staff_log(interaction.guild, "🔒 Ticket fermé", f"Ticket {interaction.channel.mention} fermé par {interaction.user.mention}")
    await asyncio.sleep(5)
    await interaction.channel.delete(reason=f"Ticket fermé par {interaction.user}")

# ------------------ PANEL STAFF ------------------
class StaffPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.refresh_buttons()

    def refresh_buttons(self):
        # Supprime tous les boutons existants
        self.clear_items()
        open_tickets = load_open_tickets()
        for ch_id, info in open_tickets.items():
            label = f"Ticket: {ch_id}"
            self.add_item(discord.ui.Button(label=label, style=discord.ButtonStyle.red, custom_id=f"close_{ch_id}"))

    @discord.ui.button(label="Rafraîchir", style=discord.ButtonStyle.secondary, row=1)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.refresh_buttons()
        await interaction.response.edit_message(view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        is_admin = any(role.permissions.administrator for role in interaction.user.roles)
        if not is_admin:
            await interaction.response.send_message("❌ Vous n'avez pas accès au panel staff.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type == discord.InteractionType.component:
        custom_id = interaction.data.get("custom_id")
        if custom_id and custom_id.startswith("close_"):
            ch_id = custom_id.replace("close_", "")
            open_tickets = load_open_tickets()
            if ch_id in open_tickets:
                channel = interaction.guild.get_channel(int(ch_id))
                if channel:
                    await channel.delete(reason=f"Fermeture par staff {interaction.user}")
                open_tickets.pop(ch_id)
                save_open_tickets(open_tickets)
                await interaction.response.send_message(f"✅ Ticket {ch_id} fermé par {interaction.user.mention}", ephemeral=True)
                await send_staff_log(interaction.guild, "🔒 Ticket fermé via panel", f"Ticket {ch_id} fermé par {interaction.user.mention}")
            else:
                await interaction.response.send_message("❌ Ticket déjà fermé ou inexistant.", ephemeral=True)

# ------------------ MODÉRATION ------------------
@bot.tree.command(name="ban", description="Bannir un utilisateur")
@app_commands.describe(user="Utilisateur à bannir", temps="Durée (facultatif, ex: 1d, 2h)", raison="Raison du ban")
@app_commands.checks.has_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, user: discord.Member, temps: str | None = None, raison: str | None = None):
    raison_text = raison or "Raison non donnée"
    await user.ban(reason=raison_text)
    embed = discord.Embed(title="⛔ Utilisateur banni", color=discord.Color.red(), timestamp=discord.utils.utcnow())
    embed.add_field(name="Utilisateur", value=user.mention, inline=True)
    embed.add_field(name="Par", value=interaction.user.mention, inline=True)
    embed.add_field(name="Raison", value=raison_text, inline=False)
    if temps:
        seconds = parse_time(temps)
        if seconds:
            await asyncio.sleep(seconds)
            await interaction.guild.unban(user, reason="Ban temporaire expiré")
            embed_temp = discord.Embed(title="✅ Ban temporaire terminé", color=discord.Color.green())
            embed_temp.add_field(name="Utilisateur", value=user.mention)
            await send_staff_log(interaction.guild, "Ban temporaire terminé", f"{user.mention} a été débanni automatiquement après {temps}")
    await interaction.response.send_message(embed=embed)
    await send_staff_log(interaction.guild, "⛔ Utilisateur banni", f"{user.mention} banni par {interaction.user.mention} | Raison : {raison_text}")

@bot.tree.command(name="unban", description="Débannir un utilisateur")
@app_commands.describe(user="Utilisateur à débannir")
@app_commands.checks.has_permissions(ban_members=True)
async def unban(interaction: discord.Interaction, user: discord.User):
    await interaction.guild.unban(user, reason=f"Débanni par {interaction.user}")
    embed = discord.Embed(title="✅ Utilisateur débanni", color=discord.Color.green(), timestamp=discord.utils.utcnow())
    embed.add_field(name="Utilisateur", value=user.mention)
    embed.add_field(name="Par", value=interaction.user.mention)
    await interaction.response.send_message(embed=embed)
    await send_staff_log(interaction.guild, "✅ Utilisateur débanni", f"{user.mention} débanni par {interaction.user.mention}")

@bot.tree.command(name="kick", description="Expulser un utilisateur")
@app_commands.describe(user="Utilisateur à expulser", raison="Raison (facultatif)")
@app_commands.checks.has_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, user: discord.Member, raison: str | None = None):
    raison_text = raison or "Raison non donnée"
    await user.kick(reason=raison_text)
    embed = discord.Embed(title="👢 Utilisateur expulsé", color=discord.Color.orange(), timestamp=discord.utils.utcnow())
    embed.add_field(name="Utilisateur", value=user.mention)
    embed.add_field(name="Par", value=interaction.user.mention)
    embed.add_field(name="Raison", value=raison_text)
    await interaction.response.send_message(embed=embed)
    await send_staff_log(interaction.guild, "👢 Utilisateur expulsé", f"{user.mention} expulsé par {interaction.user.mention} | Raison : {raison_text}")

@bot.tree.command(name="mute", description="Mute un utilisateur")
@app_commands.describe(user="Utilisateur à mute", temps="Durée obligatoire (ex: 10m, 1h)", raison="Raison (facultatif)")
@app_commands.checks.has_permissions(manage_roles=True)
async def mute(interaction: discord.Interaction, user: discord.Member, temps: str, raison: str | None = None):
    mute_role = await get_or_create_mute_role(interaction.guild)
    await user.add_roles(mute_role, reason=raison or "Raison non donnée")
    embed = discord.Embed(title="🔇 Utilisateur muté", color=discord.Color.dark_gray(), timestamp=discord.utils.utcnow())
    embed.add_field(name="Utilisateur", value=user.mention)
    embed.add_field(name="Par", value=interaction.user.mention)
    embed.add_field(name="Raison", value=raison or "Raison non donnée")
    embed.add_field(name="Durée", value=temps)
    await interaction.response.send_message(embed=embed)
    await send_staff_log(interaction.guild, "🔇 Utilisateur muté", f"{user.mention} mute par {interaction.user.mention} | Durée : {temps} | Raison : {raison or 'Raison non donnée'}")
    seconds = parse_time(temps)
    if seconds:
        await asyncio.sleep(seconds)
        await user.remove_roles(mute_role, reason="Mute temporaire expiré")
        await send_staff_log(interaction.guild, "✅ Mute terminé", f"{user.mention} a été unmute automatiquement après {temps}")

@bot.tree.command(name="unmute", description="Unmute un utilisateur")
@app_commands.describe(user="Utilisateur à unmute")
@app_commands.checks.has_permissions(manage_roles=True)
async def unmute(interaction: discord.Interaction, user: discord.Member):
    mute_role = await get_or_create_mute_role(interaction.guild)
    await user.remove_roles(mute_role, reason=f"Unmute par {interaction.user}")
    embed = discord.Embed(title="✅ Utilisateur unmute", color=discord.Color.green(), timestamp=discord.utils.utcnow())
    embed.add_field(name="Utilisateur", value=user.mention)
    embed.add_field(name="Par", value=interaction.user.mention)
    await interaction.response.send_message(embed=embed)
    await send_staff_log(interaction.guild, "✅ Utilisateur unmute", f"{user.mention} unmute par {interaction.user.mention}")

@bot.tree.command(name="purge", description="Supprimer un nombre de messages")
@app_commands.describe(nombre="Nombre de messages à supprimer")
@app_commands.checks.has_permissions(manage_messages=True)
async def purge(interaction: discord.Interaction, nombre: int):
    deleted = await interaction.channel.purge(limit=nombre)
    embed = discord.Embed(title="🧹 Messages supprimés", color=discord.Color.blurple(), timestamp=discord.utils.utcnow())
    embed.add_field(name="Nombre supprimé", value=str(len(deleted)))
    embed.add_field(name="Par", value=interaction.user.mention)
    await interaction.response.send_message(embed=embed)
    await send_staff_log(interaction.guild, "🧹 Purge", f"{len(deleted)} messages supprimés par {interaction.user.mention}")

@bot.tree.command(name="warn", description="Avertir un utilisateur")
@app_commands.describe(user="Utilisateur à avertir", raison="Raison de l'avertissement")
@app_commands.checks.has_permissions(kick_members=True)
async def warn(interaction: discord.Interaction, user: discord.Member, raison: str):
    embed = discord.Embed(title="⚠️ Avertissement", color=discord.Color.yellow(), timestamp=discord.utils.utcnow())
    embed.add_field(name="Utilisateur", value=user.mention)
    embed.add_field(name="Par", value=interaction.user.mention)
    embed.add_field(name="Raison", value=raison)
    await interaction.response.send_message(embed=embed)
    await send_staff_log(interaction.guild, "⚠️ Avertissement", f"{user.mention} averti par {interaction.user.mention} | Raison : {raison}")

# ------------------ POLL ------------------
@bot.tree.command(name="poll", description="Créer un sondage")
@app_commands.describe(salon="Salon obligatoire", mention="Mention facultative")
@app_commands.checks.has_permissions(administrator=True)
async def poll(interaction: discord.Interaction, salon: discord.TextChannel, mention: str | None = None):
    class PollModal(discord.ui.Modal, title="Création de sondage"):
        title_field = discord.ui.TextInput(label="Titre", required=True)
        question_field = discord.ui.TextInput(label="Question", style=discord.TextStyle.paragraph, required=True)
        options_field = discord.ui.TextInput(label="Options (séparées par |)", required=True)
        async def on_submit(self, inter: discord.Interaction):
            options = [opt.strip() for opt in self.options_field.value.split("|") if opt.strip()]
            if len(options) < 2 or len(options) > 10:
                await inter.response.send_message("❌ Le sondage doit avoir entre 2 et 10 options.", ephemeral=True)
                return
            embed = discord.Embed(title=self.title_field.value, description=self.question_field.value, color=discord.Color.blurple())
            for i, opt in enumerate(options, start=1):
                embed.add_field(name=f"{i}. {opt}", value="\u200b", inline=False)
            msg = await salon.send(content=mention or "", embed=embed)
            for i in range(len(options)):
                await msg.add_reaction(f"{i+1}\N{COMBINING ENCLOSING KEYCAP}")
            await inter.response.send_message(f"✅ Sondage créé dans {salon.mention}", ephemeral=True)
            await send_staff_log(inter.guild, "📊 Sondage créé", f"Sondage créé par {interaction.user.mention} dans {salon.mention}\nTitre : {self.title_field.value}")

    await interaction.response.send_modal(PollModal())

    # ------------------ PANEL ADMIN COMMANDES ------------------
class AdminPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    # ------------------ BAN ------------------
    @discord.ui.button(label="Ban", style=discord.ButtonStyle.danger, row=0)
    async def ban_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        class BanModal(discord.ui.Modal, title="Bannir un utilisateur"):
            user = discord.ui.TextInput(label="Utilisateur (@mention obligatoire)", required=True)
            raison = discord.ui.TextInput(label="Raison (facultatif)", required=False)
            temps = discord.ui.TextInput(label="Durée (facultatif, ex: 1d, 2h)", required=False)

            async def on_submit(self, inter: discord.Interaction):
                member = inter.guild.get_member_named(self.user.value.strip("@"))
                if not member:
                    await inter.response.send_message("❌ Utilisateur introuvable.", ephemeral=True)
                    return
                raison_text = self.raison.value or "Raison non donnée"
                await member.ban(reason=raison_text)
                embed = discord.Embed(title="⛔ Utilisateur banni", color=discord.Color.red())
                embed.add_field(name="Utilisateur", value=member.mention)
                embed.add_field(name="Par", value=inter.user.mention)
                embed.add_field(name="Raison", value=raison_text)
                await inter.response.send_message(embed=embed)
                await send_staff_log(inter.guild, "⛔ Utilisateur banni", f"{member.mention} banni par {inter.user.mention} | Raison : {raison_text}")
                # Ban temporaire si temps renseigné
                if self.temps.value:
                    seconds = parse_time(self.temps.value)
                    if seconds:
                        await asyncio.sleep(seconds)
                        await inter.guild.unban(member, reason="Ban temporaire expiré")
                        await send_staff_log(inter.guild, "✅ Ban temporaire terminé", f"{member.mention} débanni automatiquement après {self.temps.value}")

        await interaction.response.send_modal(BanModal())

    # ------------------ MUTE ------------------
    @discord.ui.button(label="Mute", style=discord.ButtonStyle.gray, row=0)
    async def mute_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        class MuteModal(discord.ui.Modal, title="Muter un utilisateur"):
            user = discord.ui.TextInput(label="Utilisateur (@mention obligatoire)", required=True)
            temps = discord.ui.TextInput(label="Durée (obligatoire, ex: 10m, 1h)", required=True)
            raison = discord.ui.TextInput(label="Raison (facultatif)", required=False)

            async def on_submit(self, inter: discord.Interaction):
                member = inter.guild.get_member_named(self.user.value.strip("@"))
                if not member:
                    await inter.response.send_message("❌ Utilisateur introuvable.", ephemeral=True)
                    return
                mute_role = await get_or_create_mute_role(inter.guild)
                await member.add_roles(mute_role, reason=self.raison.value or "Raison non donnée")
                embed = discord.Embed(title="🔇 Utilisateur muté", color=discord.Color.dark_gray())
                embed.add_field(name="Utilisateur", value=member.mention)
                embed.add_field(name="Par", value=inter.user.mention)
                embed.add_field(name="Raison", value=self.raison.value or "Raison non donnée")
                embed.add_field(name="Durée", value=self.temps.value)
                await inter.response.send_message(embed=embed)
                await send_staff_log(inter.guild, "🔇 Utilisateur muté", f"{member.mention} mute par {inter.user.mention} | Durée : {self.temps.value} | Raison : {self.raison.value or 'Raison non donnée'}")
                seconds = parse_time(self.temps.value)
                if seconds:
                    await asyncio.sleep(seconds)
                    await member.remove_roles(mute_role, reason="Mute temporaire expiré")
                    await send_staff_log(inter.guild, "✅ Mute terminé", f"{member.mention} a été unmute automatiquement après {self.temps.value}")

    # ------------------ WARN ------------------
    @discord.ui.button(label="Warn", style=discord.ButtonStyle.blurple, row=1)
    async def warn_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        class WarnModal(discord.ui.Modal, title="Avertir un utilisateur"):
            user = discord.ui.TextInput(label="Utilisateur (@mention obligatoire)", required=True)
            raison = discord.ui.TextInput(label="Raison obligatoire", required=True)

            async def on_submit(self, inter: discord.Interaction):
                member = inter.guild.get_member_named(self.user.value.strip("@"))
                if not member:
                    await inter.response.send_message("❌ Utilisateur introuvable.", ephemeral=True)
                    return
                embed = discord.Embed(title="⚠️ Avertissement", color=discord.Color.yellow())
                embed.add_field(name="Utilisateur", value=member.mention)
                embed.add_field(name="Par", value=inter.user.mention)
                embed.add_field(name="Raison", value=self.raison.value)
                await inter.response.send_message(embed=embed)
                await send_staff_log(inter.guild, "⚠️ Avertissement", f"{member.mention} averti par {inter.user.mention} | Raison : {self.raison.value}")

    # ------------------ UNBAN ------------------
    @discord.ui.button(label="Unban", style=discord.ButtonStyle.green, row=1)
    async def unban_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        class UnbanModal(discord.ui.Modal, title="Débannir un utilisateur"):
            user = discord.ui.TextInput(label="Utilisateur (@mention obligatoire)", required=True)

            async def on_submit(self, inter: discord.Interaction):
                user_obj = await bot.fetch_user(int(self.user.value.strip("<@!>")))
                await inter.guild.unban(user_obj, reason=f"Débanni par {inter.user}")
                embed = discord.Embed(title="✅ Utilisateur débanni", color=discord.Color.green())
                embed.add_field(name="Utilisateur", value=user_obj.mention)
                embed.add_field(name="Par", value=inter.user.mention)
                await inter.response.send_message(embed=embed)
                await send_staff_log(inter.guild, "✅ Utilisateur débanni", f"{user_obj.mention} débanni par {inter.user.mention}")

    # ------------------ UNMUTE ------------------
    @discord.ui.button(label="Unmute", style=discord.ButtonStyle.green, row=1)
    async def unmute_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        class UnmuteModal(discord.ui.Modal, title="Unmute utilisateur"):
            user = discord.ui.TextInput(label="Utilisateur (@mention obligatoire)", required=True)

            async def on_submit(self, inter: discord.Interaction):
                member = inter.guild.get_member_named(self.user.value.strip("@"))
                if not member:
                    await inter.response.send_message("❌ Utilisateur introuvable.", ephemeral=True)
                    return
                mute_role = await get_or_create_mute_role(inter.guild)
                await member.remove_roles(mute_role, reason=f"Unmute par {inter.user}")
                embed = discord.Embed(title="✅ Utilisateur unmute", color=discord.Color.green())
                embed.add_field(name="Utilisateur", value=member.mention)
                embed.add_field(name="Par", value=inter.user.mention)
                await inter.response.send_message(embed=embed)
                await send_staff_log(inter.guild, "✅ Utilisateur unmute", f"{member.mention} unmute par {inter.user.mention}")

# ------------------ COMMANDE POUR OUVRIR LE PANEL ------------------
@bot.tree.command(name="adminpanel", description="Ouvre le panel admin pour modération rapide")
@app_commands.checks.has_permissions(administrator=True)
async def adminpanel(interaction: discord.Interaction):
    embed = discord.Embed(title="🔧 Panel Admin", description="Utilisez les boutons ci-dessous pour exécuter des actions de modération", color=discord.Color.blurple())
    await interaction.response.send_message(embed=embed, view=AdminPanel())


# ------------------ READY ------------------
@bot.event
async def on_ready():
    print(f"{bot.user} est connecté et prêt !")
    # Synchronisation des commandes
    await bot.tree.sync()
    print("Commandes synchronisées !")

bot.run(TOKEN)
