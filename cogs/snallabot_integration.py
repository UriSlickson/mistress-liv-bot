"""
Snallabot Integration Cog - Monitors Snallabot's synced data and automatically
detects playoff results to generate payments.

This cog watches the #scores channel where Snallabot posts game results,
detects playoff games (weeks 19, 20, 21, 23), and automatically:
1. Records playoff winners
2. Updates seedings
3. Generates payments when Super Bowl is complete
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
import sqlite3
from datetime import datetime
import logging
import re
from typing import Optional, Dict, List, Tuple

logger = logging.getLogger('MistressLIV.SnallabotIntegration')

# Playoff week mapping (Madden weeks)
PLAYOFF_WEEKS = {
    19: 'wildcard',
    20: 'divisional', 
    21: 'conference',
    23: 'superbowl'  # Week 22 is Pro Bowl, skipped
}

# Team abbreviation to conference mapping
AFC_TEAMS = ['BAL', 'BUF', 'CIN', 'CLE', 'DEN', 'HOU', 'IND', 'JAX', 
             'KC', 'LAC', 'LV', 'MIA', 'NE', 'NYJ', 'PIT', 'TEN']
NFC_TEAMS = ['ARI', 'ATL', 'CAR', 'CHI', 'DAL', 'DET', 'GB', 'LAR',
             'MIN', 'NO', 'NYG', 'PHI', 'SEA', 'SF', 'TB', 'WAS']

# Team name variations for parsing Snallabot messages
TEAM_ALIASES = {
    '49ers': 'SF', 'niners': 'SF', 'san francisco': 'SF',
    'bears': 'CHI', 'chicago': 'CHI',
    'bengals': 'CIN', 'cincinnati': 'CIN',
    'bills': 'BUF', 'buffalo': 'BUF',
    'broncos': 'DEN', 'denver': 'DEN',
    'browns': 'CLE', 'cleveland': 'CLE',
    'buccaneers': 'TB', 'bucs': 'TB', 'tampa': 'TB', 'tampa bay': 'TB',
    'cardinals': 'ARI', 'arizona': 'ARI',
    'chargers': 'LAC', 'la chargers': 'LAC', 'los angeles chargers': 'LAC',
    'chiefs': 'KC', 'kansas city': 'KC',
    'colts': 'IND', 'indianapolis': 'IND',
    'commanders': 'WAS', 'washington': 'WAS',
    'cowboys': 'DAL', 'dallas': 'DAL',
    'dolphins': 'MIA', 'miami': 'MIA',
    'eagles': 'PHI', 'philadelphia': 'PHI',
    'falcons': 'ATL', 'atlanta': 'ATL',
    'giants': 'NYG', 'new york giants': 'NYG', 'ny giants': 'NYG',
    'jaguars': 'JAX', 'jags': 'JAX', 'jacksonville': 'JAX',
    'jets': 'NYJ', 'new york jets': 'NYJ', 'ny jets': 'NYJ',
    'lions': 'DET', 'detroit': 'DET',
    'packers': 'GB', 'green bay': 'GB',
    'panthers': 'CAR', 'carolina': 'CAR',
    'patriots': 'NE', 'pats': 'NE', 'new england': 'NE',
    'raiders': 'LV', 'las vegas': 'LV',
    'rams': 'LAR', 'la rams': 'LAR', 'los angeles rams': 'LAR',
    'ravens': 'BAL', 'baltimore': 'BAL',
    'saints': 'NO', 'new orleans': 'NO',
    'seahawks': 'SEA', 'seattle': 'SEA',
    'steelers': 'PIT', 'pittsburgh': 'PIT',
    'texans': 'HOU', 'houston': 'HOU',
    'titans': 'TEN', 'tennessee': 'TEN',
    'vikings': 'MIN', 'minnesota': 'MIN',
}

# Add abbreviations as aliases too
for abbr in AFC_TEAMS + NFC_TEAMS:
    TEAM_ALIASES[abbr.lower()] = abbr


class SnallabotIntegrationCog(commands.Cog):
    """Cog for integrating with Snallabot's synced data for automated playoff processing."""
    
    def __init__(self, bot):
        self.bot = bot
        self.db_path = bot.db_path
        self._ensure_tables()
        self.processed_messages = set()  # Track processed message IDs
        
    def _ensure_tables(self):
        """Ensure required tables exist."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Table to track processed playoff games
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS processed_playoff_games (
                game_id TEXT PRIMARY KEY,
                season INTEGER,
                week INTEGER,
                round TEXT,
                winner_team TEXT,
                loser_team TEXT,
                winner_score INTEGER,
                loser_score INTEGER,
                processed_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Table to track auto-generated payments
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS auto_payment_log (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                season INTEGER,
                round TEXT,
                generated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                payment_count INTEGER
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def get_team_conference(self, team_abbr: str) -> str:
        """Get the conference for a team."""
        if team_abbr in AFC_TEAMS:
            return 'AFC'
        elif team_abbr in NFC_TEAMS:
            return 'NFC'
        return 'UNKNOWN'
    
    def parse_team_from_text(self, text: str) -> Optional[str]:
        """Parse team abbreviation from text."""
        text_lower = text.lower().strip()
        
        # Direct abbreviation match
        for abbr in AFC_TEAMS + NFC_TEAMS:
            if abbr.lower() == text_lower:
                return abbr
        
        # Alias match
        for alias, abbr in TEAM_ALIASES.items():
            if alias in text_lower:
                return abbr
        
        return None
    
    def parse_score_message(self, content: str) -> Optional[Dict]:
        """
        Parse a Snallabot score message to extract game info.
        
        Expected formats from Snallabot:
        - "Team1 XX - YY Team2" 
        - "Team1 defeats Team2 XX-YY"
        - Various embed formats
        """
        # Pattern 1: "Team1 XX - YY Team2" or "Team1 XX-YY Team2"
        pattern1 = r'(\w+(?:\s+\w+)?)\s+(\d+)\s*[-–]\s*(\d+)\s+(\w+(?:\s+\w+)?)'
        match = re.search(pattern1, content, re.IGNORECASE)
        if match:
            team1_text, score1, score2, team2_text = match.groups()
            team1 = self.parse_team_from_text(team1_text)
            team2 = self.parse_team_from_text(team2_text)
            
            if team1 and team2:
                score1, score2 = int(score1), int(score2)
                if score1 > score2:
                    return {'winner': team1, 'loser': team2, 'winner_score': score1, 'loser_score': score2}
                elif score2 > score1:
                    return {'winner': team2, 'loser': team1, 'winner_score': score2, 'loser_score': score1}
        
        # Pattern 2: "Team1 defeats/beat Team2"
        pattern2 = r'(\w+(?:\s+\w+)?)\s+(?:defeats?|beat|won against|over)\s+(\w+(?:\s+\w+)?)'
        match = re.search(pattern2, content, re.IGNORECASE)
        if match:
            winner_text, loser_text = match.groups()
            winner = self.parse_team_from_text(winner_text)
            loser = self.parse_team_from_text(loser_text)
            
            if winner and loser:
                # Try to extract scores
                score_pattern = r'(\d+)\s*[-–]\s*(\d+)'
                score_match = re.search(score_pattern, content)
                if score_match:
                    s1, s2 = int(score_match.group(1)), int(score_match.group(2))
                    winner_score, loser_score = (s1, s2) if s1 > s2 else (s2, s1)
                else:
                    winner_score, loser_score = 0, 0
                
                return {'winner': winner, 'loser': loser, 'winner_score': winner_score, 'loser_score': loser_score}
        
        return None
    
    def is_playoff_week(self, week: int) -> bool:
        """Check if a week is a playoff week."""
        return week in PLAYOFF_WEEKS
    
    def get_playoff_round(self, week: int) -> Optional[str]:
        """Get the playoff round name for a week."""
        return PLAYOFF_WEEKS.get(week)
    
    def get_current_season(self) -> int:
        """Get the current season from the database or default."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT MAX(season) FROM season_standings')
        result = cursor.fetchone()
        conn.close()
        return result[0] if result and result[0] else 2025
    
    async def record_playoff_winner(self, season: int, round_name: str, winner_team: str, 
                                     loser_team: str, winner_score: int, loser_score: int,
                                     guild: discord.Guild) -> bool:
        """Record a playoff game winner and trigger payment generation if needed."""
        
        winner_conf = self.get_team_conference(winner_team)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get the winner's Discord ID
        cursor.execute('SELECT user_discord_id FROM teams WHERE team_id = ?', (winner_team,))
        result = cursor.fetchone()
        winner_discord_id = result[0] if result else None
        
        if not winner_discord_id:
            logger.warning(f"Could not find owner for team {winner_team}")
            conn.close()
            return False
        
        # Record the playoff result
        cursor.execute('''
            INSERT OR REPLACE INTO playoff_results 
            (season, round, conference, winner_discord_id, recorded_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (season, round_name, winner_conf, winner_discord_id, datetime.now().isoformat()))
        
        # Also record in processed games
        game_id = f"{season}_{round_name}_{winner_team}_{loser_team}"
        cursor.execute('''
            INSERT OR IGNORE INTO processed_playoff_games
            (game_id, season, week, round, winner_team, loser_team, winner_score, loser_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (game_id, season, 0, round_name, winner_team, loser_team, winner_score, loser_score))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Recorded playoff winner: {winner_team} ({round_name}) for Season {season}")
        
        # If this is the Super Bowl, trigger payment generation
        if round_name == 'superbowl':
            await self.auto_generate_payments(season, guild)
        
        return True
    
    async def auto_generate_payments(self, season: int, guild: discord.Guild):
        """Automatically generate all playoff payments after Super Bowl."""
        
        logger.info(f"Auto-generating payments for Season {season}")
        
        # Get the profitability cog to use its payment generation
        profitability_cog = self.bot.get_cog('ProfitabilityCog')
        if not profitability_cog:
            logger.error("ProfitabilityCog not found, cannot generate payments")
            return
        
        # Use the existing generate_payments method
        try:
            await profitability_cog.generate_payments(season)
            
            # Post to payouts channel
            payouts_channel = self.get_payouts_channel(guild)
            if payouts_channel:
                embed = discord.Embed(
                    title="🏆 Season Payouts Auto-Generated!",
                    description=f"The Super Bowl has concluded and all Season {season} payments have been automatically generated!",
                    color=discord.Color.gold()
                )
                embed.add_field(
                    name="📊 View Payments",
                    value="Use `/viewpayments` to see all payment obligations.",
                    inline=False
                )
                embed.add_field(
                    name="💰 Payment Structure",
                    value="• NFC Seeds 8-16 pay into the pot\n• AFC/NFC seed pairings (80/20 split)\n• Playoff round earnings",
                    inline=False
                )
                embed.set_footer(text=f"Auto-generated by Mistress LIV | {datetime.now().strftime('%Y-%m-%d %H:%M')}")
                
                await payouts_channel.send(embed=embed)
                
            # Log the auto-generation
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO auto_payment_log (season, round, payment_count)
                VALUES (?, 'superbowl', ?)
            ''', (season, 0))  # payment_count would need to be calculated
            conn.commit()
            conn.close()
            
            logger.info(f"Successfully auto-generated payments for Season {season}")
            
        except Exception as e:
            logger.error(f"Error auto-generating payments: {e}")
    
    def get_payouts_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        """Find the payouts channel."""
        for name in ['payouts', 'payout', 'finances']:
            channel = discord.utils.get(guild.text_channels, name=name)
            if channel:
                return channel
        return None
    
    def get_scores_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        """Find the scores channel."""
        for name in ['scores', 'game-scores', 'results']:
            channel = discord.utils.get(guild.text_channels, name=name)
            if channel:
                return channel
        return None
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listen for Snallabot score messages in the scores channel."""
        
        # Ignore messages from self
        if message.author == self.bot.user:
            return
        
        # Only process messages from Snallabot (My Madden)
        if not message.author.bot:
            return
        
        # Check if this is from Snallabot
        snallabot_names = ['my madden', 'mymadden', 'snallabot']
        if not any(name in message.author.name.lower() for name in snallabot_names):
            return
        
        # Check if this is in a scores channel
        if message.channel.name not in ['scores', 'game-scores', 'results']:
            return
        
        # Don't process already processed messages
        if message.id in self.processed_messages:
            return
        
        # Try to parse the message for game results
        content = message.content
        
        # Also check embeds
        for embed in message.embeds:
            if embed.title:
                content += " " + embed.title
            if embed.description:
                content += " " + embed.description
            for field in embed.fields:
                content += " " + field.name + " " + field.value
        
        game_result = self.parse_score_message(content)
        
        if game_result:
            # Check if this looks like a playoff game
            # We need to determine the week - this might be in the message or we need to track it
            
            # For now, we'll check if we're in playoff weeks based on message patterns
            playoff_keywords = ['playoff', 'wild card', 'wildcard', 'divisional', 'championship', 
                               'conference', 'super bowl', 'superbowl', 'nfc', 'afc', 'postseason']
            
            is_playoff = any(kw in content.lower() for kw in playoff_keywords)
            
            if is_playoff:
                # Determine the round from keywords
                round_name = None
                if any(kw in content.lower() for kw in ['wild card', 'wildcard']):
                    round_name = 'wildcard'
                elif 'divisional' in content.lower():
                    round_name = 'divisional'
                elif any(kw in content.lower() for kw in ['conference', 'championship', 'nfc championship', 'afc championship']):
                    round_name = 'conference'
                elif any(kw in content.lower() for kw in ['super bowl', 'superbowl']):
                    round_name = 'superbowl'
                
                if round_name:
                    season = self.get_current_season()
                    
                    await self.record_playoff_winner(
                        season=season,
                        round_name=round_name,
                        winner_team=game_result['winner'],
                        loser_team=game_result['loser'],
                        winner_score=game_result['winner_score'],
                        loser_score=game_result['loser_score'],
                        guild=message.guild
                    )
                    
                    self.processed_messages.add(message.id)
                    
                    # Send confirmation
                    conf = self.get_team_conference(game_result['winner'])
                    await message.channel.send(
                        f"🏈 **Playoff Result Recorded!**\n"
                        f"**{round_name.title()}**: {game_result['winner']} defeats {game_result['loser']} "
                        f"({game_result['winner_score']}-{game_result['loser_score']})\n"
                        f"Conference: {conf}"
                    )
    
    @app_commands.command(name="snallabottest", description="[Admin] Test Snallabot integration by simulating a playoff result")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        season="Season number",
        round_name="Playoff round (wildcard, divisional, conference, superbowl)",
        winner="Winning team abbreviation (e.g., KC, SF)",
        loser="Losing team abbreviation",
        winner_score="Winner's score",
        loser_score="Loser's score"
    )
    async def snallabot_test(self, interaction: discord.Interaction, season: int, 
                             round_name: str, winner: str, loser: str,
                             winner_score: int, loser_score: int):
        """Test the Snallabot integration by simulating a playoff result."""
        
        round_name = round_name.lower()
        if round_name not in ['wildcard', 'divisional', 'conference', 'superbowl']:
            await interaction.response.send_message(
                "❌ Invalid round. Use: wildcard, divisional, conference, or superbowl",
                ephemeral=True
            )
            return
        
        winner = winner.upper()
        loser = loser.upper()
        
        if winner not in AFC_TEAMS + NFC_TEAMS:
            await interaction.response.send_message(f"❌ Invalid winner team: {winner}", ephemeral=True)
            return
        
        if loser not in AFC_TEAMS + NFC_TEAMS:
            await interaction.response.send_message(f"❌ Invalid loser team: {loser}", ephemeral=True)
            return
        
        await interaction.response.defer(thinking=True)
        
        success = await self.record_playoff_winner(
            season=season,
            round_name=round_name,
            winner_team=winner,
            loser_team=loser,
            winner_score=winner_score,
            loser_score=loser_score,
            guild=interaction.guild
        )
        
        if success:
            conf = self.get_team_conference(winner)
            msg = f"✅ **Test Playoff Result Recorded!**\n"
            msg += f"**{round_name.title()}**: {winner} defeats {loser} ({winner_score}-{loser_score})\n"
            msg += f"Conference: {conf}\n"
            
            if round_name == 'superbowl':
                msg += "\n🏆 **Super Bowl detected! Payments have been auto-generated!**"
            
            await interaction.followup.send(msg)
        else:
            await interaction.followup.send("❌ Failed to record playoff result. Check logs for details.")
    
    @app_commands.command(name="viewplayoffresults", description="View recorded playoff results for a season")
    @app_commands.describe(season="Season number to view")
    async def view_playoff_results(self, interaction: discord.Interaction, season: int):
        """View all recorded playoff results for a season."""
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT round, winner_team, loser_team, winner_score, loser_score, processed_at
            FROM processed_playoff_games
            WHERE season = ?
            ORDER BY 
                CASE round 
                    WHEN 'wildcard' THEN 1 
                    WHEN 'divisional' THEN 2 
                    WHEN 'conference' THEN 3 
                    WHEN 'superbowl' THEN 4 
                END
        ''', (season,))
        
        results = cursor.fetchall()
        conn.close()
        
        if not results:
            await interaction.response.send_message(
                f"📋 No playoff results recorded for Season {season}.",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title=f"🏈 Season {season} Playoff Results",
            color=discord.Color.blue()
        )
        
        rounds = {'wildcard': [], 'divisional': [], 'conference': [], 'superbowl': []}
        
        for round_name, winner, loser, w_score, l_score, processed_at in results:
            rounds[round_name].append(f"{winner} def. {loser} ({w_score}-{l_score})")
        
        round_emojis = {'wildcard': '🎯', 'divisional': '🏆', 'conference': '👑', 'superbowl': '🏈'}
        
        for round_name, games in rounds.items():
            if games:
                embed.add_field(
                    name=f"{round_emojis.get(round_name, '🏈')} {round_name.title()}",
                    value="\n".join(games),
                    inline=False
                )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="clearplayoffgames", description="[Admin] Clear recorded playoff games for a season (type CLEAR)")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        season="Season number to clear",
        confirm="Type CLEAR to confirm"
    )
    async def clear_playoff_games(self, interaction: discord.Interaction, season: int, confirm: str):
        """Clear all recorded playoff games for a season."""
        
        if confirm != "CLEAR":
            await interaction.response.send_message(
                "⚠️ This will clear all recorded playoff games for the season.\n"
                "Type `CLEAR` in the confirm field to proceed.",
                ephemeral=True
            )
            return
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM processed_playoff_games WHERE season = ?', (season,))
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        
        await interaction.response.send_message(
            f"✅ Cleared {deleted} playoff game records for Season {season}."
        )


async def setup(bot):
    await bot.add_cog(SnallabotIntegrationCog(bot))
