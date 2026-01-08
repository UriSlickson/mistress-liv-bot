"""
Auto Settlement Cog - Automatically settles wagers based on game results
Monitors the #scores channel for MyMadden bot messages and auto-settles matching wagers.
Uses MyMadden website as additional reference for verification.
"""
import discord
from discord.ext import commands, tasks
from discord import app_commands
import sqlite3
import re
import logging
import asyncio
from datetime import datetime
from typing import Optional, Tuple, List, Dict

logger = logging.getLogger('MistressLIV.AutoSettlement')

# Team name to abbreviation mapping (for parsing MyMadden messages)
TEAM_NAME_TO_ABBR = {
    'cardinals': 'ARI', 'falcons': 'ATL', 'ravens': 'BAL', 'bills': 'BUF',
    'panthers': 'CAR', 'bears': 'CHI', 'bengals': 'CIN', 'browns': 'CLE',
    'cowboys': 'DAL', 'broncos': 'DEN', 'lions': 'DET', 'packers': 'GB',
    'texans': 'HOU', 'colts': 'IND', 'jaguars': 'JAX', 'chiefs': 'KC',
    'chargers': 'LAC', 'rams': 'LAR', 'raiders': 'LV', 'dolphins': 'MIA',
    'vikings': 'MIN', 'patriots': 'NE', 'saints': 'NO', 'giants': 'NYG',
    'jets': 'NYJ', 'eagles': 'PHI', 'steelers': 'PIT', 'seahawks': 'SEA',
    '49ers': 'SF', 'buccaneers': 'TB', 'titans': 'TEN', 'commanders': 'WAS',
    # Also include abbreviations themselves
    'ari': 'ARI', 'atl': 'ATL', 'bal': 'BAL', 'buf': 'BUF',
    'car': 'CAR', 'chi': 'CHI', 'cin': 'CIN', 'cle': 'CLE',
    'dal': 'DAL', 'den': 'DEN', 'det': 'DET', 'gb': 'GB',
    'hou': 'HOU', 'ind': 'IND', 'jax': 'JAX', 'kc': 'KC',
    'lac': 'LAC', 'lar': 'LAR', 'lv': 'LV', 'mia': 'MIA',
    'min': 'MIN', 'ne': 'NE', 'no': 'NO', 'nyg': 'NYG',
    'nyj': 'NYJ', 'phi': 'PHI', 'pit': 'PIT', 'sea': 'SEA',
    'sf': 'SF', 'tb': 'TB', 'ten': 'TEN', 'was': 'WAS'
}

ABBR_TO_NAME = {
    'ARI': 'Cardinals', 'ATL': 'Falcons', 'BAL': 'Ravens', 'BUF': 'Bills',
    'CAR': 'Panthers', 'CHI': 'Bears', 'CIN': 'Bengals', 'CLE': 'Browns',
    'DAL': 'Cowboys', 'DEN': 'Broncos', 'DET': 'Lions', 'GB': 'Packers',
    'HOU': 'Texans', 'IND': 'Colts', 'JAX': 'Jaguars', 'KC': 'Chiefs',
    'LAC': 'Chargers', 'LAR': 'Rams', 'LV': 'Raiders', 'MIA': 'Dolphins',
    'MIN': 'Vikings', 'NE': 'Patriots', 'NO': 'Saints', 'NYG': 'Giants',
    'NYJ': 'Jets', 'PHI': 'Eagles', 'PIT': 'Steelers', 'SEA': 'Seahawks',
    'SF': '49ers', 'TB': 'Buccaneers', 'TEN': 'Titans', 'WAS': 'Commanders'
}


