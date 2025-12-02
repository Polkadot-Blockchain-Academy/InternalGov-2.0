# Commit Message: AI Feedback Collection and Subsquare Approval Workflow

## Overview
This commit introduces a comprehensive feedback collection and summarization system that allows DAO members to provide optional comments when voting, automatically generates AI-powered summaries of community feedback, and enables controlled publishing of these summaries to Subsquare governance platforms.

## Features Added

### 1. Optional Voter Feedback Collection
- **What it does**: After a user casts a vote (AYE/NAY/RECUSE), the bot sends a follow-up message in the thread asking for optional feedback
- **How it works**: Users reply to the bot's message with their comments, which are automatically captured and stored
- **Storage**: All comments are stored in PostgreSQL database (`feedback_comments` table) with metadata including user ID, username, thread ID, vote type, comment text, and timestamp
- **Integration**: Seamlessly integrated into existing vote button interaction flow without disrupting current voting functionality

### 2. AI-Powered Feedback Summarization
- **What it does**: Automatically generates concise summaries of all collected feedback comments for each proposal
- **AI Model**: Uses OpenAI GPT-4o-mini by default (configurable via `OPENAI_MODEL` env var)
- **When it runs**: During the `autonomous_voting()` cycle, before on-chain votes are cast
- **Output**: Creates a single-paragraph summary (~100 words) that captures key themes, concerns, and sentiments from all comments
- **Posting**: Summary is automatically posted as a pinned embed message in the Discord thread
- **Fallback**: If AI summarization fails, a simple fallback message is posted instead

### 3. Subsquare Publishing with Approval Workflow
- **What it does**: Queues AI-generated summaries for review and approval before publishing to Subsquare governance platforms
- **Security**: Uses sr25519 cryptographic signatures (same mnemonic as on-chain voting) to authenticate comments
- **Approval Process**: Summaries are queued in `data/pending_subsquare.json` and require explicit approval via slash command
- **Slash Commands**: 
  - `/subsquare publish <referendum>` - Publishes approved summary to Subsquare
  - `/subsquare discard <referendum>` - Discards a queued summary
- **Permission Control**: Only users with `SUBSQUARE_APPROVER_ROLE` (defaults to admin role) can approve/discard summaries

## Complete Workflow

### Step 1: User Votes and Provides Feedback
1. User clicks AYE/NAY/RECUSE button in Discord thread
2. Bot registers the vote (existing functionality)
3. Bot sends follow-up message: "💬 Optional Feedback: Reply to this message to add a comment..."
4. User optionally replies with their feedback
5. Bot saves comment to PostgreSQL database with ✅ reaction confirmation

### Step 2: AI Summary Generation (During Autonomous Voting)
1. `autonomous_voting()` runs on schedule (every 12 hours by default)
2. For each proposal about to be voted on:
   - Bot queries database for all comments associated with that proposal's thread
   - If comments exist, calls AI summarizer with:
     - Proposal title and index
     - Vote result (AYE/NAY/RECUSE)
     - Vote counts
     - Origin information
     - All collected comments
   - AI generates summary following BPA Alumni DAO context
   - Summary is posted as pinned embed in Discord thread

### Step 3: Subsquare Queue (If Enabled)
1. If `SUBSQUARE_POST_SUMMARY=true` in config:
   - Summary data is queued to `data/pending_subsquare.json`
   - Includes: referendum index, block height, title, vote result, vote counts, origin, summary text, thread URL
   - Bot posts message in thread: "📝 Subsquare summary queued. Use `/subsquare publish <id>` to publish..."
2. Summary remains in queue until approved or discarded

### Step 4: Approval and Publishing
1. Approver reviews queued summary in Discord thread
2. Approver runs `/subsquare publish <referendum_number>`
3. Bot:
   - Validates approver has required role
   - Loads summary from queue
   - Signs comment payload with sr25519 (using existing mnemonic)
   - Posts to Subsquare API: `https://{network}-api.subsquare.io/sima/referenda/{index}/comments`
   - Removes summary from queue
   - Confirms publication in Discord thread
4. Summary appears on Subsquare proposal page as official DAO comment

## Technical Implementation

