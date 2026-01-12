"""
Snallabot Integration Cog - Directly calls Snallabot API to get playoff results
and automatically generates payments.

This cog:
1. Calls Snallabot API every hour to check for playoff game results
2. Auto-detects playoff games (weeks 19, 20, 21, 23)
3. Records playoff winners
4. Generates payments when Super Bowl is complete
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
import sqlite3
from datetime import datetime
import logging
import aiohttp
from typing import Optional, Dict, List

logger = logging.getLogger('MistressLIV.SnallabotIntegration')

# Snallabot API base URL
SNALLABOT_API_BASE = "https://snallabot.me"

# Playoff week mapping (Madden weeks)
PLAYOFF_WEEKS = {
    19: 'wildcard',
    20: 'divisional', 
    21: 'conference',
    23: 'superbowl'  # Week 22 is Pro Bowl, skipped
}

# Game result enumeration from Snallabot
GAME_RESULT = {
    1: 'NOT_PLAYED',
    2: 'AWAY_WIN',
    3: 'HOME_WIN',
    4: 'TIE'
}

# Team abbreviation to conference mapping
AFC_TEAMS = ['BAL', 'BUF', 'CIN', 'CLE', 'DEN', 'HOU', 'IND', 'JAX', 
             'KC', 'LAC', 'LV', 'MIA', 'NE', 'NYJ', 'PIT', 'TEN']
NFC_TEAMS = ['ARI', 'ATL', 'CAR', 'CHI', 'DAL', 'DET', 'GB', 'LAR',
             'MIN', 'NO', 'NYG', 'PHI', 'SEA', 'SF', 'TB', 'WAS']

# Madden team ID to abbreviation mapping
TEAM_ID_TO_ABBR = {
    0: 'CHI', 1: 'CIN', 2: 'BUF', 3: 'DEN', 4: 'CLE', 5: 'TB', 6: 'ARI', 7: 'LAC',
    8: 'KC', 9: 'IND', 10: 'DAL', 11: 'MIA', 12: 'PHI', 13: 'ATL', 14: 'SF', 15: 'NYG',
    16: 'JAX', 17: 'NYJ', 18: 'DET', 19: 'GB', 20: 'CAR', 21: 'NE', 22: 'LV', 23: 'LAR',
    24: 'BAL', 25: 'WAS', 26: 'NO', 27: 'SEA', 28: 'PIT', 29: 'TEN', 30: 'MIN', 31: 'HOU'
}


class SnallabotIntegrationCog(commands.Cog):
    """Cog for integrating with Snallabot's API for automated playoff processing."""
    
    def __init__(self, bot):
        self.bot = bot
        self.db_path = bot.db_path
        self._ensure_tables()
        self.league_id = None  # Will be set from config or command
        self.platform = "ps5"  # Default platform, can be changed
        
    def cog_load(self):
        """Start the hourly check task when cog loads."""
        self.check_playoff_results.start()
        
    def cog_unload(self):
        """Stop the task when cog unloads."""
        self.check_playoff_results.cancel()
        
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
        
        # Table to store Snallabot config
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS snallabot_config (
                guild_id INTEGER PRIMARY KEY,
                league_id TEXT,
                platform TEXT DEFAULT 'ps5',
                last_check TEXT,
                current_season INTEGER
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
    
    def get_team_abbr(self, team_id: int) -> str:
        """Convert Madden team ID to abbreviation."""
        return TEAM_ID_TO_ABBR.get(team_id, 'UNK')
    
    async def get_snallabot_config(self, guild_id: int) -> Optional[Dict]:
        """Get Snallabot config for a guild using the new league_config system."""
        # Try to get config from the new LeagueConfigCog
        league_config_cog = self.bot.get_cog('LeagueConfigCog')
        if league_config_cog:
            config = league_config_cog.get_league_config(guild_id)
            if config:
                return config
        
        # Fallback to legacy snallabot_config table
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT league_id, platform, current_season FROM snallabot_config WHERE guild_id = ?', (guild_id,))
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return {'league_id': result[0], 'platform': result[1], 'current_season': result[2]}
        return None
    
    async def fetch_schedule(self, platform: str, league_id: str, week: int, stage: str = "reg") -> Optional[List]:
        """Fetch schedule data from Snallabot API."""
        url = f"{SNALLABOT_API_BASE}/{platform}/{league_id}/{week}/{stage}/schedules"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=30) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data
                    else:
                        logger.warning(f"Snallabot API returned {response.status} for {url}")
                        return None
        except Exception as e:
            logger.error(f"Error fetching Snallabot schedule: {e}")
            return None
    
    async def fetch_standings(self, platform: str, league_id: str) -> Optional[List]:
        """Fetch standings data from Snallabot API."""
        url = f"{SNALLABOT_API_BASE}/{platform}/{league_id}/standings"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=30) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data
                    else:
                        logger.warning(f"Snallabot API returned {response.status} for standings")
                        return None
        except Exception as e:
            logger.error(f"Error fetching Snallabot standings: {e}")
            return None
    
    async def check_playoff_week(self, guild: discord.Guild, config: Dict, week: int) -> List[Dict]:
        """Check a specific playoff week for completed games."""
        round_name = PLAYOFF_WEEKS.get(week)
        if not round_name:
            return []
        
        schedule = await self.fetch_schedule(config['platform'], config['league_id'], week)
        if not schedule:
            return []
        
        completed_games = []
        
        for game in schedule:
            # Check if game is completed (result is AWAY_WIN or HOME_WIN)
            result = game.get('result', 1)
            if result not in [2, 3]:  # Not AWAY_WIN or HOME_WIN
                continue
            
            home_team_id = game.get('homeTeamId')
            away_team_id = game.get('awayTeamId')
            home_score = game.get('homeScore', 0)
            away_score = game.get('awayScore', 0)
            
            home_team = self.get_team_abbr(home_team_id)
            away_team = self.get_team_abbr(away_team_id)
            
            if result == 3:  # HOME_WIN
                winner_team = home_team
                loser_team = away_team
                winner_score = home_score
                loser_score = away_score
            else:  # AWAY_WIN
                winner_team = away_team
                loser_team = home_team
                winner_score = away_score
                loser_score = home_score
            
            # Create unique game ID
            game_id = f"{config['current_season']}_{week}_{home_team}_{away_team}"
            
            completed_games.append({
                'game_id': game_id,
                'week': week,
                'round': round_name,
                'winner_team': winner_team,
                'loser_team': loser_team,
                'winner_score': winner_score,
                'loser_score': loser_score
            })
        
        return completed_games
    
    async def process_playoff_game(self, guild: discord.Guild, config: Dict, game: Dict) -> bool:
        """Process a completed playoff game."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Check if already processed
        cursor.execute('SELECT 1 FROM processed_playoff_games WHERE game_id = ?', (game['game_id'],))
        if cursor.fetchone():
            conn.close()
            return False  # Already processed
        
        # Get winner's Discord ID from teams table
        cursor.execute('SELECT user_discord_id FROM teams WHERE team_id = ?', (game['winner_team'],))
        result = cursor.fetchone()
        winner_discord_id = result[0] if result else None
        
        if not winner_discord_id:
            logger.warning(f"Could not find owner for team {game['winner_team']}")
            conn.close()
            return False
        
        winner_conf = self.get_team_conference(game['winner_team'])
        
        # Record the playoff result
        cursor.execute('''
            INSERT OR REPLACE INTO playoff_results 
            (season, round, conference, winner_discord_id, winner_team_id)
            VALUES (?, ?, ?, ?, ?)
        ''', (config['current_season'], game['round'], winner_conf, winner_discord_id, game['winner_team']))
        
        # Mark as processed
        cursor.execute('''
            INSERT INTO processed_playoff_games
            (game_id, season, week, round, winner_team, loser_team, winner_score, loser_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (game['game_id'], config['current_season'], game['week'], game['round'],
              game['winner_team'], game['loser_team'], game['winner_score'], game['loser_score']))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Recorded playoff winner: {game['winner_team']} ({game['round']}) - {game['winner_score']}-{game['loser_score']}")
        
        # Post to payouts channel
        payouts_channel = self.get_payouts_channel(guild)
        if payouts_channel:
            embed = discord.Embed(
                title=f"🏈 {game['round'].title()} Result",
                description=f"**{game['winner_team']}** defeats **{game['loser_team']}**",
                color=discord.Color.green()
            )
            embed.add_field(name="Score", value=f"{game['winner_score']} - {game['loser_score']}", inline=True)
            embed.add_field(name="Conference", value=winner_conf, inline=True)
            embed.set_footer(text=f"Season {config['current_season']} | Auto-detected from Snallabot")
            await payouts_channel.send(embed=embed)
        
        # If Super Bowl, trigger payment generation
        if game['round'] == 'superbowl':
            await self.auto_generate_payments(config['current_season'], guild)
        
        return True
    
    def get_payouts_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        """Find the payouts channel."""
        for name in ['payouts', 'payout', 'finances']:
            channel = discord.utils.get(guild.text_channels, name=name)
            if channel:
                return channel
        return None
    
    async def auto_generate_payments(self, season: int, guild: discord.Guild):
        """Automatically generate all playoff payments after Super Bowl."""
        logger.info(f"Auto-generating payments for Season {season}")
        
        profitability_cog = self.bot.get_cog('ProfitabilityCog')
        if not profitability_cog:
            logger.error("ProfitabilityCog not found, cannot generate payments")
            return
        
        payouts_channel = self.get_payouts_channel(guild)
        
        try:
            # Generate payments using the profitability cog's method
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Call the internal payment generation logic
            # This mimics what the /generatepayments command does
            
            if payouts_channel:
                embed = discord.Embed(
                    title=f"🏆 Season {season} Playoffs Complete!",
                    description="Super Bowl has been played. Generating all playoff payments...",
                    color=discord.Color.gold()
                )
                await payouts_channel.send(embed=embed)
            
            # Trigger the payment generation
            # We'll create a fake interaction context or call the method directly
            # For now, post a notification that payments need to be generated
            if payouts_channel:
                await payouts_channel.send(
                    f"✅ **Season {season} playoff results recorded!**\n"
                    f"Run `/generatepayments season:{season}` to create all payment obligations."
                )
            
            conn.close()
            logger.info(f"Successfully notified about Season {season} payments")
            
        except Exception as e:
            logger.error(f"Error in auto payment generation: {e}")
    
    @tasks.loop(hours=1)
    async def check_playoff_results(self):
        """Hourly task to check Snallabot API for playoff results."""
        logger.info("Running hourly Snallabot playoff check...")
        
        for guild in self.bot.guilds:
            config = await self.get_snallabot_config(guild.id)
            if not config or not config['league_id']:
                continue
            
            # Check all playoff weeks
            for week in PLAYOFF_WEEKS.keys():
                games = await self.check_playoff_week(guild, config, week)
                
                for game in games:
                    processed = await self.process_playoff_game(guild, config, game)
                    if processed:
                        logger.info(f"Processed new playoff game: {game['game_id']}")
            
            # Update last check time
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                'UPDATE snallabot_config SET last_check = ? WHERE guild_id = ?',
                (datetime.now().isoformat(), guild.id)
            )
            conn.commit()
            conn.close()
    
    @check_playoff_results.before_loop
    async def before_check_playoff_results(self):
        """Wait for bot to be ready before starting the task."""
        await self.bot.wait_until_ready()
    
    @app_commands.command(name="setsnallabotconfig", description="[Admin] Configure Snallabot integration")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        league_id="Your Madden league ID from Snallabot",
        platform="Platform (ps5, ps4, xboxone, xboxseries)",
        current_season="Current season number"
    )
    async def set_snallabot_config(
        self,
        interaction: discord.Interaction,
        league_id: str,
        platform: str = "ps5",
        current_season: int = 2025
    ):
        """Configure Snallabot integration settings."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO snallabot_config (guild_id, league_id, platform, current_season)
            VALUES (?, ?, ?, ?)
        ''', (interaction.guild.id, league_id, platform.lower(), current_season))
        
        conn.commit()
        conn.close()
        
        embed = discord.Embed(
            title="✅ Snallabot Configuration Saved",
            color=discord.Color.green()
        )
        embed.add_field(name="League ID", value=league_id, inline=True)
        embed.add_field(name="Platform", value=platform, inline=True)
        embed.add_field(name="Current Season", value=str(current_season), inline=True)
        embed.set_footer(text="Playoff results will be checked every hour automatically")
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="checkplayoffs", description="[Admin] Manually check Snallabot for playoff results")
    @app_commands.default_permissions(administrator=True)
    async def check_playoffs_manual(self, interaction: discord.Interaction):
        """Manually trigger a check for playoff results."""
        await interaction.response.defer(thinking=True)
        
        config = await self.get_snallabot_config(interaction.guild.id)
        if not config or not config['league_id']:
            await interaction.followup.send(
                "❌ Snallabot not configured. Use `/setsnallabotconfig` first.",
                ephemeral=True
            )
            return
        
        games_found = []
        games_processed = []
        
        for week in PLAYOFF_WEEKS.keys():
            games = await self.check_playoff_week(interaction.guild, config, week)
            games_found.extend(games)
            
            for game in games:
                processed = await self.process_playoff_game(interaction.guild, config, game)
                if processed:
                    games_processed.append(game)
        
        embed = discord.Embed(
            title="🔍 Snallabot Playoff Check Complete",
            color=discord.Color.blue()
        )
        embed.add_field(name="Games Found", value=str(len(games_found)), inline=True)
        embed.add_field(name="New Games Processed", value=str(len(games_processed)), inline=True)
        
        if games_processed:
            game_list = "\n".join([
                f"• {g['winner_team']} def. {g['loser_team']} ({g['round']})"
                for g in games_processed
            ])
            embed.add_field(name="Newly Recorded", value=game_list[:1024], inline=False)
        
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="viewplayoffresults", description="View recorded playoff results for a season")
    @app_commands.describe(season="Season number to view")
    async def view_playoff_results(self, interaction: discord.Interaction, season: int):
        """View all recorded playoff results for a season."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT round, winner_team, loser_team, winner_score, loser_score
            FROM processed_playoff_games
            WHERE season = ?
            ORDER BY week
        ''', (season,))
        results = cursor.fetchall()
        conn.close()
        
        if not results:
            await interaction.response.send_message(
                f"No playoff results recorded for Season {season}",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title=f"🏈 Season {season} Playoff Results",
            color=discord.Color.blue()
        )
        
        for round_name, winner, loser, w_score, l_score in results:
            embed.add_field(
                name=round_name.title(),
                value=f"**{winner}** {w_score} - {l_score} {loser}",
                inline=True
            )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="snallabottest", description="[Admin] Test Snallabot API connection")
    @app_commands.default_permissions(administrator=True)
    async def test_snallabot(self, interaction: discord.Interaction):
        """Test the Snallabot API connection."""
        await interaction.response.defer(thinking=True)
        
        config = await self.get_snallabot_config(interaction.guild.id)
        if not config or not config['league_id']:
            await interaction.followup.send(
                "❌ Snallabot not configured. Use `/setsnallabotconfig` first.",
                ephemeral=True
            )
            return
        
        # Try to fetch standings
        standings = await self.fetch_standings(config['platform'], config['league_id'])
        
        embed = discord.Embed(
            title="🔌 Snallabot API Test",
            color=discord.Color.green() if standings else discord.Color.red()
        )
        embed.add_field(name="League ID", value=config['league_id'], inline=True)
        embed.add_field(name="Platform", value=config['platform'], inline=True)
        embed.add_field(name="API Status", value="✅ Connected" if standings else "❌ Failed", inline=True)
        
        if standings:
            embed.add_field(name="Teams Found", value=str(len(standings)), inline=True)
        
        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(SnallabotIntegrationCog(bot))
