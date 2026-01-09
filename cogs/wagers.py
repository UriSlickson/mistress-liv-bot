"""
Wagers Cog - Complete wager system for Mistress LIV Bot
Handles creating, tracking, and settling wagers between league members.
Allows betting on ANY game, not just games between the two bettors.
"""
import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
from datetime import datetime
import logging
from typing import Optional, Literal

logger = logging.getLogger('MistressLIV.Wagers')

# NFL Teams for autocomplete
NFL_TEAMS = [
    'ARI', 'ATL', 'BAL', 'BUF', 'CAR', 'CHI', 'CIN', 'CLE',
    'DAL', 'DEN', 'DET', 'GB', 'HOU', 'IND', 'JAX', 'KC',
    'LAC', 'LAR', 'LV', 'MIA', 'MIN', 'NE', 'NO', 'NYG',
    'NYJ', 'PHI', 'PIT', 'SEA', 'SF', 'TB', 'TEN', 'WAS'
]

TEAM_NAMES = {
    'ARI': 'Cardinals', 'ATL': 'Falcons', 'BAL': 'Ravens', 'BUF': 'Bills',
    'CAR': 'Panthers', 'CHI': 'Bears', 'CIN': 'Bengals', 'CLE': 'Browns',
    'DAL': 'Cowboys', 'DEN': 'Broncos', 'DET': 'Lions', 'GB': 'Packers',
    'HOU': 'Texans', 'IND': 'Colts', 'JAX': 'Jaguars', 'KC': 'Chiefs',
    'LAC': 'Chargers', 'LAR': 'Rams', 'LV': 'Raiders', 'MIA': 'Dolphins',
    'MIN': 'Vikings', 'NE': 'Patriots', 'NO': 'Saints', 'NYG': 'Giants',
    'NYJ': 'Jets', 'PHI': 'Eagles', 'PIT': 'Steelers', 'SEA': 'Seahawks',
    'SF': '49ers', 'TB': 'Buccaneers', 'TEN': 'Titans', 'WAS': 'Commanders'
}


