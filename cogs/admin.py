"""
Admin Cog - Administrative commands for server management
CONSOLIDATED COMMANDS:
/admin helmet sync - Sync helmet for a member
/admin helmet syncall - Sync all helmets
/admin helmet remove - Remove helmet from member
/admin setup roles - Create team roles
/admin setup payouts - Create payouts channel
/help - Get help with commands
/ping - Check bot latency
/serverinfo - Get server info
"""

import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
from datetime import datetime
from typing import Optional
import logging
import re

logger = logging.getLogger('MistressLIV.Admin')

# NFL Team data with custom helmet emojis
NFL_TEAMS = {
    'ARI': {'name': 'Cardinals', 'emoji': '<:arihelmet:1458225274884849760>', 'color': 0x97233F},
    'ATL': {'name': 'Falcons', 'emoji': '<:atlhelmet:1458225284900851898>', 'color': 0xA71930},
    'BAL': {'name': 'Ravens', 'emoji': '<:balhelmet:1458225293029413029>', 'color': 0x241773},
    'BUF': {'name': 'Bills', 'emoji': '<:bufhelmet:1458225301019427121>', 'color': 0x00338D},
    'CAR': {'name': 'Panthers', 'emoji': '<:carhelmet:1458225309076684894>', 'color': 0x0085CA},
    'CHI': {'name': 'Bears', 'emoji': '<:chihelmet:1458225317071028390>', 'color': 0x0B162A},
    'CIN': {'name': 'Bengals', 'emoji': '<:cinhelmet:1458225325136679187>', 'color': 0xFB4F14},
    'CLE': {'name': 'Browns', 'emoji': '<:clehelmet:1458225333521223750>', 'color': 0x311D00},
    'DAL': {'name': 'Cowboys', 'emoji': '<:dalhelmet:1458225342287184059>', 'color': 0x003594},
    'DEN': {'name': 'Broncos', 'emoji': '<:denhelmet:1458225349321298123>', 'color': 0xFB4F14},
    'DET': {'name': 'Lions', 'emoji': '<:dethelmet:1458225356556337245>', 'color': 0x0076B6},
    'GB': {'name': 'Packers', 'emoji': '<:gbhelmet:1458225365217579190>', 'color': 0x203731},
    'HOU': {'name': 'Texans', 'emoji': '<:houhelmet:1458225372708737164>', 'color': 0x03202F},
    'IND': {'name': 'Colts', 'emoji': '<:indhelmet:1458225379473887405>', 'color': 0x002C5F},
    'JAX': {'name': 'Jaguars', 'emoji': '<:jaxhelmet:1458225387799843010>', 'color': 0x006778},
    'KC': {'name': 'Chiefs', 'emoji': '<:kchelmet:1458225396410482769>', 'color': 0xE31837},
    'LAC': {'name': 'Chargers', 'emoji': '<:lachelmet:1458225404589375548>', 'color': 0x0080C6},
    'LAR': {'name': 'Rams', 'emoji': '<:larhelmet:1458225412961468446>', 'color': 0x003594},
    'LV': {'name': 'Raiders', 'emoji': '<:lvhelmet:1458225420989108297>', 'color': 0x000000},
    'MIA': {'name': 'Dolphins', 'emoji': '<:miahelmet:1458225429684162712>', 'color': 0x008E97},
    'MIN': {'name': 'Vikings', 'emoji': '<:minhelmet:1458225438173167636>', 'color': 0x4F2683},
    'NE': {'name': 'Patriots', 'emoji': '<:nehelmet:1458225445249093805>', 'color': 0x002244},
    'NO': {'name': 'Saints', 'emoji': '<:nohelmet:1458225453503352855>', 'color': 0xD3BC8D},
    'NYG': {'name': 'Giants', 'emoji': '<:nyghelmet:1458225461686571192>', 'color': 0x0B2265},
    'NYJ': {'name': 'Jets', 'emoji': '<:nyjhelmet:1458225468917547170>', 'color': 0x125740},
    'PHI': {'name': 'Eagles', 'emoji': '<:phihelmet:1458225476219965492>', 'color': 0x004C54},
    'PIT': {'name': 'Steelers', 'emoji': '<:pithelmet:1458225488915988573>', 'color': 0xFFB612},
    'SEA': {'name': 'Seahawks', 'emoji': '<:seahelmet:1458225497036165234>', 'color': 0x002244},
    'SF': {'name': '49ers', 'emoji': '<:sfhelmet:1458225505726632222>', 'color': 0xAA0000},
    'TB': {'name': 'Buccaneers', 'emoji': '<:tbhelmet:1458225513305997314>', 'color': 0xD50A0A},
    'TEN': {'name': 'Titans', 'emoji': '<:tenhelmet:1458225521576906794>', 'color': 0x0C2340},
    'WAS': {'name': 'Commanders', 'emoji': '<:washelmet:1458225528879186097>', 'color': 0x5A1414},
}

