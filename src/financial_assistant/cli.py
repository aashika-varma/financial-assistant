"""Interactive application entry point. Run with poetry run financial-assistant."""
import argparse
import asyncio
import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

from financial_assistant.features.investment_brief.service import BriefService, load_portfolio

HELP = """
/brief                 Generate a brief using the selected price session
/ask QUESTION          Ask a standalone question about your portfolio
/portfolio             Show confirmed holdings (no LLM call)
/session YYYY-MM-DD    Change the price session; does not download prices
/status                Show dates and enabled sources
/help                  Show commands
/exit                  Quit
Each request is independent; follow-up conversation memory is not enabled.
"""


def make_parser():
    parser = argparse.ArgumentParser(description='Interactive financial assistant')
    parser.add_argument('--user-id', required=True)
    parser.add_argument('--session', type=date.fromisoformat, required=True,
                        help='Exact stored closing-price session, YYYY-MM-DD')
    parser.add_argument('--holdings-as-of', type=date.fromisoformat,
                        help='Optional portfolio cutoff; defaults to today in India')
    parser.add_argument('--rss', action='store_true', help='Enable stored RSS summaries')
    parser.add_argument('--web-search', action='store_true', dest='web_search',
                        help='Enable live Tavily web search (requires TAVILY_API_KEY)')
    parser.add_argument('--once', action='store_true', help='Generate one brief and exit')
    return parser


def status(args, output):
    cutoff = args.holdings_as_of or datetime.now(ZoneInfo('Asia/Kolkata')).date()
    output(f'User: {args.user_id} | Price session: {args.session} | Portfolio cutoff: {cutoff}')
    output('Prices: stored Neon data | RSS: ' + ('enabled (stored snapshots)' if args.rss else 'disabled'))
    output('Live web search: ' + ('enabled (Tavily)' if args.web_search else 'disabled') +
           ' | This CLI does not ingest or refresh source data.')


async def run(args, *, input_fn=input, output=print, service=None, portfolio_loader=load_portfolio):
    service = service or BriefService(rss_enabled=args.rss, web_search_enabled=args.web_search)
    status(args, output)
    if not args.once:
        output(HELP)
    while True:
        try:
            raw = '/brief' if args.once else input_fn('finance> ').strip()
        except (EOFError, KeyboardInterrupt):
            output('Goodbye.')
            return 0
        if not raw:
            continue
        command, _, argument = raw.partition(' ')
        argument = argument.strip()
        if command in {'/exit', '/quit'}:
            output('Goodbye.')
            return 0
        if command == '/help':
            output(HELP)
            continue
        if command == '/status':
            status(args, output)
            continue
        try:
            if command == '/session':
                new_session = date.fromisoformat(argument)
                if new_session > datetime.now(ZoneInfo('Asia/Kolkata')).date():
                    raise ValueError('A price session cannot be in the future')
                args.session = new_session
                status(args, output)
            elif command == '/portfolio':
                cutoff = args.holdings_as_of or datetime.now(ZoneInfo('Asia/Kolkata')).date()
                versions = portfolio_loader(args.user_id, cutoff)
                for v in versions:
                    output(f"Account: {v['account_reference']} | Version: {v['portfolio_version_id']} | Holdings as of: {v['holdings_as_of']}")
                    for h in v['holdings']:
                        output(f"  {h['symbol']}: {h['quantity']} shares")
                    for warning in v.get('warnings', []):
                        output(f'  Note: {warning}')
            elif command in {'/brief', '/ask'}:
                if command == '/ask' and not argument:
                    raise ValueError('Usage: /ask YOUR QUESTION')
                output('Working...')
                result = await service.ask(
                    args.user_id, args.session,
                    argument if command == '/ask' else 'Generate my investment brief. Retrieve all portfolio prices together. If RSS is enabled, retrieve announcements too.',
                    brief=command == '/brief', holdings_date=args.holdings_as_of,
                )
                output('Tools used: ' + ', '.join(result['tools_used']))
                answer = result['answer']
                output(answer if isinstance(answer, str) else json.dumps(answer, ensure_ascii=False))
            else:
                output('Unknown command. Use /help or /ask YOUR QUESTION.')
        except ValueError as exc:
            output(f'Input/data issue: {exc}')
            if args.once:
                return 1
        except Exception as exc:
            # Do not print provider errors that may contain URLs or credentials.
            output(f'Request failed ({type(exc).__name__}). Check credentials, database availability and stored data; retry when ready.')
            if args.once:
                return 1
        if args.once:
            return 0


def main():
    args = make_parser().parse_args()
    if args.session > datetime.now(ZoneInfo('Asia/Kolkata')).date():
        raise SystemExit('A price session cannot be in the future')
    try:
        raise SystemExit(asyncio.run(run(args)))
    except KeyboardInterrupt:
        print('\nGoodbye.')


if __name__ == '__main__':
    main()
