"""
Auto Settlement Cog - Automatically settles wagers based on game results
Monitors the #scores channel for MyMadden bot messages and auto-settles matching wagers.
"""
import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import re
import logging
from datetime import datetime
from typing import Optional, Tuple

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


class AutoSettlementCog(commands.Cog):
    """Cog for automatically settling wagers based on game results."""
    
    def __init__(self, bot):
        self.bot = bot
        self.db_path = bot.db_path
        # Channel ID for #scores - will be set dynamically
        self.scores_channel_id = None
        # MyMadden bot user ID (or name pattern)
        self.mymadden_bot_name = "LIV on MyMadden"
        
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
        
        Returns dict with: away_team, home_team, away_score, home_score, week, season_type, year
        """
        lines = content.strip().split('\n')
        
        if len(lines) < 4:
            return None
        
        # Check if this is a MyMadden score message
        if 'on MyMadden' not in lines[0]:
            return None
        
        # Parse the score line (line 2)
        # Format: "Ravens 11-6-0 35 AT 17 Steelers 11-6-0"
        score_line = lines[1].strip()
        
        # Regex pattern to match: TeamName Record Score AT Score TeamName Record
        # Pattern: (TeamName) (Record) (Score) AT (Score) (TeamName) (Record)
        score_pattern = r'^(\w+)\s+(\d+-\d+-\d+)\s+(\d+)\s+AT\s+(\d+)\s+(\w+)\s+(\d+-\d+-\d+)$'
        match = re.match(score_pattern, score_line, re.IGNORECASE)
        
        if not match:
            # Try alternative pattern without records
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
        
        # Normalize team names to abbreviations
        away_team = self.normalize_team(away_team_name)
        home_team = self.normalize_team(home_team_name)
        
        if not away_team or not home_team:
            logger.warning(f"Could not normalize teams: {away_team_name} vs {home_team_name}")
            return None
        
        # Parse season info (line 4)
        # Format: "2027 | Post Season | Divisional"
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
            # Try to extract week number
            week_match = re.search(r'(\d+)', week_str)
            if week_match:
                week = int(week_match.group(1))
            else:
                # Map playoff round names to week numbers
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
            winner = None  # Tie
        
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
    
    async def settle_wagers_for_game(self, game_result: dict, channel: discord.TextChannel) -> list:
        """
        Find and settle all wagers matching this game result.
        Returns list of settled wager info for notification.
        """
        settled_wagers = []
        
        away_team = game_result['away_team']
        home_team = game_result['home_team']
        winner = game_result['winner']
        week = game_result.get('week')
        year = game_result.get('year')
        
        if not winner:
            logger.info(f"Game ended in tie: {away_team} @ {home_team} - no wagers settled")
            return settled_wagers
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Find matching wagers that are:
        # 1. Accepted (away_accepted = 1)
        # 2. Not yet settled (winner_user_id IS NULL)
        # 3. Match the game (home_team_id and away_team_id)
        # 4. Optionally match week if provided
        
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
            
            # Determine wager winner based on picks
            # home_user is the challenger (creator), away_user is the opponent
            if challenger_pick == winner:
                wager_winner = home_user
                wager_loser = away_user
            else:
                wager_winner = away_user
                wager_loser = home_user
            
            # Update the wager
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
                'week': wager_week
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
            
            embed = discord.Embed(
                title="🤖 Wager Auto-Settled!",
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
            embed.set_footer(text="Auto-settled by Mistress LIV based on game results")
            
            await channel.send(embed=embed)
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listen for score messages in #scores channel."""
        # Ignore our own messages
        if message.author == self.bot.user:
            return
        
        # Check if this is from the scores channel
        if message.channel.name != 'scores':
            return
        
        # Check if this looks like a MyMadden score message
        content = message.content
        
        # Also check embeds (MyMadden might use embeds)
        if message.embeds:
            for embed in message.embeds:
                if embed.description:
                    content = embed.description
                elif embed.title and 'MyMadden' in embed.title:
                    # Build content from embed fields
                    content = f"{embed.title}\n"
                    for field in embed.fields:
                        content += f"{field.value}\n"
        
        # Try to parse the score
        game_result = self.parse_mymadden_score(content)
        
        if game_result:
            logger.info(f"Detected game result: {game_result['away_team']} {game_result['away_score']} @ {game_result['home_team']} {game_result['home_score']}")
            
            # Settle matching wagers
            settled = await self.settle_wagers_for_game(game_result, message.channel)
            
            # Send notifications
            if settled:
                await self.send_settlement_notifications(settled, message.channel)
    
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
        
        # Check if user has admin permissions
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
        
        # Validate winning team is one of the teams in the game
        if winning_team_norm not in [home_team, away_team]:
            conn.close()
            await interaction.followup.send(
                f"❌ {winning_team_norm} wasn't in this game! The game was {away_team} @ {home_team}.",
                ephemeral=True
            )
            return
        
        # Determine who won the wager based on picks
        if challenger_pick == winning_team_norm:
            wager_winner = home_user
            wager_loser = away_user
        else:
            wager_winner = away_user
            wager_loser = home_user
        
        # Update the wager
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
        for wager in wagers[:15]:  # Limit to 15
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


async def setup(bot):
    await bot.add_cog(AutoSettlementCog(bot))
