import unittest
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

from financial_assistant.cli import make_parser, run
from financial_assistant.features.investment_brief.service import build_request

VERSIONS = [{'portfolio_version_id': 1, 'account_reference': 'ACCOUNT_1',
             'holdings_as_of': date(2026, 9, 25), 'warnings': ['Synthetic sample'],
             'holdings': [{'symbol': 'TCS', 'quantity': '10'}]}]


class CliTests(unittest.IsolatedAsyncioTestCase):
    def args(self, *extra):
        return make_parser().parse_args(['--user-id', 'demo_user', '--session', '2026-09-25', *extra])

    async def test_portfolio_does_not_call_llm_and_exit(self):
        service = AsyncMock()
        commands = iter(['/portfolio', '/exit'])
        out = []
        code = await run(self.args(), input_fn=lambda _: next(commands), output=out.append,
                         service=service, portfolio_loader=lambda u, d: VERSIONS)
        self.assertEqual(code, 0)
        service.ask.assert_not_called()
        self.assertTrue(any('TCS: 10 shares' in line for line in out))

    async def test_ask_brief_and_session_routing(self):
        service = AsyncMock()
        service.ask.return_value = {'tools_used': [], 'answer': 'answer'}
        commands = iter(['/session 2026-09-24', '/ask Explain daily change', '/brief', '/exit'])
        await run(self.args(), input_fn=lambda _: next(commands), output=lambda _: None, service=service)
        calls = service.ask.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].args[1], date(2026, 9, 24))
        self.assertFalse(calls[0].kwargs['brief'])
        self.assertTrue(calls[1].kwargs['brief'])

    async def test_bad_commands_do_not_call_service(self):
        service = AsyncMock()
        commands = iter(['/ask', '/session invalid', '/session 2999-01-01', '/oops', '/exit'])
        args = self.args()
        await run(args, input_fn=lambda _: next(commands), output=lambda _: None, service=service)
        self.assertEqual(args.session, date(2026, 9, 25))
        service.ask.assert_not_called()

    async def test_failure_recovery_and_redaction(self):
        service = AsyncMock()
        service.ask.side_effect = [RuntimeError('secret-provider-token'), {'tools_used': [], 'answer': 'ok'}]
        commands = iter(['/brief', '/brief', '/exit'])
        out = []
        await run(self.args(), input_fn=lambda _: next(commands), output=out.append, service=service)
        self.assertNotIn('secret-provider-token', '\n'.join(out))
        self.assertIn('ok', out)

    async def test_once_failure_returns_nonzero(self):
        service = AsyncMock()
        service.ask.side_effect = RuntimeError('failed')
        code = await run(self.args('--once'), output=lambda _: None, service=service)
        self.assertEqual(code, 1)

    async def test_eof_exits(self):
        def eof(_):
            raise EOFError
        self.assertEqual(await run(self.args(), input_fn=eof, output=lambda _: None), 0)


class RequestTests(unittest.TestCase):
    def test_rss_off_and_dates_separate(self):
        request = build_request(VERSIONS, date(2026, 9, 24), 'brief')
        self.assertIn('RSS disabled', request)
        self.assertIn('2026-09-24', request)
        self.assertIn('2026-09-25', request)
        self.assertIn('Synthetic sample', request)

    def test_rss_window_automatic(self):
        now = datetime(2026, 9, 29, 4, tzinfo=timezone.utc)
        request = build_request(VERSIONS, date(2026, 9, 25), 'brief', rss_enabled=True, now=now)
        self.assertIn('2026-09-28T04:00:00+00:00 inclusive', request)
        self.assertIn('2026-09-29T04:00:00+00:00 exclusive', request)

    def test_empty_portfolio_rejected(self):
        with self.assertRaises(ValueError):
            build_request([], date(2026, 9, 25), 'brief')


if __name__ == '__main__':
    unittest.main()
