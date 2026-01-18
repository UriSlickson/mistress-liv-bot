"""
Madden Export Integration Cog - Automatically imports playoff data and generates payments.
Data Source Priority:
1. Snallabot API (primary)
2. Madden Export API (fallback)

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

# API URLs
SNALLABOT_API_BASE = "https://snallabot.me"
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
    """Cog for integrating with Snallabot/Madden Export API and auto-generating payments."""
    
    def __init__(self, bot):
        self.bot = bot
        self.db_path = bot.db_path
        self.api_url = MADDEN_EXPORT_API_URL
        self.last_standings_hash = None
    
    async def get_snallabot_config(self, guild_id: int) -> Optional[Dict]:
        """Get Snallabot configuration for a guild."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Try league_config first
        cursor.execute('''
            SELECT league_id, platform, current_season FROM league_config 
            WHERE guild_id = ? AND is_active = 1
        ''', (guild_id,))
        row = cursor.fetchone()
        
        if row:
            conn.close()
            return {'league_id': row[0], 'platform': row[1], 'current_season': row[2]}
        
        # Fallback to snallabot_config
        cursor.execute('SELECT league_id, platform, current_season FROM snallabot_config WHERE guild_id = ?', (guild_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {'league_id': row[0], 'platform': row[1], 'current_season': row[2]}
        return None
    
    async def fetch_standings_from_snallabot(self, guild_id: int) -> Optional[Dict]:
        """Fetch current standings from Snallabot API (PRIMARY SOURCE)."""
        config = await self.get_snallabot_config(guild_id)
        if not config:
            logger.warning("No Snallabot config found, cannot fetch from Snallabot")
            return None
        
        league_id = config.get('league_id', 'liv')
        platform = config.get('platform', 'xboxone')
        
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{SNALLABOT_API_BASE}/{platform}/{league_id}/standings"
                logger.info(f"Fetching standings from Snallabot: {url}")
                
                async with session.get(url, timeout=30) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        logger.info(f"Successfully fetched standings from Snallabot")
                        return {'source': 'snallabot', 'data': data}
        except Exception as e:
            logger.error(f"Error fetching standings from Snallabot: {e}")
        return None
    
    async def fetch_standings_from_madden_export(self) -> Optional[Dict]:
        """Fetch current standings from Madden Export API (FALLBACK SOURCE)."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.api_url}/api/standings", timeout=30) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        logger.info(f"Successfully fetched standings from Madden Export API")
                        return {'source': 'madden_export', 'data': data}
        except Exception as e:
            logger.error(f"Error fetching standings from Madden Export: {e}")
        return None
    
    async def fetch_standings(self, guild_id: int) -> Optional[Dict]:
        """Fetch standings - tries Snallabot first, then Madden Export as fallback."""
        # Try Snallabot FIRST (primary source)
        result = await self.fetch_standings_from_snallabot(guild_id)
        if result:
            return result
        
        # Fallback to Madden Export API
        logger.info("Snallabot unavailable, trying Madden Export API...")
        result = await self.fetch_standings_from_madden_export()
        if result:
            return result
        
        logger.error("Could not fetch standings from any source")
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
    
    @app_commands.command(name="checkexportapi", description="Check status of data sources (Snallabot + Madden Export)")
    async def check_export_api(self, interaction: discord.Interaction):
        """Check if the data sources are online and have data."""
        await interaction.response.defer(thinking=True)
        
        embed = discord.Embed(
            title="🔌 Data Source Status",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        # Check Snallabot (PRIMARY)
        snallabot_status = "❌ Unavailable"
        try:
            config = await self.get_snallabot_config(interaction.guild.id)
            if config:
                async with aiohttp.ClientSession() as session:
                    league_id = config.get('league_id', 'liv')
                    platform = config.get('platform', 'xboxone')
                    url = f"{SNALLABOT_API_BASE}/{platform}/{league_id}/standings"
                    async with session.get(url, timeout=10) as resp:
                        if resp.status == 200:
                            snallabot_status = "✅ Online"
                        else:
                            snallabot_status = f"⚠️ Status {resp.status}"
            else:
                snallabot_status = "⚠️ Not configured"
        except Exception as e:
            snallabot_status = f"❌ Error: {str(e)[:30]}"
        
        embed.add_field(
            name="1️⃣ Snallabot API (Primary)",
            value=snallabot_status,
            inline=False
        )
        
        # Check Madden Export (FALLBACK)
        madden_status = "❌ Unavailable"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.api_url}/", timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        madden_status = f"✅ {data.get('status', 'Online')}"
                    else:
                        madden_status = f"⚠️ Status {resp.status}"
        except Exception as e:
            madden_status = f"❌ Error: {str(e)[:30]}"
        
        embed.add_field(
            name="2️⃣ Madden Export API (Fallback)",
            value=madden_status,
            inline=False
        )
        
        embed.set_footer(text="Snallabot is checked first, Madden Export is used as fallback")
        await interaction.followup.send(embed=embed)
    
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
                "1. Import current standings (Snallabot first, then Madden Export)\n"
                "2. Generate all playoff payments based on seedings and results\n"
                "3. Post payment summary to #payouts\n\n"
                "Type `AUTOPAY` in the confirm field to proceed.",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(thinking=True)
        
        results = []
        
        # Step 1: Import standings (Snallabot first, then Madden Export)
        standings_result = await self.fetch_standings(interaction.guild.id)
        
        if not standings_result:
            await interaction.followup.send(
                "❌ Could not fetch standings from any source.\n"
                "• Snallabot: Check `/setsnallabotconfig`\n"
                "• Madden Export: Export standings from Madden Companion App\n"
            )
            return
        
        source = standings_result['source']
        standings = standings_result['data']
        results.append(f"✅ Fetched standings from **{source.replace('_', ' ').title()}**")
        
        # Process standings based on source format
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        imported_count = 0
        
        if source == 'snallabot':
            # Snallabot format: standings grouped by conference
            for conf_data in standings.get('standingsInfoList', []):
                conf = 'AFC' if conf_data.get('confId') == 0 else 'NFC'
                for team_data in conf_data.get('teams', []):
                    team_id = team_data.get('teamId')
                    team_abbr = TEAM_ID_MAP.get(team_id, f"TEAM{team_id}")
                    seed = team_data.get('seed', 0)
                    
                    if seed > 0:
                        cursor.execute('''
                            INSERT OR REPLACE INTO season_standings 
                            (season, conference, seed, team_id, user_discord_id)
                            VALUES (?, ?, ?, ?, ?)
                        ''', (season, conf, seed, team_abbr, self.get_team_owner(team_abbr)))
                        imported_count += 1
        else:
            # Madden Export format
            if "leagueTeamInfoList" not in standings:
                await interaction.followup.send(
                    "❌ Invalid standings data format from Madden Export API."
                )
                conn.close()
                return
            
            teams = standings["leagueTeamInfoList"]
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
                f"✅ Imported {imported_count} playoff seedings for Season {season} from **{source.replace('_', ' ').title()}**.\n\n"
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
        
        # Step 3: Generate payments (same logic as before)
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
        
        payments_created = 0
        
        # Generate payments for each NFC payer (seeds 8-16)
        for nfc_seed, payer_info in NFC_PAYER_STRUCTURE.items():
            if nfc_seed not in nfc_seedings:
                continue
            
            payer = nfc_seedings[nfc_seed]
            if not payer['user']:
                continue
            
            round_name = payer_info['round']
            amount = payer_info['amount']
            
            # Find winners for this round
            round_winners = winners_by_round.get(round_name, [])
            
            for winner in round_winners:
                if not winner['user']:
                    continue
                
                # Calculate payout per winner
                num_winners = len(round_winners)
                payout_per_winner = amount // num_winners
                
                # Check if payment already exists
                cursor.execute('''
                    SELECT id FROM payments 
                    WHERE from_user_id = ? AND to_user_id = ? AND season = ? AND reason LIKE ?
                ''', (payer['user'], winner['user'], season, f'%{round_name}%'))
                
                if not cursor.fetchone():
                    cursor.execute('''
                        INSERT INTO payments (from_user_id, to_user_id, amount, season, reason, is_paid)
                        VALUES (?, ?, ?, ?, ?, 0)
                    ''', (payer['user'], winner['user'], payout_per_winner, season, 
                          f"Playoff {round_name.title()} - NFC Seed {nfc_seed} to {winner['team']}"))
                    payments_created += 1
        
        conn.commit()
        conn.close()
        
        results.append(f"✅ Created {payments_created} payment obligations")
        
        # Send summary
        embed = discord.Embed(
            title=f"🏈 Auto Playoffs - Season {season}",
            description="\n".join(results),
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        embed.add_field(
            name="Data Source",
            value=source.replace('_', ' ').title(),
            inline=True
        )
        embed.set_footer(text="Use /payments schedule to view all obligations")
        
        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(MaddenExportCog(bot))