class MyMaddenScraper:
    """Inline scraper for MyMadden website game results."""
    
    BASE_URL = "https://mymadden.com/lg/liv"
    
    def __init__(self):
        self.session = None
    
    async def _ensure_session(self):
        """Ensure aiohttp session exists."""
        try:
            import aiohttp
            if self.session is None or self.session.closed:
                self.session = aiohttp.ClientSession()
        except ImportError:
            logger.warning("aiohttp not installed, MyMadden scraping disabled")
            self.session = None
    
    async def close(self):
        """Close the aiohttp session."""
        if self.session and not self.session.closed:
            await self.session.close()
    
    def _normalize_team(self, team_name: str) -> Optional[str]:
        """Convert team name to standard abbreviation."""
        team_lower = team_name.lower().strip()
        return TEAM_NAME_TO_ABBR.get(team_lower)
    
    def _build_schedule_url(self, year: int, season_type: str, week: int) -> str:
        """Build the URL for a specific week's schedule."""
        if season_type == 'post':
            week_map = {
                19: 'wildcard', 20: 'divisional', 21: 'conference', 22: 'superbowl'
            }
            week_str = week_map.get(week, str(week))
        else:
            week_str = str(week)
        
        return f"{self.BASE_URL}/schedule/{year}/{season_type}/{week_str}"
    
    async def fetch_schedule_page(self, year: int, season_type: str, week: int) -> Optional[str]:
        """Fetch the HTML content of a schedule page."""
        await self._ensure_session()
        if not self.session:
            return None
        
        import aiohttp
        url = self._build_schedule_url(year, season_type, week)
        logger.info(f"Fetching schedule from: {url}")
        
        try:
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    return await response.text()
                else:
                    logger.error(f"Failed to fetch schedule: HTTP {response.status}")
                    return None
        except Exception as e:
            logger.error(f"Error fetching schedule: {e}")
            return None
    
    def parse_games_from_html(self, html_content: str) -> List[Dict]:
        """Parse game results from the schedule page HTML."""
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            logger.warning("BeautifulSoup not installed, cannot parse HTML")
            return []
        
        games = []
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Find all game cards - they use custom <basic-panel> elements with 'game' class
        game_divs = soup.find_all('basic-panel')
        game_divs = [d for d in game_divs if d.get('class') and 'game' in d.get('class')]
        
        for game_div in game_divs:
            try:
                text_content = game_div.get_text(separator='|', strip=True)
                parts = [p.strip() for p in text_content.split('|') if p.strip()]
                
                if len(parts) < 4:
                    continue
                
                away_team_name = None
                away_score = None
                home_team_name = None
                home_score = None
                
                idx = 0
                
                # Away team
                if idx < len(parts) and not parts[idx].isdigit() and not re.match(r'\d+-\d+-\d+', parts[idx]):
                    away_team_name = parts[idx]
                    idx += 1
                
                # Away score
                if idx < len(parts) and parts[idx].isdigit():
                    away_score = int(parts[idx])
                    idx += 1
                
                # Skip record
                if idx < len(parts) and re.match(r'\d+-\d+-\d+', parts[idx]):
                    idx += 1
                
                # Skip game day
                if idx < len(parts) and parts[idx] in ['TNF', 'MNF', 'SNF', 'SUN', 'SAT']:
                    idx += 1
                
                # Home team
                if idx < len(parts) and not parts[idx].isdigit() and not re.match(r'\d+-\d+-\d+', parts[idx]):
                    home_team_name = parts[idx]
                    idx += 1
                
                # Home score
                if idx < len(parts) and parts[idx].isdigit():
                    home_score = int(parts[idx])
                
                if not all([away_team_name, home_team_name]):
                    continue
                
                away_team = self._normalize_team(away_team_name)
                home_team = self._normalize_team(home_team_name)
                
                if not away_team or not home_team:
                    continue
                
                completed = away_score is not None and home_score is not None
                winner = None
                
                if completed:
                    if away_score > home_score:
                        winner = away_team
                    elif home_score > away_score:
                        winner = home_team
                
                games.append({
                    'away_team': away_team,
                    'home_team': home_team,
                    'away_score': away_score,
                    'home_score': home_score,
                    'winner': winner,
                    'completed': completed
                })
                
            except Exception as e:
                logger.error(f"Error parsing game div: {e}")
                continue
        
        return games
    
    async def get_games_for_week(self, year: int, season_type: str, week: int) -> List[Dict]:
        """Fetch and parse all games for a specific week."""
        html = await self.fetch_schedule_page(year, season_type, week)
        if not html:
            return []
        return self.parse_games_from_html(html)
    
    async def verify_game_result(self, away_team: str, home_team: str, 
                                  year: int, season_type: str, week: int) -> Optional[Dict]:
        """Verify a specific game result from the MyMadden website."""
        games = await self.get_games_for_week(year, season_type, week)
        
        for game in games:
            if game['away_team'] == away_team and game['home_team'] == home_team:
                return game
            # Try reverse
            if game['away_team'] == home_team and game['home_team'] == away_team:
                return game
        
        return None


