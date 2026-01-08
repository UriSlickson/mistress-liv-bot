"""
Whiner Cog - Track who complains the most in the server
Features:
- Monitors messages for complaint keywords
- Tracks complaint counts per user
- Leaderboard of biggest whiners
"""

import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
from datetime import datetime, timedelta
from typing import Optional
import logging
import re

logger = logging.getLogger('MistressLIV.Whiner')

# Keywords and phrases that indicate complaining
COMPLAINT_KEYWORDS = [
    # Direct complaints
    'bs', 'bullshit', 'rigged', 'cheating', 'cheat', 'unfair', 'broken',
    'trash', 'garbage', 'terrible', 'awful', 'worst', 'stupid', 'dumb',
    'ridiculous', 'pathetic', 'joke', 'scam', 'robbed', 'screwed',
    # Frustration expressions
    'wtf', 'smh', 'ffs', 'omfg', 'bruh', 'come on', 'seriously',
    'are you kidding', 'no way', 'thats crazy', "that's crazy",
    # Game-specific complaints
    'ea', 'madden sucks', 'this game', 'lag', 'glitch', 'bug',
    'animation', 'catch', 'fumble', 'interception', 'dropped',
    'missed', 'ref', 'refs', 'penalty', 'flag',
    # Whining phrases
    'always happens', 'every time', 'never works', 'so lucky',
    'of course', 'typical', 'figures', 'knew it',
    # Excuses
    'should have', 'would have', 'could have', 'supposed to',
    'not my fault', 'blame', 'lucky'
]

# Phrases that strongly indicate whining (weighted higher)
STRONG_COMPLAINTS = [
    'rigged', 'cheating', 'bs', 'bullshit', 'robbed', 'screwed',
    'ea sucks', 'madden sucks', 'this game sucks', 'trash game'
]


