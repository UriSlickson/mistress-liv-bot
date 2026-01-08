"""
Announcements Cog - League-wide announcements and offseason communications
Uses registered team owner Discord IDs from database (no Server Members Intent needed)
"""

import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
from typing import Optional
import sqlite3
import logging
import asyncio

logger = logging.getLogger('MistressLIV.Announcements')


class AnnouncementsCog(commands.Cog):
    """Cog for league-wide announcements."""
    
    def __init__(self, bot):
        self.bot = bot
        self.db_path = 'data/mistress_liv.db'
    
    def get_registered_owners(self) -> list:
        """Get all registered team owner Discord IDs from database."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT team_id, team_name, user_discord_id FROM teams WHERE user_discord_id IS NOT NULL"
            )
            results = cursor.fetchall()
            conn.close()
            return results
        except Exception as e:
            logger.error(f"Error getting registered owners: {e}")
            return []
    
    @app_commands.command(name="postcommands", description="[Admin] Post the full command list to a channel")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(channel="Channel to post the command list to")
    async def post_commands(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Post the comprehensive command list as an embed."""
        await interaction.response.defer(ephemeral=True)
        
        # Create the main embed
        embed = discord.Embed(
            title="📋 MISTRESS LIV LEAGUE COMMANDS",
            description="All available commands for the league",
            color=discord.Color.gold(),
            timestamp=datetime.utcnow()
        )
        
        # MyMadden Commands
        mymadden_cmds = """
`/register` - Register your team
`/connectservices` - Link Twitch/YouTube to #broadcasts
`/players` - Post players to #otb
`/sync info` - Sync league info
`/sync stats` - Sync player stats
`/sync rosters` - Sync team rosters
"""
        embed.add_field(name="🏈 MyMadden Commands *(use in #townsquare)*", value=mymadden_cmds, inline=False)
        
        # Info Commands
        info_cmds = """
`/help` - Show all commands
`/serverinfo` - View server stats
"""
        embed.add_field(name="ℹ️ Info Commands", value=info_cmds, inline=False)
        
        # Payment Commands
        payment_cmds = """
`/mypayments` - View your payment summary
`/whooowesme` - See who owes you money
`/whoiowe` - See who you owe money to
`/paymentschedule` - View all outstanding dues
`/markpaid` - Mark a payment as complete
`/topearners` - Earnings leaderboard
`/toplosers` - Losses leaderboard
"""
        embed.add_field(name="💰 Payment & Dues Commands", value=payment_cmds, inline=False)
        
        # Profitability Commands
        profit_cmds = """
`/profitability` - View all-time franchise profits
`/myprofit` - View your profit history
"""
        embed.add_field(name="📊 Profitability Commands", value=profit_cmds, inline=False)
        
        # Fun Commands
        fun_cmds = """
`/whiner` - See who complains the most 😤
`/mywhines` - Check your complaint stats
"""
        embed.add_field(name="🎮 Fun Commands", value=fun_cmds, inline=False)
        
        # Admin Commands
        admin_cmds = """
`/announce` - Post league announcement
`/createpayment` - Create a payment obligation
`/clearpayment` - Delete a payment
`/resetwhiner` - Reset complaint stats
`/generatepayments` - Generate playoff payments
`/setseeding` - Set team playoff seeding
"""
        embed.add_field(name="🔧 Admin Commands", value=admin_cmds, inline=False)
        
        embed.set_footer(text="Mistress LIV Bot • Use / to see all commands")
        
        try:
            await channel.send(embed=embed)
            await interaction.followup.send(f"✅ Command list posted to {channel.mention}!", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to post: {e}", ephemeral=True)
    
    @app_commands.command(name="announcement", description="[Admin] Post announcement to channels and DM team owners")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(message="The announcement message to send")
    async def announcement(self, interaction: discord.Interaction, message: str):
        """Post announcement to channels and DM all registered team owners."""
        # IMMEDIATELY defer to prevent timeout - this is critical!
        await interaction.response.defer(ephemeral=True)
        
        guild = interaction.guild
        results = []
        
        # Create the announcement embed
        embed = discord.Embed(
            title="📢 League Announcement",
            description=message,
            color=discord.Color.gold(),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text=f"Posted by {interaction.user.display_name}")
        
        # Post to #announcements
        announcements_channel = discord.utils.get(guild.text_channels, name='announcements')
        if announcements_channel:
            try:
                await announcements_channel.send(embed=embed)
                results.append(f"✅ Posted to {announcements_channel.mention}")
            except Exception as e:
                results.append(f"❌ Failed to post to #announcements: {e}")
        else:
            results.append("⚠️ #announcements channel not found")
        
        # Post to #townsquare
        townsquare_channel = discord.utils.get(guild.text_channels, name='townsquare')
        if townsquare_channel:
            try:
                await townsquare_channel.send(embed=embed)
                results.append(f"✅ Posted to {townsquare_channel.mention}")
            except Exception as e:
                results.append(f"❌ Failed to post to #townsquare: {e}")
        else:
            results.append("⚠️ #townsquare channel not found")
        
        # Get registered team owners from database
        registered_owners = self.get_registered_owners()
        
        dm_embed = discord.Embed(
            title="📢 Mistress LIV - Offseason Announcement",
            description=message,
            color=discord.Color.gold(),
            timestamp=datetime.utcnow()
        )
        dm_embed.set_footer(text=f"From: {guild.name}")
        
        dm_success = 0
        dm_failed = 0
        failed_teams = []
        
        for team_id, team_name, discord_id in registered_owners:
            try:
                # Fetch user by ID (works without Server Members Intent)
                user = await self.bot.fetch_user(discord_id)
                await user.send(embed=dm_embed)
                dm_success += 1
                logger.info(f"DMed {team_id} owner ({discord_id})")
                await asyncio.sleep(0.3)
            except discord.NotFound:
                dm_failed += 1
                failed_teams.append(f"{team_id} (user not found)")
            except discord.Forbidden:
                dm_failed += 1
                failed_teams.append(f"{team_id} (DMs disabled)")
            except Exception as e:
                dm_failed += 1
                failed_teams.append(f"{team_id} ({str(e)[:20]})")
                logger.error(f"Error DMing {team_id}: {e}")
        
        results.append(f"\n📬 **DMs sent:** {dm_success}")
        if dm_failed > 0:
            results.append(f"❌ **DMs failed:** {dm_failed}")
            if failed_teams:
                results.append(f"   Failed: {', '.join(failed_teams[:5])}")
        
        results.append(f"\n👥 **Registered owners:** {len(registered_owners)}/32")
        
        if len(registered_owners) == 0:
            results.append("\n⚠️ **No team owners registered!**")
            results.append("Have team owners run `/register` to sign up for announcements.")
        elif len(registered_owners) < 32:
            results.append(f"\n💡 Tip: Run `/registerall` to prompt unregistered owners to sign up.")
        
        await interaction.followup.send("\n".join(results), ephemeral=True)
    
    @app_commands.command(name="announce", description="[Admin] Post an announcement to specified channels")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        message="The announcement message",
        channel1="First channel to post to",
        channel2="Second channel to post to (optional)",
        dm_owners="Also DM all registered team owners (default: False)"
    )
    async def announce(
        self,
        interaction: discord.Interaction,
        message: str,
        channel1: discord.TextChannel,
        channel2: Optional[discord.TextChannel] = None,
        dm_owners: bool = False
    ):
        """Post an announcement to specified channels."""
        # IMMEDIATELY defer to prevent timeout
        await interaction.response.defer(ephemeral=True)
        
        guild = interaction.guild
        results = []
        
        embed = discord.Embed(
            title="📢 League Announcement",
            description=message,
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text=f"Posted by {interaction.user.display_name}")
        
        # Post to channel1
        try:
            await channel1.send(embed=embed)
            results.append(f"✅ Posted to {channel1.mention}")
        except Exception as e:
            results.append(f"❌ Failed: {e}")
        
        # Post to channel2 if provided
        if channel2:
            try:
                await channel2.send(embed=embed)
                results.append(f"✅ Posted to {channel2.mention}")
            except Exception as e:
                results.append(f"❌ Failed: {e}")
        
        # DM owners if requested
        if dm_owners:
            registered_owners = self.get_registered_owners()
            dm_success = 0
            dm_failed = 0
            
            dm_embed = discord.Embed(
                title="📢 Mistress LIV - Announcement",
                description=message,
                color=discord.Color.blue(),
                timestamp=datetime.utcnow()
            )
            dm_embed.set_footer(text=f"From: {guild.name}")
            
            for team_id, team_name, discord_id in registered_owners:
                try:
                    user = await self.bot.fetch_user(discord_id)
                    await user.send(embed=dm_embed)
                    dm_success += 1
                    await asyncio.sleep(0.3)
                except:
                    dm_failed += 1
            
            results.append(f"📬 DMs: {dm_success} sent, {dm_failed} failed")
        
        await interaction.followup.send("\n".join(results), ephemeral=True)
    
    @app_commands.command(name="dmowners", description="[Admin] Send a DM to all registered team owners")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(message="The message to send to all team owners")
    async def dm_owners(self, interaction: discord.Interaction, message: str):
        """Send a DM to all registered team owners."""
        # IMMEDIATELY defer to prevent timeout
        await interaction.response.defer(ephemeral=True)
        
        guild = interaction.guild
        registered_owners = self.get_registered_owners()
        
        if not registered_owners:
            await interaction.followup.send(
                "⚠️ No team owners registered! Have them run `/register` first.",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title="📬 Message from League Admin",
            description=message,
            color=discord.Color.purple(),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text=f"From: {guild.name} | Sent by {interaction.user.display_name}")
        
        dm_success = 0
        dm_failed = 0
        
        for team_id, team_name, discord_id in registered_owners:
            try:
                user = await self.bot.fetch_user(discord_id)
                await user.send(embed=embed)
                dm_success += 1
                await asyncio.sleep(0.3)
            except:
                dm_failed += 1
        
        await interaction.followup.send(
            f"✅ **DM Results:**\n📬 Sent: {dm_success}\n❌ Failed: {dm_failed}\n👥 Registered: {len(registered_owners)}/32",
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(AnnouncementsCog(bot))
