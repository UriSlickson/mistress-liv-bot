"""
Profitability Cog - Comprehensive payment generation, tracking, and franchise profitability
CONSOLIDATED COMMANDS:
/playoff seeding - Set NFC/AFC seeding for a season
/playoff winner - Record a playoff round winner
/playoff generate - Generate all payment obligations
/playoff pairings - View AFC/NFC seed pairings
/playoff clear - Clear payment/playoff/season data
/playoff post - Post payment summaries to channels
/profit view - View league-wide profitability
/profit mine - View personal profitability
/profit structure - View payout structure
"""

import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
from datetime import datetime
from typing import Optional, List, Dict
import logging

logger = logging.getLogger('MistressLIV.Profitability')

# Payment structure constants
PLAYOFF_PAYOUTS = {
    'wildcard': 50,
    'divisional': 100,
    'conference': 200,
    'superbowl': 300,
}

AFC_RETENTION_RATE = 0.20
NFC_PAIRED_RATE = 0.80

NFC_PAYER_STRUCTURE = {
    15: {'round': 'wildcard', 'amount': 100},
    16: {'round': 'wildcard', 'amount': 100},
    13: {'round': 'divisional', 'amount': 100},
    14: {'round': 'divisional', 'amount': 100},
    11: {'round': 'conference', 'amount': 100},
    12: {'round': 'conference', 'amount': 100},
    8: {'round': 'superbowl', 'amount': 100},
    9: {'round': 'superbowl', 'amount': 100},
    10: {'round': 'superbowl', 'amount': 100},
}

AFC_TEAMS = ['BAL', 'BUF', 'CIN', 'CLE', 'DEN', 'HOU', 'IND', 'JAX', 
             'KC', 'LAC', 'LV', 'MIA', 'NE', 'NYJ', 'PIT', 'TEN']
NFC_TEAMS = ['ARI', 'ATL', 'CAR', 'CHI', 'DAL', 'DET', 'GB', 'LAR',
             'MIN', 'NO', 'NYG', 'PHI', 'SEA', 'SF', 'TB', 'WAS']

CPU_PAYOUT_REDUCTION = {
    1: {'wildcard': 0.50},
    2: {'wildcard': 0.00},
    3: {'wildcard': 0.00, 'divisional': 0.50},
    4: {'wildcard': 0.00, 'divisional': 0.00},
    5: {'wildcard': 0.00, 'divisional': 0.00, 'conference': 0.50},
    6: {'wildcard': 0.00, 'divisional': 0.00, 'conference': 0.00},
    7: {'wildcard': 0.00, 'divisional': 0.00, 'conference': 0.00, 'superbowl': 0.67},
    8: {'wildcard': 0.00, 'divisional': 0.00, 'conference': 0.00, 'superbowl': 0.33},
    9: {'wildcard': 0.00, 'divisional': 0.00, 'conference': 0.00, 'superbowl': 0.00},
}

DIVISION_CHANNELS = {
    'AFC East': 'afc-east', 'AFC North': 'afc-north', 
    'AFC South': 'afc-south', 'AFC West': 'afc-west',
    'NFC East': 'nfc-east', 'NFC North': 'nfc-north',
    'NFC South': 'nfc-south', 'NFC West': 'nfc-west',
}


