"""
Best Ball Fantasy Football Cog
Features:
- Create and manage Best Ball events
- Roster building with autocomplete player search
- Automatic weekly lineup optimization
- PPR scoring based on Madden sim stats (via Snallabot)
- Loser-pays-winner payout system (bottom pays top)
- Integration with wager/payment tracking
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
import sqlite3
import json
import asyncio
import logging
from datetime import datetime
from typing import Optional, List, Dict, Tuple
import aiohttp
import re

logger = logging.getLogger('MistressLIV.BestBall')

# Snallabot API base URL
SNALLABOT_API_BASE = "https://snallabot.me"

# Madden team ID to abbreviation mapping
TEAM_ID_TO_ABBR = {
    0: 'CHI', 1: 'CIN', 2: 'BUF', 3: 'DEN', 4: 'CLE', 5: 'TB', 6: 'ARI', 7: 'LAC',
    8: 'KC', 9: 'IND', 10: 'DAL', 11: 'MIA', 12: 'PHI', 13: 'ATL', 14: 'SF', 15: 'NYG',
    16: 'JAX', 17: 'NYJ', 18: 'DET', 19: 'GB', 20: 'CAR', 21: 'NE', 22: 'LV', 23: 'LAR',
    24: 'BAL', 25: 'WAS', 26: 'NO', 27: 'SEA', 28: 'PIT', 29: 'TEN', 30: 'MIN', 31: 'HOU'
}

# Scoring constants (PPR)
SCORING = {
    'passing_yards': 0.04,
    'passing_td': 4,
    'interception': -2,
    'rushing_yards': 0.1,
    'rushing_td': 6,
    'receiving_yards': 0.1,
    'receiving_td': 6,
    'reception': 1,  # PPR
    'two_pt_conversion': 2,
    'fumble_lost': -2,
    # Bonuses
    'bonus_100_rush_yards': 3,
    'bonus_100_rec_yards': 3,
    'bonus_300_pass_yards': 3,
    # DST scoring
    'dst_sack': 1,
    'dst_interception': 2,
    'dst_fumble_recovery': 2,
    'dst_td': 6,
    'dst_safety': 2,
    'dst_points_allowed_0': 10,
    'dst_points_allowed_1_6': 7,
    'dst_points_allowed_7_13': 4,
    'dst_points_allowed_14_20': 1,
    'dst_points_allowed_21_27': 0,
    'dst_points_allowed_28_34': -1,
    'dst_points_allowed_35_plus': -4,
}

# Roster requirements
ROSTER_SIZE = 20
MIN_ROSTER = {
    'QB': 1,
    'RB': 2,
    'WR': 3,
    'TE': 1,
    'DST': 0
}
MAX_ROSTER = {
    'QB': 2,
    'RB': 6,
    'WR': 7,
    'TE': 3,
    'DST': 2
}

# Starting lineup
STARTING_LINEUP = {
    'QB': 1,
    'RB': 2,
    'WR': 3,
    'TE': 1,
    'FLEX': 2,  # RB/WR/TE
    'DST': 1
}


class BestBallCog(commands.Cog):
    """Cog for Best Ball fantasy football management."""
    
    def __init__(self, bot):
        self.bot = bot
        self.db_path = bot.db_path
        self._ensure_tables()
        self.player_cache = []  # Cache of players for autocomplete
        self.player_cache_time = None
        
    def cog_load(self):
        """Start the weekly scoring task when cog loads."""
        self.weekly_scoring_task.start()
        self.refresh_player_cache.start()
        
    def cog_unload(self):
        """Stop tasks when cog unloads."""
        self.weekly_scoring_task.cancel()
        self.refresh_player_cache.cancel()
        
    def get_db_connection(self):
        """Get a database connection."""
        return sqlite3.connect(self.db_path)
    
    def _ensure_tables(self):
        """Create all required tables for Best Ball."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Best Ball Events table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bestball_events (
                event_id TEXT PRIMARY KEY,
                event_name TEXT,
                creator_id INTEGER NOT NULL,
                entry_fee REAL DEFAULT 0,
                duration_weeks INTEGER DEFAULT 17,
                status TEXT DEFAULT 'open',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                closed_at TEXT,
                season INTEGER,
                current_week INTEGER DEFAULT 0,
                start_week INTEGER DEFAULT 1
            )
        ''')
        
        # Participants table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bestball_participants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                joined_at TEXT DEFAULT CURRENT_TIMESTAMP,
                total_points REAL DEFAULT 0,
                total_bench_points REAL DEFAULT 0,
                total_tds INTEGER DEFAULT 0,
                final_rank INTEGER,
                FOREIGN KEY (event_id) REFERENCES bestball_events(event_id),
                UNIQUE(event_id, user_id)
            )
        ''')
        
        # Rosters table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bestball_rosters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                player_id TEXT NOT NULL,
                player_name TEXT NOT NULL,
                position TEXT NOT NULL,
                team TEXT,
                added_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (event_id) REFERENCES bestball_events(event_id),
                UNIQUE(event_id, user_id, player_id)
            )
        ''')
        
        # Weekly scores table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bestball_weekly_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                week INTEGER NOT NULL,
                player_id TEXT NOT NULL,
                points REAL DEFAULT 0,
                is_starter INTEGER DEFAULT 0,
                lineup_position TEXT,
                stats_json TEXT,
                FOREIGN KEY (event_id) REFERENCES bestball_events(event_id),
                UNIQUE(event_id, user_id, week, player_id)
            )
        ''')
        
        # Best Ball payments table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bestball_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL,
                payer_id INTEGER NOT NULL,
                payee_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                payer_rank INTEGER,
                payee_rank INTEGER,
                is_paid INTEGER DEFAULT 0,
                paid_date TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (event_id) REFERENCES bestball_events(event_id)
            )
        ''')
        
        # Player cache table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bestball_player_cache (
                player_id TEXT PRIMARY KEY,
                first_name TEXT,
                last_name TEXT,
                position TEXT,
                team_id INTEGER,
                team_abbr TEXT,
                overall INTEGER,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("Best Ball tables initialized")
    
    async def _get_snallabot_config(self, guild_id: int = None) -> Optional[Dict]:
        """Get Snallabot config using the new league_config system."""
        # Try to get config from the new LeagueConfigCog
        league_config_cog = self.bot.get_cog('LeagueConfigCog')
        if league_config_cog and guild_id:
            config = league_config_cog.get_league_config(guild_id)
            if config:
                return config
        
        # Fallback to legacy snallabot_config table or defaults
        conn = self.get_db_connection()
        cursor = conn.cursor()
        if guild_id:
            cursor.execute('SELECT league_id, platform, current_season FROM snallabot_config WHERE guild_id = ?', (guild_id,))
        else:
            cursor.execute('SELECT league_id, platform, current_season FROM snallabot_config LIMIT 1')
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return {'league_id': result[0], 'platform': result[1], 'current_season': result[2]}
        return {'league_id': 'liv', 'platform': 'luna', 'current_season': 2026}
    
    async def _fetch_player_stats(self, platform: str, league_id: str, week: int) -> Optional[List]:
        """Fetch weekly player stats from Snallabot API."""
        url = f"{SNALLABOT_API_BASE}/{platform}/{league_id}/{week}/reg/weeklystats"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=30) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data
                    else:
                        logger.warning(f"Snallabot API returned {response.status} for weekly stats")
                        return None
        except Exception as e:
            logger.error(f"Error fetching weekly stats: {e}")
            return None
    
    async def _fetch_rosters(self, platform: str, league_id: str) -> Optional[List]:
        """Fetch all rosters/players from Snallabot API."""
        url = f"{SNALLABOT_API_BASE}/{platform}/{league_id}/rosters"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=30) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data
                    else:
                        logger.warning(f"Snallabot API returned {response.status} for rosters")
                        return None
        except Exception as e:
            logger.error(f"Error fetching rosters: {e}")
            return None
    
    @tasks.loop(hours=6)
    async def refresh_player_cache(self):
        """Refresh the player cache from Snallabot for all configured guilds."""
        try:
            # Get config from first available guild (player data is shared)
            config = None
            for guild in self.bot.guilds:
                config = await self._get_snallabot_config(guild.id)
                if config and config.get('league_id'):
                    break
            
            if not config:
                logger.warning("No league configuration found for player cache refresh")
                return
            
            rosters = await self._fetch_rosters(config['platform'], config['league_id'])
            if not rosters:
                return
            
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            self.player_cache = []
            
            for player in rosters:
                player_id = str(player.get('rosterId', player.get('playerId', '')))
                first_name = player.get('firstName', '')
                last_name = player.get('lastName', '')
                position = player.get('position', 'UNK')
                team_id = player.get('teamId', 0)
                team_abbr = TEAM_ID_TO_ABBR.get(team_id, 'FA')
                overall = player.get('playerBestOvr', player.get('overall', 0))
                
                # Update cache table
                cursor.execute('''
                    INSERT OR REPLACE INTO bestball_player_cache 
                    (player_id, first_name, last_name, position, team_id, team_abbr, overall, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (player_id, first_name, last_name, position, team_id, team_abbr, overall, datetime.now().isoformat()))
                
                # Add to memory cache
                self.player_cache.append({
                    'id': player_id,
                    'name': f"{first_name} {last_name}".strip(),
                    'position': position,
                    'team': team_abbr,
                    'overall': overall
                })
            
            conn.commit()
            conn.close()
            self.player_cache_time = datetime.now()
            logger.info(f"Refreshed player cache with {len(self.player_cache)} players")
            
        except Exception as e:
            logger.error(f"Error refreshing player cache: {e}")
    
    @refresh_player_cache.before_loop
    async def before_refresh_cache(self):
        """Wait for bot to be ready before starting cache refresh."""
        await self.bot.wait_until_ready()
    
    @tasks.loop(hours=24)
    async def weekly_scoring_task(self):
        """Check for and process weekly scores for active Best Ball events."""
        try:
            config = await self._get_snallabot_config()
            if not config:
                return
            
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            # Get active events
            cursor.execute('''
                SELECT event_id, current_week, duration_weeks, start_week
                FROM bestball_events
                WHERE status = 'active'
            ''')
            active_events = cursor.fetchall()
            
            for event_id, current_week, duration_weeks, start_week in active_events:
                # Calculate the Madden week to check
                madden_week = (start_week or 1) + current_week
                
                if current_week >= duration_weeks:
                    # Event is complete
                    continue
                
                # Fetch stats for this week
                stats = await self._fetch_player_stats(config['platform'], config['league_id'], madden_week)
                if not stats:
                    continue
                
                # Process scores for each participant
                await self._process_weekly_scores(event_id, current_week + 1, stats)
                
                # Update current week
                cursor.execute('''
                    UPDATE bestball_events SET current_week = ? WHERE event_id = ?
                ''', (current_week + 1, event_id))
                
                # Check if event is now complete
                if current_week + 1 >= duration_weeks:
                    cursor.execute('''
                        UPDATE bestball_events SET status = 'completed' WHERE event_id = ?
                    ''', (event_id,))
                    
                    # Generate payments
                    self._generate_payments(event_id)
                    
                    # Notify in best-ball channel
                    for guild in self.bot.guilds:
                        channel = discord.utils.get(guild.channels, name='best-ball')
                        if channel:
                            await channel.send(
                                f"🏆 **Best Ball Event `{event_id}` Complete!**\n"
                                f"Use `/bestballstatus {event_id}` to see final standings and payments!"
                            )
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error in weekly scoring task: {e}")
    
    @weekly_scoring_task.before_loop
    async def before_weekly_scoring(self):
        """Wait for bot to be ready before starting scoring task."""
        await self.bot.wait_until_ready()
    
    async def _process_weekly_scores(self, event_id: str, week: int, stats: List):
        """Process weekly stats and calculate fantasy points for all participants."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Get all participants and their rosters
        cursor.execute('''
            SELECT DISTINCT user_id FROM bestball_participants WHERE event_id = ?
        ''', (event_id,))
        participants = cursor.fetchall()
        
        # Build stats lookup by player ID
        stats_by_player = {}
        for stat in stats:
            player_id = str(stat.get('rosterId', stat.get('playerId', '')))
            stats_by_player[player_id] = stat
        
        for (user_id,) in participants:
            # Get user's roster
            cursor.execute('''
                SELECT player_id, player_name, position
                FROM bestball_rosters
                WHERE event_id = ? AND user_id = ?
            ''', (event_id, user_id))
            roster = cursor.fetchall()
            
            roster_scores = []
            
            for player_id, player_name, position in roster:
                player_stats = stats_by_player.get(player_id, {})
                points = self._calculate_player_score(player_stats, position)
                
                roster_scores.append({
                    'player_id': player_id,
                    'player_name': player_name,
                    'position': position,
                    'points': points,
                    'stats': player_stats
                })
            
            # Optimize lineup
            starters, bench = self._optimize_lineup(roster_scores)
            
            # Calculate totals
            starter_points = sum(p['points'] for p in starters)
            bench_points = sum(p['points'] for p in bench)
            total_tds = sum(
                p['stats'].get('rushTDs', 0) + p['stats'].get('recTDs', 0) + p['stats'].get('passTDs', 0)
                for p in roster_scores
            )
            
            # Save weekly scores
            for player in starters:
                cursor.execute('''
                    INSERT OR REPLACE INTO bestball_weekly_scores
                    (event_id, user_id, week, player_id, points, is_starter, lineup_position, stats_json)
                    VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                ''', (event_id, user_id, week, player['player_id'], player['points'],
                      player.get('lineup_position', ''), json.dumps(player['stats'])))
            
            for player in bench:
                cursor.execute('''
                    INSERT OR REPLACE INTO bestball_weekly_scores
                    (event_id, user_id, week, player_id, points, is_starter, lineup_position, stats_json)
                    VALUES (?, ?, ?, ?, ?, 0, 'BENCH', ?)
                ''', (event_id, user_id, week, player['player_id'], player['points'], json.dumps(player['stats'])))
            
            # Update participant totals
            cursor.execute('''
                UPDATE bestball_participants
                SET total_points = total_points + ?,
                    total_bench_points = total_bench_points + ?,
                    total_tds = total_tds + ?
                WHERE event_id = ? AND user_id = ?
            ''', (starter_points, bench_points, total_tds, event_id, user_id))
        
        conn.commit()
        conn.close()
    
    def _calculate_player_score(self, stats: Dict, position: str) -> float:
        """Calculate fantasy points for a player based on their stats."""
        points = 0.0
        
        if position == 'DST':
            # DST scoring
            points += stats.get('defSacks', 0) * SCORING['dst_sack']
            points += stats.get('defInts', 0) * SCORING['dst_interception']
            points += stats.get('defForcedFum', 0) * SCORING['dst_fumble_recovery']
            points += stats.get('defTDs', 0) * SCORING['dst_td']
            points += stats.get('defSafeties', 0) * SCORING['dst_safety']
            
            # Points allowed scoring
            pts_allowed = stats.get('defPtsPerGame', stats.get('ptsAllowed', 0))
            if pts_allowed == 0:
                points += SCORING['dst_points_allowed_0']
            elif pts_allowed <= 6:
                points += SCORING['dst_points_allowed_1_6']
            elif pts_allowed <= 13:
                points += SCORING['dst_points_allowed_7_13']
            elif pts_allowed <= 20:
                points += SCORING['dst_points_allowed_14_20']
            elif pts_allowed <= 27:
                points += SCORING['dst_points_allowed_21_27']
            elif pts_allowed <= 34:
                points += SCORING['dst_points_allowed_28_34']
            else:
                points += SCORING['dst_points_allowed_35_plus']
        else:
            # Offensive player scoring
            # Passing
            pass_yds = stats.get('passYds', 0)
            points += pass_yds * SCORING['passing_yards']
            points += stats.get('passTDs', 0) * SCORING['passing_td']
            points += stats.get('passInts', 0) * SCORING['interception']
            
            # Rushing
            rush_yds = stats.get('rushYds', 0)
            points += rush_yds * SCORING['rushing_yards']
            points += stats.get('rushTDs', 0) * SCORING['rushing_td']
            
            # Receiving
            rec_yds = stats.get('recYds', 0)
            points += rec_yds * SCORING['receiving_yards']
            points += stats.get('recTDs', 0) * SCORING['receiving_td']
            points += stats.get('recCatches', stats.get('receptions', 0)) * SCORING['reception']
            
            # Fumbles
            points += stats.get('fumLost', 0) * SCORING['fumble_lost']
            
            # Bonuses
            if rush_yds >= 100:
                points += SCORING['bonus_100_rush_yards']
            if rec_yds >= 100:
                points += SCORING['bonus_100_rec_yards']
            if pass_yds >= 300:
                points += SCORING['bonus_300_pass_yards']
        
        return round(points, 2)
    
    def _optimize_lineup(self, roster_scores: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
        """
        Optimize lineup by selecting best players for each position.
        Returns (starters, bench)
        """
        # Group by position
        by_position = {'QB': [], 'RB': [], 'WR': [], 'TE': [], 'DST': []}
        for player in roster_scores:
            pos = player['position'].upper()
            if pos in by_position:
                by_position[pos].append(player)
            elif pos in ['HB', 'FB']:
                by_position['RB'].append(player)
        
        # Sort each position by points
        for pos in by_position:
            by_position[pos].sort(key=lambda x: x['points'], reverse=True)
        
        starters = []
        used_players = set()
        
        # Fill required positions
        for pos, count in [('QB', 1), ('RB', 2), ('WR', 3), ('TE', 1), ('DST', 1)]:
            for i in range(count):
                if by_position[pos]:
                    player = by_position[pos].pop(0)
                    player['lineup_position'] = pos
                    starters.append(player)
                    used_players.add(player['player_id'])
        
        # Fill FLEX spots (best remaining RB/WR/TE)
        flex_pool = by_position['RB'] + by_position['WR'] + by_position['TE']
        flex_pool.sort(key=lambda x: x['points'], reverse=True)
        
        for i in range(2):  # 2 FLEX spots
            if flex_pool:
                player = flex_pool.pop(0)
                player['lineup_position'] = 'FLEX'
                starters.append(player)
                used_players.add(player['player_id'])
        
        # Remaining players are bench
        bench = [p for p in roster_scores if p['player_id'] not in used_players]
        
        return starters, bench
    
    def _generate_payments(self, event_id: str) -> List[Dict]:
        """
        Generate loser-pays-winner payments for a completed event.
        Bottom finisher pays top finisher, 2nd bottom pays 2nd place, etc.
        """
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Get event info
        cursor.execute('SELECT entry_fee FROM bestball_events WHERE event_id = ?', (event_id,))
        result = cursor.fetchone()
        if not result:
            conn.close()
            return []
        
        entry_fee = result[0]
        
        # Get final rankings
        cursor.execute('''
            SELECT user_id, total_points, total_bench_points, total_tds
            FROM bestball_participants
            WHERE event_id = ?
            ORDER BY total_points DESC, total_bench_points DESC, total_tds DESC
        ''', (event_id,))
        rankings = cursor.fetchall()
        
        if len(rankings) < 2:
            conn.close()
            return []
        
        # Update final ranks
        for rank, (user_id, _, _, _) in enumerate(rankings, 1):
            cursor.execute('''
                UPDATE bestball_participants 
                SET final_rank = ? 
                WHERE event_id = ? AND user_id = ?
            ''', (rank, event_id, user_id))
        
        # Generate payments: bottom half pays top half
        payments = []
        num_participants = len(rankings)
        num_payers = num_participants // 2
        
        for i in range(num_payers):
            winner_rank = i + 1
            loser_rank = num_participants - i
            
            winner_id = rankings[winner_rank - 1][0]
            loser_id = rankings[loser_rank - 1][0]
            
            # Insert payment record
            cursor.execute('''
                INSERT INTO bestball_payments 
                (event_id, payer_id, payee_id, amount, payer_rank, payee_rank)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (event_id, loser_id, winner_id, entry_fee, loser_rank, winner_rank))
            
            payments.append({
                'payer_id': loser_id,
                'payee_id': winner_id,
                'amount': entry_fee,
                'payer_rank': loser_rank,
                'payee_rank': winner_rank
            })
        
        conn.commit()
        conn.close()
        
        return payments
    
    def _get_roster_status(self, event_id: str, user_id: int) -> Dict:
        """Get current roster status including counts by position."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT position, COUNT(*) 
            FROM bestball_rosters
            WHERE event_id = ? AND user_id = ?
            GROUP BY position
        ''', (event_id, user_id))
        
        position_counts = dict(cursor.fetchall())
        conn.close()
        
        total = sum(position_counts.values())
        remaining = ROSTER_SIZE - total
        
        # Calculate what's still needed
        needs = {}
        for pos, min_count in MIN_ROSTER.items():
            current = position_counts.get(pos, 0)
            if current < min_count:
                needs[pos] = min_count - current
        
        # Calculate what's still available
        available = {}
        for pos, max_count in MAX_ROSTER.items():
            current = position_counts.get(pos, 0)
            if current < max_count:
                available[pos] = max_count - current
        
        return {
            'total': total,
            'remaining': remaining,
            'by_position': position_counts,
            'needs': needs,
            'available': available
        }
    
    def _generate_event_id(self, season: int = None) -> str:
        """Generate a unique event ID."""
        if season is None:
            season = datetime.now().year
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) FROM bestball_events 
            WHERE event_id LIKE ?
        ''', (f'BB-SZN{season}-%',))
        count = cursor.fetchone()[0]
        conn.close()
        
        return f"BB-SZN{season}-{count + 1:03d}"
    
    # ==================== AUTOCOMPLETE ====================
    
    async def player_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> List[app_commands.Choice[str]]:
        """Autocomplete for player names."""
        if not self.player_cache:
            # Load from database if memory cache is empty
            conn = self.get_db_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT player_id, first_name, last_name, position, team_abbr, overall
                FROM bestball_player_cache
                ORDER BY overall DESC
                LIMIT 500
            ''')
            rows = cursor.fetchall()
            conn.close()
            
            self.player_cache = [
                {
                    'id': row[0],
                    'name': f"{row[1]} {row[2]}".strip(),
                    'position': row[3],
                    'team': row[4],
                    'overall': row[5]
                }
                for row in rows
            ]
        
        if not current:
            # Return top players by overall
            return [
                app_commands.Choice(
                    name=f"{p['name']} ({p['position']} - {p['team']})",
                    value=p['id']
                )
                for p in self.player_cache[:25]
            ]
        
        # Filter by search term
        current_lower = current.lower()
        matches = [
            p for p in self.player_cache
            if current_lower in p['name'].lower()
        ]
        
        # Sort by relevance (starts with > contains) then by overall
        matches.sort(key=lambda p: (
            not p['name'].lower().startswith(current_lower),
            -p['overall']
        ))
        
        return [
            app_commands.Choice(
                name=f"{p['name']} ({p['position']} - {p['team']})",
                value=p['id']
            )
            for p in matches[:25]
        ]
    
    async def event_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> List[app_commands.Choice[str]]:
        """Autocomplete for event selection - shows creator name and event details."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT event_id, event_name, creator_id, entry_fee, status,
                   (SELECT COUNT(*) FROM bestball_participants WHERE event_id = e.event_id) as participants
            FROM bestball_events e
            ORDER BY created_at DESC
            LIMIT 25
        ''')
        events = cursor.fetchall()
        conn.close()
        
        choices = []
        for event_id, event_name, creator_id, entry_fee, status, participants in events:
            # Get creator name
            member = interaction.guild.get_member(creator_id)
            creator_name = member.display_name if member else f"User {creator_id}"
            
            # Build display name
            display_name = event_name or event_id
            label = f"{display_name} by {creator_name} (${entry_fee:.0f}, {participants} players, {status})"
            
            # Filter by current search
            if current and current.lower() not in label.lower():
                continue
            
            choices.append(app_commands.Choice(name=label[:100], value=event_id))
        
        return choices[:25]
    
    # ==================== COMMANDS ====================
    
    @app_commands.command(name="startbestball", description="Start a new Best Ball event")
    @app_commands.describe(
        event_name="Name for this event (e.g., 'Season 5 Best Ball')",
        entry_fee="Entry fee amount (default: $50)",
        duration_weeks="Number of weeks to run (default: 17)",
        start_week="Madden week to start scoring from (default: 1)"
    )
    async def start_best_ball(
        self,
        interaction: discord.Interaction,
        event_name: Optional[str] = None,
        entry_fee: Optional[float] = 50.0,
        duration_weeks: Optional[int] = 17,
        start_week: Optional[int] = 1
    ):
        """Create a new Best Ball event."""
        await interaction.response.defer()
        
        event_id = self._generate_event_id()
        if not event_name:
            event_name = f"{interaction.user.display_name}'s Best Ball"
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO bestball_events 
            (event_id, event_name, creator_id, entry_fee, duration_weeks, status, season, start_week)
            VALUES (?, ?, ?, ?, ?, 'open', ?, ?)
        ''', (event_id, event_name, interaction.user.id, entry_fee, duration_weeks, datetime.now().year, start_week))
        
        conn.commit()
        conn.close()
        
        embed = discord.Embed(
            title="🏈 New Best Ball Event Started!",
            description=f"**{event_name}**\n`{event_id}`",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        
        embed.add_field(name="💰 Entry Fee", value=f"${entry_fee:.2f}", inline=True)
        embed.add_field(name="📅 Duration", value=f"{duration_weeks} weeks", inline=True)
        embed.add_field(name="🏁 Start Week", value=f"Week {start_week}", inline=True)
        
        embed.add_field(
            name="📋 How to Join",
            value=f"Use `/joinbestball` and select this event!\n1 entry per person.",
            inline=False
        )
        
        embed.add_field(
            name="💸 Payout Structure",
            value=(
                "**Losers pay Winners (bottom-up):**\n"
                "• Last place pays 1st place\n"
                "• 2nd to last pays 2nd place\n"
                "• And so on...\n"
                f"Each loser pays ${entry_fee:.2f} to their paired winner"
            ),
            inline=False
        )
        
        embed.set_footer(text=f"Created by {interaction.user.display_name}")
        
        await interaction.followup.send(embed=embed)
        
        # Also post to #best-ball channel if it exists
        best_ball_channel = discord.utils.get(interaction.guild.channels, name='best-ball')
        if best_ball_channel:
            await best_ball_channel.send(
                f"@everyone New Best Ball event started by {interaction.user.mention}!",
                embed=embed
            )
    
    @app_commands.command(name="joinbestball", description="Join a Best Ball event")
    @app_commands.describe(event="Select the event to join")
    @app_commands.autocomplete(event=event_autocomplete)
    async def join_best_ball(self, interaction: discord.Interaction, event: str):
        """Join an existing Best Ball event."""
        # Check if user is a welcher
        welcher_cog = self.bot.get_cog('WelcherCog')
        if welcher_cog and await welcher_cog.is_welcher(str(interaction.guild_id), str(interaction.user.id)):
            await interaction.response.send_message(
                "🚫 You are currently banned from Best Ball events due to unpaid debts. Contact an admin to resolve.",
                ephemeral=True
            )
            return
        
        event_id = event  # The autocomplete returns the event_id as value
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Check event exists and is open
        cursor.execute('''
            SELECT status, entry_fee, event_name FROM bestball_events WHERE event_id = ?
        ''', (event_id,))
        result = cursor.fetchone()
        
        if not result:
            await interaction.response.send_message(
                f"❌ Event not found.", ephemeral=True
            )
            conn.close()
            return
        
        status, entry_fee, event_name = result
        
        if status != 'open':
            await interaction.response.send_message(
                f"❌ This event is no longer accepting participants (Status: {status}).",
                ephemeral=True
            )
            conn.close()
            return
        
        # Check if already joined
        cursor.execute('''
            SELECT id FROM bestball_participants 
            WHERE event_id = ? AND user_id = ?
        ''', (event_id, interaction.user.id))
        
        if cursor.fetchone():
            await interaction.response.send_message(
                "❌ You already have an entry in this event.", ephemeral=True
            )
            conn.close()
            return
        
        # Add participant
        cursor.execute('''
            INSERT INTO bestball_participants (event_id, user_id)
            VALUES (?, ?)
        ''', (event_id, interaction.user.id))
        
        conn.commit()
        conn.close()
        
        embed = discord.Embed(
            title="✅ Joined Best Ball Event!",
            description=f"**{event_name}**",
            color=discord.Color.green()
        )
        
        embed.add_field(name="💰 Entry Fee", value=f"${entry_fee:.2f}", inline=True)
        embed.add_field(
            name="📋 Next Step",
            value=f"Build your roster with `/selectyourteam`",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="selectyourteam", description="Build your Best Ball roster")
    @app_commands.describe(event="Select the event to build roster for")
    @app_commands.autocomplete(event=event_autocomplete)
    async def select_your_team(self, interaction: discord.Interaction, event: str):
        """Interactive roster building with progress tracking."""
        event_id = event
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Verify participation
        cursor.execute('''
            SELECT p.id, e.status, e.event_name FROM bestball_participants p
            JOIN bestball_events e ON p.event_id = e.event_id
            WHERE p.event_id = ? AND p.user_id = ?
        ''', (event_id, interaction.user.id))
        result = cursor.fetchone()
        
        if not result:
            await interaction.response.send_message(
                f"❌ You haven't joined this event. Use `/joinbestball` first.",
                ephemeral=True
            )
            conn.close()
            return
        
        _, status, event_name = result
        if status != 'open':
            await interaction.response.send_message(
                "❌ This event is closed. Rosters can no longer be modified.",
                ephemeral=True
            )
            conn.close()
            return
        
        conn.close()
        
        # Get roster status
        roster_status = self._get_roster_status(event_id, interaction.user.id)
        
        if roster_status['total'] >= ROSTER_SIZE:
            await interaction.response.send_message(
                f"✅ Your roster is complete ({roster_status['total']}/{ROSTER_SIZE} players).\n"
                f"Use `/reviewbestballroster` to view it.",
                ephemeral=True
            )
            return
        
        # Build status embed
        embed = discord.Embed(
            title=f"🏈 Build Your Roster: {event_name}",
            description=f"**Progress:** {roster_status['total']}/{ROSTER_SIZE} players ({roster_status['remaining']} remaining)",
            color=discord.Color.blue()
        )
        
        # Current roster by position
        pos_status = []
        for pos in ['QB', 'RB', 'WR', 'TE', 'DST']:
            current = roster_status['by_position'].get(pos, 0)
            min_req = MIN_ROSTER.get(pos, 0)
            max_req = MAX_ROSTER.get(pos, 0)
            
            if current < min_req:
                status_emoji = "❌"
            elif current >= max_req:
                status_emoji = "✅"
            else:
                status_emoji = "⚠️"
            
            pos_status.append(f"{status_emoji} **{pos}:** {current}/{max_req} (min: {min_req})")
        
        embed.add_field(
            name="📊 Roster Status",
            value="\n".join(pos_status),
            inline=False
        )
        
        # What's still needed
        if roster_status['needs']:
            needs_text = ", ".join([f"{count} {pos}" for pos, count in roster_status['needs'].items()])
            embed.add_field(
                name="⚠️ Still Need",
                value=needs_text,
                inline=False
            )
        
        embed.add_field(
            name="🔍 Add Players",
            value="Use `/addplayer` and start typing a player name to search!",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="addplayer", description="Add a player to your Best Ball roster")
    @app_commands.describe(
        event="Select the event",
        player="Search for a player by name"
    )
    @app_commands.autocomplete(event=event_autocomplete, player=player_autocomplete)
    async def add_player(
        self,
        interaction: discord.Interaction,
        event: str,
        player: str
    ):
        """Add a player to roster with autocomplete search."""
        event_id = event
        player_id = player  # This is the player ID from autocomplete
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Verify participation and event status
        cursor.execute('''
            SELECT e.status, e.event_name FROM bestball_participants p
            JOIN bestball_events e ON p.event_id = e.event_id
            WHERE p.event_id = ? AND p.user_id = ?
        ''', (event_id, interaction.user.id))
        result = cursor.fetchone()
        
        if not result:
            await interaction.response.send_message(
                f"❌ You haven't joined this event.",
                ephemeral=True
            )
            conn.close()
            return
        
        status, event_name = result
        if status != 'open':
            await interaction.response.send_message(
                "❌ This event is closed. Rosters cannot be modified.",
                ephemeral=True
            )
            conn.close()
            return
        
        # Get player info from cache
        cursor.execute('''
            SELECT player_id, first_name, last_name, position, team_abbr, overall
            FROM bestball_player_cache WHERE player_id = ?
        ''', (player_id,))
        player_data = cursor.fetchone()
        
        if not player_data:
            await interaction.response.send_message(
                "❌ Player not found. Try refreshing the player list.",
                ephemeral=True
            )
            conn.close()
            return
        
        player_id, first_name, last_name, position, team_abbr, overall = player_data
        player_name = f"{first_name} {last_name}".strip()
        
        # Check roster limits
        roster_status = self._get_roster_status(event_id, interaction.user.id)
        
        if roster_status['total'] >= ROSTER_SIZE:
            await interaction.response.send_message(
                f"❌ Your roster is full ({ROSTER_SIZE} players).",
                ephemeral=True
            )
            conn.close()
            return
        
        pos_upper = position.upper()
        if pos_upper in ['HB', 'FB']:
            pos_upper = 'RB'
        
        if pos_upper in MAX_ROSTER:
            current_count = roster_status['by_position'].get(pos_upper, 0)
            if current_count >= MAX_ROSTER[pos_upper]:
                await interaction.response.send_message(
                    f"❌ You already have {current_count} {pos_upper}s (max: {MAX_ROSTER[pos_upper]}).",
                    ephemeral=True
                )
                conn.close()
                return
        
        # Check if player already on roster
        cursor.execute('''
            SELECT id FROM bestball_rosters
            WHERE event_id = ? AND user_id = ? AND player_id = ?
        ''', (event_id, interaction.user.id, player_id))
        
        if cursor.fetchone():
            await interaction.response.send_message(
                f"❌ {player_name} is already on your roster.",
                ephemeral=True
            )
            conn.close()
            return
        
        # Add player
        cursor.execute('''
            INSERT INTO bestball_rosters 
            (event_id, user_id, player_id, player_name, position, team)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (event_id, interaction.user.id, player_id, player_name, pos_upper, team_abbr))
        
        conn.commit()
        conn.close()
        
        # Get updated roster status
        new_status = self._get_roster_status(event_id, interaction.user.id)
        
        embed = discord.Embed(
            title="✅ Player Added!",
            description=f"**{player_name}** ({pos_upper} - {team_abbr})",
            color=discord.Color.green()
        )
        
        embed.add_field(
            name="📊 Roster Progress",
            value=f"{new_status['total']}/{ROSTER_SIZE} players ({new_status['remaining']} remaining)",
            inline=False
        )
        
        if new_status['needs']:
            needs_text = ", ".join([f"{count} {pos}" for pos, count in new_status['needs'].items()])
            embed.add_field(name="⚠️ Still Need", value=needs_text, inline=False)
        elif new_status['remaining'] == 0:
            embed.add_field(name="🎉 Roster Complete!", value="Your roster is ready!", inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="removeplayer", description="Remove a player from your Best Ball roster")
    @app_commands.describe(
        event="Select the event",
        player_name="Name of player to remove"
    )
    @app_commands.autocomplete(event=event_autocomplete)
    async def remove_player(
        self,
        interaction: discord.Interaction,
        event: str,
        player_name: str
    ):
        """Remove a player from roster."""
        event_id = event
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Verify participation and event status
        cursor.execute('''
            SELECT e.status FROM bestball_participants p
            JOIN bestball_events e ON p.event_id = e.event_id
            WHERE p.event_id = ? AND p.user_id = ?
        ''', (event_id, interaction.user.id))
        result = cursor.fetchone()
        
        if not result or result[0] != 'open':
            await interaction.response.send_message(
                "❌ Cannot modify roster (not joined or event closed).",
                ephemeral=True
            )
            conn.close()
            return
        
        # Find and remove player
        cursor.execute('''
            DELETE FROM bestball_rosters
            WHERE event_id = ? AND user_id = ? AND LOWER(player_name) LIKE ?
        ''', (event_id, interaction.user.id, f"%{player_name.lower()}%"))
        
        if cursor.rowcount > 0:
            conn.commit()
            await interaction.response.send_message(
                f"✅ Removed player matching '{player_name}' from your roster.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"❌ No player found matching '{player_name}' on your roster.",
                ephemeral=True
            )
        
        conn.close()
    
    @app_commands.command(name="reviewbestballroster", description="View a Best Ball roster")
    @app_commands.describe(
        event="Select the event",
        user="User to view (leave blank for your own)"
    )
    @app_commands.autocomplete(event=event_autocomplete)
    async def review_roster(
        self,
        interaction: discord.Interaction,
        event: str,
        user: Optional[discord.Member] = None
    ):
        """View a participant's roster."""
        event_id = event
        target_user = user or interaction.user
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Get event name
        cursor.execute('SELECT event_name FROM bestball_events WHERE event_id = ?', (event_id,))
        event_result = cursor.fetchone()
        event_name = event_result[0] if event_result else event_id
        
        # Get roster
        cursor.execute('''
            SELECT player_name, position, team
            FROM bestball_rosters
            WHERE event_id = ? AND user_id = ?
            ORDER BY 
                CASE position 
                    WHEN 'QB' THEN 1 
                    WHEN 'RB' THEN 2 
                    WHEN 'WR' THEN 3 
                    WHEN 'TE' THEN 4 
                    WHEN 'DST' THEN 5 
                    ELSE 6 
                END,
                player_name
        ''', (event_id, target_user.id))
        roster = cursor.fetchall()
        conn.close()
        
        if not roster:
            await interaction.response.send_message(
                f"❌ No roster found for {target_user.display_name} in this event.",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title=f"🏈 {target_user.display_name}'s Roster",
            description=f"**{event_name}**\n**Players:** {len(roster)}/{ROSTER_SIZE}",
            color=discord.Color.blue()
        )
        
        # Group by position
        by_pos = {}
        for name, pos, team in roster:
            if pos not in by_pos:
                by_pos[pos] = []
            by_pos[pos].append(f"{name} ({team})")
        
        for pos in ['QB', 'RB', 'WR', 'TE', 'DST']:
            if pos in by_pos:
                embed.add_field(
                    name=f"**{pos}** ({len(by_pos[pos])})",
                    value="\n".join(by_pos[pos]),
                    inline=True
                )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="bestballstatus", description="Check Best Ball event status and leaderboard")
    @app_commands.describe(event="Select an event (leave blank for latest)")
    @app_commands.autocomplete(event=event_autocomplete)
    async def best_ball_status(
        self,
        interaction: discord.Interaction,
        event: Optional[str] = None
    ):
        """Show event status and leaderboard."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Get event
        if event:
            cursor.execute('''
                SELECT event_id, event_name, creator_id, entry_fee, duration_weeks, status, current_week
                FROM bestball_events WHERE event_id = ?
            ''', (event,))
        else:
            cursor.execute('''
                SELECT event_id, event_name, creator_id, entry_fee, duration_weeks, status, current_week
                FROM bestball_events 
                ORDER BY created_at DESC LIMIT 1
            ''')
        
        event_data = cursor.fetchone()
        
        if not event_data:
            await interaction.response.send_message(
                "❌ No Best Ball events found.",
                ephemeral=True
            )
            conn.close()
            return
        
        event_id, event_name, creator_id, entry_fee, duration_weeks, status, current_week = event_data
        
        # Get participants
        cursor.execute('''
            SELECT user_id, total_points, total_bench_points
            FROM bestball_participants
            WHERE event_id = ?
            ORDER BY total_points DESC, total_bench_points DESC
            LIMIT 10
        ''', (event_id,))
        participants = cursor.fetchall()
        
        cursor.execute('''
            SELECT COUNT(*) FROM bestball_participants WHERE event_id = ?
        ''', (event_id,))
        total_participants = cursor.fetchone()[0]
        
        conn.close()
        
        creator = interaction.guild.get_member(creator_id)
        creator_name = creator.display_name if creator else "Unknown"
        
        embed = discord.Embed(
            title=f"🏈 {event_name}",
            description=f"`{event_id}`",
            color=discord.Color.gold() if status == 'open' else discord.Color.blue()
        )
        
        embed.add_field(name="👤 Creator", value=creator_name, inline=True)
        embed.add_field(name="💰 Entry Fee", value=f"${entry_fee:.2f}", inline=True)
        embed.add_field(name="📊 Status", value=status.title(), inline=True)
        embed.add_field(name="👥 Participants", value=str(total_participants), inline=True)
        embed.add_field(name="📅 Week", value=f"{current_week}/{duration_weeks}", inline=True)
        embed.add_field(
            name="💸 Total Pot",
            value=f"${entry_fee * total_participants:.2f}",
            inline=True
        )
        
        if participants and current_week > 0:
            leaderboard = []
            for i, (user_id, points, bench_pts) in enumerate(participants[:5], 1):
                member = interaction.guild.get_member(user_id)
                name = member.display_name if member else f"User {user_id}"
                leaderboard.append(f"**{i}.** {name}: {points:.1f} pts")
            
            embed.add_field(
                name="🏆 Top 5 Leaderboard",
                value="\n".join(leaderboard) if leaderboard else "No scores yet",
                inline=False
            )
        
        # Check if user is in event
        for user_id, points, _ in participants:
            if user_id == interaction.user.id:
                embed.add_field(
                    name="📊 Your Score",
                    value=f"{points:.1f} points",
                    inline=False
                )
                break
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="closebestball", description="[Admin] Close a Best Ball event and start scoring")
    @app_commands.describe(event="Select the event to close")
    @app_commands.autocomplete(event=event_autocomplete)
    async def close_best_ball(self, interaction: discord.Interaction, event: str):
        """Close an event and lock rosters."""
        event_id = event
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Check if user is creator or admin
        cursor.execute('''
            SELECT creator_id, status, event_name FROM bestball_events WHERE event_id = ?
        ''', (event_id,))
        result = cursor.fetchone()
        
        if not result:
            await interaction.response.send_message(
                f"❌ Event not found.",
                ephemeral=True
            )
            conn.close()
            return
        
        creator_id, status, event_name = result
        
        if interaction.user.id != creator_id and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Only the event creator or admins can close events.",
                ephemeral=True
            )
            conn.close()
            return
        
        if status != 'open':
            await interaction.response.send_message(
                f"❌ Event is already {status}.",
                ephemeral=True
            )
            conn.close()
            return
        
        # Close event
        cursor.execute('''
            UPDATE bestball_events 
            SET status = 'active', closed_at = ?
            WHERE event_id = ?
        ''', (datetime.now().isoformat(), event_id))
        
        conn.commit()
        conn.close()
        
        await interaction.response.send_message(
            f"✅ **{event_name}** is now closed!\n"
            f"Rosters are locked and automated weekly scoring will begin."
        )
    
    @app_commands.command(name="endbestball", description="[Admin] End a Best Ball event and generate payments")
    @app_commands.describe(event="Select the event to end")
    @app_commands.autocomplete(event=event_autocomplete)
    async def end_best_ball(self, interaction: discord.Interaction, event: str):
        """End an event and generate payment obligations."""
        await interaction.response.defer()
        
        event_id = event
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Check permissions
        cursor.execute('''
            SELECT creator_id, status, entry_fee, event_name FROM bestball_events WHERE event_id = ?
        ''', (event_id,))
        result = cursor.fetchone()
        
        if not result:
            await interaction.followup.send(f"❌ Event not found.")
            conn.close()
            return
        
        creator_id, status, entry_fee, event_name = result
        
        if interaction.user.id != creator_id and not interaction.user.guild_permissions.administrator:
            await interaction.followup.send("❌ Only the event creator or admins can end events.")
            conn.close()
            return
        
        conn.close()
        
        # Generate payments
        payments = self._generate_payments(event_id)
        
        # Update event status
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE bestball_events SET status = 'completed' WHERE event_id = ?
        ''', (event_id,))
        conn.commit()
        conn.close()
        
        embed = discord.Embed(
            title=f"🏆 {event_name} Complete!",
            description="Final standings and payment obligations generated!",
            color=discord.Color.gold()
        )
        
        # Show final standings
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT user_id, total_points, final_rank
            FROM bestball_participants
            WHERE event_id = ?
            ORDER BY final_rank
        ''', (event_id,))
        standings = cursor.fetchall()
        conn.close()
        
        standings_text = []
        for user_id, points, rank in standings[:10]:
            member = interaction.guild.get_member(user_id)
            name = member.display_name if member else f"User {user_id}"
            standings_text.append(f"**{rank}.** {name}: {points:.1f} pts")
        
        embed.add_field(
            name="📊 Final Standings",
            value="\n".join(standings_text) if standings_text else "No participants",
            inline=False
        )
        
        # Show payments
        if payments:
            payment_text = []
            for p in payments[:10]:
                payer = interaction.guild.get_member(p['payer_id'])
                payee = interaction.guild.get_member(p['payee_id'])
                payer_name = payer.display_name if payer else f"User {p['payer_id']}"
                payee_name = payee.display_name if payee else f"User {p['payee_id']}"
                payment_text.append(
                    f"#{p['payer_rank']} {payer_name} → #{p['payee_rank']} {payee_name}: ${p['amount']:.2f}"
                )
            
            embed.add_field(
                name="💸 Payment Obligations (Loser → Winner)",
                value="\n".join(payment_text) if payment_text else "None",
                inline=False
            )
        
        await interaction.followup.send(embed=embed)
        
        # Post to #best-ball channel
        best_ball_channel = discord.utils.get(interaction.guild.channels, name='best-ball')
        if best_ball_channel:
            await best_ball_channel.send(embed=embed)
    
    @app_commands.command(name="cancelbestball", description="[Admin] Cancel a Best Ball event")
    @app_commands.describe(event="Select the event to cancel")
    @app_commands.autocomplete(event=event_autocomplete)
    async def cancel_best_ball(self, interaction: discord.Interaction, event: str):
        """Cancel an event and remove all associated data."""
        event_id = event
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Check if user is creator or admin
        cursor.execute('''
            SELECT creator_id, status, event_name FROM bestball_events WHERE event_id = ?
        ''', (event_id,))
        result = cursor.fetchone()
        
        if not result:
            await interaction.response.send_message(
                f"❌ Event not found.",
                ephemeral=True
            )
            conn.close()
            return
        
        creator_id, status, event_name = result
        
        if interaction.user.id != creator_id and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Only the event creator or admins can cancel events.",
                ephemeral=True
            )
            conn.close()
            return
        
        if status == 'completed':
            await interaction.response.send_message(
                "❌ Cannot cancel a completed event. Payments have already been generated.",
                ephemeral=True
            )
            conn.close()
            return
        
        # Delete all associated data
        cursor.execute('DELETE FROM bestball_weekly_scores WHERE event_id = ?', (event_id,))
        cursor.execute('DELETE FROM bestball_rosters WHERE event_id = ?', (event_id,))
        cursor.execute('DELETE FROM bestball_participants WHERE event_id = ?', (event_id,))
        cursor.execute('DELETE FROM bestball_payments WHERE event_id = ?', (event_id,))
        cursor.execute('DELETE FROM bestball_events WHERE event_id = ?', (event_id,))
        
        conn.commit()
        conn.close()
        
        await interaction.response.send_message(
            f"✅ **{event_name}** has been cancelled and all data removed."
        )
        
        # Notify in best-ball channel
        best_ball_channel = discord.utils.get(interaction.guild.channels, name='best-ball')
        if best_ball_channel:
            await best_ball_channel.send(
                f"⚠️ Best Ball event **{event_name}** has been cancelled by {interaction.user.mention}."
            )
    
    @app_commands.command(name="bestballhelp", description="Show Best Ball rules and commands")
    async def best_ball_help(self, interaction: discord.Interaction):
        """Display help information for Best Ball."""
        embed = discord.Embed(
            title="🏈 Best Ball Fantasy Football",
            description="Low-maintenance fantasy where the bot auto-optimizes your lineup!",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="📋 Overview",
            value=(
                "• Build a 20-player roster at the start\n"
                "• No weekly management - bot picks best lineup\n"
                "• PPR scoring based on Madden sim stats\n"
                "• Highest total points wins!"
            ),
            inline=False
        )
        
        embed.add_field(
            name="👥 Roster Requirements",
            value=(
                f"• **QB:** {MIN_ROSTER['QB']}-{MAX_ROSTER['QB']}\n"
                f"• **RB:** {MIN_ROSTER['RB']}-{MAX_ROSTER['RB']}\n"
                f"• **WR:** {MIN_ROSTER['WR']}-{MAX_ROSTER['WR']}\n"
                f"• **TE:** {MIN_ROSTER['TE']}-{MAX_ROSTER['TE']}\n"
                f"• **DST:** 0-{MAX_ROSTER['DST']}\n"
                f"• **Total:** {ROSTER_SIZE} players"
            ),
            inline=True
        )
        
        embed.add_field(
            name="🎯 Weekly Starters",
            value=(
                "• 1 QB\n"
                "• 2 RB\n"
                "• 3 WR\n"
                "• 1 TE\n"
                "• 2 FLEX (RB/WR/TE)\n"
                "• 1 DST"
            ),
            inline=True
        )
        
        embed.add_field(
            name="📊 Scoring (PPR)",
            value=(
                "**Passing:** 0.04/yd, 4/TD, -2/INT\n"
                "**Rush/Rec:** 0.1/yd, 6/TD, 1/rec\n"
                "**Bonus:** +3 for 100+ rush/rec yd, 300+ pass yd"
            ),
            inline=False
        )
        
        embed.add_field(
            name="💸 Payout Structure",
            value=(
                "**Losers pay Winners (bottom-up):**\n"
                "• Last place pays 1st place\n"
                "• 2nd to last pays 2nd place\n"
                "• And so on..."
            ),
            inline=False
        )
        
        embed.add_field(
            name="🔧 Commands",
            value=(
                "`/startbestball` - Create new event\n"
                "`/joinbestball` - Join an event\n"
                "`/selectyourteam` - Check roster progress\n"
                "`/addplayer` - Add player (autocomplete search!)\n"
                "`/removeplayer` - Remove a player\n"
                "`/reviewbestballroster` - View roster\n"
                "`/bestballstatus` - Check standings\n"
                "`/closebestball` - Lock rosters (admin)\n"
                "`/endbestball` - End event & generate payments\n"
                "`/cancelbestball` - Cancel an event (admin)"
            ),
            inline=False
        )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="bestballrules", description="View detailed Best Ball rules and dynamics")
    async def bestball_rules(self, interaction: discord.Interaction):
        """Display comprehensive Best Ball rules and dynamics."""
        
        # Create multiple embeds for detailed rules
        embeds = []
        
        # Embed 1: Overview
        overview = discord.Embed(
            title="🏈 Best Ball Rules & Dynamics",
            description=(
                "Best Ball is a **set-it-and-forget-it** fantasy football format. "
                "You draft a roster of Madden players, and each week the bot automatically "
                "selects your highest-scoring lineup. No weekly management needed!"
            ),
            color=discord.Color.gold()
        )
        overview.add_field(
            name="📋 How It Works",
            value=(
                "1. **Join an Event** - Pay the entry fee to participate\n"
                "2. **Draft Your Roster** - Select 20 players from the Madden player pool\n"
                "3. **Auto-Optimize** - Each week, the bot picks your best lineup\n"
                "4. **Accumulate Points** - Your weekly scores add up over the event duration\n"
                "5. **Get Paid** - At the end, losers pay winners based on final standings"
            ),
            inline=False
        )
        embeds.append(overview)
        
        # Embed 2: Roster Requirements
        roster = discord.Embed(
            title="👥 Roster Requirements",
            description="Build a 20-player roster with the following position limits:",
            color=discord.Color.blue()
        )
        roster.add_field(
            name="📊 Position Limits",
            value=(
                "**QB:** 1-3 players\n"
                "**RB:** 2-6 players\n"
                "**WR:** 3-7 players\n"
                "**TE:** 1-3 players\n"
                "**K:** 1-2 players\n"
                "**DST:** 1-2 players"
            ),
            inline=True
        )
        roster.add_field(
            name="🎯 Weekly Starting Lineup",
            value=(
                "**1 QB** - Quarterback\n"
                "**2 RB** - Running Backs\n"
                "**3 WR** - Wide Receivers\n"
                "**1 TE** - Tight End\n"
                "**2 FLEX** - RB/WR/TE\n"
                "**1 DST** - Defense/ST"
            ),
            inline=True
        )
        roster.add_field(
            name="💡 Strategy Tip",
            value=(
                "Since the bot auto-selects your best players each week, "
                "draft for **upside and volume**. Target players with high ceilings "
                "who get consistent opportunities in the Madden sim."
            ),
            inline=False
        )
        embeds.append(roster)
        
        # Embed 3: Scoring
        scoring = discord.Embed(
            title="📊 Scoring System (PPR)",
            description="Points Per Reception format with standard fantasy scoring:",
            color=discord.Color.green()
        )
        scoring.add_field(
            name="🏈 Passing",
            value=(
                "• **0.04 pts** per passing yard\n"
                "• **4 pts** per passing TD\n"
                "• **-2 pts** per interception"
            ),
            inline=True
        )
        scoring.add_field(
            name="🏃 Rushing",
            value=(
                "• **0.1 pts** per rushing yard\n"
                "• **6 pts** per rushing TD\n"
                "• **+3 pts** bonus for 100+ yards"
            ),
            inline=True
        )
        scoring.add_field(
            name="🙌 Receiving",
            value=(
                "• **1 pt** per reception (PPR)\n"
                "• **0.1 pts** per receiving yard\n"
                "• **6 pts** per receiving TD\n"
                "• **+3 pts** bonus for 100+ yards"
            ),
            inline=True
        )
        scoring.add_field(
            name="⚡ Bonuses",
            value=(
                "• **+3 pts** for 300+ passing yards\n"
                "• **+3 pts** for 100+ rushing yards\n"
                "• **+3 pts** for 100+ receiving yards"
            ),
            inline=False
        )
        embeds.append(scoring)
        
        # Embed 4: Payout Structure
        payouts = discord.Embed(
            title="💰 Payout Structure",
            description=(
                "Best Ball uses a **Loser-Pays-Winner** system, similar to our playoff payouts. "
                "The bottom half of finishers pay the top half."
            ),
            color=discord.Color.red()
        )
        payouts.add_field(
            name="🏆 How Payouts Work",
            value=(
                "• **Last place** pays **1st place**\n"
                "• **2nd to last** pays **2nd place**\n"
                "• **3rd to last** pays **3rd place**\n"
                "• And so on until the middle is reached..."
            ),
            inline=False
        )
        payouts.add_field(
            name="📊 Example (12 Players, $50 Entry)",
            value=(
                "```\n"
                "Rank 12 (Last)  → Pays Rank 1  = $50\n"
                "Rank 11         → Pays Rank 2  = $50\n"
                "Rank 10         → Pays Rank 3  = $50\n"
                "Rank 9          → Pays Rank 4  = $50\n"
                "Rank 8          → Pays Rank 5  = $50\n"
                "Rank 7          → Pays Rank 6  = $50\n"
                "```"
            ),
            inline=False
        )
        payouts.add_field(
            name="🤝 Tiebreakers",
            value=(
                "1. **Total Points** - Higher total wins\n"
                "2. **Bench Points** - More unused points wins\n"
                "3. **Total TDs** - More touchdowns wins"
            ),
            inline=False
        )
        embeds.append(payouts)
        
        # Embed 5: Timeline & Commands
        timeline = discord.Embed(
            title="⏰ Event Timeline",
            description="How a Best Ball event progresses:",
            color=discord.Color.purple()
        )
        timeline.add_field(
            name="📅 Event Phases",
            value=(
                "**1. Registration** - Event created, players join and pay entry\n"
                "**2. Drafting** - Build your 20-player roster\n"
                "**3. Active** - Rosters locked, weekly scoring begins\n"
                "**4. Completed** - Event ends, payments generated"
            ),
            inline=False
        )
        timeline.add_field(
            name="🔧 Key Commands",
            value=(
                "`/joinbestball` - Join an event\n"
                "`/addplayer` - Add player to roster\n"
                "`/selectyourteam` - View roster progress\n"
                "`/bestballstatus` - Check standings\n"
                "`/bestballhelp` - Quick reference"
            ),
            inline=True
        )
        timeline.add_field(
            name="⚙️ Admin Commands",
            value=(
                "`/startbestball` - Create event\n"
                "`/closebestball` - Lock rosters\n"
                "`/endbestball` - End & pay out\n"
                "`/cancelbestball` - Cancel event"
            ),
            inline=True
        )
        embeds.append(timeline)
        
        # Send all embeds
        await interaction.response.send_message(embeds=embeds)

    @app_commands.command(name="refreshplayers", description="[Admin] Refresh the player database from Snallabot")
    @app_commands.default_permissions(administrator=True)
    async def refresh_players(self, interaction: discord.Interaction):
        """Manually refresh the player cache."""
        await interaction.response.defer(ephemeral=True)
        
        await self.refresh_player_cache()
        
        await interaction.followup.send(
            f"✅ Player cache refreshed! {len(self.player_cache)} players loaded.",
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(BestBallCog(bot))