HELMET_EMOJI_PATTERN = re.compile(r'^<:[a-z]+helmet:\d+>\s*')
LEGACY_EMOJIS = ['🦬', '🐬', '🏈', '✈️', '🐦‍⬛', '🐅', '🟤', '⚙️', '🤠', '🐴', '🐆', '⚔️',
                '🐎', '🪶', '☠️', '⚡', '⭐', '🗽', '🦅', '🎖️', '🐻', '🦁', '🧀', '⚜️',
                '🏴‍☠️', '🐦', '🐏', '⛏️']


def remove_helmet_from_name(name):
    """Remove any helmet emoji prefix from a name."""
    name = HELMET_EMOJI_PATTERN.sub('', name)
    for emoji in LEGACY_EMOJIS:
        if name.startswith(emoji + ' '):
            name = name[len(emoji) + 1:]
            break
        elif name.startswith(emoji):
            name = name[len(emoji):]
            break
    return name.strip()


class AdminCog(commands.Cog):
    """Cog for administrative commands."""
    
    def __init__(self, bot):
        self.bot = bot
        self.db_path = bot.db_path
    
    def get_db_connection(self):
        return sqlite3.connect(self.db_path)
    
    # ==================== STANDALONE COMMANDS ====================
    
    @app_commands.command(name="help", description="Get help with bot commands")
    async def help_command(self, interaction: discord.Interaction):
        """Display help information about bot commands."""
        embed = discord.Embed(
            title="🤖 Mistress LIV Bot - Help",
            description="Your comprehensive Madden league management bot!",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="💰 Payments",
            value="`/payments owedtome` `/payments iowe` `/payments status`",
            inline=False
        )
        embed.add_field(
            name="🎰 Wagers",
            value="`/wager` `/acceptwager` `/declinewager` `/mywagers` `/wagerwin`",
            inline=False
        )
        embed.add_field(
            name="🏈 Best Ball",
            value="`/bestball start` `/bestball join` `/bestball roster` `/bestball add`",
            inline=False
        )
        embed.add_field(
            name="📊 Profitability",
            value="`/profit view` `/profit mine` `/profit structure`",
            inline=False
        )
        embed.add_field(
            name="📜 League Info",
            value="`/rules` `/dynamics` `/requirements` `/payouts`",
            inline=False
        )
        embed.add_field(
            name="⚙️ Admin",
            value="`/admin helmet sync` `/admin setup roles` `/league setup`",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="ping", description="Check bot latency")
    async def ping(self, interaction: discord.Interaction):
        """Check the bot's latency."""
        latency = round(self.bot.latency * 1000)
        status = "🟢 Excellent" if latency < 100 else "🟡 Good" if latency < 200 else "🔴 High"
        
        embed = discord.Embed(
            title="🏓 Pong!",
            description=f"**Latency:** {latency}ms\n**Status:** {status}",
            color=discord.Color.green() if latency < 200 else discord.Color.red()
        )
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="serverinfo", description="Get server information")
    async def server_info(self, interaction: discord.Interaction):
        """Display server information."""
        guild = interaction.guild
        
        embed = discord.Embed(
            title=f"📊 {guild.name} Server Info",
            color=discord.Color.blue()
        )
        
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        
        embed.add_field(name="👥 Members", value=str(guild.member_count), inline=True)
        embed.add_field(name="📝 Channels", value=str(len(guild.channels)), inline=True)
        embed.add_field(name="🎭 Roles", value=str(len(guild.roles)), inline=True)
        embed.add_field(name="📅 Created", value=guild.created_at.strftime("%B %d, %Y"), inline=True)
        embed.add_field(name="👑 Owner", value=guild.owner.mention if guild.owner else "Unknown", inline=True)
        
        await interaction.response.send_message(embed=embed)

    # ==================== ADMIN COMMAND GROUP ====================
    
    admin_group = app_commands.Group(name="admin", description="Admin commands")
    helmet_group = app_commands.Group(name="helmet", description="Helmet emoji management", parent=admin_group)
    setup_group = app_commands.Group(name="setup", description="Server setup commands", parent=admin_group)
    
    @helmet_group.command(name="sync", description="Add helmet emoji to a member's nickname")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(member="The member to update")
    async def helmet_sync(self, interaction: discord.Interaction, member: discord.Member):
        """Sync a member's helmet emoji based on their team role."""
        team_role = None
        for role in member.roles:
            if role.name.upper() in NFL_TEAMS:
                team_role = role.name.upper()
                break
        
        base_name = remove_helmet_from_name(member.display_name)
        
        if team_role:
            team_data = NFL_TEAMS[team_role]
            new_nickname = f"{team_data['emoji']} {base_name}"
        else:
            new_nickname = base_name
            await interaction.response.send_message(
                f"ℹ️ {member.display_name} doesn't have a team role.",
                ephemeral=True
            )
            return
        
        try:
            if len(new_nickname) <= 32:
                await member.edit(nick=new_nickname if new_nickname != member.name else None)
                await interaction.response.send_message(
                    f"✅ Updated {member.mention}'s nickname to: **{new_nickname}**"
                )
            else:
                truncated = new_nickname[:32]
                await member.edit(nick=truncated)
                await interaction.response.send_message(
                    f"✅ Updated {member.mention}'s nickname to: **{truncated}** (truncated)"
                )
        except discord.Forbidden:
            await interaction.response.send_message(
                f"❌ Cannot change nickname - insufficient permissions",
                ephemeral=True
            )
    
    @helmet_group.command(name="syncall", description="Add helmet emojis to all registered team owners")
    @app_commands.default_permissions(administrator=True)
    async def helmet_syncall(self, interaction: discord.Interaction):
        """Sync helmet emojis for all registered team owners."""
        await interaction.response.defer()
        
        updated = 0
        failed = 0
        skipped = 0
        not_found = 0
        
        try:
            conn = sqlite3.connect('data/mistress_liv.db')
            cursor = conn.cursor()
            cursor.execute(
                "SELECT team_id, team_name, user_discord_id FROM teams WHERE user_discord_id IS NOT NULL"
            )
            registered_owners = cursor.fetchall()
            conn.close()
        except Exception as e:
            await interaction.followup.send(f"❌ Database error: {e}")
            return
        
        if not registered_owners:
            await interaction.followup.send("⚠️ No team owners registered!")
            return
        
        for team_id, team_name, user_id in registered_owners:
            try:
                member = await interaction.guild.fetch_member(user_id)
            except:
                not_found += 1
                continue
            
            if team_id.upper() not in NFL_TEAMS:
                continue
            
            team_data = NFL_TEAMS[team_id.upper()]
            base_name = remove_helmet_from_name(member.display_name)
            new_nickname = f"{team_data['emoji']} {base_name}"
            
            if member.display_name.startswith(team_data['emoji']):
                skipped += 1
                continue
            
            try:
                if len(new_nickname) <= 32:
                    await member.edit(nick=new_nickname if new_nickname != member.name else None)
                    updated += 1
                else:
                    await member.edit(nick=new_nickname[:32])
                    updated += 1
            except:
                failed += 1
        
        embed = discord.Embed(
            title="🏈 Helmet Sync Complete",
            color=discord.Color.green()
        )
        embed.add_field(name="✅ Updated", value=str(updated), inline=True)
        embed.add_field(name="⏭️ Already Set", value=str(skipped), inline=True)
        embed.add_field(name="❌ Failed", value=str(failed), inline=True)
        embed.add_field(name="🔍 Not Found", value=str(not_found), inline=True)
        
        await interaction.followup.send(embed=embed)
    
    @helmet_group.command(name="remove", description="Remove helmet emoji from a member's nickname")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(member="The member to update")
    async def helmet_remove(self, interaction: discord.Interaction, member: discord.Member):
        """Remove helmet emoji from a member's nickname."""
        base_name = remove_helmet_from_name(member.display_name)
        
        if base_name == member.display_name:
            await interaction.response.send_message(
                f"ℹ️ {member.display_name} doesn't have a helmet emoji.",
                ephemeral=True
            )
            return
        
        try:
            await member.edit(nick=base_name if base_name != member.name else None)
            await interaction.response.send_message(
                f"✅ Removed helmet from {member.mention}'s nickname: **{base_name}**"
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                f"❌ Cannot change nickname - insufficient permissions",
                ephemeral=True
            )
    
    @setup_group.command(name="roles", description="Create team roles with proper colors")
    @app_commands.default_permissions(administrator=True)
    async def setup_roles(self, interaction: discord.Interaction):
        """Create or update team roles with proper colors."""
        await interaction.response.defer()
        
        created = 0
        updated = 0
        
        for team_id, team_data in NFL_TEAMS.items():
            existing_role = discord.utils.get(interaction.guild.roles, name=team_id)
            
            if existing_role:
                if existing_role.color.value != team_data['color']:
                    try:
                        await existing_role.edit(color=discord.Color(team_data['color']))
                        updated += 1
                    except:
                        pass
            else:
                try:
                    await interaction.guild.create_role(
                        name=team_id,
                        color=discord.Color(team_data['color']),
                        reason="Mistress LIV Bot - Team role setup"
                    )
                    created += 1
                except:
                    pass
        
        embed = discord.Embed(
            title="🎨 Role Setup Complete",
            color=discord.Color.green()
        )
        embed.add_field(name="✅ Created", value=str(created), inline=True)
        embed.add_field(name="🔄 Updated", value=str(updated), inline=True)
        
        await interaction.followup.send(embed=embed)
    
    @setup_group.command(name="payouts", description="Create the payouts channel")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(category="The category to create the channel in")
    async def setup_payouts(
        self,
        interaction: discord.Interaction,
        category: Optional[discord.CategoryChannel] = None
    ):
        """Create a payouts channel with restricted permissions."""
        await interaction.response.defer()
        
        guild = interaction.guild
        
        existing = discord.utils.get(guild.text_channels, name="payouts")
        if existing:
            await interaction.followup.send(
                f"⚠️ A #payouts channel already exists: {existing.mention}",
                ephemeral=True
            )
            return
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=False,
                read_message_history=True,
                use_application_commands=True,
                add_reactions=False
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_messages=True,
                embed_links=True
            )
        }
        
        for role in guild.roles:
            if role.permissions.administrator:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    manage_messages=True,
                    use_application_commands=True
                )
        
        try:
            channel = await guild.create_text_channel(
                name="payouts",
                category=category,
                overwrites=overwrites,
                topic="💰 League payouts and payment tracking"
            )
            
            welcome_embed = discord.Embed(
                title="💰 League Payouts",
                description=(
                    "Welcome to the payouts channel!\n\n"
                    "**Available Commands:**\n"
                    "• `/payments owedtome` - See who owes you\n"
                    "• `/payments iowe` - See who you owe\n"
                    "• `/profit view` - View profitability leaderboard\n"
                    "• `/profit mine` - View your profit breakdown"
                ),
                color=discord.Color.gold()
            )
            
            await channel.send(embed=welcome_embed)
            
            await interaction.followup.send(
                f"✅ Created {channel.mention} with restricted permissions!"
            )
            
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ I don't have permission to create channels!",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error creating payouts channel: {e}")
            await interaction.followup.send(f"❌ An error occurred: {str(e)}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(AdminCog(bot))
