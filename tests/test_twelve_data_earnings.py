import json
import unittest
from urllib.parse import parse_qs, urlparse

from market_data.twelve_data_earnings import TwelveDataEarningsProvider


class TwelveDataEarningsProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_parses_date_only_history_without_claiming_announcement_time(self):
        seen = []
        def fetch(url):
            seen.append(url)
            return json.dumps({"earnings":[
                {"date":"2026-01-28","eps_estimate":"2.0"},
                {"datetime":"2025-10-29T00:00:00","eps_actual":"1.9"},
            ]})
        p=TwelveDataEarningsProvider(api_key="secret",fetch_text=fetch)
        events=await p.history(" msft ")
        self.assertEqual([x.earnings_date.isoformat() for x in events],["2025-10-29","2026-01-28"])
        self.assertTrue(all(x.symbol=="MSFT" for x in events))
        self.assertTrue(all("secret" not in x.source_reference for x in events))
        qs=parse_qs(urlparse(seen[0]).query)
        self.assertEqual(qs["symbol"],["MSFT"])
        self.assertEqual(qs["apikey"],["secret"])

    async def test_invalid_rows_are_ignored_deterministically(self):
        p=TwelveDataEarningsProvider(
            api_key="x",
            fetch_text=lambda _: json.dumps({"earnings":[{"date":"bad"},{"foo":"bar"},{"date":"2026-02-01"}]}),
        )
        events=await p.history("AAPL")
        self.assertEqual(len(events),1)
        self.assertEqual(events[0].source_reference,"twelve-data:earnings:AAPL:2026-02-01")


if __name__=="__main__":
    unittest.main()