### New Files Created
- `bot/utils/ai_summarizer.py` - OpenAI integration for comment summarization
- `bot/utils/subsquare_client.py` - Subsquare API client with sr25519 signing
- `data/pending_subsquare.json` - Queue file for pending summaries (auto-created)

### Modified Files
- `bot/governance_monitor.py` - Added comment collection, queue management, Subsquare client initialization
- `bot/main.py` - Integrated AI summarization into autonomous voting, added `/subsquare` slash command
- `bot/utils/config.py` - Added configuration for OpenAI, database, and Subsquare settings
- `bot/utils/database_handler.py` - Added `feedback_comments` table and related methods
- `requirements.txt` - Added `openai==1.12.0` and `psycopg2-binary==2.9.9`
- `README.md` - Updated documentation with new features and configuration

### Database Schema
New `feedback_comments` table:
```sql
CREATE TABLE feedback_comments (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    username TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    vote_type TEXT NOT NULL,
    comment TEXT NOT NULL,
    comment_message_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(thread_id) REFERENCES referenda_thread(thread_id)
);
```

### Configuration Requirements

#### Required (for AI summaries):
- `OPENAI_API_KEY` - Your OpenAI API key
- `OPENAI_MODEL` - Model to use (default: `gpt-4o-mini`)

#### Required (for database):
- `DB_HOST` - PostgreSQL host (default: `localhost`)
- `DB_PORT` - PostgreSQL port (default: `5432`)
- `DB_NAME` - Database name (default: `governance`)
- `DB_USER` - Database user (default: `postgres`)
- `DB_PASSWORD` - Database password

#### Optional (for Subsquare):
- `SUBSQUARE_POST_SUMMARY` - Enable Subsquare queue (default: `false`)
- `SUBSQUARE_APPROVER_ROLE` - Role name for approvers (defaults to admin role)
- `SUBSQUARE_SS58_FORMAT` - SS58 address format (0 for Polkadot, 2 for Kusama, auto-detected from network)

#### Existing (already required):
- `MNEMONIC` - Used for signing Subsquare comments (same as voting)

## Dependencies Added
- `openai==1.12.0` - OpenAI API client
- `psycopg2-binary==2.9.9` - PostgreSQL adapter

## Backward Compatibility
- **All new features are optional**: Bot works exactly as before if new env vars are not set
- **No breaking changes**: Existing voting, embeds, and automation flows remain unchanged
- **Graceful degradation**: If AI/database/Subsquare fail, bot continues normal operation with error logging
- **Database optional**: If database connection fails, comment collection is skipped but voting continues

## Error Handling
- Database connection failures: Logged, voting continues
- AI API failures: Fallback message posted, voting continues
- Subsquare API failures: Error logged, approver notified, queue entry preserved
- Missing permissions: Clear error messages to users
- Invalid referendum IDs: Validation before queue operations

## Security Considerations
- Subsquare comments are cryptographically signed using sr25519 (same security as on-chain voting)
- Approval workflow prevents unauthorized publishing
- Role-based access control for approval commands
- Database stores user comments with proper foreign key constraints

## Usage Examples

### Enable AI Summaries Only
```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
DB_HOST=localhost
DB_PASSWORD=your_password
```

### Enable Full Workflow (Including Subsquare)
```env
OPENAI_API_KEY=sk-...
DB_PASSWORD=your_password
SUBSQUARE_POST_SUMMARY=true
SUBSQUARE_APPROVER_ROLE=Governance Lead
```

### Approve a Summary
```
/subsquare publish 123
```

### Discard a Summary
```
/subsquare discard 123
```

## Testing Checklist
- [x] Comment collection works after voting
- [x] Comments saved to database correctly
- [x] AI summarization generates coherent summaries
- [x] Summaries posted to Discord threads
- [x] Queue system stores summaries correctly
- [x] Approval command validates permissions
- [x] Subsquare posting with correct signatures
- [x] Error handling doesn't break existing flows
- [x] Backward compatibility maintained

## Notes
- Subsquare comments include: vote result, vote counts, origin, AI summary, Discord thread link, and contact information
- All Subsquare operations require the referendum's block height from governance cache
- The approval workflow ensures quality control before public publishing
- Database migrations are handled automatically on first run

