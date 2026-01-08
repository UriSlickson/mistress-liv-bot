"""
Admin Cog - Administrative commands for server management
Features:
- Helmet logo management
- Role synchronization
- Server aesthetics
- Help commands
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
import sqlite3
from datetime import datetime
from typing import Optional
import logging
import re

logger = logging.getLogger('MistressLIV.Admin')

# NFL Team data with custom helmet emojis (uploaded to server)
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

# Regex pattern to match custom Discord emojis in nicknames
HELMET_EMOJI_PATTERN = re.compile(r'^<:[a-z]+helmet:\d+>\s*')

# Legacy Unicode emojis (for backwards compatibility when removing)
LEGACY_EMOJIS = ['🦬', '🐬', '🏈', '✈️', '🐦‍⬛', '🐅', '🟤', '⚙️', '🤠', '🐴', '🐆', '⚔️',
                '🐎', '🪶', '☠️', '⚡', '⭐', '🗽', '🦅', '🎖️', '🐻', '🦁', '🧀', '⚜️',
                '🏴‍☠️', '🐦', '🐏', '⛏️']


def remove_helmet_from_name(name):
    """Remove any helmet emoji prefix from a name."""
    # Remove custom emoji pattern (e.g., <:bufhelmet:123456789>)
    name = HELMET_EMOJI_PATTERN.sub('', name)
    
    # Also remove any legacy Unicode emoji prefixes
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
        """Get a database connection."""
        return sqlite3.connect(self.db_path)
    
    @app_commands.command(name="help", description="Get help with bot commands")
    async def help_command(self, interaction: discord.Interaction):
        """Display help information about bot commands."""
        embed = discord.Embed(
            title="🤖 Mistress LIV Bot - Help",
            description="Your comprehensive Madden league management bot!",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        # Payment Commands
        embed.add_field(
            name="💰 Payment Commands",
            value=(
                "`/setpayment` - Set your payment methods (Venmo, Cash App, etc.)\n"
                "`/mypayments` - View your payment info and balances\n"
                "`/paymentinfo @user` - Look up someone's payment info\n"
                "`/markpaid @user amount` - Mark a payment as completed\n"
                "`/confirmpaid @user amount` - Confirm you received payment\n"
                "`/dues` - View the season dues tracker"
            ),
            inline=False
        )
        
        # Wager Commands
        embed.add_field(
            name="🎰 Wager Commands",
            value=(
                "`/wager @opponent amount` - Create a wager for your game\n"
                "`/mywagers` - View your active wagers\n"
                "`/markwagerpaid week` - Mark a wager as paid\n"
                "`/wagerboard` - View the wager leaderboard"
            ),
            inline=False
        )
        
        # Stats Commands
        embed.add_field(
            name="📊 Stats Commands",
            value=(
                "`/mystats` - View your franchise statistics\n"
                "`/leaderboard [category]` - View franchise leaderboards\n"
                "`/halloffame` - View the Hall of Fame\n"
                "`/compare @user1 @user2` - Compare two users' stats"
            ),
            inline=False
        )
        
        # Recruitment Commands
        embed.add_field(
            name="📢 Recruitment Commands",
            value=(
                "`/openteams` - View currently open teams\n"
                "`/recruitpreview` - Preview the recruitment post"
            ),
            inline=False
        )
        
        embed.set_footer(text="Mistress LIV Bot | Type /command for more info")
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="synchelmet", description="[Admin] Add helmet emoji to a member's nickname")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(member="The member to update")
    async def sync_helmet(self, interaction: discord.Interaction, member: discord.Member):
        """Manually sync a member's helmet emoji based on their team role."""
        # Find their team role
        team_role = None
        for role in member.roles:
            role_name_upper = role.name.upper()
            if role_name_upper in NFL_TEAMS:
                team_role = role_name_upper
                break
        
        # Get base name (remove any existing emoji prefix)
        base_name = remove_helmet_from_name(member.display_name)
        
        if team_role:
            # Member has a team role - add helmet emoji
            team_data = NFL_TEAMS[team_role]
            emoji = team_data['emoji']
            new_nickname = f"{emoji} {base_name}"
        else:
            # Member has no team role - remove helmet emoji
            new_nickname = base_name
            await interaction.response.send_message(
                f"ℹ️ {member.display_name} doesn't have a team role. Removing any helmet emoji.",
                ephemeral=True
            )
        
        try:
            if len(new_nickname) <= 32:
                await member.edit(nick=new_nickname if new_nickname != member.name else None)
                await interaction.response.send_message(
                    f"✅ Updated {member.mention}'s nickname to: **{new_nickname}**"
                )
            else:
                # Truncate if too long
                truncated = new_nickname[:32]
                await member.edit(nick=truncated)
                await interaction.response.send_message(
                    f"✅ Updated {member.mention}'s nickname to: **{truncated}** (truncated)"
                )
        except discord.Forbidden:
            await interaction.response.send_message(
                f"❌ Cannot change nickname for {member.display_name} - insufficient permissions",
                ephemeral=True
            )
    
    @app_commands.command(name="syncallhelmets", description="[Admin] Add helmet emojis to all registered team owners")
    @app_commands.default_permissions(administrator=True)
    async def sync_all_helmets(self, interaction: discord.Interaction):
        """Sync helmet emojis for all registered team owners (uses database, no Server Members Intent needed)."""
        await interaction.response.send_message("🏈 Syncing helmets for registered team owners...", ephemeral=True)
        
        updated = 0
        failed = 0
        skipped = 0
        not_found = 0
        
        # Get registered owners from database
        try:
            conn = sqlite3.connect('data/mistress_liv.db')
            cursor = conn.cursor()
            cursor.execute(
                "SELECT team_id, team_name, user_discord_id FROM teams WHERE user_discord_id IS NOT NULL"
            )
            registered_owners = cursor.fetchall()
            conn.close()
        except Exception as e:
            await interaction.edit_original_response(content=f"❌ Database error: {e}")
            return
        
        if not registered_owners:
            await interaction.edit_original_response(
                content="⚠️ No team owners registered! Have them run `/register` first."
            )
            return
        
        guild = interaction.guild
        
        for team_id, team_name, discord_id in registered_owners:
            try:
                # Try to get member from guild
                member = guild.get_member(discord_id)
                if not member:
                    # Try to fetch if not in cache
                    try:
                        member = await guild.fetch_member(discord_id)
                    except:
                        not_found += 1
                        continue
                
                if member.bot:
                    continue
                
                # Get team data
                if team_id not in NFL_TEAMS:
                    continue
                
                team_data = NFL_TEAMS[team_id]
                emoji = team_data['emoji']
                
                # Get base name (remove any existing helmet)
                base_name = remove_helmet_from_name(member.display_name)
                new_nickname = f"{emoji} {base_name}"
                
                # Check if already has correct emoji
                if member.display_name == new_nickname:
                    skipped += 1
                    continue
                
                # Update nickname
                if len(new_nickname) <= 32:
                    await member.edit(nick=new_nickname if new_nickname != member.name else None)
                    updated += 1
                else:
                    truncated = new_nickname[:32]
                    await member.edit(nick=truncated)
                    updated += 1
                    
            except discord.Forbidden:
                failed += 1
            except Exception as e:
                logger.error(f"Error updating {team_id} owner: {e}")
                failed += 1
        
        embed = discord.Embed(
            title="🏈 Helmet Sync Complete",
            description=f"Synced helmets for {len(registered_owners)} registered team owners!",
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="✅ Updated", value=str(updated), inline=True)
        embed.add_field(name="⏭️ Already Set", value=str(skipped), inline=True)
        embed.add_field(name="❌ Failed", value=str(failed), inline=True)
        embed.add_field(name="🔍 Not Found", value=str(not_found), inline=True)
        embed.add_field(name="📋 Registered", value=f"{len(registered_owners)}/32", inline=True)
        
        if len(registered_owners) < 32:
            embed.set_footer(text="Tip: Run /registerall to prompt unregistered owners to sign up")
        
        await interaction.edit_original_response(content=None, embed=embed)
    
    @app_commands.command(name="removehelmet", description="[Admin] Remove helmet emoji from a member's nickname")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(member="The member to update")
    async def remove_helmet(self, interaction: discord.Interaction, member: discord.Member):
        """Remove helmet emoji from a member's nickname."""
        # Get base name (remove any existing emoji prefix)
        base_name = remove_helmet_from_name(member.display_name)
        
        if base_name == member.display_name:
            await interaction.response.send_message(
                f"ℹ️ {member.display_name} doesn't have a helmet emoji to remove.",
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
                f"❌ Cannot change nickname for {member.display_name} - insufficient permissions",
                ephemeral=True
            )
    
    @app_commands.command(name="setuproles", description="[Admin] Create team roles with proper colors")
    @app_commands.default_permissions(administrator=True)
    async def setup_roles(self, interaction: discord.Interaction):
        """Create or update team roles with proper colors."""
        await interaction.response.defer()
        
        created = 0
        updated = 0
        
        for team_id, team_data in NFL_TEAMS.items():
            # Check if role exists
            existing_role = discord.utils.get(interaction.guild.roles, name=team_id)
            
            if existing_role:
                # Update color if different
                if existing_role.color.value != team_data['color']:
                    try:
                        await existing_role.edit(color=discord.Color(team_data['color']))
                        updated += 1
                    except discord.Forbidden:
                        pass
            else:
                # Create new role
                try:
                    await interaction.guild.create_role(
                        name=team_id,
                        color=discord.Color(team_data['color']),
                        reason="Mistress LIV Bot - Team role setup"
                    )
                    created += 1
                except discord.Forbidden:
                    pass
        
        embed = discord.Embed(
            title="🎨 Role Setup Complete",
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="✅ Created", value=str(created), inline=True)
        embed.add_field(name="🔄 Updated", value=str(updated), inline=True)
        
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="ping", description="Check bot latency")
    async def ping(self, interaction: discord.Interaction):
        """Check the bot's latency."""
        latency = round(self.bot.latency * 1000)
        
        if latency < 100:
            status = "🟢 Excellent"
        elif latency < 200:
            status = "🟡 Good"
        else:
            status = "🔴 High"
        
        embed = discord.Embed(
            title="🏓 Pong!",
            description=f"**Latency:** {latency}ms\n**Status:** {status}",
            color=discord.Color.green() if latency < 200 else discord.Color.red(),
            timestamp=datetime.utcnow()
        )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="serverinfo", description="Get server information")
    async def server_info(self, interaction: discord.Interaction):
        """Display server information."""
        guild = interaction.guild
        
        embed = discord.Embed(
            title=f"📊 {guild.name} Server Info",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        
        embed.add_field(name="👥 Members", value=str(guild.member_count), inline=True)
        embed.add_field(name="📝 Channels", value=str(len(guild.channels)), inline=True)
        embed.add_field(name="🎭 Roles", value=str(len(guild.roles)), inline=True)
        embed.add_field(name="📅 Created", value=guild.created_at.strftime("%B %d, %Y"), inline=True)
        embed.add_field(name="👑 Owner", value=guild.owner.mention if guild.owner else "Unknown", inline=True)
        embed.add_field(name="🆔 Server ID", value=str(guild.id), inline=True)
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="createfinances", description="[Admin] Create the finances channel with restricted permissions")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        category="The category to create the channel in (optional)"
    )
    async def create_finances_channel(
        self,
        interaction: discord.Interaction,
        category: Optional[discord.CategoryChannel] = None
    ):
        """Create a finances channel where only commands and bot responses are allowed."""
        await interaction.response.defer()
        
        guild = interaction.guild
        
        # Check if channel already exists
        existing = discord.utils.get(guild.text_channels, name="finances")
        if existing:
            await interaction.followup.send(
                f"⚠️ A #finances channel already exists: {existing.mention}",
                ephemeral=True
            )
            return
        
        # Set up permissions
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=False,  # Regular members can't send messages
                read_message_history=True,
                use_application_commands=True,  # But can use slash commands
                add_reactions=False
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,  # Bot can send messages
                read_message_history=True,
                manage_messages=True,
                embed_links=True
            )
        }
        
        # Add admin permissions
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
            # Create the channel
            channel = await guild.create_text_channel(
                name="finances",
                category=category,
                overwrites=overwrites,
                topic="💰 League finances and payment tracking. Use slash commands to interact.",
                reason=f"Created by {interaction.user.display_name} via bot command"
            )
            
            # Send welcome message
            welcome_embed = discord.Embed(
                title="💰 League Finances",
                description=(
                    "Welcome to the finances channel!\n\n"
                    "This channel is for tracking league payments, dues, and profitability.\n"
                    "**Only slash commands and bot responses are allowed here.**\n\n"
                    "**Available Commands:**\n"
                    "• `/mypayments` - View your payment info and balances\n"
                    "• `/setpayment` - Set your payment methods\n"
                    "• `/paymentinfo @user` - Look up someone's payment info\n"
                    "• `/markpaid @user amount` - Mark a payment as sent\n"
                    "• `/confirmpaid @user amount` - Confirm you received payment\n"
                    "• `/dues` - View current season dues tracker\n"
                    "• `/profitability` - View franchise profitability leaderboard\n"
                    "• `/myprofit` - View your personal profit breakdown"
                ),
                color=discord.Color.gold(),
                timestamp=datetime.utcnow()
            )
            welcome_embed.set_footer(text="Use /bothelp for all available commands")
            
            await channel.send(embed=welcome_embed)
            
            await interaction.followup.send(
                f"✅ Created {channel.mention} with restricted permissions!\n"
                f"• Members can view and use slash commands\n"
                f"• Only the bot and admins can send messages",
                ephemeral=False
            )
            
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ I don't have permission to create channels!",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error creating finances channel: {e}")
            await interaction.followup.send(
                f"❌ An error occurred: {str(e)}",
                ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(AdminCog(bot))
