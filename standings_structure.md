# MyMadden Standings Structure

## URL Pattern
`https://mymadden.com/lg/liv/standings/{year}/conf`

## Conference Standings Format
- Shows AFC and NFC standings with seed numbers 1-16
- Seeds 1-7 are playoff teams (marked with Y, X, or Z indicators)
- Seeds 8-16 are non-playoff teams

## Table Structure
| Column | Description |
|--------|-------------|
| # | Seed number (1-16) |
| Team | Team logo/link |
| W | Wins |
| L | Losses |
| T | Ties |
| % | Win percentage |
| PF | Points For |
| PA | Points Against |
| Net | Point differential |
| Div | Division record |
| Conf | Conference record |
| Home | Home record |
| Away | Away record |
| Streak | Current streak |
| ISoS | Initial Strength of Schedule |
| TSoS | Total Strength of Schedule |
| PSoS | Played Strength of Schedule |
| RSoS | Remaining Strength of Schedule |

## Key Observations
1. The # column contains the seed number (1-16)
2. Team column has team logo images with links to team pages
3. Playoff teams (seeds 1-7) have indicators (Z, Y, X)
4. Can scrape team name from the team link/image

## Scraping Approach
1. Fetch the conference standings page
2. Parse AFC Standings table - extract seeds 1-16 with team names
3. Parse NFC Standings table - extract seeds 1-16 with team names
4. Map team names to Discord users via registration data
