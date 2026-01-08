# MyMadden Game Data Structure

## HTML Structure
Games are contained in divs with class: `panel flex flex-col w-full overflow-y-visible rounded my-2 mx-auto p-1 shadow-sm bg-gray-200 dark:bg-gray-800 game`

## Game Data Format (parsed from innerText)
Each game card contains these lines in order:

| Line Index | Content | Example |
|------------|---------|---------|
| 0 | GAMECENTER link | "GAMECENTER" |
| 1 | Away Team Name | "Jaguars" |
| 2 | Away Score | "44" |
| 3 | Away Record | "10-7-0" |
| 4 | Game Day (optional) | "TNF" (Thursday Night Football) |
| 5 | Home Team Name | "Chargers" |
| 6 | Home Score | "3" |
| 7 | Home Record | "4-13-0" |
| 8 | FW Status | "FW: None" |
| 9 | Start Status | "Started 1 Time" |

Note: Line 4 (Game Day) may not always be present, so indices 5-9 may shift to 4-8.

## Example Games from 2027 Regular Season Week 4

| Away Team | Away Score | Home Team | Home Score | Winner |
|-----------|------------|-----------|------------|--------|
| Jaguars | 44 | Chargers | 3 | Jaguars |
| Buccaneers | 24 | Falcons | 34 | Falcons |

## Scraping Logic
1. Find all divs with class containing "game"
2. Extract innerText and split by newlines
3. Parse team names and scores
4. Away team is always first, Home team is second
5. Higher score = winner