class ProfitabilityCog(commands.Cog):
    """Cog for payment generation and franchise profitability tracking."""
    
    def __init__(self, bot):
        self.bot = bot
        self.db_path = bot.db_path
        self._ensure_tables()
        
    def get_db_connection(self):
        return sqlite3.connect(self.db_path)
    
    def _ensure_tables(self):
        """Ensure all required tables exist."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS playoff_results (
                result_id INTEGER PRIMARY KEY AUTOINCREMENT,
                season INTEGER NOT NULL,
                round TEXT NOT NULL,
                winner_discord_id INTEGER NOT NULL,
                winner_team_id TEXT,
                conference TEXT,
                loser_discord_id INTEGER,
                loser_team_id TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS season_standings (
                standing_id INTEGER PRIMARY KEY AUTOINCREMENT,
                season INTEGER NOT NULL,
                conference TEXT NOT NULL,
                seed INTEGER NOT NULL,
                team_id TEXT NOT NULL,
                user_discord_id INTEGER,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                UNIQUE(season, conference, seed)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS franchise_profitability (
                user_discord_id INTEGER NOT NULL,
                season INTEGER NOT NULL,
                playoff_earnings REAL DEFAULT 0,
                dues_paid REAL DEFAULT 0,
                wager_profit REAL DEFAULT 0,
                net_profit REAL DEFAULT 0,
                PRIMARY KEY (user_discord_id, season)
            )
        ''')
        
        try:
            cursor.execute('ALTER TABLE playoff_results ADD COLUMN conference TEXT')
        except sqlite3.OperationalError:
            pass
        
        conn.commit()
        conn.close()
    
    def _get_team_conference(self, team_id: str) -> str:
        if team_id and team_id.upper() in AFC_TEAMS:
            return 'AFC'
        elif team_id and team_id.upper() in NFC_TEAMS:
            return 'NFC'
        return None
    
    def _count_cpu_nfc_payers(self, cursor, season: int) -> int:
        cpu_count = 0
        cursor.execute('''
            SELECT ss.seed, ss.user_discord_id, ss.team_id, t.is_cpu
            FROM season_standings ss
            LEFT JOIN teams t ON ss.team_id = t.team_id
            WHERE ss.season = ? AND ss.conference = 'NFC' AND ss.seed >= 8 AND ss.seed <= 16
            ORDER BY ss.seed DESC
        ''', (season,))
        nfc_payers = cursor.fetchall()
        
        for seed, user_id, team_id, is_cpu in nfc_payers:
            if is_cpu == 1 or user_id is None:
                cpu_count += 1
        return cpu_count
    
    def _get_payout_multiplier(self, cpu_count: int, round_name: str) -> float:
        if cpu_count == 0:
            return 1.0
        if cpu_count > 9:
            cpu_count = 9
        reduction_rules = CPU_PAYOUT_REDUCTION.get(cpu_count, {})
        return reduction_rules.get(round_name, 1.0)
    
    def _calculate_afc_earnings(self, cursor, season: int) -> Dict[int, Dict]:
        afc_earnings = {}
        cursor.execute('''
            SELECT seed, user_discord_id, team_id 
            FROM season_standings 
            WHERE season = ? AND conference = 'AFC' AND seed <= 7
            ORDER BY seed
        ''', (season,))
        afc_seeds = cursor.fetchall()
        
        cursor.execute('''
            SELECT round, winner_discord_id, winner_team_id
            FROM playoff_results
            WHERE season = ? AND conference = 'AFC'
        ''', (season,))
        afc_results = cursor.fetchall()
        
        for seed, user_id, team_id in afc_seeds:
            afc_earnings[seed] = {
                'user_id': user_id,
                'team_id': team_id,
                'total_earnings': 0.0,
                'rounds_won': []
            }
        
        for round_name, winner_id, team_id in afc_results:
            for seed, data in afc_earnings.items():
                if data['user_id'] == winner_id:
                    payout = PLAYOFF_PAYOUTS.get(round_name, 0)
                    data['total_earnings'] += payout
                    data['rounds_won'].append(round_name)
                    break
        
        return afc_earnings
    
    async def _get_payouts_channel(self, guild):
        return discord.utils.get(guild.text_channels, name='payouts')
    
    async def _post_payments_to_channel(self, channel, season, guild):
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT payer_discord_id, payee_discord_id, amount, reason, is_paid
            FROM payments WHERE season = ? AND is_paid = 0
            ORDER BY amount DESC
        ''', (season,))
        payments = cursor.fetchall()
        conn.close()
        
        if not payments:
            await channel.send(f"✅ No outstanding payments for Season {season}")
            return
        
        embed = discord.Embed(
            title=f"💰 Season {season} Outstanding Payments",
            color=discord.Color.gold()
        )
        
        lines = []
        for payer_id, payee_id, amount, reason, is_paid in payments[:25]:
            payer = guild.get_member(payer_id)
            payee = guild.get_member(payee_id)
            payer_name = payer.display_name if payer else f"User {payer_id}"
            payee_name = payee.display_name if payee else f"User {payee_id}"
            lines.append(f"**{payer_name}** → **{payee_name}**: ${amount:.2f}")
        
        embed.description = "\n".join(lines)
        await channel.send(embed=embed)
    
    async def _auto_generate_payments(self, guild, season: int) -> dict:
        """Auto-generate payments after Super Bowl."""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            payments_created = 0
            
            # Get NFC payers
            cursor.execute('''
                SELECT seed, user_discord_id, team_id 
                FROM season_standings 
                WHERE season = ? AND conference = 'NFC' AND seed >= 8
                ORDER BY seed
            ''', (season,))
            nfc_payers = cursor.fetchall()
            
            # Get playoff winners
            cursor.execute('''
                SELECT round, winner_discord_id, winner_team_id
                FROM playoff_results WHERE season = ? AND conference = 'NFC'
            ''', (season,))
            nfc_results = cursor.fetchall()
            
            nfc_winners_by_round = {'wildcard': [], 'divisional': [], 'conference': [], 'superbowl': []}
            for round_name, winner_id, team_id in nfc_results:
                if round_name in nfc_winners_by_round:
                    nfc_winners_by_round[round_name].append(winner_id)
            
            cpu_count = self._count_cpu_nfc_payers(cursor, season)
            
            # Create payments from NFC payers to winners
            for seed, payer_id, team_id in nfc_payers:
                if payer_id is None:
                    continue
                
                payer_info = NFC_PAYER_STRUCTURE.get(seed)
                if not payer_info:
                    continue
                
                round_name = payer_info['round']
                base_amount = payer_info['amount']
                
                multiplier = self._get_payout_multiplier(cpu_count, round_name)
                if multiplier == 0:
                    continue
                
                winners = nfc_winners_by_round.get(round_name, [])
                if not winners:
                    continue
                
                amount_per_winner = (base_amount * multiplier) / len(winners)
                
                for winner_id in winners:
                    if winner_id == payer_id:
                        continue
                    
                    cursor.execute('''
                        INSERT INTO payments (payer_discord_id, payee_discord_id, amount, reason, season, is_paid)
                        VALUES (?, ?, ?, ?, ?, 0)
                    ''', (payer_id, winner_id, amount_per_winner, f"NFC #{seed} → {round_name.title()} Winner", season))
                    payments_created += 1
            
            conn.commit()
            conn.close()
            return {'success': True, 'payments_created': payments_created}
        except Exception as e:
            logger.error(f"Error generating payments: {e}")
            return {'success': False, 'error': str(e)}

    # ==================== PLAYOFF COMMAND GROUP ====================
    
    playoff_group = app_commands.Group(name="playoff", description="Playoff management commands (Admin)")
    
    @playoff_group.command(name="seeding", description="Set NFC/AFC seeding for a season")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        season="Season number",
        conference="NFC or AFC",
        seed="Seed number (1-16)",
        user="The user who has this seed"
    )
    async def playoff_seeding(
        self,
        interaction: discord.Interaction,
        season: int,
        conference: str,
        seed: int,
        user: discord.Member
    ):
        """Set a team's seeding for a season."""
        conference = conference.upper()
        if conference not in ['NFC', 'AFC']:
            await interaction.response.send_message("Conference must be NFC or AFC", ephemeral=True)
            return
            
        if seed < 1 or seed > 16:
            await interaction.response.send_message("Seed must be between 1 and 16", ephemeral=True)
            return
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        team_id = None
        for role in user.roles:
            if role.name.upper() in AFC_TEAMS + NFC_TEAMS:
                team_id = role.name.upper()
                break
        
        cursor.execute('''
            INSERT OR REPLACE INTO season_standings 
            (season, conference, seed, team_id, user_discord_id)
            VALUES (?, ?, ?, ?, ?)
        ''', (season, conference, seed, team_id, user.id))
        
        conn.commit()
        conn.close()
        
        await interaction.response.send_message(
            f"✅ Set {user.display_name} as {conference} #{seed} seed for Season {season}",
            ephemeral=True
        )
    
    @playoff_group.command(name="winner", description="Record a playoff round winner")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        season="Season number",
        round="Playoff round",
        winner="The user who won this round",
        conference="Conference (AFC or NFC)"
    )
    @app_commands.choices(round=[
        app_commands.Choice(name="Wild Card / Bye", value="wildcard"),
        app_commands.Choice(name="Divisional", value="divisional"),
        app_commands.Choice(name="Conference Championship", value="conference"),
        app_commands.Choice(name="Super Bowl", value="superbowl"),
    ])
    async def playoff_winner(
        self,
        interaction: discord.Interaction,
        season: int,
        round: str,
        winner: discord.Member,
        conference: Optional[str] = None
    ):
        """Record a playoff round winner."""
        await interaction.response.defer(thinking=True)
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        team_id = None
        for role in winner.roles:
            if role.name.upper() in AFC_TEAMS + NFC_TEAMS:
                team_id = role.name.upper()
                break
        
        if not conference and team_id:
            conference = self._get_team_conference(team_id)
        elif conference:
            conference = conference.upper()
        
        cursor.execute('''
            INSERT INTO playoff_results (season, round, winner_discord_id, winner_team_id, conference)
            VALUES (?, ?, ?, ?, ?)
        ''', (season, round, winner.id, team_id, conference))
        
        conn.commit()
        conn.close()
        
        round_names = {
            'wildcard': 'Wild Card/Bye',
            'divisional': 'Divisional Round',
            'conference': 'Conference Championship',
            'superbowl': 'Super Bowl'
        }
        
        conf_str = f" ({conference})" if conference else ""
        
        if round == 'superbowl':
            await interaction.followup.send(
                f"🏆 **{winner.display_name}** wins the Super Bowl for Season {season}!\n\n"
                f"💰 Auto-generating season payouts..."
            )
            
            result = await self._auto_generate_payments(interaction.guild, season)
            
            if result['success']:
                payouts_channel = await self._get_payouts_channel(interaction.guild)
                if payouts_channel:
                    await self._post_payments_to_channel(payouts_channel, season, interaction.guild)
                    await interaction.followup.send(
                        f"✅ Season {season} payouts generated and posted to {payouts_channel.mention}!"
                    )
                else:
                    await interaction.followup.send(
                        f"✅ Season {season} payouts generated! Use `/playoff post` to post them."
                    )
            else:
                await interaction.followup.send(
                    f"⚠️ Recorded Super Bowl winner but payment generation had issues:\n{result['error']}"
                )
        else:
            await interaction.followup.send(
                f"✅ Recorded {winner.display_name}{conf_str} as {round_names[round]} winner for Season {season}"
            )
    
    @playoff_group.command(name="generate", description="Generate all payment obligations for a season")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(season="Season number")
    async def playoff_generate(self, interaction: discord.Interaction, season: int):
        """Generate all payment obligations."""
        await interaction.response.defer(thinking=True)
        
        result = await self._auto_generate_payments(interaction.guild, season)
        
        if result['success']:
            await interaction.followup.send(
                f"✅ Generated {result['payments_created']} payments for Season {season}"
            )
        else:
            await interaction.followup.send(f"❌ Error: {result['error']}")
    
    @playoff_group.command(name="pairings", description="View AFC/NFC seed pairings")
    @app_commands.describe(season="Season to view")
    async def playoff_pairings(self, interaction: discord.Interaction, season: int):
        """View AFC/NFC seed pairings and potential earnings."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT conference, seed, team_id, user_discord_id
            FROM season_standings WHERE season = ? AND seed <= 7
            ORDER BY seed
        ''', (season,))
        standings = cursor.fetchall()
        conn.close()
        
        afc_seeds = {row[1]: row for row in standings if row[0] == 'AFC'}
        nfc_seeds = {row[1]: row for row in standings if row[0] == 'NFC'}
        
        embed = discord.Embed(
            title=f"🔗 Season {season} AFC/NFC Pairings",
            description="NFC owners get 80% of their paired AFC team's playoff earnings",
            color=discord.Color.blue()
        )
        
        for seed in range(1, 8):
            afc = afc_seeds.get(seed)
            nfc = nfc_seeds.get(seed)
            
            afc_name = interaction.guild.get_member(afc[3]).display_name if afc and afc[3] else "TBD"
            nfc_name = interaction.guild.get_member(nfc[3]).display_name if nfc and nfc[3] else "TBD"
            
            embed.add_field(
                name=f"#{seed} Seed",
                value=f"AFC: {afc_name}\nNFC: {nfc_name}",
                inline=True
            )
        
        await interaction.response.send_message(embed=embed)
    
    @playoff_group.command(name="clear", description="Clear payment/playoff/season data")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        season="Season to clear",
        data_type="What to clear",
        confirm="Type CONFIRM to proceed"
    )
    @app_commands.choices(data_type=[
        app_commands.Choice(name="Payments Only", value="payments"),
        app_commands.Choice(name="Playoff Results", value="playoffs"),
        app_commands.Choice(name="All Season Data", value="all"),
    ])
    async def playoff_clear(
        self,
        interaction: discord.Interaction,
        season: int,
        data_type: str,
        confirm: str
    ):
        """Clear season data."""
        if confirm != "CONFIRM":
            await interaction.response.send_message("❌ Type CONFIRM to proceed", ephemeral=True)
            return
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        cleared = []
        if data_type in ['payments', 'all']:
            cursor.execute('DELETE FROM payments WHERE season = ?', (season,))
            cleared.append("payments")
        if data_type in ['playoffs', 'all']:
            cursor.execute('DELETE FROM playoff_results WHERE season = ?', (season,))
            cleared.append("playoff results")
        if data_type == 'all':
            cursor.execute('DELETE FROM season_standings WHERE season = ?', (season,))
            cursor.execute('DELETE FROM franchise_profitability WHERE season = ?', (season,))
            cleared.append("standings")
            cleared.append("profitability")
        
        conn.commit()
        conn.close()
        
        await interaction.response.send_message(
            f"✅ Cleared {', '.join(cleared)} for Season {season}"
        )
    
    @playoff_group.command(name="post", description="Post payment summaries to channels")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(season="Season to post")
    async def playoff_post(self, interaction: discord.Interaction, season: int):
        """Post payment summaries."""
        await interaction.response.defer()
        
        payouts_channel = await self._get_payouts_channel(interaction.guild)
        if payouts_channel:
            await self._post_payments_to_channel(payouts_channel, season, interaction.guild)
            await interaction.followup.send(f"✅ Posted to {payouts_channel.mention}")
        else:
            await interaction.followup.send("❌ No #payouts channel found", ephemeral=True)

    # ==================== PROFIT COMMAND GROUP ====================
    
    profit_group = app_commands.Group(name="profit", description="Profitability viewing commands")
    
    @profit_group.command(name="view", description="View league-wide profitability rankings")
    @app_commands.describe(season="Season to view (optional)")
    async def profit_view(self, interaction: discord.Interaction, season: Optional[int] = None):
        """Show profitability leaderboard."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        if season:
            cursor.execute('''
                SELECT user_discord_id, playoff_earnings, dues_paid, wager_profit, net_profit
                FROM franchise_profitability WHERE season = ?
                ORDER BY net_profit DESC
            ''', (season,))
            title = f"💰 Season {season} Profitability"
        else:
            cursor.execute('''
                SELECT user_discord_id, 
                       SUM(playoff_earnings), SUM(dues_paid), SUM(wager_profit), SUM(net_profit)
                FROM franchise_profitability
                GROUP BY user_discord_id ORDER BY SUM(net_profit) DESC
            ''')
            title = "💰 All-Time Profitability"
        
        results = cursor.fetchall()
        conn.close()
        
        embed = discord.Embed(title=title, color=discord.Color.gold())
        
        if not results:
            embed.description = "*No profitability data recorded yet.*"
        else:
            lines = []
            for i, (user_id, earnings, dues, wagers, net) in enumerate(results[:10], 1):
                member = interaction.guild.get_member(user_id)
                name = member.display_name if member else f"User {user_id}"
                medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"{i}.")
                profit_str = f"+${net:.2f}" if net >= 0 else f"-${abs(net):.2f}"
                lines.append(f"{medal} **{name}**: {profit_str}")
            
            embed.description = "\n".join(lines)
        
        await interaction.response.send_message(embed=embed)
    
    @profit_group.command(name="mine", description="View your personal profitability")
    async def profit_mine(self, interaction: discord.Interaction):
        """Show personal profitability."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT season, playoff_earnings, dues_paid, wager_profit, net_profit
            FROM franchise_profitability WHERE user_discord_id = ?
            ORDER BY season DESC
        ''', (interaction.user.id,))
        results = cursor.fetchall()
        
        cursor.execute('''
            SELECT SUM(playoff_earnings), SUM(dues_paid), SUM(wager_profit), SUM(net_profit)
            FROM franchise_profitability WHERE user_discord_id = ?
        ''', (interaction.user.id,))
        totals = cursor.fetchone()
        conn.close()
        
        embed = discord.Embed(
            title=f"💰 {interaction.user.display_name}'s Profitability",
            color=discord.Color.gold()
        )
        
        if not results or totals[0] is None:
            embed.description = "*No profitability data recorded yet.*"
        else:
            total_earnings, total_dues, total_wagers, total_profit = totals
            profit_color = "🟢" if total_profit >= 0 else "🔴"
            embed.add_field(
                name="📊 All-Time Summary",
                value=(
                    f"**Playoff Earnings:** ${total_earnings:.2f}\n"
                    f"**Dues Paid:** ${total_dues:.2f}\n"
                    f"**Wager Profit:** ${total_wagers:.2f}\n"
                    f"{profit_color} **Net Profit:** ${total_profit:.2f}"
                ),
                inline=False
            )
        
        await interaction.response.send_message(embed=embed)
    
    @profit_group.command(name="structure", description="View the complete payout structure")
    async def profit_structure(self, interaction: discord.Interaction):
        """Display payout structure."""
        embed = discord.Embed(
            title="💰 Season Payout Structure",
            color=discord.Color.gold()
        )
        
        embed.add_field(
            name="🏆 Playoff Round Payouts",
            value=(
                f"**Wild Card/Bye Win:** ${PLAYOFF_PAYOUTS['wildcard']}\n"
                f"**Divisional Win:** ${PLAYOFF_PAYOUTS['divisional']}\n"
                f"**Conference Championship:** ${PLAYOFF_PAYOUTS['conference']}\n"
                f"**Super Bowl Win:** ${PLAYOFF_PAYOUTS['superbowl']}\n"
                f"*Total Possible:* ${sum(PLAYOFF_PAYOUTS.values())}"
            ),
            inline=False
        )
        
        nfc_pot_lines = []
        for seed in sorted(NFC_PAYER_STRUCTURE.keys()):
            info = NFC_PAYER_STRUCTURE[seed]
            nfc_pot_lines.append(f"NFC #{seed}: ${info['amount']} → {info['round'].title()} Winners")
        
        embed.add_field(
            name="📤 NFC Seeds 8-16 Pay Into Pot",
            value="\n".join(nfc_pot_lines),
            inline=False
        )
        
        embed.add_field(
            name="🔗 AFC/NFC Seed Pairing (Seeds 1-7)",
            value=(
                f"**AFC Team Earnings Split:**\n"
                f"• AFC owner keeps: **{int(AFC_RETENTION_RATE*100)}%**\n"
                f"• NFC paired owner gets: **{int(NFC_PAIRED_RATE*100)}%**"
            ),
            inline=False
        )
        
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(ProfitabilityCog(bot))
