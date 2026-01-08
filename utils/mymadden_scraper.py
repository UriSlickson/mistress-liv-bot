"""
MyMadden Website Scraper
Fetches game results from the MyMadden website for verification and cross-referencing.
"""
import aiohttp
import asyncio
import re
import logging
from typing import Optional, List, Dict
from bs4 import BeautifulSoup

logger = logging.getLogger('MistressLIV.MyMaddenScraper')

# Team name to abbreviation mapping
TEAM_NAME_TO_ABBR = {
    'cardinals': 'ARI', 'falcons': 'ATL', 'ravens': 'BAL', 'bills': 'BUF',
    'panthers': 'CAR', 'bears': 'CHI', 'bengals': 'CIN', 'browns': 'CLE',
    'cowboys': 'DAL', 'broncos': 'DEN', 'lions': 'DET', 'packers': 'GB',
    'texans': 'HOU', 'colts': 'IND', 'jaguars': 'JAX', 'chiefs': 'KC',
    'chargers': 'LAC', 'rams': 'LAR', 'raiders': 'LV', 'dolphins': 'MIA',
    'vikings': 'MIN', 'patriots': 'NE', 'saints': 'NO', 'giants': 'NYG',
    'jets': 'NYJ', 'eagles': 'PHI', 'steelers': 'PIT', 'seahawks': 'SEA',
    '49ers': 'SF', 'buccaneers': 'TB', 'titans': 'TEN', 'commanders': 'WAS',
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
    """Scraper for MyMadden website game results."""
    
    BASE_URL = "https://mymadden.com/lg/liv"
    
    def __init__(self):
        self.session = None
    
    async def _ensure_session(self):
        """Ensure aiohttp session exists."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
    
    async def close(self):
        """Close the aiohttp session."""
        if self.session and not self.session.closed:
            await self.session.close()
    
    def _normalize_team(self, team_name: str) -> Optional[str]:
        """Convert team name to standard abbreviation."""
        team_lower = team_name.lower().strip()
        return TEAM_NAME_TO_ABBR.get(team_lower)
    
    def _build_schedule_url(self, year: int, season_type: str, week: int) -> str:
        """
        Build the URL for a specific week's schedule.
        
        Args:
            year: Season year (e.g., 2027)
            season_type: 'pre', 'reg', or 'post'
            week: Week number (1-18 for regular season, or playoff round)
        """
        # Map week numbers to playoff round names for post-season
        if season_type == 'post':
            week_map = {
                19: 'wildcard', 'wildcard': 'wildcard',
                20: 'divisional', 'divisional': 'divisional',
                21: 'conference', 'conference': 'conference',
                22: 'superbowl', 'super bowl': 'superbowl'
            }
            week_str = week_map.get(week, str(week))
        else:
            week_str = str(week)
        
        return f"{self.BASE_URL}/schedule/{year}/{season_type}/{week_str}"
    
    async def fetch_schedule_page(self, year: int, season_type: str, week: int) -> Optional[str]:
        """Fetch the HTML content of a schedule page."""
        await self._ensure_session()
        
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
        """
        Parse game results from the schedule page HTML.
        
        Returns list of game dicts with:
        - away_team: Team abbreviation
        - home_team: Team abbreviation
        - away_score: int
        - home_score: int
        - winner: Team abbreviation (or None for tie)
        - completed: bool (whether game has been played)
        """
        games = []
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Find all game cards - they use custom <basic-panel> elements with 'game' class
        game_divs = soup.find_all('basic-panel')
        # Filter to only those with 'game' in their class list
        game_divs = [d for d in game_divs if d.get('class') and 'game' in d.get('class')]
        
        for game_div in game_divs:
            try:
                # Get all text content - use | separator for cleaner parsing
                text_content = game_div.get_text(separator='|', strip=True)
                parts = [p.strip() for p in text_content.split('|') if p.strip()]
                
                # Skip if not enough content
                if len(parts) < 4:
                    continue
                
                # Parse game data
                # Format from basic-panel: AwayTeam|AwayScore|AwayRecord|[GameDay]|HomeTeam|HomeScore|HomeRecord|...
                # Note: GAMECENTER link text is not included in the text content
                
                away_team_name = None
                away_score = None
                home_team_name = None
                home_score = None
                
                idx = 0
                
                # Away team (first non-numeric, non-record item)
                if idx < len(parts) and not parts[idx].isdigit() and not re.match(r'\d+-\d+-\d+', parts[idx]):
                    away_team_name = parts[idx]
                    idx += 1
                
                # Away score (should be a number)
                if idx < len(parts) and parts[idx].isdigit():
                    away_score = int(parts[idx])
                    idx += 1
                
                # Skip record (format: X-X-X)
                if idx < len(parts) and re.match(r'\d+-\d+-\d+', parts[idx]):
                    idx += 1
                
                # Skip optional game day (TNF, MNF, etc.)
                if idx < len(parts) and parts[idx] in ['TNF', 'MNF', 'SNF', 'SUN', 'SAT']:
                    idx += 1
                
                # Home team
                if idx < len(parts) and not parts[idx].isdigit() and not re.match(r'\d+-\d+-\d+', parts[idx]):
                    home_team_name = parts[idx]
                    idx += 1
                
                # Home score
                if idx < len(parts) and parts[idx].isdigit():
                    home_score = int(parts[idx])
                
                # Validate we got all required data
                if not all([away_team_name, home_team_name]):
                    continue
                
                # Normalize team names
                away_team = self._normalize_team(away_team_name)
                home_team = self._normalize_team(home_team_name)
                
                if not away_team or not home_team:
                    logger.warning(f"Could not normalize teams: {away_team_name} vs {home_team_name}")
                    continue
                
                # Determine if game is completed and who won
                completed = away_score is not None and home_score is not None
                winner = None
                
                if completed:
                    if away_score > home_score:
                        winner = away_team
                    elif home_score > away_score:
                        winner = home_team
                    # else: tie (winner stays None)
                
                games.append({
                    'away_team': away_team,
                    'home_team': home_team,
                    'away_score': away_score,
                    'home_score': home_score,
                    'winner': winner,
                    'completed': completed,
                    'away_team_name': away_team_name,
                    'home_team_name': home_team_name
                })
                
            except Exception as e:
                logger.error(f"Error parsing game div: {e}")
                continue
        
        return games
    
    async def get_games_for_week(self, year: int, season_type: str, week: int) -> List[Dict]:
        """
        Fetch and parse all games for a specific week.
        
        Args:
            year: Season year
            season_type: 'pre', 'reg', or 'post'
            week: Week number
            
        Returns:
            List of game dicts
        """
        html = await self.fetch_schedule_page(year, season_type, week)
        if not html:
            return []
        
        return self.parse_games_from_html(html)
    
    async def verify_game_result(self, away_team: str, home_team: str, 
                                  year: int, season_type: str, week: int) -> Optional[Dict]:
        """
        Verify a specific game result from the MyMadden website.
        
        Args:
            away_team: Away team abbreviation
            home_team: Home team abbreviation
            year: Season year
            season_type: 'pre', 'reg', or 'post'
            week: Week number
            
        Returns:
            Game dict if found, None otherwise
        """
        games = await self.get_games_for_week(year, season_type, week)
        
        for game in games:
            if game['away_team'] == away_team and game['home_team'] == home_team:
                return game
        
        # Try reverse (in case teams are swapped)
        for game in games:
            if game['away_team'] == home_team and game['home_team'] == away_team:
                logger.warning(f"Found game with swapped teams: {home_team} @ {away_team}")
                return game
        
        return None
    
    async def get_completed_games_for_week(self, year: int, season_type: str, week: int) -> List[Dict]:
        """Get only completed games for a week."""
        games = await self.get_games_for_week(year, season_type, week)
        return [g for g in games if g['completed']]


# Team ID to name mapping (based on MyMadden team logo IDs)
TEAM_ID_TO_NAME = {
    '0': 'unknown', '1': 'bears', '2': 'bengals', '3': 'bills', '4': 'broncos',
    '5': 'browns', '6': 'buccaneers', '7': 'cardinals', '8': 'chargers',
    '9': 'chiefs', '10': 'colts', '11': 'commanders', '12': 'cowboys',
    '13': 'dolphins', '14': 'eagles', '15': 'falcons', '16': 'giants',
    '17': 'jaguars', '18': 'jets', '19': 'lions', '20': 'packers',
    '21': 'panthers', '22': 'patriots', '23': 'raiders', '24': 'rams',
    '25': 'ravens', '26': 'saints', '27': 'seahawks', '28': 'steelers',
    '29': 'texans', '30': 'titans', '31': '49ers', '32': 'vikings'
}

# AFC and NFC team lists for conference detection
AFC_TEAMS = ['BAL', 'BUF', 'CIN', 'CLE', 'DEN', 'HOU', 'IND', 'JAX', 'KC', 'LV', 'LAC', 'MIA', 'NE', 'NYJ', 'PIT', 'TEN']
NFC_TEAMS = ['ARI', 'ATL', 'CAR', 'CHI', 'DAL', 'DET', 'GB', 'LAR', 'MIN', 'NO', 'NYG', 'PHI', 'SEA', 'SF', 'TB', 'WAS']


class StandingsScraper:
    """Scraper for MyMadden standings/seedings."""
    
    BASE_URL = "https://mymadden.com/lg/liv"
    
    def __init__(self):
        self.session = None
    
    async def _ensure_session(self):
        """Ensure aiohttp session exists."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
    
    async def close(self):
        """Close the aiohttp session."""
        if self.session and not self.session.closed:
            await self.session.close()
    
    def _team_id_to_abbr(self, team_id: str) -> Optional[str]:
        """Convert team ID to abbreviation."""
        team_name = TEAM_ID_TO_NAME.get(team_id, '')
        return TEAM_NAME_TO_ABBR.get(team_name)
    
    async def fetch_standings_page(self, year: int) -> Optional[str]:
        """Fetch the conference standings page for a given year."""
        await self._ensure_session()
        
        url = f"{self.BASE_URL}/standings/{year}/conf"
        logger.info(f"Fetching standings from: {url}")
        
        try:
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    return await response.text()
                else:
                    logger.error(f"Failed to fetch standings: HTTP {response.status}")
                    return None
        except Exception as e:
            logger.error(f"Error fetching standings: {e}")
            return None
    
    def parse_standings_from_html(self, html_content: str) -> Dict[str, List[Dict]]:
        """
        Parse conference standings from HTML.
        
        Returns dict with 'afc' and 'nfc' keys, each containing list of:
        - seed: int (1-16)
        - team_id: str
        - team_abbr: str
        - team_name: str
        """
        results = {'afc': [], 'nfc': []}
        soup = BeautifulSoup(html_content, 'html.parser')
        
        tables = soup.find_all('table')
        
        # Tables: [0] = header/nav, [1] = AFC, [2] = NFC
        for table_idx, conference in [(1, 'afc'), (2, 'nfc')]:
            if table_idx >= len(tables):
                continue
            
            table = tables[table_idx]
            rows = table.find_all('tr')
            
            for row_idx, row in enumerate(rows):
                if row_idx == 0:  # Skip header
                    continue
                
                cells = row.find_all('td')
                if len(cells) < 2:
                    continue
                
                try:
                    # First cell is seed number
                    seed = int(cells[0].get_text(strip=True))
                    
                    # Second cell contains team image
                    img = cells[1].find('img')
                    if not img:
                        continue
                    
                    img_src = img.get('src', '')
                    # Extract team ID from URL like /teamlogos/256/22.png
                    id_match = re.search(r'/(\d+)\.png', img_src)
                    if not id_match:
                        continue
                    
                    team_id = id_match.group(1)
                    team_name = TEAM_ID_TO_NAME.get(team_id, f'unknown_{team_id}')
                    team_abbr = TEAM_NAME_TO_ABBR.get(team_name)
                    
                    results[conference].append({
                        'seed': seed,
                        'team_id': team_id,
                        'team_name': team_name,
                        'team_abbr': team_abbr
                    })
                    
                except (ValueError, AttributeError) as e:
                    logger.warning(f"Error parsing standings row: {e}")
                    continue
        
        return results
    
    async def get_standings(self, year: int) -> Dict[str, List[Dict]]:
        """
        Get conference standings for a given year.
        
        Returns dict with 'afc' and 'nfc' keys.
        """
        html = await self.fetch_standings_page(year)
        if not html:
            return {'afc': [], 'nfc': []}
        
        return self.parse_standings_from_html(html)
    
    async def get_playoff_seedings(self, year: int) -> Dict[str, List[Dict]]:
        """
        Get playoff seedings (seeds 1-7) for both conferences.
        
        Returns dict with 'afc' and 'nfc' keys, each containing seeds 1-7.
        """
        standings = await self.get_standings(year)
        
        return {
            'afc': [s for s in standings['afc'] if s['seed'] <= 7],
            'nfc': [s for s in standings['nfc'] if s['seed'] <= 7]
        }
    
    async def get_nfc_pot_payers(self, year: int) -> List[Dict]:
        """
        Get NFC seeds 8-16 who pay into the pot.
        
        Returns list of teams with seeds 8-16.
        """
        standings = await self.get_standings(year)
        return [s for s in standings['nfc'] if 8 <= s['seed'] <= 16]


# Singleton instances for reuse
_scraper_instance = None
_standings_scraper_instance = None

def get_scraper() -> MyMaddenScraper:
    """Get or create the singleton scraper instance."""
    global _scraper_instance
    if _scraper_instance is None:
        _scraper_instance = MyMaddenScraper()
    return _scraper_instance


def get_standings_scraper() -> StandingsScraper:
    """Get or create the singleton standings scraper instance."""
    global _standings_scraper_instance
    if _standings_scraper_instance is None:
        _standings_scraper_instance = StandingsScraper()
    return _standings_scraper_instance


async def test_scraper():
    """Test the scraper functionality."""
    scraper = get_scraper()
    
    # Test fetching 2027 regular season week 4
    print("Fetching HTML...")
    html = await scraper.fetch_schedule_page(2027, 'reg', 4)
    if html:
        print(f"Got HTML, length: {len(html)}")
        # Save HTML for debugging
        with open('/tmp/mymadden_debug.html', 'w') as f:
            f.write(html)
        print("Saved HTML to /tmp/mymadden_debug.html")
    else:
        print("Failed to fetch HTML")
        return
    
    games = await scraper.get_games_for_week(2027, 'reg', 4)
    
    print(f"Found {len(games)} games:")
    for game in games:
        status = "✅" if game['completed'] else "⏳"
        winner_str = f" - Winner: {game['winner']}" if game['winner'] else ""
        score_str = f"{game['away_score']}-{game['home_score']}" if game['completed'] else "TBD"
        print(f"{status} {game['away_team']} @ {game['home_team']}: {score_str}{winner_str}")
    
    await scraper.close()


if __name__ == "__main__":
    asyncio.run(test_scraper())
