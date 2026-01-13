"""
Madden Export Integration Cog - Automatically imports playoff data from Madden Export API
and generates earnings/payments when playoff results are detected.
Commands:
- /autoplayoffs - Import standings and generate payments (all-in-one)
- /checkexportapi - Check API status
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
import sqlite3
from datetime import datetime
import logging
import aiohttp
import os
from typing import Optional, Dict

logger = logging.getLogger('MistressLIV.MaddenExport')

# Madden Export API URL
MADDEN_EXPORT_API_URL = os.environ.get('MADDEN_EXPORT_API_URL', 'https://web-production-eee7f.up.railway.app')

# Team ID to abbreviation mapping (Madden uses numeric IDs)
TEAM_ID_MAP = {
    0: 'CHI', 1: 'CIN', 2: 'BUF', 3: 'DEN', 4: 'CLE', 5: 'TB', 6: 'ARI', 7: 'LAC',
    8: 'KC', 9: 'IND', 10: 'DAL', 11: 'MIA', 12: 'PHI', 13: 'ATL', 14: 'SF', 15: 'NYG',
    16: 'JAX', 17: 'NYJ', 18: 'DET', 19: 'GB', 20: 'CAR', 21: 'NE', 22: 'LV', 23: 'LAR',
    24: 'BAL', 25: 'WAS', 26: 'NO', 27: 'SEA', 28: 'PIT', 29: 'TEN', 30: 'MIN', 31: 'HOU'
}

# Conference mapping
AFC_TEAMS = ['BAL', 'BUF', 'CIN', 'CLE', 'DEN', 'HOU', 'IND', 'JAX', 
             'KC', 'LAC', 'LV', 'MIA', 'NE', 'NYJ', 'PIT', 'TEN']
NFC_TEAMS = ['ARI', 'ATL', 'CAR', 'CHI', 'DAL', 'DET', 'GB', 'LAR',
             'MIN', 'NO', 'NYG', 'PHI', 'SEA', 'SF', 'TB', 'WAS']

# Playoff payout structure
PLAYOFF_PAYOUTS = {
    'wildcard': 50,
    'divisional': 100,
    'conference': 200,
    'superbowl': 300,
}

# NFC Seeds 8-16 payment structure
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

AFC_RETENTION_RATE = 0.20
NFC_PAIRED_RATE = 0.80


class MaddenExportCog(commands.Cog):
    """Cog for integrating with Madden Export API and auto-generating payments."""
    
    def __init__(self, bot):
        self.bot = bot
        self.db_path = bot.db_path
        self.api_url = MADDEN_EXPORT_API_URL
        self.last_standings_hash = None
    
    async def fetch_standings(self) -> Optional[Dict]:
        """Fetch current standings from Madden Export API."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.api_url}/api/standings") as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception as e:
            logger.error(f"Error fetching standings: {e}")
        return None
    
    def get_team_owner(self, team_abbr: str) -> Optional[int]:
        """Get the Discord ID of a team's owner."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT user_discord_id FROM teams WHERE team_id = ?', (team_abbr,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    
    def get_payouts_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        """Find the payouts channel."""
        for name in ['payouts', 'payout', 'finances']:
            channel = discord.utils.get(guild.text_channels, name=name)
            if channel:
                return channel
        return None
    
    @app_commands.command(name="checkexportapi", description="Check status of Madden Export API")
    async def check_export_api(self, interaction: discord.Interaction):
        """Check if the Madden Export API is online and has data."""
        await interaction.response.defer(thinking=True)
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.api_url}/") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        
                        embed = discord.Embed(
                            title="🔌 Madden Export API Status",
                            color=discord.Color.green(),
                            timestamp=datetime.utcnow()
                        )
                        
                        embed.add_field(
                            name="Status",
                            value=f"✅ {data.get('status', 'Unknown')}",
                            inline=True
                        )
                        embed.add_field(
                            name="Version",
                            value=data.get('version', 'Unknown'),
                            inline=True
                        )
                        embed.add_field(
                            name="API URL",
                            value=f"`{self.api_url}`",
                            inline=False
                        )
                        
                        # Check for standings data
                        async with session.get(f"{self.api_url}/api/playoff-seeds") as seeds_resp:
                            if seeds_resp.status == 200:
                                seeds_data = await seeds_resp.json()
                                if "error" not in seeds_data:
                                    afc_count = len(seeds_data.get('afc', []))
                                    nfc_count = len(seeds_data.get('nfc', []))
                                    embed.add_field(
                                        name="📊 Standings Data",
                                        value=f"AFC: {afc_count} teams\nNFC: {nfc_count} teams",
                                        inline=False
                                    )
                                else:
                                    embed.add_field(
                                        name="📊 Standings Data",
                                        value="❌ No standings exported yet",
                                        inline=False
                                    )
                        
                        embed.set_footer(text="Export standings from Madden Companion App to populate data")
                        await interaction.followup.send(embed=embed)
                    else:
                        await interaction.followup.send(
                            f"❌ Madden Export API returned status {resp.status}",
                            ephemeral=True
                        )
        except Exception as e:
            await interaction.followup.send(
                f"❌ Could not connect to Madden Export API: {e}\n"
                f"API URL: {self.api_url}",
                ephemeral=True
            )
    
    @app_commands.command(name="autoplayoffs", description="[Admin] Automatically import standings and generate payments")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        season="Season number",
        confirm="Type AUTOPAY to confirm automatic payment generation"
    )
    async def auto_playoffs(self, interaction: discord.Interaction, season: int, confirm: str):
        """One-command automation: Import standings from API and generate all payments."""
        if confirm != "AUTOPAY":
            await interaction.response.send_message(
                "⚠️ **Auto Playoffs** will:\n"
                "1. Import current standings from Madden Export API\n"
                "2. Generate all playoff payments based on seedings and results\n"
                "3. Post payment summary to #payouts\n\n"
                "Type `AUTOPAY` in the confirm field to proceed.",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(thinking=True)
        
        results = []
        
        # Step 1: Import standings
        standings = await self.fetch_standings()
        
        if not standings or "error" in standings or "leagueTeamInfoList" not in standings:
            await interaction.followup.send(
                "❌ Could not fetch standings from Madden Export API.\n"
                "Make sure you've exported standings from the Madden Companion App first.\n"
                f"API URL: {self.api_url}"
            )
            return
        
        teams = standings["leagueTeamInfoList"]
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        imported_count = 0
        for team in teams:
            team_id = team.get("teamId")
            team_abbr = TEAM_ID_MAP.get(team_id, f"TEAM{team_id}")
            seed = team.get("seed", 0)
            conf = "AFC" if team_abbr in AFC_TEAMS else "NFC"
            
            if seed > 0:
                cursor.execute('''
                    INSERT OR REPLACE INTO season_standings 
                    (season, conference, seed, team_id, user_discord_id)
                    VALUES (?, ?, ?, ?, ?)
                ''', (season, conf, seed, team_abbr, self.get_team_owner(team_abbr)))
                imported_count += 1
        
        conn.commit()
        results.append(f"✅ Imported {imported_count} playoff seedings")
        
        # Step 2: Check for playoff results
        cursor.execute('SELECT COUNT(*) FROM playoff_results WHERE season = ?', (season,))
        result_count = cursor.fetchone()[0]
        
        if result_count == 0:
            conn.close()
            await interaction.followup.send(
                f"✅ Imported {imported_count} playoff seedings for Season {season}.\n\n"
                "⚠️ **No playoff results recorded yet.**\n"
                "Use `/playoff winner` to record winners for each round:\n"
                "• Wildcard (4 winners)\n"
                "• Divisional (2 winners)\n"
                "• Conference (1 winner per conference)\n"
                "• Super Bowl (1 winner)\n\n"
                "Then run `/autoplayoffs` again to generate payments."
            )
            return
        
        results.append(f"✅ Found {result_count} playoff results")
        
        # Step 3: Generate payments
        cursor.execute('''
            SELECT conference, seed, team_id, user_discord_id 
            FROM season_standings 
            WHERE season = ?
        ''', (season,))
        seedings = cursor.fetchall()
        
        cursor.execute('''
            SELECT round, winner_discord_id, winner_team_id, conference
            FROM playoff_results
            WHERE season = ?
        ''', (season,))
        playoff_results = cursor.fetchall()
        
        afc_seedings = {s[1]: {'team': s[2], 'user': s[3]} for s in seedings if s[0] == 'AFC'}
        nfc_seedings = {s[1]: {'team': s[2], 'user': s[3]} for s in seedings if s[0] == 'NFC'}
        
        winners_by_round = {}
        for r in playoff_results:
            round_name, winner_id, winner_team, conf = r
            if round_name not in winners_by_round:
                winners_by_round[round_name] = []
            winners_by_round[round_name].append({
                'user': winner_id,
                'team': winner_team,
                'conf': conf
            })
        
        payments_created = []
        
        # NFC Seeds 8-16 pay into pot
        for seed, payment_info in NFC_PAYER_STRUCTURE.items():
            if seed in nfc_seedings:
                payer = nfc_seedings[seed]
                round_name = payment_info['round']
                amount = payment_info['amount']
                
                if round_name in winners_by_round:
                    round_winners = winners_by_round[round_name]
                    amount_per_winner = amount / len(round_winners) if round_winners else 0
                    
                    for winner in round_winners:
                        if payer['user'] and winner['user']:
                            cursor.execute('''
                                INSERT INTO payments 
                                (payer_discord_id, payee_discord_id, amount, reason, season_year, is_paid)
                                VALUES (?, ?, ?, ?, ?, 0)
                            ''', (
                                payer['user'],
                                winner['user'],
                                amount_per_winner,
                                f"NFC Seed {seed} → {round_name.title()} Winner ({winner['team']})",
                                season
                            ))
                            payments_created.append({
                                'from': payer['team'],
                                'to': winner['team'],
                                'amount': amount_per_winner
                            })
        
        # AFC/NFC Seed Pairing
        for seed in range(1, 8):
            if seed in afc_seedings and seed in nfc_seedings:
                afc_team = afc_seedings[seed]
                nfc_team = nfc_seedings[seed]
                
                afc_earnings = 0
                for round_name, payout in PLAYOFF_PAYOUTS.items():
                    if round_name in winners_by_round:
                        for winner in winners_by_round[round_name]:
                            if winner['user'] == afc_team['user']:
                                afc_earnings += payout
                
                if afc_earnings > 0 and afc_team['user'] and nfc_team['user']:
                    nfc_payout = afc_earnings * NFC_PAIRED_RATE
                    
                    cursor.execute('''
                        INSERT INTO payments 
                        (payer_discord_id, payee_discord_id, amount, reason, season_year, is_paid)
                        VALUES (?, ?, ?, ?, ?, 0)
                    ''', (
                        afc_team['user'],
                        nfc_team['user'],
                        nfc_payout,
                        f"AFC/NFC Seed {seed} Pairing (80% of ${afc_earnings:.0f})",
                        season
                    ))
                    payments_created.append({
                        'from': afc_team['team'],
                        'to': nfc_team['team'],
                        'amount': nfc_payout
                    })
        
        conn.commit()
        conn.close()
        
        results.append(f"✅ Created {len(payments_created)} payments")
        
        # Create summary embed
        total_amount = sum(p['amount'] for p in payments_created)
        
        embed = discord.Embed(
            title=f"🏆 Season {season} Playoff Payments - Auto Generated",
            description="\n".join(results),
            color=discord.Color.gold(),
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name="📊 Summary",
            value=f"**{len(payments_created)}** payments totaling **${total_amount:.2f}**",
            inline=False
        )
        
        if payments_created[:8]:
            payment_list = "\n".join([
                f"• {p['from']} → {p['to']}: ${p['amount']:.2f}"
                for p in payments_created[:8]
            ])
            if len(payments_created) > 8:
                payment_list += f"\n*... and {len(payments_created) - 8} more*"
            embed.add_field(name="💸 Payments Created", value=payment_list, inline=False)
        
        embed.set_footer(text="Payments posted to #payouts")
        
        await interaction.followup.send(embed=embed)
        
        # Post to payouts channel
        payouts_channel = self.get_payouts_channel(interaction.guild)
        if payouts_channel:
            await payouts_channel.send(embed=embed)


async def setup(bot):
    await bot.add_cog(MaddenExportCog(bot))
