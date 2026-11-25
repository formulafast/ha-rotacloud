import unittest
from unittest.mock import AsyncMock, MagicMock
from custom_components.rotacloud_attendance.api import Client, ApiError

class ApiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = Client(MagicMock(), 'example-not-a-real-key', 7)
        self.client._request = AsyncMock()

    async def test_clock_in_shift(self):
        self.client._request.return_value = ({'user': 1, 'in_time': 100}, {})
        await self.client.clock_in(1, 9)
        self.client._request.assert_awaited_once_with('POST', '/users_clocked_in', body={'method':'terminal','terminal':7,'user':1,'shift':9})

    async def test_clock_in_unscheduled(self):
        self.client._request.return_value = ({'user': 1, 'in_time': 100}, {})
        await self.client.clock_in(1)
        self.client._request.assert_awaited_once_with('POST', '/users_clocked_in', body={'method':'terminal','terminal':7,'user':1})

    async def test_break_actions(self):
        self.client._request.return_value = ({'start_time': 100}, {})
        b = await self.client.set_break(1, 'start_break')
        self.assertIsNone(b.end)
        self.client._request.assert_awaited_with('POST','/users_clocked_in/1',body={'method':'terminal','terminal':7,'action':'start_break'})
        self.client._request.return_value = ({'start_time': 100, 'end_time': 160}, {})
        b = await self.client.set_break(1, 'end_break')
        self.assertEqual(b.seconds(999),60)

    async def test_clock_out(self):
        self.client._request.return_value = ({'user': 1, 'in_time': 100, 'out_time': 200}, {})
        a = await self.client.clock_out(1)
        self.assertEqual(a.state,'gone')
        self.client._request.assert_awaited_once_with('DELETE','/users_clocked_in/1',body={'method':'terminal','terminal':7})

    async def test_pin_response_minimised(self):
        self.client._request.return_value = ({'id':1,'first_name':'Test','last_name':'User','salary':99}, {})
        e = await self.client.identify('0000')
        self.assertEqual(e.id,1)
        self.assertFalse(hasattr(e,'salary'))
        with self.assertRaises(ValueError):
            await self.client.identify('../users')

    async def test_no_retry_on_uncertain_write(self):
        self.client._request.side_effect = ApiError(None, uncertain=True)
        with self.assertRaises(ApiError):
            await self.client.clock_in(1)
        self.assertEqual(self.client._request.await_count,1)

    async def test_pagination(self):
        self.client._request.side_effect = [([{'user':1,'in_time':100}], {'X-Total-Count':'2'}), ([{'user':2,'in_time':100}], {'X-Total-Count':'2'})]
        self.assertEqual([a.user_id for a in await self.client.clocked_in()],[1,2])
