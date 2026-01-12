import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite
from datetime import datetime
from typing import Optional

class WelcherCog(commands.Cog):
    """Cog for managing users who don't pay their debts (welchers)"""
    
    def __init__(self, bot):
        self.bot = bot
        self.db_path = "mistress_liv.db"
    
    async def cog_load(self):
        """Initialize the welcher table when cog loads"""
        await self._ensure_welcher_table()
    
    async def _ensure_welcher_table(self):
        """Create the welcher table if it doesn't exist"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS welchers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    banned_by TEXT NOT NULL,
                    reason TEXT,
                    amount_owed REAL DEFAULT 0,
                    banned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active INTEGER DEFAULT 1,
                    reactivated_at TIMESTAMP,
                    reactivated_by TEXT,
                    UNIQUE(guild_id, user_id)
                )
            ''')
            await db.commit()
    
    async def is_welcher(self, guild_id: str, user_id: str) -> bool:
        """Check if a user is currently banned as a welcher"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT is_active FROM welchers 
                WHERE guild_id = ? AND user_id = ? AND is_active = 1
            ''', (guild_id, user_id))
            result = await cursor.fetchone()
            return result is not None
    
    async def get_welcher_info(self, guild_id: str, user_id: str) -> Optional[dict]:
        """Get welcher information for a user"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT user_id, banned_by, reason, amount_owed, banned_at, is_active
                FROM welchers 
                WHERE guild_id = ? AND user_id = ?
            ''', (guild_id, user_id))
            result = await cursor.fetchone()
            if result:
                return {
                    'user_id': result[0],
                    'banned_by': result[1],
                    'reason': result[2],
                    'amount_owed': result[3],
                    'banned_at': result[4],
                    'is_active': result[5]
                }
            return None
    
    @app_commands.command(name="welcher", description="Ban a user from wagering, payouts, and Best Ball for not paying")
    @app_commands.describe(
        user="The user to ban",
        reason="Reason for the ban (e.g., 'Didn't pay $50 wager to @opponent')",
        amount_owed="Amount the user owes (optional)"
    )
    @app_commands.default_permissions(administrator=True)
    async def welcher(
        self, 
        interaction: discord.Interaction, 
        user: discord.Member,
        reason: str,
        amount_owed: Optional[float] = 0
    ):
        """Ban a user from all money-related activities"""
        guild_id = str(interaction.guild_id)
        user_id = str(user.id)
        banned_by = str(interaction.user.id)
        
        # Check if already banned
        existing = await self.get_welcher_info(guild_id, user_id)
        if existing and existing['is_active']:
            await interaction.response.send_message(
                f"⚠️ {user.mention} is already banned as a welcher.",
                ephemeral=True
            )
            return
        
        async with aiosqlite.connect(self.db_path) as db:
            if existing:
                # Reactivate existing ban
                await db.execute('''
                    UPDATE welchers 
                    SET is_active = 1, banned_by = ?, reason = ?, amount_owed = ?, 
                        banned_at = CURRENT_TIMESTAMP, reactivated_at = NULL, reactivated_by = NULL
                    WHERE guild_id = ? AND user_id = ?
                ''', (banned_by, reason, amount_owed, guild_id, user_id))
            else:
                # Create new ban
                await db.execute('''
                    INSERT INTO welchers (guild_id, user_id, banned_by, reason, amount_owed)
                    VALUES (?, ?, ?, ?, ?)
                ''', (guild_id, user_id, banned_by, reason, amount_owed))
            await db.commit()
        
        # Create embed
        embed = discord.Embed(
            title="🚫 User Banned - Welcher",
            description=f"{user.mention} has been banned from all money-related activities.",
            color=discord.Color.red()
        )
        embed.add_field(name="Banned User", value=user.mention, inline=True)
        embed.add_field(name="Banned By", value=interaction.user.mention, inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        if amount_owed > 0:
            embed.add_field(name="Amount Owed", value=f"${amount_owed:.2f}", inline=True)
        embed.add_field(
            name="Restrictions", 
            value="❌ Cannot create or accept wagers\n❌ Cannot participate in playoff payouts\n❌ Cannot join Best Ball events",
            inline=False
        )
        embed.set_footer(text="Use /redeemed to reactivate this user")
        embed.timestamp = datetime.utcnow()
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="redeemed", description="Reactivate a user who was banned as a welcher")
    @app_commands.describe(
        user="The user to reactivate",
        reason="Reason for reactivation (e.g., 'Paid their debt')"
    )
    @app_commands.default_permissions(administrator=True)
    async def unwelcher(
        self, 
        interaction: discord.Interaction, 
        user: discord.Member,
        reason: Optional[str] = "Debt settled"
    ):
        """Reactivate a banned user"""
        guild_id = str(interaction.guild_id)
        user_id = str(user.id)
        reactivated_by = str(interaction.user.id)
        
        # Check if user is actually banned
        existing = await self.get_welcher_info(guild_id, user_id)
        if not existing or not existing['is_active']:
            await interaction.response.send_message(
                f"⚠️ {user.mention} is not currently banned as a welcher.",
                ephemeral=True
            )
            return
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                UPDATE welchers 
                SET is_active = 0, reactivated_at = CURRENT_TIMESTAMP, reactivated_by = ?
                WHERE guild_id = ? AND user_id = ?
            ''', (reactivated_by, guild_id, user_id))
            await db.commit()
        
        # Create embed
        embed = discord.Embed(
            title="✅ User Reactivated",
            description=f"{user.mention} has been reactivated and can participate in money-related activities again.",
            color=discord.Color.green()
        )
        embed.add_field(name="User", value=user.mention, inline=True)
        embed.add_field(name="Reactivated By", value=interaction.user.mention, inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(
            name="Restored Access", 
            value="✅ Can create and accept wagers\n✅ Can participate in playoff payouts\n✅ Can join Best Ball events",
            inline=False
        )
        embed.timestamp = datetime.utcnow()
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="welcherlist", description="View all users currently banned as welchers")
    async def welcherlist(self, interaction: discord.Interaction):
        """List all current welchers"""
        guild_id = str(interaction.guild_id)
        
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT user_id, reason, amount_owed, banned_at
                FROM welchers 
                WHERE guild_id = ? AND is_active = 1
                ORDER BY banned_at DESC
            ''', (guild_id,))
            welchers = await cursor.fetchall()
        
        if not welchers:
            embed = discord.Embed(
                title="📋 Welcher List",
                description="No users are currently banned as welchers.",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed)
            return
        
        embed = discord.Embed(
            title="🚫 Welcher List",
            description=f"**{len(welchers)}** user(s) currently banned",
            color=discord.Color.red()
        )
        
        for user_id, reason, amount_owed, banned_at in welchers:
            user = interaction.guild.get_member(int(user_id))
            user_display = user.mention if user else f"<@{user_id}>"
            
            value = f"**Reason:** {reason}"
            if amount_owed > 0:
                value += f"\n**Owed:** ${amount_owed:.2f}"
            value += f"\n**Since:** {banned_at[:10] if banned_at else 'Unknown'}"
            
            embed.add_field(name=user_display, value=value, inline=False)
        
        embed.set_footer(text="Use /redeemed to reactivate a user")
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="checkwelcher", description="Check if a user is banned as a welcher")
    @app_commands.describe(user="The user to check")
    async def checkwelcher(self, interaction: discord.Interaction, user: discord.Member):
        """Check a specific user's welcher status"""
        guild_id = str(interaction.guild_id)
        user_id = str(user.id)
        
        info = await self.get_welcher_info(guild_id, user_id)
        
        if not info or not info['is_active']:
            embed = discord.Embed(
                title="✅ User Status: Clear",
                description=f"{user.mention} is **not** banned as a welcher.",
                color=discord.Color.green()
            )
            if info and not info['is_active']:
                embed.add_field(
                    name="History", 
                    value="This user was previously banned but has been reactivated.",
                    inline=False
                )
        else:
            embed = discord.Embed(
                title="🚫 User Status: Banned",
                description=f"{user.mention} is currently banned as a welcher.",
                color=discord.Color.red()
            )
            embed.add_field(name="Reason", value=info['reason'], inline=False)
            if info['amount_owed'] > 0:
                embed.add_field(name="Amount Owed", value=f"${info['amount_owed']:.2f}", inline=True)
            embed.add_field(name="Banned Since", value=info['banned_at'][:10] if info['banned_at'] else 'Unknown', inline=True)
            
            banned_by = interaction.guild.get_member(int(info['banned_by']))
            if banned_by:
                embed.add_field(name="Banned By", value=banned_by.mention, inline=True)
        
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(WelcherCog(bot))
