# NPL Auction System

This document describes the implementation of the NPL auction system that follows specific auction rules for in-season bidding.

## Auction Rules

The system implements the following rules:

1. **One Bid Per Team**: You are allowed to make only one bid per auction
2. **Nominations vs Bids**: Nominations are NON-BINDING; you MUST bid to win an auction
3. **Blind Auctions**: FA auction time does NOT extend; auctions are blind and expire at 3 PM ET on Friday each week
4. **Dollar Amounts**: Bids must be in dollars (positive integers)
5. **Winning Amount**: The winning amount will be $1 greater than the second highest bid
6. **EST Timezone**: All times are EST

## System Components

### Models

#### Auction Model
- `player`: Foreign key to Player being auctioned
- `closes`: DateTime when auction expires
- `is_nomination`: Boolean to distinguish nominations from binding auctions
- `min_bid`: Minimum bid amount in dollars (default: $1)
- `active`: Whether auction is still being processed

Key methods:
- `is_expired()`: Check if auction has passed closing time
- `has_bids()`: Check if any bids have been placed
- `winning_bid()`: Calculate winner and winning amount based on rules
- `leading_bid()`: Display appropriate info for blind auctions

#### MLBAuctionBid Model
- `team`: Foreign key to bidding team
- `auction`: Foreign key to auction
- `max_bid`: Bid amount in dollars
- Unique constraint: one bid per team per auction

Validation:
- Bid must be positive dollar amount
- Must meet minimum bid requirement
- Cannot bid on expired auctions
- Cannot bid on nomination-only auctions

### Views

#### auction_bid_api
API endpoint for submitting bids:
- Validates auction is active and user has permission
- Enforces one-bid-per-team rule
- Validates bid amount meets requirements
- Returns success/error messages
- Maintains blind auction by not revealing competitive info

#### auction_list
Display page for active auctions:
- Shows active auctions (excludes nominations)
- Displays minimal info for blind auctions
- Shows user's own bid if placed
- Shows recent expired auctions with results

### Templates

#### auction_list.html
- Rules explanation at top
- Active auctions table with blind auction info
- Recent results section showing winners
- JavaScript validation for bid input

#### includes/bidding_buttons.html
- Number input with minimum bid validation
- Clear labeling for blind auction rules
- Submit button with appropriate messaging

### Management Commands

#### process_expired_auctions
Command to process expired auctions and determine winners:

```bash
# Dry run to see what would be processed
python manage.py process_expired_auctions --dry-run

# Actually process expired auctions
python manage.py process_expired_auctions
```

Features:
- Finds all expired, unprocessed auctions
- Calculates winners based on second-highest-bid + $1 rule
- Creates transaction records
- Assigns players to winning teams
- Marks auctions as processed

#### create_weekly_auctions
Command to create weekly auctions that expire on Fridays at 3 PM EST:

```bash
# Preview what auctions would be created (recommended first)
python manage.py create_weekly_auctions --dry-run --max-players 10 --min-bid 5

# Create 10 auctions with $5 minimum bid
python manage.py create_weekly_auctions --max-players 10 --min-bid 5

# Create 5 auctions with $1 minimum bid (defaults)
python manage.py create_weekly_auctions --max-players 5

# Create default number of auctions (10) with $1 minimum
python manage.py create_weekly_auctions
```

Features:
- Automatically calculates next Friday at 3 PM EST
- Prevents duplicate auctions for the same week
- Customizable number of players and minimum bid
- Selects random unowned players not already in active auctions
- Dry-run mode for testing

### Admin Interface

Enhanced admin for auction management:
- List view shows key auction info
- Editable fields for quick updates
- Winning bid info for expired auctions
- Action to process multiple expired auctions
- Filtering by active status, nomination type, closing date

## Usage

### Creating Auctions

1. **Regular Auctions**: Set `is_nomination=False`, set appropriate `closes` datetime
2. **Nominations**: Set `is_nomination=True` for view-only nominations
3. **Minimum Bid**: Set `min_bid` to desired minimum (default $1)

### Bidding Process

