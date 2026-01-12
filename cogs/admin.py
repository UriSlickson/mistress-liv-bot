"""
Admin Cog - Administrative commands for server management
COMMANDS:
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

logger = logging.getLogger('MistressLIV.Admin')

# NFL Team data (colors only, no helmet emojis)
NFL_TEAMS = {
    'ARI': {'name': 'Cardinals', 'color': 0x97233F},
    'ATL': {'name': 'Falcons', 'color': 0xA71930},
    'BAL': {'name': 'Ravens', 'color': 0x241773},
    'BUF': {'name': 'Bills', 'color': 0x00338D},
    'CAR': {'name': 'Panthers', 'color': 0x0085CA},
    'CHI': {'name': 'Bears', 'color': 0x0B162A},
    'CIN': {'name': 'Bengals', 'color': 0xFB4F14},
    'CLE': {'name': 'Browns', 'color': 0x311D00},
    'DAL': {'name': 'Cowboys', 'color': 0x003594},
    'DEN': {'name': 'Broncos', 'color': 0xFB4F14},
    'DET': {'name': 'Lions', 'color': 0x0076B6},
    'GB': {'name': 'Packers', 'color': 0x203731},
    'HOU': {'name': 'Texans', 'color': 0x03202F},
    'IND': {'name': 'Colts', 'color': 0x002C5F},
    'JAX': {'name': 'Jaguars', 'color': 0x006778},
    'KC': {'name': 'Chiefs', 'color': 0xE31837},
    'LAC': {'name': 'Chargers', 'color': 0x0080C6},
    'LAR': {'name': 'Rams', 'color': 0x003594},
    'LV': {'name': 'Raiders', 'color': 0x000000},
    'MIA': {'name': 'Dolphins', 'color': 0x008E97},
    'MIN': {'name': 'Vikings', 'color': 0x4F2683},
    'NE': {'name': 'Patriots', 'color': 0x002244},
    'NO': {'name': 'Saints', 'color': 0xD3BC8D},
    'NYG': {'name': 'Giants', 'color': 0x0B2265},
    'NYJ': {'name': 'Jets', 'color': 0x125740},
    'PHI': {'name': 'Eagles', 'color': 0x004C54},
    'PIT': {'name': 'Steelers', 'color': 0xFFB612},
    'SEA': {'name': 'Seahawks', 'color': 0x002244},
    'SF': {'name': '49ers', 'color': 0xAA0000},
    'TB': {'name': 'Buccaneers', 'color': 0xD50A0A},
    'TEN': {'name': 'Titans', 'color': 0x0C2340},
    'WAS': {'name': 'Commanders', 'color': 0x5A1414},
}


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
            value="`/admin setup roles` `/admin setup payouts` `/league setup`",
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
    setup_group = app_commands.Group(name="setup", description="Server setup commands", parent=admin_group)
    
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