class WagersCog(commands.Cog):
    """Cog for managing wagers between league members."""
    
    def __init__(self, bot):
        self.bot = bot
        self.db_path = bot.db_path
        self._ensure_tables()
    
    def _ensure_tables(self):
        """Ensure wagers table has all required columns."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Check if we need to add new columns
        cursor.execute("PRAGMA table_info(wagers)")
        columns = [col[1] for col in cursor.fetchall()]
        
        # Add challenger_pick column if it doesn't exist
        if 'challenger_pick' not in columns:
            try:
                cursor.execute('ALTER TABLE wagers ADD COLUMN challenger_pick TEXT')
            except:
                pass
        
        # Add opponent_pick column if it doesn't exist
        if 'opponent_pick' not in columns:
            try:
                cursor.execute('ALTER TABLE wagers ADD COLUMN opponent_pick TEXT')
            except:
                pass
        
        # Add game_winner column if it doesn't exist
        if 'game_winner' not in columns:
            try:
                cursor.execute('ALTER TABLE wagers ADD COLUMN game_winner TEXT')
            except:
                pass
        
        conn.commit()
        conn.close()
    
    def normalize_team(self, team_input: str) -> Optional[str]:
        """Normalize team input to standard abbreviation."""
        team_upper = team_input.upper().strip()
        
        # Direct abbreviation match
        if team_upper in NFL_TEAMS:
            return team_upper
        
        # Check team names
        for abbr, name in TEAM_NAMES.items():
            if name.lower() == team_input.lower() or name.lower() in team_input.lower():
                return abbr
        
        return None
    
    async def team_autocomplete(self, interaction: discord.Interaction, current: str):
        """Autocomplete for team selection."""
        choices = []
        current_lower = current.lower()
        
        for abbr in NFL_TEAMS:
            name = TEAM_NAMES.get(abbr, abbr)
            display = f"{name} ({abbr})"
            if current_lower in abbr.lower() or current_lower in name.lower():
                choices.append(app_commands.Choice(name=display, value=abbr))
        
        return choices[:25]  # Discord limit
    
    @app_commands.command(name="wager", description="Create a wager on any game")
    @app_commands.describe(
        opponent="The person you want to bet against",
        amount="Amount of the wager in dollars (max $1,000)",
        week="Week number (1-18 regular, 19-22 playoffs)",
        away_team="The AWAY team in the game",
        home_team="The HOME team in the game",
        your_pick="Which team YOU are picking to win"
    )
    @app_commands.autocomplete(away_team=team_autocomplete, home_team=team_autocomplete, your_pick=team_autocomplete)
    async def wager(
        self, 
        interaction: discord.Interaction, 
        opponent: discord.Member,
        amount: float,
        week: int,
        away_team: str,
        home_team: str,
        your_pick: str
    ):
        """Create a wager challenge on any game."""
        await interaction.response.defer()
        
        # Validate amount
        if amount <= 0:
            await interaction.followup.send("❌ Wager amount must be greater than $0!", ephemeral=True)
            return
        
        if amount > 1000:
            await interaction.followup.send("❌ Maximum wager amount is $1,000!", ephemeral=True)
            return
        
        # Validate week
        if week < 1 or week > 22:
            await interaction.followup.send("❌ Week must be between 1-18 (regular) or 19-22 (playoffs)!", ephemeral=True)
            return
        
        # Can't wager against yourself
        if opponent.id == interaction.user.id:
            await interaction.followup.send("❌ You can't wager against yourself!", ephemeral=True)
            return
        
        # Can't wager against bots
        if opponent.bot:
            await interaction.followup.send("❌ You can't wager against a bot!", ephemeral=True)
            return
        
        # Normalize team inputs
        away_team_norm = self.normalize_team(away_team)
        home_team_norm = self.normalize_team(home_team)
        your_pick_norm = self.normalize_team(your_pick)
        
        if not away_team_norm:
            await interaction.followup.send(f"❌ Invalid away team: {away_team}. Use team abbreviation (e.g., DAL, SF, GB).", ephemeral=True)
            return
        
        if not home_team_norm:
            await interaction.followup.send(f"❌ Invalid home team: {home_team}. Use team abbreviation (e.g., DAL, SF, GB).", ephemeral=True)
            return
        
        if not your_pick_norm:
            await interaction.followup.send(f"❌ Invalid pick: {your_pick}. Use team abbreviation (e.g., DAL, SF, GB).", ephemeral=True)
            return
        
        # Your pick must be one of the teams in the game
        if your_pick_norm not in [away_team_norm, home_team_norm]:
            await interaction.followup.send(f"❌ Your pick must be either {away_team_norm} or {home_team_norm}!", ephemeral=True)
            return
        
        # Can't have same team as home and away
        if away_team_norm == home_team_norm:
            await interaction.followup.send("❌ Away team and home team can't be the same!", ephemeral=True)
            return
        
        # Determine opponent's pick (opposite of yours)
        opponent_pick = home_team_norm if your_pick_norm == away_team_norm else away_team_norm
        
        # Determine week type
        week_type = "regular" if week <= 18 else "playoffs"
        
        # Get current season (use current year)
        season_year = datetime.now().year
        
        # Check if wager already exists for this exact game between these users
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT wager_id FROM wagers 
            WHERE season_year = ? AND week = ?
            AND home_team_id = ? AND away_team_id = ?
            AND ((home_user_id = ? AND away_user_id = ?) OR (home_user_id = ? AND away_user_id = ?))
            AND winner_user_id IS NULL
        ''', (season_year, week, home_team_norm, away_team_norm, 
              interaction.user.id, opponent.id, opponent.id, interaction.user.id))
        
        existing = cursor.fetchone()
        if existing:
            conn.close()
            await interaction.followup.send(
                f"❌ You already have an active wager with {opponent.display_name} on {away_team_norm} @ {home_team_norm} for Week {week}!", 
                ephemeral=True
            )
            return
        
        # Create the wager
        cursor.execute('''
            INSERT INTO wagers (season_year, week, week_type, home_team_id, away_team_id, 
                               home_user_id, away_user_id, amount, home_accepted, challenger_pick, opponent_pick)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
        ''', (season_year, week, week_type, home_team_norm, away_team_norm, 
              interaction.user.id, opponent.id, amount, your_pick_norm, opponent_pick))
        
        wager_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # Get team full names
        away_name = TEAM_NAMES.get(away_team_norm, away_team_norm)
        home_name = TEAM_NAMES.get(home_team_norm, home_team_norm)
        pick_name = TEAM_NAMES.get(your_pick_norm, your_pick_norm)
        opp_pick_name = TEAM_NAMES.get(opponent_pick, opponent_pick)
        
        # Create embed for the wager challenge
        embed = discord.Embed(
            title="🎰 New Wager Challenge!",
            description=f"{interaction.user.mention} has challenged {opponent.mention} to a wager!",
            color=discord.Color.gold()
        )
        
        embed.add_field(name="💰 Amount", value=f"${amount:.2f}", inline=True)
        embed.add_field(name="📅 Season/Week", value=f"SZN {season_year} - Week {week}", inline=True)
        embed.add_field(name="🆔 Wager ID", value=f"#{wager_id}", inline=True)
        embed.add_field(name="🏈 Game", value=f"**{away_name}** @ **{home_name}**", inline=False)
        embed.add_field(name=f"🎯 {interaction.user.display_name}'s Pick", value=f"**{pick_name}**", inline=True)
        embed.add_field(name=f"🎯 {opponent.display_name}'s Pick", value=f"**{opp_pick_name}**", inline=True)
        
        embed.add_field(
            name="⏳ Status", 
            value=f"Waiting for {opponent.mention} to accept!\n`/acceptwager {wager_id}` to accept\n`/declinewager {wager_id}` to decline",
            inline=False
        )
        
        embed.set_footer(text=f"Wager created at {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        
        await interaction.followup.send(embed=embed)
        
        # Try to DM the opponent
        try:
            dm_embed = discord.Embed(
                title="🎰 You've Been Challenged to a Wager!",
                description=f"**{interaction.user.display_name}** wants to bet **${amount:.2f}** on a game!",
                color=discord.Color.gold()
            )
            dm_embed.add_field(name="📅 Season/Week", value=f"SZN {season_year} - Week {week}", inline=True)
            dm_embed.add_field(name="🆔 Wager ID", value=f"#{wager_id}", inline=True)
            dm_embed.add_field(name="🏈 Game", value=f"**{away_name}** @ **{home_name}**", inline=False)
            dm_embed.add_field(name=f"Their Pick", value=f"**{pick_name}**", inline=True)
            dm_embed.add_field(name=f"Your Pick", value=f"**{opp_pick_name}**", inline=True)
            dm_embed.add_field(
                name="📋 Actions",
                value=f"`/acceptwager {wager_id}` to accept\n`/declinewager {wager_id}` to decline",
                inline=False
            )
            await opponent.send(embed=dm_embed)
        except:
            pass  # DMs might be disabled
    
    @app_commands.command(name="acceptwager", description="Accept a pending wager")
    @app_commands.describe(wager_id="The ID of the wager to accept")
    async def acceptwager(self, interaction: discord.Interaction, wager_id: int):
        """Accept a wager that was sent to you."""
        await interaction.response.defer()
        
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
        
        if interaction.user.id != away_user:
            conn.close()
            await interaction.followup.send("❌ This wager wasn't sent to you!", ephemeral=True)
            return
        
        if accepted:
            conn.close()
            await interaction.followup.send("❌ This wager has already been accepted!", ephemeral=True)
            return
        
        if winner:
            conn.close()
            await interaction.followup.send("❌ This wager has already been completed!", ephemeral=True)
            return
        
        cursor.execute('UPDATE wagers SET away_accepted = 1 WHERE wager_id = ?', (wager_id,))
        conn.commit()
        conn.close()
        
        challenger = interaction.guild.get_member(home_user)
        challenger_mention = challenger.mention if challenger else f"<@{home_user}>"
        
        away_name = TEAM_NAMES.get(away_team, away_team)
        home_name = TEAM_NAMES.get(home_team, home_team)
        
        embed = discord.Embed(
            title="✅ Wager Accepted!",
            description=f"{interaction.user.mention} has accepted the wager from {challenger_mention}!",
            color=discord.Color.green()
        )
        embed.add_field(name="🆔 Wager ID", value=f"#{wager_id}", inline=True)
        embed.add_field(name="💰 Amount", value=f"${amount:.2f}", inline=True)
        embed.add_field(name="📅 Season/Week", value=f"SZN {season} - Week {week}", inline=True)
        embed.add_field(name="🏈 Game", value=f"**{away_name}** @ **{home_name}**", inline=False)
        
        if challenger_pick and opponent_pick:
            challenger_name = challenger.display_name if challenger else "Challenger"
            embed.add_field(name=f"🎯 {challenger_name}'s Pick", value=f"**{TEAM_NAMES.get(challenger_pick, challenger_pick)}**", inline=True)
            embed.add_field(name=f"🎯 {interaction.user.display_name}'s Pick", value=f"**{TEAM_NAMES.get(opponent_pick, opponent_pick)}**", inline=True)
        
        embed.add_field(
            name="📋 Next Steps",
            value="After the game, the winner uses `/wagerwin` to claim victory!",
            inline=False
        )
        
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="declinewager", description="Decline a pending wager")
    @app_commands.describe(wager_id="The ID of the wager to decline")
    async def declinewager(self, interaction: discord.Interaction, wager_id: int):
        """Decline a wager that was sent to you."""
        await interaction.response.defer()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT wager_id, home_user_id, away_user_id, amount, away_accepted
            FROM wagers WHERE wager_id = ?
        ''', (wager_id,))
        
        wager = cursor.fetchone()
        
        if not wager:
            conn.close()
            await interaction.followup.send(f"❌ Wager #{wager_id} not found!", ephemeral=True)
            return
        
        wager_id, home_user, away_user, amount, accepted = wager
        
        if interaction.user.id != away_user:
            conn.close()
            await interaction.followup.send("❌ This wager wasn't sent to you!", ephemeral=True)
            return
        
        if accepted:
            conn.close()
            await interaction.followup.send("❌ This wager has already been accepted! You can't decline it now.", ephemeral=True)
            return
        
        cursor.execute('DELETE FROM wagers WHERE wager_id = ?', (wager_id,))
        conn.commit()
        conn.close()
        
        challenger = interaction.guild.get_member(home_user)
        challenger_mention = challenger.mention if challenger else f"<@{home_user}>"
        
        embed = discord.Embed(
            title="❌ Wager Declined",
            description=f"{interaction.user.mention} has declined the ${amount:.2f} wager from {challenger_mention}.",
            color=discord.Color.red()
        )
        
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="cancelwager", description="Cancel a wager you created (before it's accepted)")
    @app_commands.describe(wager_id="The ID of the wager to cancel")
    async def cancelwager(self, interaction: discord.Interaction, wager_id: int):
        """Cancel a wager that hasn't been accepted yet."""
        await interaction.response.defer()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT wager_id, home_user_id, away_user_id, amount, away_accepted
            FROM wagers WHERE wager_id = ?
        ''', (wager_id,))
        
        wager = cursor.fetchone()
        
        if not wager:
            conn.close()
            await interaction.followup.send(f"❌ Wager #{wager_id} not found!", ephemeral=True)
            return
        
        wager_id, home_user, away_user, amount, accepted = wager
        
        if interaction.user.id != home_user:
            conn.close()
            await interaction.followup.send("❌ You didn't create this wager!", ephemeral=True)
            return
        
        if accepted:
            conn.close()
            await interaction.followup.send("❌ This wager has already been accepted! You can't cancel it now.", ephemeral=True)
            return
        
        cursor.execute('DELETE FROM wagers WHERE wager_id = ?', (wager_id,))
        conn.commit()
        conn.close()
        
        embed = discord.Embed(
            title="🚫 Wager Cancelled",
            description=f"Wager #{wager_id} for ${amount:.2f} has been cancelled.",
            color=discord.Color.orange()
        )
        
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="mywagers", description="View all your wagers")
    async def mywagers(self, interaction: discord.Interaction):
        """View all wagers for the user."""
        await interaction.response.defer()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT wager_id, season_year, week, home_team_id, away_team_id, 
                   home_user_id, away_user_id, amount, away_accepted, winner_user_id, is_paid,
                   challenger_pick, opponent_pick
            FROM wagers 
            WHERE home_user_id = ? OR away_user_id = ?
            ORDER BY season_year DESC, week DESC
        ''', (interaction.user.id, interaction.user.id))
        
        wagers = cursor.fetchall()
        conn.close()
        
        if not wagers:
            await interaction.followup.send("📭 You don't have any wagers yet! Use `/wager` to create one.")
            return
        
        embed = discord.Embed(
            title=f"🎰 {interaction.user.display_name}'s Wagers",
            color=discord.Color.gold()
        )
        
        pending = []
        active = []
        completed = []
        
        for w in wagers:
            wager_id, season, week, home_team, away_team, home_user, away_user, amount, accepted, winner, paid, challenger_pick, opponent_pick = w
            
            is_challenger = interaction.user.id == home_user
            other_user_id = away_user if is_challenger else home_user
            other_user = interaction.guild.get_member(other_user_id)
            other_name = other_user.display_name if other_user else f"<@{other_user_id}>"
            
            away_name = TEAM_NAMES.get(away_team, away_team)
            home_name = TEAM_NAMES.get(home_team, home_team)
            
            my_pick = challenger_pick if is_challenger else opponent_pick
            my_pick_name = TEAM_NAMES.get(my_pick, my_pick) if my_pick else "?"
            
            line = f"**#{wager_id}** | ${amount:.2f} | SZN {season} Wk {week}\n"
            line += f"  {away_name} @ {home_name} | My Pick: **{my_pick_name}** | vs {other_name}"
            
            if winner:
                won = winner == interaction.user.id
                status = "✅ WON" if won else "❌ LOST"
                if paid:
                    status += " (Paid)"
                completed.append(f"{line}\n  {status}")
            elif accepted:
                active.append(f"{line}\n  ⚔️ Active")
            else:
                if is_challenger:
                    pending.append(f"{line}\n  ⏳ Waiting for {other_name}")
                else:
                    pending.append(f"{line}\n  📩 Pending your response")
        
        if pending:
            embed.add_field(name="⏳ Pending", value="\n\n".join(pending[:5]) or "None", inline=False)
        if active:
            embed.add_field(name="⚔️ Active", value="\n\n".join(active[:5]) or "None", inline=False)
        if completed:
            embed.add_field(name="✅ Completed", value="\n\n".join(completed[:5]) or "None", inline=False)
        
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="wagerwin", description="Claim victory on a wager after the game")
    @app_commands.describe(
        wager_id="The ID of the wager",
        winning_team="The team that won the game"
    )
    @app_commands.autocomplete(winning_team=team_autocomplete)
    async def wagerwin(self, interaction: discord.Interaction, wager_id: int, winning_team: str):
        """Claim victory on a completed wager by specifying the game winner."""
        await interaction.response.defer()
        
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
        
        # Check if user is part of this wager
        if interaction.user.id not in [home_user, away_user]:
            conn.close()
            await interaction.followup.send("❌ You're not part of this wager!", ephemeral=True)
            return
        
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
        
        winning_team_name = TEAM_NAMES.get(winning_team_norm, winning_team_norm)
        away_name = TEAM_NAMES.get(away_team, away_team)
        home_name = TEAM_NAMES.get(home_team, home_team)
        
        embed = discord.Embed(
            title="🏆 Wager Settled!",
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
        
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="markwagerpaid", description="Mark a wager as paid (winner confirms)")
    @app_commands.describe(wager_id="The ID of the wager to mark as paid")
    async def markwagerpaid(self, interaction: discord.Interaction, wager_id: int):
        """Mark a wager as paid after receiving payment."""
        await interaction.response.defer()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT wager_id, home_user_id, away_user_id, amount, winner_user_id, is_paid,
                   home_team_id, away_team_id, season_year, week
            FROM wagers WHERE wager_id = ?
        ''', (wager_id,))
        
        wager = cursor.fetchone()
        
        if not wager:
            conn.close()
            await interaction.followup.send(f"❌ Wager #{wager_id} not found!", ephemeral=True)
            return
        
        wager_id, home_user, away_user, amount, winner, paid, home_team, away_team, season, week = wager
        
        if not winner:
            conn.close()
            await interaction.followup.send("❌ This wager hasn't been settled yet! Use `/wagerwin` first.", ephemeral=True)
            return
        
        # Only winner can mark as paid
        if interaction.user.id != winner:
            conn.close()
            await interaction.followup.send("❌ Only the winner can confirm payment!", ephemeral=True)
            return
        
        if paid:
            conn.close()
            await interaction.followup.send("❌ This wager has already been marked as paid!", ephemeral=True)
            return
        
        cursor.execute('UPDATE wagers SET is_paid = 1 WHERE wager_id = ?', (wager_id,))
        conn.commit()
        conn.close()
        
        loser = away_user if winner == home_user else home_user
        loser_member = interaction.guild.get_member(loser)
        loser_mention = loser_member.mention if loser_member else f"<@{loser}>"
        
        away_name = TEAM_NAMES.get(away_team, away_team)
        home_name = TEAM_NAMES.get(home_team, home_team)
        
        embed = discord.Embed(
            title="💰 Wager Paid!",
            description=f"Wager #{wager_id} has been marked as paid!",
            color=discord.Color.green()
        )
        embed.add_field(name="💵 Amount", value=f"${amount:.2f}", inline=True)
        embed.add_field(name="🏈 Game", value=f"{away_name} @ {home_name} (SZN {season} Wk {week})", inline=True)
        embed.add_field(name="👤 Paid by", value=loser_mention, inline=True)
        
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="wagerboard", description="View the wager leaderboard")
    async def wagerboard(self, interaction: discord.Interaction):
        """View the wager leaderboard showing top winners and losers."""
        await interaction.response.defer()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get all completed wagers
        cursor.execute('''
            SELECT home_user_id, away_user_id, amount, winner_user_id, challenger_pick, opponent_pick
            FROM wagers WHERE winner_user_id IS NOT NULL
        ''')
        
        wagers = cursor.fetchall()
        
        # Get season payouts from payments table (earnings received)
        cursor.execute('''
            SELECT payee_discord_id, SUM(amount) as total_earned
            FROM payments WHERE is_paid = 1
            GROUP BY payee_discord_id
        ''')
        season_earnings = {row[0]: row[1] for row in cursor.fetchall()}
        
        # Get season dues paid (losses from payments)
        cursor.execute('''
            SELECT payer_discord_id, SUM(amount) as total_paid
            FROM payments WHERE is_paid = 1
            GROUP BY payer_discord_id
        ''')
        season_dues = {row[0]: row[1] for row in cursor.fetchall()}
        
        conn.close()
        
        # Calculate stats for each user (combining wagers + season payouts)
        user_stats = {}
        
        # Process wagers
        for home_user, away_user, amount, winner, challenger_pick, opponent_pick in wagers:
            for user_id in [home_user, away_user]:
                if user_id not in user_stats:
                    user_stats[user_id] = {
                        'wager_wins': 0, 'wager_losses': 0, 
                        'wager_won': 0.0, 'wager_lost': 0.0,
                        'season_earned': 0.0, 'season_paid': 0.0
                    }
            
            loser = away_user if winner == home_user else home_user
            user_stats[winner]['wager_wins'] += 1
            user_stats[winner]['wager_won'] += amount
            user_stats[loser]['wager_losses'] += 1
            user_stats[loser]['wager_lost'] += amount
        
        # Add season earnings/dues to user stats
        all_users = set(list(season_earnings.keys()) + list(season_dues.keys()) + list(user_stats.keys()))
        for user_id in all_users:
            if user_id not in user_stats:
                user_stats[user_id] = {
                    'wager_wins': 0, 'wager_losses': 0,
                    'wager_won': 0.0, 'wager_lost': 0.0,
                    'season_earned': 0.0, 'season_paid': 0.0
                }
            user_stats[user_id]['season_earned'] = season_earnings.get(user_id, 0.0)
            user_stats[user_id]['season_paid'] = season_dues.get(user_id, 0.0)
        
        if not user_stats:
            await interaction.followup.send("📭 No earnings data yet!")
            return
        
        # Calculate total net for each user
        def calc_net(stats):
            wager_net = stats['wager_won'] - stats['wager_lost']
            season_net = stats['season_earned'] - stats['season_paid']
            return wager_net + season_net
        
        # Sort by total net earnings
        sorted_users = sorted(
            user_stats.items(),
            key=lambda x: calc_net(x[1]),
            reverse=True
        )
        
        embed = discord.Embed(
            title="💰 Overall Earnings Leaderboard",
            description="Combined wager + season payout earnings",
            color=discord.Color.gold()
        )
        
        # Top earners
        top_earners = []
        for i, (user_id, stats) in enumerate(sorted_users[:5], 1):
            member = interaction.guild.get_member(user_id)
            name = member.display_name if member else f"<@{user_id}>"
            total_net = calc_net(stats)
            wager_net = stats['wager_won'] - stats['wager_lost']
            season_net = stats['season_earned'] - stats['season_paid']
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            top_earners.append(f"{medal} **{name}**: **${total_net:+.2f}**\n    Wagers: ${wager_net:+.2f} | Season: ${season_net:+.2f}")
        
        embed.add_field(name="🏆 Top Earners", value="\n".join(top_earners) or "No data", inline=False)
        
        # Biggest losers (bottom of the list)
        bottom_users = [u for u in sorted_users if calc_net(u[1]) < 0]
        bottom_users = sorted(bottom_users, key=lambda x: calc_net(x[1]))[:5]
        biggest_losers = []
        for i, (user_id, stats) in enumerate(bottom_users, 1):
            member = interaction.guild.get_member(user_id)
            name = member.display_name if member else f"<@{user_id}>"
            total_net = calc_net(stats)
            wager_net = stats['wager_won'] - stats['wager_lost']
            season_net = stats['season_earned'] - stats['season_paid']
            biggest_losers.append(f"{i}. **{name}**: **${total_net:+.2f}**\n    Wagers: ${wager_net:+.2f} | Season: ${season_net:+.2f}")
        
        if biggest_losers:
            embed.add_field(name="📉 Biggest Losers", value="\n".join(biggest_losers), inline=False)
        
        # Total stats
        total_wagers = len(wagers)
        total_wager_money = sum(w[2] for w in wagers)
        total_season_money = sum(season_earnings.values())
        embed.add_field(
            name="📊 Overall Stats",
            value=f"Total Wagers: **{total_wagers}** (${total_wager_money:.2f})\nSeason Payouts: **${total_season_money:.2f}**",
            inline=False
        )
        
        embed.set_footer(text="Use /wager to challenge someone! | Use /topearners for detailed stats")
        
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="unpaidwagers", description="View your unpaid wagers (won but not marked paid)")
    async def unpaidwagers(self, interaction: discord.Interaction):
        """View wagers you've won that haven't been marked as paid yet."""
        await interaction.response.defer()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get wagers where user won but not paid
        cursor.execute('''
            SELECT wager_id, season_year, week, home_team_id, away_team_id, 
                   home_user_id, away_user_id, amount, winner_user_id
            FROM wagers 
            WHERE winner_user_id = ? AND (is_paid = 0 OR is_paid IS NULL)
            ORDER BY season_year DESC, week DESC
        ''', (interaction.user.id,))
        
        won_unpaid = cursor.fetchall()
        
        # Get wagers where user lost but not paid
        cursor.execute('''
            SELECT wager_id, season_year, week, home_team_id, away_team_id, 
                   home_user_id, away_user_id, amount, winner_user_id
            FROM wagers 
            WHERE (home_user_id = ? OR away_user_id = ?)
            AND winner_user_id IS NOT NULL
            AND winner_user_id != ?
            AND (is_paid = 0 OR is_paid IS NULL)
            ORDER BY season_year DESC, week DESC
        ''', (interaction.user.id, interaction.user.id, interaction.user.id))
        
        lost_unpaid = cursor.fetchall()
        conn.close()
        
        if not won_unpaid and not lost_unpaid:
            await interaction.followup.send("✅ You have no unpaid wagers! All settled up.")
            return
        
        embed = discord.Embed(
            title=f"💵 {interaction.user.display_name}'s Unpaid Wagers",
            description="Use `/markwagerpaid <wager_id>` to mark a wager as paid after receiving payment.",
            color=discord.Color.gold()
        )
        
        # Wagers you won (waiting for payment)
        if won_unpaid:
            lines = []
            for w in won_unpaid[:10]:
                wager_id, season, week, home_team, away_team, home_user, away_user, amount, winner = w
                loser_id = away_user if winner == home_user else home_user
                loser = interaction.guild.get_member(loser_id)
                loser_name = loser.display_name if loser else f"<@{loser_id}>"
                away_name = TEAM_NAMES.get(away_team, away_team)
                home_name = TEAM_NAMES.get(home_team, home_team)
                lines.append(f"**ID: {wager_id}** | ${amount:.2f} | {away_name}@{home_name} Wk{week}\n  Owed by: {loser_name}")
            
            embed.add_field(
                name=f"✅ You Won - Awaiting Payment ({len(won_unpaid)})",
                value="\n\n".join(lines) if lines else "None",
                inline=False
            )
        
        # Wagers you lost (you owe)
        if lost_unpaid:
            lines = []
            for w in lost_unpaid[:10]:
                wager_id, season, week, home_team, away_team, home_user, away_user, amount, winner = w
                winner_member = interaction.guild.get_member(winner)
                winner_name = winner_member.display_name if winner_member else f"<@{winner}>"
                away_name = TEAM_NAMES.get(away_team, away_team)
                home_name = TEAM_NAMES.get(home_team, home_team)
                lines.append(f"**ID: {wager_id}** | ${amount:.2f} | {away_name}@{home_name} Wk{week}\n  You owe: {winner_name}")
            
            embed.add_field(
                name=f"❌ You Lost - You Owe ({len(lost_unpaid)})",
                value="\n\n".join(lines) if lines else "None",
                inline=False
            )
        
        embed.set_footer(text="Winner uses /markwagerpaid <ID> after receiving payment")
        
        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(WagersCog(bot))