class AutoSettlementCog(commands.Cog):
    """Cog for automatically settling wagers based on game results."""
    
    def __init__(self, bot):
        self.bot = bot
        self.db_path = bot.db_path
        self.scores_channel_id = None
        self.mymadden_bot_name = "LIV on MyMadden"
        self.scraper = MyMaddenScraper()
        # Start the periodic check task
        self.check_pending_wagers.start()
        
    def cog_unload(self):
        """Clean up when cog is unloaded."""
        self.check_pending_wagers.cancel()
        asyncio.create_task(self.scraper.close())
    
    def normalize_team(self, team_input: str) -> Optional[str]:
        """Normalize team name to standard abbreviation."""
        team_lower = team_input.lower().strip()
        return TEAM_NAME_TO_ABBR.get(team_lower)
    
    def parse_mymadden_score(self, content: str) -> Optional[dict]:
        """
        Parse a MyMadden score message.
        
        Expected format:
        LIV on MyMadden
        Ravens 11-6-0 35 AT 17 Steelers 11-6-0
        @Repenters AT @hi
        2027 | Post Season | Divisional
        """
        lines = content.strip().split('\n')
        
        if len(lines) < 4:
            return None
        
        if 'on MyMadden' not in lines[0]:
            return None
        
        score_line = lines[1].strip()
        
        # Regex pattern: TeamName Record Score AT Score TeamName Record
        score_pattern = r'^(\w+)\s+(\d+-\d+-\d+)\s+(\d+)\s+AT\s+(\d+)\s+(\w+)\s+(\d+-\d+-\d+)$'
        match = re.match(score_pattern, score_line, re.IGNORECASE)
        
        if not match:
            score_pattern_alt = r'^(\w+)\s+(\d+)\s+AT\s+(\d+)\s+(\w+)$'
            match = re.match(score_pattern_alt, score_line, re.IGNORECASE)
            if match:
                away_team_name = match.group(1)
                away_score = int(match.group(2))
                home_score = int(match.group(3))
                home_team_name = match.group(4)
            else:
                logger.warning(f"Could not parse score line: {score_line}")
                return None
        else:
            away_team_name = match.group(1)
            away_score = int(match.group(3))
            home_score = int(match.group(4))
            home_team_name = match.group(5)
        
        away_team = self.normalize_team(away_team_name)
        home_team = self.normalize_team(home_team_name)
        
        if not away_team or not home_team:
            logger.warning(f"Could not normalize teams: {away_team_name} vs {home_team_name}")
            return None
        
        # Parse season info
        season_line = lines[3].strip() if len(lines) > 3 else ""
        season_parts = [p.strip() for p in season_line.split('|')]
        
        year = None
        season_type = "Regular Season"
        week = None
        
        if len(season_parts) >= 1:
            try:
                year = int(season_parts[0])
            except ValueError:
                year = datetime.now().year
        
        if len(season_parts) >= 2:
            season_type = season_parts[1].strip()
        
        if len(season_parts) >= 3:
            week_str = season_parts[2].strip()
            week_match = re.search(r'(\d+)', week_str)
            if week_match:
                week = int(week_match.group(1))
            else:
                week_map = {
                    'wildcard': 19, 'wild card': 19,
                    'divisional': 20,
                    'conference': 21,
                    'super bowl': 22, 'superbowl': 22
                }
                week = week_map.get(week_str.lower(), None)
        
        # Determine winner
        if away_score > home_score:
            winner = away_team
        elif home_score > away_score:
            winner = home_team
        else:
            winner = None
        
        return {
            'away_team': away_team,
            'home_team': home_team,
            'away_score': away_score,
            'home_score': home_score,
            'winner': winner,
            'year': year,
            'season_type': season_type,
            'week': week
        }
    
    async def verify_with_website(self, game_result: dict) -> Optional[dict]:
        """
        Verify game result using MyMadden website as additional reference.
        Returns verified game result or None if verification fails.
        """
        year = game_result.get('year')
        season_type = game_result.get('season_type', 'Regular Season')
        week = game_result.get('week')
        
        if not year or not week:
            logger.info("Cannot verify - missing year or week info")
            return game_result  # Return original if we can't verify
        
        # Map season type to URL format
        season_type_map = {
            'Regular Season': 'reg',
            'Pre Season': 'pre',
            'Post Season': 'post',
            'Preseason': 'pre',
            'Postseason': 'post'
        }
        season_type_url = season_type_map.get(season_type, 'reg')
        
        try:
            website_result = await self.scraper.verify_game_result(
                game_result['away_team'],
                game_result['home_team'],
                year,
                season_type_url,
                week
            )
            
            if website_result:
                # Compare results
                if website_result['winner'] == game_result['winner']:
                    logger.info(f"✅ Website verification SUCCESS: {game_result['away_team']} @ {game_result['home_team']}")
                    game_result['verified'] = True
                    game_result['verification_source'] = 'MyMadden Website'
                else:
                    logger.warning(f"⚠️ Website verification MISMATCH: Discord says {game_result['winner']}, Website says {website_result['winner']}")
                    # Use website result as authoritative
                    game_result['winner'] = website_result['winner']
                    game_result['away_score'] = website_result['away_score']
                    game_result['home_score'] = website_result['home_score']
                    game_result['verified'] = True
                    game_result['verification_source'] = 'MyMadden Website (corrected)'
            else:
                logger.info(f"Could not find game on website for verification")
                game_result['verified'] = False
                game_result['verification_source'] = 'Discord only'
                
        except Exception as e:
            logger.error(f"Error during website verification: {e}")
            game_result['verified'] = False
            game_result['verification_source'] = 'Discord only (verification error)'
        
        return game_result
    
    async def settle_wagers_for_game(self, game_result: dict, channel: discord.TextChannel) -> list:
        """Find and settle all wagers matching this game result."""
        settled_wagers = []
        
        away_team = game_result['away_team']
        home_team = game_result['home_team']
        winner = game_result['winner']
        week = game_result.get('week')
        
        if not winner:
            logger.info(f"Game ended in tie: {away_team} @ {home_team} - no wagers settled")
            return settled_wagers
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        query = '''
            SELECT wager_id, season_year, week, home_team_id, away_team_id,
                   home_user_id, away_user_id, amount, challenger_pick, opponent_pick
            FROM wagers
            WHERE away_accepted = 1
            AND winner_user_id IS NULL
            AND home_team_id = ?
            AND away_team_id = ?
        '''
        params = [home_team, away_team]
        
        if week:
            query += ' AND week = ?'
            params.append(week)
        
        cursor.execute(query, params)
        wagers = cursor.fetchall()
        
        logger.info(f"Found {len(wagers)} pending wagers for {away_team} @ {home_team}")
        
        for wager in wagers:
            wager_id, season, wager_week, h_team, a_team, home_user, away_user, amount, challenger_pick, opponent_pick = wager
            
            if challenger_pick == winner:
                wager_winner = home_user
                wager_loser = away_user
            else:
                wager_winner = away_user
                wager_loser = home_user
            
            cursor.execute('''
                UPDATE wagers SET winner_user_id = ?, game_winner = ? WHERE wager_id = ?
            ''', (wager_winner, winner, wager_id))
            
            settled_wagers.append({
                'wager_id': wager_id,
                'winner_user_id': wager_winner,
                'loser_user_id': wager_loser,
                'amount': amount,
                'game_winner': winner,
                'away_team': away_team,
                'home_team': home_team,
                'week': wager_week,
                'verified': game_result.get('verified', False),
                'verification_source': game_result.get('verification_source', 'Unknown')
            })
            
            logger.info(f"Auto-settled wager #{wager_id}: {winner} won, user {wager_winner} wins ${amount}")
        
        conn.commit()
        conn.close()
        
        return settled_wagers
    
    async def send_settlement_notifications(self, settled_wagers: list, channel: discord.TextChannel):
        """Send notifications for auto-settled wagers."""
        if not settled_wagers:
            return
        
        for wager in settled_wagers:
            winner_member = channel.guild.get_member(wager['winner_user_id'])
            loser_member = channel.guild.get_member(wager['loser_user_id'])
            
            winner_mention = winner_member.mention if winner_member else f"<@{wager['winner_user_id']}>"
            loser_mention = loser_member.mention if loser_member else f"<@{wager['loser_user_id']}>"
            
            away_name = ABBR_TO_NAME.get(wager['away_team'], wager['away_team'])
            home_name = ABBR_TO_NAME.get(wager['home_team'], wager['home_team'])
            winner_name = ABBR_TO_NAME.get(wager['game_winner'], wager['game_winner'])
            
            # Add verification badge
            if wager.get('verified'):
                title = "🤖✅ Wager Auto-Settled (Verified)"
            else:
                title = "🤖 Wager Auto-Settled"
            
            embed = discord.Embed(
                title=title,
                description=f"**{winner_name}** won the game!",
                color=discord.Color.green()
            )
            embed.add_field(name="🆔 Wager ID", value=f"#{wager['wager_id']}", inline=True)
            embed.add_field(name="💰 Amount", value=f"${wager['amount']:.2f}", inline=True)
            embed.add_field(name="📅 Week", value=f"{wager['week']}", inline=True)
            embed.add_field(name="🏈 Game", value=f"{away_name} @ {home_name}", inline=False)
            embed.add_field(name="🏆 Wager Winner", value=winner_mention, inline=True)
            embed.add_field(name="💸 Owes Payment", value=loser_mention, inline=True)
            embed.add_field(
                name="📋 Next Steps",
                value=f"{loser_mention} pays ${wager['amount']:.2f} to {winner_mention}\nThen {winner_mention} uses `/markwagerpaid {wager['wager_id']}` to confirm",
                inline=False
            )
            
            # Add verification source
            if wager.get('verification_source'):
                embed.set_footer(text=f"Source: {wager['verification_source']} | Auto-settled by Mistress LIV")
            else:
                embed.set_footer(text="Auto-settled by Mistress LIV based on game results")
            
            await channel.send(embed=embed)
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listen for score messages in #scores channel."""
        if message.author == self.bot.user:
            return
        
        if message.channel.name != 'scores':
            return
        
        content = message.content
        
        if message.embeds:
            for embed in message.embeds:
                if embed.description:
                    content = embed.description
                elif embed.title and 'MyMadden' in embed.title:
                    content = f"{embed.title}\n"
                    for field in embed.fields:
                        content += f"{field.value}\n"
        
        game_result = self.parse_mymadden_score(content)
        
        if game_result:
            logger.info(f"Detected game result: {game_result['away_team']} {game_result['away_score']} @ {game_result['home_team']} {game_result['home_score']}")
            
            # Verify with MyMadden website
            game_result = await self.verify_with_website(game_result)
            
            # Settle matching wagers
            settled = await self.settle_wagers_for_game(game_result, message.channel)
            
            if settled:
                await self.send_settlement_notifications(settled, message.channel)
    
    @tasks.loop(minutes=30)
    async def check_pending_wagers(self):
        """Periodically check for pending wagers and try to settle them using MyMadden website."""
        await self.bot.wait_until_ready()
        
        logger.info("Running periodic wager check...")
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get pending wagers grouped by game
        cursor.execute('''
            SELECT DISTINCT season_year, week, home_team_id, away_team_id
            FROM wagers
            WHERE away_accepted = 1 AND winner_user_id IS NULL
        ''')
        
        pending_games = cursor.fetchall()
        conn.close()
        
        if not pending_games:
            logger.info("No pending wagers to check")
            return
        
        logger.info(f"Found {len(pending_games)} games with pending wagers")
        
        for year, week, home_team, away_team in pending_games:
            try:
                # Try to get result from website
                website_result = await self.scraper.verify_game_result(
                    away_team, home_team, year, 'reg', week
                )
                
                if website_result and website_result.get('completed') and website_result.get('winner'):
                    logger.info(f"Found completed game on website: {away_team} @ {home_team}, winner: {website_result['winner']}")
                    
                    # Create game result dict
                    game_result = {
                        'away_team': away_team,
                        'home_team': home_team,
                        'away_score': website_result['away_score'],
                        'home_score': website_result['home_score'],
                        'winner': website_result['winner'],
                        'year': year,
                        'week': week,
                        'verified': True,
                        'verification_source': 'MyMadden Website (periodic check)'
                    }
                    
                    # Find a channel to send notifications
                    for guild in self.bot.guilds:
                        scores_channel = discord.utils.get(guild.text_channels, name='scores')
                        if scores_channel:
                            settled = await self.settle_wagers_for_game(game_result, scores_channel)
                            if settled:
                                await self.send_settlement_notifications(settled, scores_channel)
                            break
                            
            except Exception as e:
                logger.error(f"Error checking game {away_team} @ {home_team}: {e}")
                continue
            
            # Small delay between requests
            await asyncio.sleep(2)
    
    @check_pending_wagers.before_loop
    async def before_check_pending_wagers(self):
        """Wait for bot to be ready before starting the task."""
        await self.bot.wait_until_ready()
    
    @app_commands.command(name="checkscore", description="Check a game result from MyMadden website")
    @app_commands.describe(
        away_team="The away team",
        home_team="The home team",
        year="Season year (e.g., 2027)",
        week="Week number"
    )
    async def checkscore(self, interaction: discord.Interaction, away_team: str, home_team: str, year: int, week: int):
        """Check a game result directly from MyMadden website."""
        await interaction.response.defer(ephemeral=True)
        
        away_abbr = self.normalize_team(away_team)
        home_abbr = self.normalize_team(home_team)
        
        if not away_abbr or not home_abbr:
            await interaction.followup.send(f"❌ Invalid team name(s): {away_team}, {home_team}", ephemeral=True)
            return
        
        result = await self.scraper.verify_game_result(away_abbr, home_abbr, year, 'reg', week)
        
        if result:
            away_name = ABBR_TO_NAME.get(result['away_team'], result['away_team'])
            home_name = ABBR_TO_NAME.get(result['home_team'], result['home_team'])
            
            if result['completed']:
                winner_name = ABBR_TO_NAME.get(result['winner'], 'TIE') if result['winner'] else 'TIE'
                embed = discord.Embed(
                    title="📊 Game Result from MyMadden",
                    description=f"**{winner_name}** won!",
                    color=discord.Color.green()
                )
                embed.add_field(name="Away Team", value=f"{away_name} ({result['away_team']})", inline=True)
                embed.add_field(name="Home Team", value=f"{home_name} ({result['home_team']})", inline=True)
                embed.add_field(name="Score", value=f"{result['away_score']} - {result['home_score']}", inline=True)
            else:
                embed = discord.Embed(
                    title="📊 Game from MyMadden",
                    description="Game not yet completed",
                    color=discord.Color.orange()
                )
                embed.add_field(name="Away Team", value=f"{away_name} ({result['away_team']})", inline=True)
                embed.add_field(name="Home Team", value=f"{home_name} ({result['home_team']})", inline=True)
            
            embed.add_field(name="Year", value=str(year), inline=True)
            embed.add_field(name="Week", value=str(week), inline=True)
            embed.set_footer(text="Data from mymadden.com")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(f"❌ Could not find game: {away_team} @ {home_team} (Week {week}, {year})", ephemeral=True)
    
    @app_commands.command(name="parsescore", description="Manually parse a score message to test auto-settlement")
    @app_commands.describe(message_content="The score message to parse (copy/paste from #scores)")
    async def parsescore(self, interaction: discord.Interaction, message_content: str):
        """Test the score parsing without actually settling wagers."""
        await interaction.response.defer(ephemeral=True)
        
        result = self.parse_mymadden_score(message_content)
        
        if result:
            away_name = ABBR_TO_NAME.get(result['away_team'], result['away_team'])
            home_name = ABBR_TO_NAME.get(result['home_team'], result['home_team'])
            winner_name = ABBR_TO_NAME.get(result['winner'], 'TIE') if result['winner'] else 'TIE'
            
            embed = discord.Embed(
                title="📊 Score Parse Result",
                color=discord.Color.blue()
            )
            embed.add_field(name="Away Team", value=f"{away_name} ({result['away_team']})", inline=True)
            embed.add_field(name="Home Team", value=f"{home_name} ({result['home_team']})", inline=True)
            embed.add_field(name="Score", value=f"{result['away_score']} - {result['home_score']}", inline=True)
            embed.add_field(name="Winner", value=winner_name, inline=True)
            embed.add_field(name="Year", value=str(result.get('year', 'Unknown')), inline=True)
            embed.add_field(name="Week", value=str(result.get('week', 'Unknown')), inline=True)
            embed.add_field(name="Season Type", value=result.get('season_type', 'Unknown'), inline=True)
            
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send("❌ Could not parse score message. Make sure it's in MyMadden format.", ephemeral=True)
    
    @app_commands.command(name="settlewager", description="Manually settle a wager by specifying the game winner")
    @app_commands.describe(
        wager_id="The ID of the wager to settle",
        winning_team="The team that won the game"
    )
    async def settlewager(self, interaction: discord.Interaction, wager_id: int, winning_team: str):
        """Admin command to manually settle a wager."""
        await interaction.response.defer()
        
        if not interaction.user.guild_permissions.administrator:
            await interaction.followup.send("❌ Only admins can manually settle wagers!", ephemeral=True)
            return
        
        winning_team_norm = self.normalize_team(winning_team)
        if not winning_team_norm:
            await interaction.followup.send(f"❌ Invalid team: {winning_team}", ephemeral=True)
            return
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT wager_id, season_year, week, home_team_id, away_team_id,
                   home_user_id, away_user_id, amount, away_accepted, winner_user_id,
                   challenger_pick, opponent_pick
            FROM wagers WHERE wager_id = ?
        ''', (wager_id,))
        
        wager = cursor.fetchone()
        
        if not wager:
            conn.close()
            await interaction.followup.send(f"❌ Wager #{wager_id} not found!", ephemeral=True)
            return
        
        wager_id, season, week, home_team, away_team, home_user, away_user, amount, accepted, winner, challenger_pick, opponent_pick = wager
        
        if not accepted:
            conn.close()
            await interaction.followup.send("❌ This wager hasn't been accepted yet!", ephemeral=True)
            return
        
        if winner:
            conn.close()
            await interaction.followup.send("❌ This wager has already been settled!", ephemeral=True)
            return
        
        if winning_team_norm not in [home_team, away_team]:
            conn.close()
            await interaction.followup.send(
                f"❌ {winning_team_norm} wasn't in this game! The game was {away_team} @ {home_team}.",
                ephemeral=True
            )
            return
        
        if challenger_pick == winning_team_norm:
            wager_winner = home_user
            wager_loser = away_user
        else:
            wager_winner = away_user
            wager_loser = home_user
        
        cursor.execute('''
            UPDATE wagers SET winner_user_id = ?, game_winner = ? WHERE wager_id = ?
        ''', (wager_winner, winning_team_norm, wager_id))
        conn.commit()
        conn.close()
        
        winner_member = interaction.guild.get_member(wager_winner)
        loser_member = interaction.guild.get_member(wager_loser)
        winner_mention = winner_member.mention if winner_member else f"<@{wager_winner}>"
        loser_mention = loser_member.mention if loser_member else f"<@{wager_loser}>"
        
        winning_team_name = ABBR_TO_NAME.get(winning_team_norm, winning_team_norm)
        away_name = ABBR_TO_NAME.get(away_team, away_team)
        home_name = ABBR_TO_NAME.get(home_team, home_team)
        
        embed = discord.Embed(
            title="🏆 Wager Manually Settled!",
            description=f"**{winning_team_name}** won the game!",
            color=discord.Color.green()
        )
        embed.add_field(name="🆔 Wager ID", value=f"#{wager_id}", inline=True)
        embed.add_field(name="💰 Amount", value=f"${amount:.2f}", inline=True)
        embed.add_field(name="🏈 Game", value=f"{away_name} @ {home_name}", inline=True)
        embed.add_field(name="🏆 Winner", value=winner_mention, inline=True)
        embed.add_field(name="💸 Owes", value=loser_mention, inline=True)
        embed.add_field(
            name="📋 Next Steps",
            value=f"{loser_mention} pays ${amount:.2f} to {winner_mention}\nThen {winner_mention} uses `/markwagerpaid {wager_id}` to confirm",
            inline=False
        )
        embed.set_footer(text=f"Settled by {interaction.user.display_name}")
        
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="pendingwagers", description="View all pending wagers waiting for game results")
    async def pendingwagers(self, interaction: discord.Interaction):
        """View all pending wagers that haven't been settled yet."""
        await interaction.response.defer()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT wager_id, season_year, week, home_team_id, away_team_id,
                   home_user_id, away_user_id, amount, challenger_pick
            FROM wagers
            WHERE away_accepted = 1 AND winner_user_id IS NULL
            ORDER BY week ASC
        ''')
        
        wagers = cursor.fetchall()
        conn.close()
        
        if not wagers:
            await interaction.followup.send("📭 No pending wagers waiting for game results!")
            return
        
        embed = discord.Embed(
            title="⏳ Pending Wagers",
            description="Wagers waiting for game results to be auto-settled",
            color=discord.Color.orange()
        )
        
        wager_list = []
        for wager in wagers[:15]:
            wager_id, season, week, home_team, away_team, home_user, away_user, amount, challenger_pick = wager
            away_name = ABBR_TO_NAME.get(away_team, away_team)
            home_name = ABBR_TO_NAME.get(home_team, home_team)
            
            wager_list.append(
                f"**#{wager_id}** - Week {week}: {away_name} @ {home_name} (${amount:.2f})"
            )
        
        embed.add_field(name="Pending Wagers", value="\n".join(wager_list) or "None", inline=False)
        
        if len(wagers) > 15:
            embed.set_footer(text=f"Showing 15 of {len(wagers)} pending wagers")
        else:
            embed.set_footer(text=f"Total: {len(wagers)} pending wagers")
        
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="forcecheckwagers", description="Force check all pending wagers against MyMadden website")
    async def forcecheckwagers(self, interaction: discord.Interaction):
        """Admin command to force check all pending wagers."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only admins can use this command!", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        # Trigger the periodic check manually
        await self.check_pending_wagers()
        
        await interaction.followup.send("✅ Forced check of all pending wagers completed. Check #scores for any settlements.")


async def setup(bot):
    await bot.add_cog(AutoSettlementCog(bot))
