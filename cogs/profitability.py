"""
Profitability Cog - Comprehensive payment generation, tracking, and franchise profitability
Features:
- Generate season payments based on NFC seeds and playoff results
- AFC/NFC seed pairing: AFC teams retain 20%, NFC teams get 80% of paired AFC earnings
- Clear/reset season payments
- Track franchise profitability (playoff earnings, wagers, dues)
- Post payment summaries to GM division channels
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
    'wildcard': 50,      # WC/Bye Win = $50 (4 payouts)
    'divisional': 100,   # Divisional Win = $100 (2 payouts)
    'conference': 200,   # Conference Win = $200 (1 payout)
    'superbowl': 300,    # Super Bowl Win = $300 (1 payout)
}

# AFC/NFC Seed Pairing Split
AFC_RETENTION_RATE = 0.20  # AFC teams keep 20% of their earnings
NFC_PAIRED_RATE = 0.80     # NFC teams get 80% of their paired AFC team's earnings

# NFC Seeds 8-16 pay into the pot
# Payment structure: who pays to whom
NFC_PAYER_STRUCTURE = {
    # Seeds 15-16 pay $50 each to WC/Bye winners (split among 4 winners)
    15: {'round': 'wildcard', 'amount': 100},
    16: {'round': 'wildcard', 'amount': 100},
    # Seeds 13-14 pay $100 each to Divisional winners (split among 2 winners)
    13: {'round': 'divisional', 'amount': 100},
    14: {'round': 'divisional', 'amount': 100},
    # Seeds 11-12 pay $100 each to Conference winner
    11: {'round': 'conference', 'amount': 100},
    12: {'round': 'conference', 'amount': 100},
    # Seeds 8-10 pay $100 each to Super Bowl winner
    8: {'round': 'superbowl', 'amount': 100},
    9: {'round': 'superbowl', 'amount': 100},
    10: {'round': 'superbowl', 'amount': 100},
}

# Team to Conference mapping
AFC_TEAMS = ['BAL', 'BUF', 'CIN', 'CLE', 'DEN', 'HOU', 'IND', 'JAX', 
             'KC', 'LAC', 'LV', 'MIA', 'NE', 'NYJ', 'PIT', 'TEN']
NFC_TEAMS = ['ARI', 'ATL', 'CAR', 'CHI', 'DAL', 'DET', 'GB', 'LAR',
             'MIN', 'NO', 'NYG', 'PHI', 'SEA', 'SF', 'TB', 'WAS']

# Division channel mapping
DIVISION_CHANNELS = {
    'AFC East': 'afc-east',
    'AFC North': 'afc-north', 
    'AFC South': 'afc-south',
    'AFC West': 'afc-west',
    'NFC East': 'nfc-east',
    'NFC North': 'nfc-north',
    'NFC South': 'nfc-south',
    'NFC West': 'nfc-west',
}


class ProfitabilityCog(commands.Cog):
    """Cog for payment generation and franchise profitability tracking."""
    
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
        
        # Playoff results table for tracking winners
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
        
        # Season standings for NFC/AFC seeds
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
        
        # Franchise profitability summary
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
        
        # Add conference column to playoff_results if it doesn't exist
        try:
            cursor.execute('ALTER TABLE playoff_results ADD COLUMN conference TEXT')
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        conn.commit()
        conn.close()
    
    def _get_team_conference(self, team_id: str) -> str:
        """Get the conference for a team."""
        if team_id and team_id.upper() in AFC_TEAMS:
            return 'AFC'
        elif team_id and team_id.upper() in NFC_TEAMS:
            return 'NFC'
        return None
    
    @app_commands.command(name="setseeding", description="[Admin] Set NFC/AFC seeding for a season")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        season="Season number",
        conference="NFC or AFC",
        seed="Seed number (1-16 for NFC, 1-7 for AFC playoffs)",
        user="The user who has this seed"
    )
    async def set_seeding(
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
        
        # Get user's team
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
    
    @app_commands.command(name="setplayoffwinner", description="[Admin] Record a playoff round winner")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        season="Season number",
        round="Playoff round (wildcard, divisional, conference, superbowl)",
        winner="The user who won this round",
        conference="Conference (AFC or NFC) - required for proper pairing"
    )
    @app_commands.choices(round=[
        app_commands.Choice(name="Wild Card / Bye", value="wildcard"),
        app_commands.Choice(name="Divisional", value="divisional"),
        app_commands.Choice(name="Conference Championship", value="conference"),
        app_commands.Choice(name="Super Bowl", value="superbowl"),
    ])
    async def set_playoff_winner(
        self,
        interaction: discord.Interaction,
        season: int,
        round: str,
        winner: discord.Member,
        conference: Optional[str] = None
    ):
        """Record a playoff round winner. Auto-generates payments after Super Bowl."""
        await interaction.response.defer(thinking=True)
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Get winner's team
        team_id = None
        for role in winner.roles:
            if role.name.upper() in AFC_TEAMS + NFC_TEAMS:
                team_id = role.name.upper()
                break
        
        # Auto-detect conference from team if not provided
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
        
        # If this is the Super Bowl winner, auto-generate payments
        if round == 'superbowl':
            await interaction.followup.send(
                f"🏆 **{winner.display_name}** wins the Super Bowl for Season {season}!\n\n"
                f"💰 Auto-generating season payouts...",
                ephemeral=False
            )
            
            # Auto-generate payments
            result = await self._auto_generate_payments(interaction.guild, season)
            
            if result['success']:
                # Find and post to #payouts channel
                payouts_channel = await self._get_payouts_channel(interaction.guild)
                if payouts_channel:
                    await self._post_payments_to_channel(payouts_channel, season, interaction.guild)
                    await interaction.followup.send(
                        f"✅ Season {season} payouts generated and posted to {payouts_channel.mention}!\n"
                        f"• {result['payments_created']} new payments created\n"
                        f"• Prior unpaid payments preserved",
                        ephemeral=False
                    )
                else:
                    await interaction.followup.send(
                        f"✅ Season {season} payouts generated!\n"
                        f"• {result['payments_created']} new payments created\n"
                        f"⚠️ No #payouts channel found - use `/createpayouts` to create one\n"
                        f"• Use `/postpayments {season}` to post manually",
                        ephemeral=False
                    )
            else:
                await interaction.followup.send(
                    f"⚠️ Recorded Super Bowl winner but payment generation had issues:\n{result['error']}",
                    ephemeral=False
                )
        else:
            await interaction.followup.send(
                f"✅ Recorded {winner.display_name}{conf_str} as {round_names[round]} winner for Season {season}",
                ephemeral=False
            )
    
    def _calculate_afc_earnings(self, cursor, season: int) -> Dict[int, Dict]:
        """
        Calculate AFC playoff earnings for each AFC seed.
        Returns dict: {seed: {'user_id': id, 'total_earnings': amount, 'rounds_won': [list]}}
        """
        afc_earnings = {}
        
        # Get AFC standings
        cursor.execute('''
            SELECT seed, user_discord_id, team_id 
            FROM season_standings 
            WHERE season = ? AND conference = 'AFC' AND seed <= 7
            ORDER BY seed
        ''', (season,))
        afc_seeds = cursor.fetchall()
        
        # Get AFC playoff results
        cursor.execute('''
            SELECT round, winner_discord_id, winner_team_id
            FROM playoff_results
            WHERE season = ? AND conference = 'AFC'
        ''', (season,))
        afc_results = cursor.fetchall()
        
        # Initialize AFC earnings by seed
        for seed, user_id, team_id in afc_seeds:
            afc_earnings[seed] = {
                'user_id': user_id,
                'team_id': team_id,
                'total_earnings': 0.0,
                'rounds_won': []
            }
        
        # Calculate earnings for each AFC playoff winner
        for round_name, winner_id, team_id in afc_results:
            # Find which seed this winner is
            for seed, data in afc_earnings.items():
                if data['user_id'] == winner_id:
                    payout = PLAYOFF_PAYOUTS.get(round_name, 0)
                    data['total_earnings'] += payout
                    data['rounds_won'].append(round_name)
                    break
        
        return afc_earnings
    
    @app_commands.command(name="generatepayments", description="[Admin] Generate all payment obligations for a season")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(season="Season number to generate payments for")
    async def generate_payments(self, interaction: discord.Interaction, season: int):
        """
        Generate all payment obligations based on:
        1. NFC seeds 8-16 paying into the pot (existing system)
        2. AFC/NFC seed pairing (20% to AFC, 80% to NFC from AFC earnings)
        """
        await interaction.response.defer(thinking=True)
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        payments_created = 0
        errors = []
        afc_pairing_payments = 0
        
        # ============================================
        # PART 1: Existing NFC Seeds 8-16 Payout System
        # ============================================
        
        # Get NFC standings (seeds 8-16 are payers)
        cursor.execute('''
            SELECT seed, user_discord_id, team_id 
            FROM season_standings 
            WHERE season = ? AND conference = 'NFC' AND seed >= 8
            ORDER BY seed
        ''', (season,))
        nfc_payers = cursor.fetchall()
        
        # Get playoff winners by round (NFC only for the pot system)
        cursor.execute('''
            SELECT round, winner_discord_id, winner_team_id
            FROM playoff_results
            WHERE season = ? AND conference = 'NFC'
        ''', (season,))
        nfc_playoff_results = cursor.fetchall()
        
        # Organize NFC winners by round
        nfc_winners_by_round = {
            'wildcard': [],
            'divisional': [],
            'conference': [],
            'superbowl': []
        }
        for result in nfc_playoff_results:
            round_name, winner_id, team_id = result
            nfc_winners_by_round[round_name].append({'user_id': winner_id, 'team_id': team_id})
        
        # Generate NFC pot payments (seeds 8-16 pay to playoff winners)
        for seed, payer_id, payer_team in nfc_payers:
            if payer_id is None:
                errors.append(f"NFC #{seed} has no user assigned")
                continue
                
            if seed not in NFC_PAYER_STRUCTURE:
                continue
                
            payment_info = NFC_PAYER_STRUCTURE[seed]
            target_round = payment_info['round']
            total_amount = payment_info['amount']
            
            # Get winners for this round
            round_winners = nfc_winners_by_round.get(target_round, [])
            
            if not round_winners:
                errors.append(f"No NFC {target_round} winners recorded for Season {season}")
                continue
            
            # Split payment among winners
            amount_per_winner = total_amount / len(round_winners)
            
            for winner in round_winners:
                if winner['user_id'] == payer_id:
                    continue  # Don't pay yourself
                    
                # Create payment record
                cursor.execute('''
                    INSERT INTO payments (season_year, payer_discord_id, payee_discord_id, amount, reason, is_paid)
                    VALUES (?, ?, ?, ?, ?, 0)
                ''', (season, payer_id, winner['user_id'], amount_per_winner, 
                      f"Season {season} - NFC #{seed} to {target_round} winner"))
                payments_created += 1
        
        # ============================================
        # PART 2: AFC/NFC Seed Pairing System
        # ============================================
        
        # Calculate AFC playoff earnings
        afc_earnings = self._calculate_afc_earnings(cursor, season)
        
        # Get NFC standings (seeds 1-7 for pairing)
        cursor.execute('''
            SELECT seed, user_discord_id, team_id 
            FROM season_standings 
            WHERE season = ? AND conference = 'NFC' AND seed <= 7
            ORDER BY seed
        ''', (season,))
        nfc_playoff_seeds = cursor.fetchall()
        
        # Create AFC/NFC pairing payments
        for nfc_seed, nfc_user_id, nfc_team_id in nfc_playoff_seeds:
            if nfc_user_id is None:
                errors.append(f"NFC #{nfc_seed} has no user assigned for pairing")
                continue
            
            # Get paired AFC seed earnings
            afc_data = afc_earnings.get(nfc_seed)
            if not afc_data or afc_data['user_id'] is None:
                errors.append(f"AFC #{nfc_seed} has no user assigned for pairing")
                continue
            
            afc_user_id = afc_data['user_id']
            afc_total_earnings = afc_data['total_earnings']
            
            if afc_total_earnings <= 0:
                continue  # No earnings to split
            
            # Calculate split amounts
            afc_keeps = afc_total_earnings * AFC_RETENTION_RATE  # AFC keeps 20%
            nfc_gets = afc_total_earnings * NFC_PAIRED_RATE      # NFC gets 80%
            
            # NFC seed pays AFC seed their 20% share
            if afc_keeps > 0 and nfc_user_id != afc_user_id:
                rounds_str = ", ".join(afc_data['rounds_won'])
                cursor.execute('''
                    INSERT INTO payments (season_year, payer_discord_id, payee_discord_id, amount, reason, is_paid)
                    VALUES (?, ?, ?, ?, ?, 0)
                ''', (season, nfc_user_id, afc_user_id, afc_keeps,
                      f"Season {season} - NFC #{nfc_seed} pays AFC #{nfc_seed} (20% of AFC earnings: {rounds_str})"))
                afc_pairing_payments += 1
                payments_created += 1
            
            # Record NFC's 80% earnings (this is implicit - they keep what they don't pay out)
            # We can track this in profitability calculations
        
        # ============================================
        # Update profitability records
        # ============================================
        self._update_profitability(cursor, season)
        
        conn.commit()
        conn.close()
        
        # Build response embed
        embed = discord.Embed(
            title=f"💰 Season {season} Payments Generated",
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name="📊 Summary",
            value=(
                f"**Total Payments Created:** {payments_created}\n"
                f"**NFC Pot Payments:** {payments_created - afc_pairing_payments}\n"
                f"**AFC/NFC Pairing Payments:** {afc_pairing_payments}\n"
                f"**Errors:** {len(errors)}"
            ),
            inline=False
        )
        
        # Show AFC earnings breakdown
        if afc_earnings:
            afc_summary = []
            for seed, data in sorted(afc_earnings.items()):
                if data['total_earnings'] > 0:
                    afc_20 = data['total_earnings'] * AFC_RETENTION_RATE
                    nfc_80 = data['total_earnings'] * NFC_PAIRED_RATE
                    afc_summary.append(
                        f"**Seed #{seed}:** ${data['total_earnings']:.0f} → "
                        f"AFC gets ${afc_20:.0f}, NFC gets ${nfc_80:.0f}"
                    )
            
            if afc_summary:
                embed.add_field(
                    name="🏈 AFC/NFC Seed Pairing Breakdown",
                    value="\n".join(afc_summary) or "No AFC playoff earnings",
                    inline=False
                )
        
        if errors:
            embed.add_field(
                name="⚠️ Issues",
                value="\n".join(errors[:5]) + ("\n*...and more*" if len(errors) > 5 else ""),
                inline=False
            )
        
        embed.add_field(
            name="📋 Next Steps",
            value="Use `/postpayments` to send payment notifications to GM channels\nUse `/dues` to view the full dues tracker",
            inline=False
        )
        
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="viewpairings", description="View AFC/NFC seed pairings and potential earnings")
    @app_commands.describe(season="Season number to view pairings for")
    async def view_pairings(self, interaction: discord.Interaction, season: int):
        """View the AFC/NFC seed pairings and their earnings breakdown."""
        await interaction.response.defer()
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Get AFC standings
        cursor.execute('''
            SELECT seed, user_discord_id, team_id 
            FROM season_standings 
            WHERE season = ? AND conference = 'AFC' AND seed <= 7
            ORDER BY seed
        ''', (season,))
        afc_seeds = {row[0]: {'user_id': row[1], 'team_id': row[2]} for row in cursor.fetchall()}
        
        # Get NFC standings
        cursor.execute('''
            SELECT seed, user_discord_id, team_id 
            FROM season_standings 
            WHERE season = ? AND conference = 'NFC' AND seed <= 7
            ORDER BY seed
        ''', (season,))
        nfc_seeds = {row[0]: {'user_id': row[1], 'team_id': row[2]} for row in cursor.fetchall()}
        
        # Calculate AFC earnings
        afc_earnings = self._calculate_afc_earnings(cursor, season)
        
        conn.close()
        
        embed = discord.Embed(
            title=f"🔗 Season {season} AFC/NFC Seed Pairings",
            description=(
                "**Payout Split:** AFC keeps 20%, NFC gets 80% of AFC earnings\n"
                "NFC seed owner pays their paired AFC seed owner 20% of AFC's playoff earnings"
            ),
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        pairings = []
        for seed in range(1, 8):
            afc_data = afc_seeds.get(seed, {})
            nfc_data = nfc_seeds.get(seed, {})
            afc_earn = afc_earnings.get(seed, {})
            
            afc_user = interaction.guild.get_member(afc_data.get('user_id'))
            nfc_user = interaction.guild.get_member(nfc_data.get('user_id'))
            
            afc_name = afc_user.display_name if afc_user else "Not Set"
            nfc_name = nfc_user.display_name if nfc_user else "Not Set"
            afc_team = afc_data.get('team_id', '???')
            nfc_team = nfc_data.get('team_id', '???')
            
            total_afc_earnings = afc_earn.get('total_earnings', 0)
            afc_keeps = total_afc_earnings * AFC_RETENTION_RATE
            nfc_gets = total_afc_earnings * NFC_PAIRED_RATE
            
            if total_afc_earnings > 0:
                earnings_str = f" → AFC: ${afc_keeps:.0f} | NFC: ${nfc_gets:.0f}"
            else:
                earnings_str = ""
            
            pairings.append(
                f"**#{seed}:** {afc_team} ({afc_name}) ↔ {nfc_team} ({nfc_name}){earnings_str}"
            )
        
        embed.add_field(
            name="Seed Pairings (AFC ↔ NFC)",
            value="\n".join(pairings),
            inline=False
        )
        
        # Payout reference
        embed.add_field(
            name="💵 Playoff Payout Values",
            value=(
                f"**Wild Card/Bye:** ${PLAYOFF_PAYOUTS['wildcard']}\n"
                f"**Divisional:** ${PLAYOFF_PAYOUTS['divisional']}\n"
                f"**Conference:** ${PLAYOFF_PAYOUTS['conference']}\n"
                f"**Super Bowl:** ${PLAYOFF_PAYOUTS['superbowl']}"
            ),
            inline=True
        )
        
        embed.add_field(
            name="📊 Split Example",
            value=(
                "If AFC #3 wins Divisional ($100):\n"
                "• AFC #3 owner gets: $20 (20%)\n"
                "• NFC #3 owner keeps: $80 (80%)\n"
                "• NFC #3 pays AFC #3 the $20"
            ),
            inline=True
        )
        
        await interaction.followup.send(embed=embed)
    
    def _update_profitability(self, cursor, season):
        """Update profitability records for all users in a season."""
        # Get all users with payments in this season
        cursor.execute('''
            SELECT DISTINCT user_id FROM (
                SELECT payer_discord_id as user_id FROM payments WHERE season_year = ?
                UNION
                SELECT payee_discord_id as user_id FROM payments WHERE season_year = ?
            )
        ''', (season, season))
        users = cursor.fetchall()
        
        for (user_id,) in users:
            # Calculate dues paid (as payer)
            cursor.execute('''
                SELECT COALESCE(SUM(amount), 0) FROM payments 
                WHERE season_year = ? AND payer_discord_id = ?
            ''', (season, user_id))
            dues_paid = cursor.fetchone()[0]
            
            # Calculate playoff earnings (as payee)
            cursor.execute('''
                SELECT COALESCE(SUM(amount), 0) FROM payments 
                WHERE season_year = ? AND payee_discord_id = ?
            ''', (season, user_id))
            playoff_earnings = cursor.fetchone()[0]
            
            # Calculate wager profit
            cursor.execute('''
                SELECT 
                    COALESCE(SUM(CASE WHEN winner_user_id = ? THEN amount ELSE 0 END), 0) -
                    COALESCE(SUM(CASE WHEN winner_user_id != ? AND (home_user_id = ? OR away_user_id = ?) THEN amount ELSE 0 END), 0)
                FROM wagers 
                WHERE season_year = ? AND winner_user_id IS NOT NULL
            ''', (user_id, user_id, user_id, user_id, season))
            wager_profit = cursor.fetchone()[0]
            
            # Calculate net profit
            net_profit = playoff_earnings - dues_paid + wager_profit
            
            # Update or insert profitability record
            cursor.execute('''
                INSERT OR REPLACE INTO franchise_profitability 
                (user_discord_id, season, playoff_earnings, dues_paid, wager_profit, net_profit)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, season, playoff_earnings, dues_paid, wager_profit, net_profit))
    
    @app_commands.command(name="clearpayments", description="[Admin] Clear payment records for a season")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        season="Season number to clear payments for",
        confirm="Type 'CONFIRM' to proceed (or 'FORCEALL' to include unpaid)",
        include_unpaid="Also delete unpaid payments (default: False, preserves unpaid)"
    )
    async def clear_payments(self, interaction: discord.Interaction, season: int, confirm: str, include_unpaid: bool = False):
        """Clear payment records for a season. By default preserves unpaid payments."""
        if confirm not in ["CONFIRM", "FORCEALL"]:
            await interaction.response.send_message(
                "⚠️ To clear payments, you must type `CONFIRM` in the confirm field.\n"
                "This will only clear PAID payments for the season.\n\n"
                "To also clear unpaid payments, type `FORCEALL` instead.\n"
                "This action cannot be undone!",
                ephemeral=True
            )
            return
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Check for unpaid payments first
        cursor.execute('SELECT COUNT(*) FROM payments WHERE season_year = ? AND is_paid = 0', (season,))
        unpaid_count = cursor.fetchone()[0]
        
        if confirm == "FORCEALL" or include_unpaid:
            # Delete ALL payments for the season
            cursor.execute('DELETE FROM payments WHERE season_year = ?', (season,))
            deleted = cursor.rowcount
            message = f"✅ Cleared {deleted} payment records for Season {season} (including {unpaid_count} unpaid)"
        else:
            # Only delete PAID payments, preserve unpaid
            cursor.execute('DELETE FROM payments WHERE season_year = ? AND is_paid = 1', (season,))
            deleted = cursor.rowcount
            if unpaid_count > 0:
                message = f"✅ Cleared {deleted} PAID payment records for Season {season}\n⚠️ Preserved {unpaid_count} unpaid payments"
            else:
                message = f"✅ Cleared {deleted} payment records for Season {season}"
        
        cursor.execute('DELETE FROM franchise_profitability WHERE season = ?', (season,))
        
        conn.commit()
        conn.close()
        
        await interaction.response.send_message(message, ephemeral=True)
    
    @app_commands.command(name="clearplayoffresults", description="[Admin] Clear playoff results for a season")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        season="Season number to clear playoff results for",
        confirm="Type 'CONFIRM' to proceed"
    )
    async def clear_playoff_results(self, interaction: discord.Interaction, season: int, confirm: str):
        """Clear all playoff result records for a season."""
        if confirm != "CONFIRM":
            await interaction.response.send_message(
                "⚠️ To clear playoff results, you must type `CONFIRM` in the confirm field.\n"
                "This action cannot be undone!",
                ephemeral=True
            )
            return
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM playoff_results WHERE season = ?', (season,))
        deleted = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        await interaction.response.send_message(
            f"✅ Cleared {deleted} playoff result records for Season {season}",
            ephemeral=True
        )
    
    @app_commands.command(name="clearseason", description="[Admin] Clear ALL data for a season (payments, playoff results, seedings)")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        season="Season number to clear all data for",
        confirm="Type 'CLEARALL' to proceed - this clears EVERYTHING for the season"
    )
    async def clear_season(self, interaction: discord.Interaction, season: int, confirm: str):
        """Clear all data for a season - payments, playoff results, and seedings."""
        if confirm != "CLEARALL":
            await interaction.response.send_message(
                f"⚠️ **WARNING: This will clear ALL data for Season {season}!**\n\n"
                f"This includes:\n"
                f"• All payments (paid and unpaid)\n"
                f"• All playoff results\n"
                f"• All seedings (AFC and NFC)\n"
                f"• All profitability records\n\n"
                f"To proceed, type `CLEARALL` in the confirm field.\n"
                f"**This action cannot be undone!**",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(thinking=True)
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        results = []
        
        # Clear payments
        cursor.execute('DELETE FROM payments WHERE season_year = ?', (season,))
        results.append(f"💰 Payments: {cursor.rowcount} deleted")
        
        # Clear playoff results
        cursor.execute('DELETE FROM playoff_results WHERE season = ?', (season,))
        results.append(f"🏆 Playoff results: {cursor.rowcount} deleted")
        
        # Clear seedings
        cursor.execute('DELETE FROM season_standings WHERE season = ?', (season,))
        results.append(f"🏈 Seedings: {cursor.rowcount} deleted")
        
        # Clear profitability
        cursor.execute('DELETE FROM franchise_profitability WHERE season = ?', (season,))
        results.append(f"📊 Profitability: {cursor.rowcount} deleted")
        
        conn.commit()
        conn.close()
        
        embed = discord.Embed(
            title=f"🗑️ Season {season} Cleared",
            description="All data for this season has been deleted.",
            color=discord.Color.red(),
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name="Deleted Records",
            value="\n".join(results),
            inline=False
        )
        
        embed.set_footer(text="This action cannot be undone")
        
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="postpayments", description="[Admin] Post payment summaries to GM division channels")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(season="Season number to post payments for")
    async def post_payments(self, interaction: discord.Interaction, season: int):
        """Post payment summaries to each GM's division channel."""
        await interaction.response.defer(thinking=True)
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Get all payments for this season
        cursor.execute('''
            SELECT payer_discord_id, payee_discord_id, amount, reason, is_paid
            FROM payments
            WHERE season_year = ?
            ORDER BY payer_discord_id
        ''', (season,))
        payments = cursor.fetchall()
        
        conn.close()
        
        if not payments:
            await interaction.followup.send(f"No payments found for Season {season}")
            return
        
        # Group payments by payer
        payer_payments = {}
        for payer_id, payee_id, amount, reason, is_paid in payments:
            if payer_id not in payer_payments:
                payer_payments[payer_id] = []
            payer_payments[payer_id].append({
                'payee_id': payee_id,
                'amount': amount,
                'reason': reason,
                'is_paid': is_paid
            })
        
        channels_posted = 0
        
        for payer_id, payment_list in payer_payments.items():
            member = interaction.guild.get_member(payer_id)
            if not member:
                continue
            
            # Find the user's division channel
            division_channel = None
            for role in member.roles:
                for div_name, channel_name in DIVISION_CHANNELS.items():
                    if div_name.lower().replace(' ', '-') in role.name.lower().replace(' ', '-'):
                        division_channel = discord.utils.get(interaction.guild.text_channels, name=channel_name)
                        break
                if division_channel:
                    break
            
            if not division_channel:
                continue
            
            # Build payment summary embed
            total_owed = sum(p['amount'] for p in payment_list if not p['is_paid'])
            
            embed = discord.Embed(
                title=f"💰 Season {season} Payment Summary",
                description=f"**{member.display_name}** owes the following:",
                color=discord.Color.orange() if total_owed > 0 else discord.Color.green(),
                timestamp=datetime.utcnow()
            )
            
            payment_lines = []
            for p in payment_list:
                payee = interaction.guild.get_member(p['payee_id'])
                payee_name = payee.display_name if payee else f"User {p['payee_id']}"
                status = "✅" if p['is_paid'] else "⏳"
                payment_lines.append(f"{status} ${p['amount']:.2f} to **{payee_name}**")
            
            embed.add_field(
                name="Payments",
                value="\n".join(payment_lines[:10]) + ("\n*...and more*" if len(payment_lines) > 10 else ""),
                inline=False
            )
            
            embed.add_field(
                name="Total Outstanding",
                value=f"**${total_owed:.2f}**",
                inline=True
            )
            
            embed.set_footer(text="Use /markpaid to record payments")
            
            try:
                await division_channel.send(embed=embed)
                channels_posted += 1
            except discord.Forbidden:
                pass
        
        await interaction.followup.send(
            f"✅ Posted payment summaries to {channels_posted} division channels"
        )
    
    @app_commands.command(name="profitability", description="View league-wide profitability rankings")
    @app_commands.describe(season="Season to view (optional, shows all-time if not specified)")
    async def profitability(self, interaction: discord.Interaction, season: Optional[int] = None):
        """Show profitability leaderboard."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        if season:
            cursor.execute('''
                SELECT user_discord_id, playoff_earnings, dues_paid, wager_profit, net_profit
                FROM franchise_profitability
                WHERE season = ?
                ORDER BY net_profit DESC
            ''', (season,))
            title = f"💰 Season {season} Profitability"
        else:
            cursor.execute('''
                SELECT user_discord_id, 
                       SUM(playoff_earnings) as total_earnings,
                       SUM(dues_paid) as total_dues,
                       SUM(wager_profit) as total_wagers,
                       SUM(net_profit) as total_profit
                FROM franchise_profitability
                GROUP BY user_discord_id
                ORDER BY total_profit DESC
            ''')
            title = "💰 All-Time Profitability"
        
        results = cursor.fetchall()
        conn.close()
        
        embed = discord.Embed(
            title=title,
            color=discord.Color.gold(),
            timestamp=datetime.utcnow()
        )
        
        if not results:
            embed.description = "*No profitability data recorded yet.*"
        else:
            top_lines = []
            for i, (user_id, earnings, dues, wagers, net) in enumerate(results[:10], 1):
                member = interaction.guild.get_member(user_id)
                name = member.display_name if member else f"User {user_id}"
                
                if i == 1:
                    rank_emoji = "🥇"
                elif i == 2:
                    rank_emoji = "🥈"
                elif i == 3:
                    rank_emoji = "🥉"
                else:
                    rank_emoji = f"{i}."
                
                profit_str = f"+${net:.2f}" if net >= 0 else f"-${abs(net):.2f}"
                top_lines.append(f"{rank_emoji} **{name}**: {profit_str}")
            
            embed.add_field(
                name="🏆 Top Earners",
                value="\n".join(top_lines),
                inline=False
            )
            
            total_pot = sum(r[2] for r in results)
            total_earnings = sum(r[1] for r in results)
            
            embed.add_field(
                name="📊 League Summary",
                value=f"**Total Pot:** ${total_pot:.2f}\n**Total Distributed:** ${total_earnings:.2f}",
                inline=False
            )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="myprofit", description="View your personal franchise profitability")
    async def my_profit(self, interaction: discord.Interaction):
        """Show the user's personal profitability breakdown."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT season, playoff_earnings, dues_paid, wager_profit, net_profit
            FROM franchise_profitability
            WHERE user_discord_id = ?
            ORDER BY season DESC
        ''', (interaction.user.id,))
        results = cursor.fetchall()
        
        cursor.execute('''
            SELECT 
                SUM(playoff_earnings) as total_earnings,
                SUM(dues_paid) as total_dues,
                SUM(wager_profit) as total_wagers,
                SUM(net_profit) as total_profit
            FROM franchise_profitability
            WHERE user_discord_id = ?
        ''', (interaction.user.id,))
        totals = cursor.fetchone()
        
        conn.close()
        
        embed = discord.Embed(
            title=f"💰 {interaction.user.display_name}'s Profitability",
            color=discord.Color.gold(),
            timestamp=datetime.utcnow()
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
            
            if results:
                season_lines = []
                for season, earnings, dues, wagers, net in results[:5]:
                    net_str = f"+${net:.2f}" if net >= 0 else f"-${abs(net):.2f}"
                    season_lines.append(f"**Season {season}:** {net_str}")
                
                embed.add_field(
                    name="📅 Recent Seasons",
                    value="\n".join(season_lines),
                    inline=False
                )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="payoutstructure", description="View the complete payout structure")
    async def payout_structure(self, interaction: discord.Interaction):
        """Display the complete payout structure including AFC/NFC pairing."""
        embed = discord.Embed(
            title="💰 Season Payout Structure",
            description="Complete breakdown of how season earnings work",
            color=discord.Color.gold(),
            timestamp=datetime.utcnow()
        )
        
        # Playoff payouts
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
        
        # NFC Pot System
        nfc_pot_lines = []
        for seed in sorted(NFC_PAYER_STRUCTURE.keys()):
            info = NFC_PAYER_STRUCTURE[seed]
            nfc_pot_lines.append(f"NFC #{seed}: ${info['amount']} → {info['round'].title()} Winners")
        
        embed.add_field(
            name="📤 NFC Seeds 8-16 Pay Into Pot",
            value="\n".join(nfc_pot_lines),
            inline=False
        )
        
        # AFC/NFC Pairing
        embed.add_field(
            name="🔗 AFC/NFC Seed Pairing (Seeds 1-7)",
            value=(
                "Each NFC playoff seed is paired with the same AFC seed.\n\n"
                f"**AFC Team Earnings Split:**\n"
                f"• AFC owner keeps: **{int(AFC_RETENTION_RATE*100)}%** of their playoff earnings\n"
                f"• NFC paired owner gets: **{int(NFC_PAIRED_RATE*100)}%** of AFC's earnings\n\n"
                f"*NFC seed pays their paired AFC seed the {int(AFC_RETENTION_RATE*100)}%*"
            ),
            inline=False
        )
        
        # Example
        embed.add_field(
            name="📊 Example: AFC #2 Wins Super Bowl ($300)",
            value=(
                "• AFC #2 owner receives: $60 (20%)\n"
                "• NFC #2 owner keeps: $240 (80%)\n"
                "• NFC #2 pays AFC #2 the $60\n\n"
                "*NFC owners benefit from their paired AFC team's success!*"
            ),
            inline=False
        )
        
        embed.set_footer(text="Use /viewpairings to see current season pairings")
        
        await interaction.response.send_message(embed=embed)
    
    async def _get_payouts_channel(self, guild):
        """Find the #payouts channel (or fallbacks)."""
        for channel in guild.text_channels:
            if channel.name.lower() in ['payouts', 'payout', 'finances']:
                return channel
        return None
    
    async def _auto_generate_payments(self, guild, season: int) -> Dict:
        """
        Auto-generate payments for a season.
        Preserves unpaid payments from prior seasons.
        Returns dict with success status and details.
        """
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            payments_created = 0
            errors = []
            
            # Check if payments already exist for this season
            cursor.execute('SELECT COUNT(*) FROM payments WHERE season_year = ?', (season,))
            existing_count = cursor.fetchone()[0]
            
            if existing_count > 0:
                conn.close()
                return {
                    'success': True,
                    'payments_created': 0,
                    'message': f'Payments already exist for Season {season}. Use /clearpayments to regenerate.'
                }
            
            # ============================================
            # PART 1: NFC Seeds 8-16 Payout System
            # ============================================
            
            cursor.execute('''
                SELECT seed, user_discord_id, team_id 
                FROM season_standings 
                WHERE season = ? AND conference = 'NFC' AND seed >= 8
                ORDER BY seed
            ''', (season,))
            nfc_payers = cursor.fetchall()
            
            cursor.execute('''
                SELECT round, winner_discord_id, winner_team_id
                FROM playoff_results
                WHERE season = ? AND conference = 'NFC'
            ''', (season,))
            nfc_playoff_results = cursor.fetchall()
            
            nfc_winners_by_round = {
                'wildcard': [],
                'divisional': [],
                'conference': [],
                'superbowl': []
            }
            for result in nfc_playoff_results:
                round_name, winner_id, team_id = result
                nfc_winners_by_round[round_name].append({'user_id': winner_id, 'team_id': team_id})
            
            for seed, payer_id, payer_team in nfc_payers:
                if payer_id is None or seed not in NFC_PAYER_STRUCTURE:
                    continue
                    
                payment_info = NFC_PAYER_STRUCTURE[seed]
                target_round = payment_info['round']
                total_amount = payment_info['amount']
                
                round_winners = nfc_winners_by_round.get(target_round, [])
                if not round_winners:
                    continue
                
                amount_per_winner = total_amount / len(round_winners)
                
                for winner in round_winners:
                    if winner['user_id'] == payer_id:
                        continue
                        
                    cursor.execute('''
                        INSERT INTO payments (season_year, payer_discord_id, payee_discord_id, amount, reason, is_paid)
                        VALUES (?, ?, ?, ?, ?, 0)
                    ''', (season, payer_id, winner['user_id'], amount_per_winner, 
                          f"Season {season} - NFC #{seed} to {target_round} winner"))
                    payments_created += 1
            
            # ============================================
            # PART 2: AFC/NFC Seed Pairing System
            # ============================================
            
            afc_earnings = self._calculate_afc_earnings(cursor, season)
            
            cursor.execute('''
                SELECT seed, user_discord_id, team_id 
                FROM season_standings 
                WHERE season = ? AND conference = 'NFC' AND seed <= 7
                ORDER BY seed
            ''', (season,))
            nfc_playoff_seeds = cursor.fetchall()
            
            for nfc_seed, nfc_user_id, nfc_team_id in nfc_playoff_seeds:
                if nfc_user_id is None:
                    continue
                
                afc_data = afc_earnings.get(nfc_seed)
                if not afc_data or afc_data['user_id'] is None:
                    continue
                
                afc_user_id = afc_data['user_id']
                afc_total_earnings = afc_data['total_earnings']
                
                if afc_total_earnings <= 0:
                    continue
                
                afc_keeps = afc_total_earnings * AFC_RETENTION_RATE
                
                if afc_keeps > 0 and nfc_user_id != afc_user_id:
                    rounds_str = ", ".join(afc_data['rounds_won'])
                    cursor.execute('''
                        INSERT INTO payments (season_year, payer_discord_id, payee_discord_id, amount, reason, is_paid)
                        VALUES (?, ?, ?, ?, ?, 0)
                    ''', (season, nfc_user_id, afc_user_id, afc_keeps,
                          f"Season {season} - NFC #{nfc_seed} pays AFC #{nfc_seed} (20% of AFC earnings: {rounds_str})"))
                    payments_created += 1
            
            # Update profitability records
            self._update_profitability(cursor, season)
            
            conn.commit()
            conn.close()
            
            return {
                'success': True,
                'payments_created': payments_created,
                'message': f'Generated {payments_created} payments for Season {season}'
            }
            
        except Exception as e:
            logger.error(f"Error auto-generating payments: {e}")
            return {
                'success': False,
                'payments_created': 0,
                'error': str(e)
            }
    
    async def _post_payments_to_channel(self, channel, season: int, guild):
        """Post payment summary to the payouts channel."""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            # Get all payments for this season
            cursor.execute('''
                SELECT payer_discord_id, payee_discord_id, amount, reason, is_paid
                FROM payments WHERE season_year = ?
                ORDER BY amount DESC
            ''', (season,))
            payments = cursor.fetchall()
            conn.close()
            
            if not payments:
                return
            
            # Create summary embed
            embed = discord.Embed(
                title=f"🏆 Season {season} Payouts Generated!",
                description=(
                    f"The Super Bowl has concluded and all payouts have been calculated.\n\n"
                    f"**Total Payments:** {len(payments)}\n"
                    f"**Total Amount:** ${sum(p[2] for p in payments):.2f}"
                ),
                color=discord.Color.gold(),
                timestamp=datetime.utcnow()
            )
            
            # Group payments by payer
            payer_totals = {}
            for payer_id, payee_id, amount, reason, is_paid in payments:
                if payer_id not in payer_totals:
                    payer_totals[payer_id] = {'total': 0, 'payments': []}
                payer_totals[payer_id]['total'] += amount
                payer_totals[payer_id]['payments'].append((payee_id, amount, reason))
            
            # Add top payers
            sorted_payers = sorted(payer_totals.items(), key=lambda x: x[1]['total'], reverse=True)[:10]
            payer_lines = []
            for payer_id, data in sorted_payers:
                member = guild.get_member(payer_id)
                name = member.display_name if member else f"User {payer_id}"
                payer_lines.append(f"• **{name}**: ${data['total']:.2f}")
            
            if payer_lines:
                embed.add_field(
                    name="💸 Who Owes (Top 10)",
                    value="\n".join(payer_lines),
                    inline=True
                )
            
            # Group by payee (who receives)
            payee_totals = {}
            for payer_id, payee_id, amount, reason, is_paid in payments:
                if payee_id not in payee_totals:
                    payee_totals[payee_id] = 0
                payee_totals[payee_id] += amount
            
            sorted_payees = sorted(payee_totals.items(), key=lambda x: x[1], reverse=True)[:10]
            payee_lines = []
            for payee_id, total in sorted_payees:
                member = guild.get_member(payee_id)
                name = member.display_name if member else f"User {payee_id}"
                payee_lines.append(f"• **{name}**: ${total:.2f}")
            
            if payee_lines:
                embed.add_field(
                    name="💰 Who Receives (Top 10)",
                    value="\n".join(payee_lines),
                    inline=True
                )
            
            embed.add_field(
                name="📋 Commands",
                value=(
                    "`/mypayments` - View your payment info\n"
                    "`/whoiowe` - See who you owe\n"
                    "`/whooowesme` - See who owes you\n"
                    "`/markpaid @user amount` - Mark payment sent"
                ),
                inline=False
            )
            
            embed.set_footer(text="Prior season unpaid payments are preserved")
            
            await channel.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error posting payments to channel: {e}")


async def setup(bot):
    await bot.add_cog(ProfitabilityCog(bot))