1. Users visit `/auctions/` to see active auctions
2. Click on auction and enter bid amount
3. System validates bid and enforces rules
4. Success/error message returned
5. Page updates to show "already bid" status

### Processing Results

Auctions should be processed regularly (suggested: hourly cron job):

```bash
# Add to crontab for automated processing
0 * * * * cd /path/to/project && python manage.py process_expired_auctions
```

### Creating Weekly Auctions

Set up automated weekly auction creation:

```bash
# Run every Monday at 9 AM to create auctions for the upcoming Friday
0 9 * * 1 cd /path/to/project && python manage.py create_weekly_auctions --max-players 10 --min-bid 5
```

### Complete Cron Job Setup

For a fully automated auction system, add both commands to your crontab:

```bash
# Edit crontab
crontab -e

# Add these lines:
# Process expired auctions every hour
0 * * * * cd /path/to/project && python manage.py process_expired_auctions

# Create weekly auctions every Monday at 9 AM
0 9 * * 1 cd /path/to/project && python manage.py create_weekly_auctions --max-players 10 --min-bid 5

# Optional: Clean up old processed auctions monthly (keep last 6 months)
0 2 1 * * cd /path/to/project && python manage.py shell -c "from npl.models import Auction; from datetime import datetime, timedelta; Auction.objects.filter(active=False, closes__lt=datetime.now()-timedelta(days=180)).delete()"
```

### Testing and Debugging

#### Web Interface Testing
Access the test page at `/auctions/test/` (staff only) to:
- Test blind auction behavior
- Debug specific auctions
- Preview weekly auction creation
- Verify all auction rules are working

#### Command Line Testing
```bash
# Test auction processing without making changes
python manage.py process_expired_auctions --dry-run

# Test weekly auction creation without making changes
python manage.py create_weekly_auctions --dry-run --max-players 5

# Debug specific auction via API (replace 123 with auction ID)
curl http://localhost:8000/api/v1/auctions/debug/123/

# Test blind auction behavior via API
curl http://localhost:8000/api/v1/auctions/test/
```

### Blind Auction Implementation

During active auctions:
- Users can see total number of bids
- Users can see their own bid amount
- Competitive information (max bid, leading team) is hidden
- Only minimum bid requirement is shown

After auction expires:
- Winning team and amounts are revealed
- Full bid details available to admins
- Transaction records created automatically

## Database Migration

To apply the new auction fields:

```bash
python manage.py makemigrations
python manage.py migrate
```

## API Endpoints

- `GET /api/v1/auctions/bid/<auction_id>/?bid=<amount>` - Submit bid
- `GET /auctions/` - View active auctions list
- `GET /auctions/test/` - Test page (staff only)
- `GET /api/v1/auctions/test/` - Test API endpoint (staff only)
- `GET /api/v1/auctions/debug/<auction_id>/` - Debug specific auction (staff only)

## Key Features

1. **Blind Auction**: Competitive bid info hidden during active auctions
2. **One Bid Rule**: Enforced at database and API level
3. **Automatic Processing**: Management command for batch processing
4. **EST Timezone**: All times handled in Eastern timezone
5. **Validation**: Multiple levels of bid validation
6. **Transaction Records**: Automatic record keeping for wins
7. **Admin Tools**: Comprehensive admin interface for management
8. **Weekly Automation**: Automated auction creation for Fridays at 3 PM EST
9. **Testing Tools**: Built-in testing and debugging interfaces

## Security Considerations

- User authentication required for bidding
- Team ownership validation
- Bid amount validation
- SQL injection protection via Django ORM
- CSRF protection on forms

## Maintenance Tasks

### Daily
- Monitor auction processing logs for errors
- Check that bids are being placed successfully

### Weekly
- Verify new auctions are created on Mondays
- Review auction results and transaction records
- Monitor for any system issues or rule violations

### Monthly
- Review and archive old auction data
- Check system performance and optimize queries if needed
- Update player eligibility criteria if needed

## Future Enhancements

Potential additions:
- Email notifications for auction results
- Bid history tracking
- Auction analytics and reporting
- Mobile-responsive bid interface
- Integration with external player databases
- Automated player valuation for minimum bids 