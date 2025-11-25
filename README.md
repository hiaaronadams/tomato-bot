# Tomato Bot 🍅

A bot that posts tomato-related artwork from museum collections to Bluesky daily.

## Features

- Automatically posts tomato artwork once per day
- Sources artwork from:
  - Cooper Hewitt Smithsonian Design Museum
  - The Cleveland Museum of Art
  - The Metropolitan Museum of Art
- Tracks posted items to avoid duplicates
- Includes metadata like artist, date, and credit lines

## Setup

### Prerequisites

- Python 3.11+
- Bluesky account with app password
- GitHub repository with Actions enabled

### Local Setup

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Create a `.env` file with your credentials:
   ```
   BSKY_HANDLE=your-handle.bsky.social
   BSKY_APP_PASSWORD=your-app-password
   COOPER_API_KEY=your-cooper-api-key
   SMITH_API_KEY=your-smith-api-key
   ```
4. Run manually:
   ```bash
   python tomato_bot.py
   ```

### Automated Daily Posting

The bot runs automatically once per day at 10:00 AM UTC via GitHub Actions.

#### Setting up GitHub Secrets

To enable automated posting, add these secrets to your GitHub repository:

1. Go to your repository settings
2. Navigate to **Secrets and variables** → **Actions**
3. Add the following repository secrets:
   - `BSKY_HANDLE` - Your Bluesky handle
   - `BSKY_APP_PASSWORD` - Your Bluesky app password
   - `COOPER_API_KEY` - Cooper Hewitt API key
   - `SMITH_API_KEY` - Smithsonian API key

#### Manual Trigger

You can also trigger a post manually:
1. Go to the **Actions** tab in your GitHub repository
2. Select **Daily Tomato Post** workflow
3. Click **Run workflow**

## How It Works

1. The bot randomly selects a museum source
2. Searches for tomato-related items with images
3. Filters for public domain/CC0 items
4. Checks against previously posted items
5. Posts to Bluesky with image and metadata
6. Saves the posted item ID to avoid duplicates

## Files

- `tomato_bot.py` - Main bot script
- `posted_ids.json` - Tracks posted artwork IDs
- `.github/workflows/daily-post.yml` - GitHub Actions workflow
- `requirements.txt` - Python dependencies

## License

This bot uses public domain and CC0 artwork from various museums.