class WhinerCog(commands.Cog):
    """Cog for tracking who complains the most."""
    
    def __init__(self, bot):
        self.bot = bot
        self.db_path = bot.db_path
        self._ensure_tables()
        
    def get_db_connection(self):
        """Get a database connection."""
        return sqlite3.connect(self.db_path)
    
    def _ensure_tables(self):
        """Ensure all required tables exist."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Complaints tracking table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS complaints (
                complaint_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                message_id INTEGER,
                channel_id INTEGER,
                complaint_text TEXT,
                complaint_score INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # User complaint summary
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS whiner_stats (
                user_id INTEGER PRIMARY KEY,
                total_complaints INTEGER DEFAULT 0,
                total_score INTEGER DEFAULT 0,
                last_complaint TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def _check_for_complaints(self, message_content: str) -> tuple[bool, int, list]:
        """Check if a message contains complaint keywords."""
        content_lower = message_content.lower()
        found_keywords = []
        score = 0
        
        # Check for strong complaints first (worth 2 points each)
        for phrase in STRONG_COMPLAINTS:
            if phrase in content_lower:
                found_keywords.append(phrase)
                score += 2
        
        # Check for regular complaints (worth 1 point each)
        for keyword in COMPLAINT_KEYWORDS:
            if keyword in content_lower and keyword not in found_keywords:
                found_keywords.append(keyword)
                score += 1
        
        # Cap the score at 5 per message to prevent spam abuse
        score = min(score, 5)
        
        return len(found_keywords) > 0, score, found_keywords
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listen for messages and track complaints."""
        # Ignore bots and DMs
        if message.author.bot or not message.guild:
            return
        
        # Check for complaints
        is_complaint, score, keywords = self._check_for_complaints(message.content)
        
        if is_complaint and score > 0:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            # Record the complaint
            cursor.execute('''
                INSERT INTO complaints (user_id, message_id, channel_id, complaint_text, complaint_score)
                VALUES (?, ?, ?, ?, ?)
            ''', (message.author.id, message.id, message.channel.id, message.content[:500], score))
            
            # Update user stats
            cursor.execute('''
                INSERT INTO whiner_stats (user_id, total_complaints, total_score, last_complaint, updated_at)
                VALUES (?, 1, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    total_complaints = total_complaints + 1,
                    total_score = total_score + ?,
                    last_complaint = ?,
                    updated_at = ?
            ''', (message.author.id, score, message.content[:200], datetime.now().isoformat(),
                  score, message.content[:200], datetime.now().isoformat()))
            
            conn.commit()
            conn.close()
            
            logger.debug(f"Recorded complaint from {message.author}: {keywords}")

    @app_commands.command(name="whiner", description="See who complains the most in the server")
    @app_commands.describe(
        timeframe="Time period to check (default: all time)",
        show_quotes="Show recent complaint quotes"
    )
    @app_commands.choices(timeframe=[
        app_commands.Choice(name="All Time", value="all"),
        app_commands.Choice(name="This Month", value="month"),
        app_commands.Choice(name="This Week", value="week"),
        app_commands.Choice(name="Today", value="day"),
    ])
    async def whiner(
        self,
        interaction: discord.Interaction,
        timeframe: str = "all",
        show_quotes: bool = False
    ):
        """Show the biggest whiners leaderboard."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Calculate date filter
        if timeframe == "day":
            date_filter = (datetime.now() - timedelta(days=1)).isoformat()
            period_name = "Today"
        elif timeframe == "week":
            date_filter = (datetime.now() - timedelta(weeks=1)).isoformat()
            period_name = "This Week"
        elif timeframe == "month":
            date_filter = (datetime.now() - timedelta(days=30)).isoformat()
            period_name = "This Month"
        else:
            date_filter = "1970-01-01"
            period_name = "All Time"
        
        # Get top whiners
        cursor.execute('''
            SELECT user_id, COUNT(*) as complaint_count, SUM(complaint_score) as total_score
            FROM complaints
            WHERE created_at > ?
            GROUP BY user_id
            ORDER BY total_score DESC
            LIMIT 10
        ''', (date_filter,))
        
        results = cursor.fetchall()
        
        if not results:
            await interaction.response.send_message(
                f"😇 **No complaints recorded {period_name.lower()}!** Everyone's been positive!",
                ephemeral=False
            )
            conn.close()
            return
        
        embed = discord.Embed(
            title=f"😭 Biggest Whiners - {period_name}",
            description="Who complains the most? Let's find out!",
            color=discord.Color.orange(),
            timestamp=datetime.now()
        )
        
        leaderboard = ""
        whiner_emojis = ["👶", "😢", "😤", "😠", "🗣️"]
        
        for i, (user_id, count, score) in enumerate(results):
            member = interaction.guild.get_member(user_id)
            name = member.display_name if member else f"User {user_id}"
            emoji = whiner_emojis[i] if i < 5 else "💬"
            leaderboard += f"{emoji} **{name}**: {count} complaints (Score: {score})\n"
        
        embed.add_field(name="🏆 Leaderboard", value=leaderboard, inline=False)
        
        # Show recent quotes if requested
        if show_quotes and results:
            top_whiner_id = results[0][0]
            cursor.execute('''
                SELECT complaint_text FROM complaints
                WHERE user_id = ? AND created_at > ?
                ORDER BY created_at DESC
                LIMIT 3
            ''', (top_whiner_id, date_filter))
            quotes = cursor.fetchall()
            
            if quotes:
                quotes_text = ""
                for (quote,) in quotes:
                    # Truncate long quotes
                    truncated = quote[:100] + "..." if len(quote) > 100 else quote
                    quotes_text += f"*\"{truncated}\"*\n"
                
                top_whiner = interaction.guild.get_member(top_whiner_id)
                top_name = top_whiner.display_name if top_whiner else "Top Whiner"
                embed.add_field(
                    name=f"📢 Recent from {top_name}",
                    value=quotes_text,
                    inline=False
                )
        
        embed.set_footer(text="Stop whining and git gud! 🎮")
        
        conn.close()
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="mywhines", description="See your own complaint stats")
    async def my_whines(self, interaction: discord.Interaction):
        """Show the user's own complaint statistics."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Get user's stats
        cursor.execute('''
            SELECT total_complaints, total_score, last_complaint
            FROM whiner_stats
            WHERE user_id = ?
        ''', (interaction.user.id,))
        
        result = cursor.fetchone()
        
        if not result or result[0] == 0:
            await interaction.response.send_message(
                "😇 **You haven't complained at all!** Keep up the positive vibes!",
                ephemeral=True
            )
            conn.close()
            return
        
        total_complaints, total_score, last_complaint = result
        
        # Get user's rank
        cursor.execute('''
            SELECT COUNT(*) + 1 FROM whiner_stats
            WHERE total_score > (SELECT total_score FROM whiner_stats WHERE user_id = ?)
        ''', (interaction.user.id,))
        rank = cursor.fetchone()[0]
        
        conn.close()
        
        embed = discord.Embed(
            title=f"😤 Complaint Stats for {interaction.user.display_name}",
            color=discord.Color.orange(),
            timestamp=datetime.now()
        )
        
        embed.add_field(name="📊 Total Complaints", value=str(total_complaints), inline=True)
        embed.add_field(name="🎯 Whiner Score", value=str(total_score), inline=True)
        embed.add_field(name="🏆 Rank", value=f"#{rank}", inline=True)
        
        if last_complaint:
            truncated = last_complaint[:150] + "..." if len(last_complaint) > 150 else last_complaint
            embed.add_field(name="💬 Last Complaint", value=f"*\"{truncated}\"*", inline=False)
        
        # Add a fun message based on score
        if total_score > 50:
            embed.set_footer(text="🧂 You're EXTRA salty! Maybe take a break?")
        elif total_score > 20:
            embed.set_footer(text="😅 You complain quite a bit... just saying!")
        elif total_score > 10:
            embed.set_footer(text="🤷 A moderate amount of complaints. Could be worse!")
        else:
            embed.set_footer(text="😊 Not too bad! Keep it positive!")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="resetwhiner", description="[Admin] Reset complaint stats for a user")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(user="User to reset stats for (leave empty to reset all)")
    async def reset_whiner(
        self,
        interaction: discord.Interaction,
        user: Optional[discord.Member] = None
    ):
        """Reset complaint statistics."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        if user:
            cursor.execute('DELETE FROM complaints WHERE user_id = ?', (user.id,))
            cursor.execute('DELETE FROM whiner_stats WHERE user_id = ?', (user.id,))
            message = f"✅ Reset complaint stats for {user.display_name}"
        else:
            cursor.execute('DELETE FROM complaints')
            cursor.execute('DELETE FROM whiner_stats')
            message = "✅ Reset ALL complaint stats"
        
        conn.commit()
        conn.close()
        
        await interaction.response.send_message(message, ephemeral=True)


async def setup(bot):
    await bot.add_cog(WhinerCog(bot))
