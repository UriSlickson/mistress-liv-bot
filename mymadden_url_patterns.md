# MyMadden URL Patterns

## Schedule URLs

Base URL: `https://mymadden.com/lg/liv/schedule`

### URL Structure:
`https://mymadden.com/lg/liv/schedule/{year}/{season_type}/{week}`

### Parameters:
- `{year}`: Season year (e.g., 2027, 2028)
- `{season_type}`: 
  - `pre` = Pre Season
  - `reg` = Regular Season
  - `post` = Post Season (playoffs)
- `{week}`: Week number (1-18 for regular season, specific for playoffs)

### Examples:
- Regular Season Week 4, 2027: `https://mymadden.com/lg/liv/schedule/2027/reg/4`
- Pre Season Week 1, 2028: `https://mymadden.com/lg/liv/schedule/2028/pre/1`
- Playoffs Wildcard: `https://mymadden.com/lg/liv/schedule/2027/post/wildcard`
- Playoffs Divisional: `https://mymadden.com/lg/liv/schedule/2027/post/divisional`

## Game Data Structure (from HTML):
- Away team on left, Home team on right
- Scores displayed prominently
- Records shown below (e.g., 10-7-0)
- "FW: None" or "Started 1 Time" indicates game status
- GAMECENTER link available for each game

## Scraping Strategy:
1. Parse the schedule page HTML
2. Extract game cards with team names and scores
3. Match games to pending wagers
4. Verify results before settling
