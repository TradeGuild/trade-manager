from unittest import TestCase

from ledger import Balance

from ledger import Amount

import time

from tappmq.tappmq import get_status
from test.helper import stop_test_man, start_test_man, TestPlugin, check_test_ticker
from test.test_plugin import check_test_ticker
from trade_manager.plugin import get_balances, create_order, submit_order, get_orders, get_credits, sync_credits, \
    get_debits, sync_debits, get_trades, sync_trades, sync_ticker, get_ticker, cancel_orders
from trade_manager.plugin import sync_balances


tp = TestPlugin()
tp.setup_connections()
tp.setup_logger()


def test_status():
    stop_test_man()
    status = get_status('helper')
    assert status == 'stopped'
    start_test_man()
    status = get_status('helper')
    assert status == 'running'
    stop_test_man()
    status = get_status('helper')
    assert status == 'stopped'


class TestPluginRunning(TestCase):
    def setUp(self):
        start_test_man()

    def tearDown(self):
        stop_test_man()

    def test_balance(self):
        sync_balances('helper')
        total, available = get_balances('helper', session=tp.session)
        countdown = 300
        while total is None and countdown > 0:
            countdown -= 1
            try:
                total, available = get_balances('helper', session=tp.session)
            except Exception:
                pass
        total, available = get_balances('helper', session=tp.session)
        assert isinstance(total, Balance)
        assert isinstance(available, Balance)
        for amount in total:
            assert amount >= available.commodity_amount(amount.commodity)

    def test_cancel_order_order_id(self):
        order = create_order('helper', 100, 0.1, 'BTC_USD', 'bid', session=tp.session, submit=False)
        assert isinstance(order.id, int)
        assert isinstance(order.price, Amount)
        assert order.price == Amount("100 USD")
        assert order.state == 'pending'
        tp.session.close()
        submit_order('helper', order.id)
        oorder = get_orders(oid=order.id, session=tp.session)
        countdown = 30
        while oorder[0].state == 'pending' and countdown > 0:
            countdown -= 1
            oorder = get_orders(oid=order.id, session=tp.session)
            if oorder[0].state == 'pending':
                time.sleep(0.01)
                tp.session.close()
        assert len(oorder) == 1
        assert oorder[0].state == 'open'
        assert 'helper|' in oorder[0].order_id
        tp.session.close()
        cancel_orders('helper', order_id=oorder[0].order_id)
        corder = get_orders(oid=order.id, session=tp.session)
        while (len(corder) == 0 or corder[0].state != 'closed') and countdown > 0:
            countdown -= 1
            corder = get_orders(oid=order.id, session=tp.session)
            if corder[0].state != 'closed':
                time.sleep(0.01)
                tp.session.close()
        assert len(corder) == 1
        assert corder[0].state == 'closed'

    def test_cancel_order_order_id_no_prefix(self):
        order = create_order('helper', 100, 0.1, 'BTC_USD', 'bid', session=tp.session, submit=False)
        assert isinstance(order.id, int)
        assert isinstance(order.price, Amount)
        assert order.price == Amount("100 USD")
        assert order.state == 'pending'
        tp.session.close()
        submit_order('helper', order.id)
        oorder = get_orders(oid=order.id, session=tp.session)
        countdown = 30
        while oorder[0].state == 'pending' and countdown > 0:
            countdown -= 1
            oorder = get_orders(oid=order.id, session=tp.session)
            if oorder[0].state == 'pending':
                time.sleep(0.01)
                tp.session.close()
        assert len(oorder) == 1
        assert oorder[0].state == 'open'
        assert 'helper|' in oorder[0].order_id
        tp.session.close()
        cancel_orders('helper', order_id=oorder[0].order_id.split("|")[1])
        corder = get_orders(oid=oorder[0].id, session=tp.session)
        while (len(corder) == 0 or corder[0].state != 'closed') and countdown > 0:
            countdown -= 1
            corder = get_orders(oid=oorder[0].id, session=tp.session)
            if corder[0].state != 'closed':
                time.sleep(0.01)
                tp.session.close()
        assert len(corder) == 1
        assert corder[0].state == 'closed'

    def test_cancel_orders_by_market(self):
        create_order('helper', 100, 0.1, 'BTC_USD', 'bid', session=tp.session, submit=False)
        create_order('helper', 100, 0.1, 'BTC_USD', 'bid', session=tp.session, submit=False)
        obids = len(get_orders(side='bid', exchange='helper', state='pending', session=tp.session))
        assert obids >= 2
        create_order('helper', 100, 0.1, 'BTC_USD', 'ask', session=tp.session, submit=False)
        create_order('helper', 100, 0.1, 'BTC_USD', 'ask', session=tp.session, submit=False)
        create_order('helper', 100, 0.1, 'DASH_BTC', 'ask', session=tp.session, submit=False)
        oasks = len(get_orders(side='ask', exchange='helper', state='pending', session=tp.session))
        assert oasks >= 3
        tp.session.close()
        cancel_orders('helper', market='BTC_USD')
        orders = len(get_orders(market='BTC_USD', exchange='helper', state='pending', session=tp.session))
        countdown = 30
        while orders != 0 and countdown > 0:
            countdown -= 1
            orders = len(get_orders(market='BTC_USD', exchange='helper', state='pending', session=tp.session))
            if orders != 0:
                time.sleep(0.01)
                tp.session.close()
        assert orders == 0
        dorders = len(get_orders(market='DASH_BTC', exchange='helper', state='pending', session=tp.session))
        assert dorders >= 1

    def test_cancel_orders_by_side(self):
        create_order('helper', 100, 0.1, 'BTC_USD', 'bid', session=tp.session, submit=False)
        create_order('helper', 100, 0.1, 'BTC_USD', 'bid', session=tp.session, submit=False)
        obids = len(get_orders(side='bid', exchange='helper', state='pending', session=tp.session))
        assert obids >= 2
        create_order('helper', 100, 0.1, 'BTC_USD', 'ask', session=tp.session, submit=False)
        create_order('helper', 100, 0.1, 'BTC_USD', 'ask', session=tp.session, submit=False)
        oasks = len(get_orders(side='ask', exchange='helper', state='pending', session=tp.session))
        assert oasks >= 2
        tp.session.close()
        cancel_orders('helper', side='bid')
        bids = len(get_orders(side='bid', exchange='helper', state='pending', session=tp.session))
        countdown = 30
        while bids != 0 and countdown > 0:
            countdown -= 1
            bids = len(get_orders(side='bid', exchange='helper', state='pending', session=tp.session))
            if bids != 0:
                time.sleep(0.01)
                tp.session.close()
        assert bids == 0
        tp.session.close()
        asks = len(get_orders(side='ask', exchange='helper', state='pending', session=tp.session))
        countdown = 30
        while asks != 0 and countdown > 0:
            countdown -= 1
            asks = len(get_orders(side='ask', exchange='helper', state='pending', session=tp.session))
            if asks != 0:
                time.sleep(0.01)
                tp.session.close()
        assert asks > 0
        assert oasks == asks

    def test_order_lifecycle(self):
        order = create_order('helper', 100, 0.1, 'BTC_USD', 'bid', session=tp.session, submit=False)
        assert isinstance(order.id, int)
        assert isinstance(order.price, Amount)
        assert order.price == Amount("100 USD")
        assert order.state == 'pending'
        porder = get_orders(oid=order.id, session=tp.session)
        assert len(porder) == 1
        assert porder[0].state == 'pending'
        tp.session.close()
        submit_order('helper', order.id)
        oorder = get_orders(oid=order.id, session=tp.session)
        countdown = 300
        while (len(oorder) == 0 or oorder[0].state != 'open') and countdown > 0:
            countdown -= 1
            oorder = get_orders(oid=order.id, session=tp.session)
            if oorder[0].state != 'open':
                time.sleep(0.01)
                tp.session.close()
        assert len(oorder) == 1
        assert oorder[0].state == 'open'
        tp.session.close()
        cancel_orders('helper', oid=order.id)
        countdown = 30
        corder = get_orders('helper', order_id=oorder[0].order_id, session=tp.session)
        while corder[0].state != 'closed' and countdown > 0:
            countdown -= 1
            corder = get_orders('helper', order_id=oorder[0].order_id, session=tp.session)
            if corder[0].state != 'closed':
                time.sleep(0.01)
                tp.session.close()
        assert len(corder) == 1
        assert corder[0].state == 'closed'

    def test_sync_credits(self):
        credits = len(get_credits(exchange='helper', session=tp.session))
        sync_credits('helper')
        newcreds = len(get_credits(exchange='helper', session=tp.session))
        countdown = 30
        while newcreds == credits and countdown > 0:
            countdown -= 1
            newcreds = len(get_credits(exchange='helper', session=tp.session))
            if newcreds == credits:
                time.sleep(0.01)
                tp.session.close()
        assert newcreds > credits

    def test_sync_debits(self):
        debits = len(get_debits(exchange='helper', session=tp.session))
        sync_debits('helper')
        newdebs = len(get_debits(exchange='helper', session=tp.session))
        countdown = 30
        while newdebs == debits and countdown > 0:
            countdown -= 1
            newdebs = len(get_debits(exchange='helper', session=tp.session))
            if newdebs == debits:
                time.sleep(0.01)
                tp.session.close()
        assert newdebs > debits

    def test_sync_trades(self):
        trades = len(get_trades(exchange='helper', session=tp.session))
        sync_trades('helper')
        newtrades = len(get_trades(exchange='helper', session=tp.session))
        countdown = 30
        while newtrades == trades and countdown > 0:
            countdown -= 1
            newtrades = len(get_trades(exchange='helper', session=tp.session))
            if newtrades == trades:
                time.sleep(0.01)
                tp.session.close()
        assert newtrades > trades

    def test_ticker(self):
        sync_ticker('helper', market='BTC_USD')
        ticker = None
        countdown = 300
        while ticker is None and countdown > 0:
            countdown -= 1
            ticker = get_ticker('helper', market='BTC_USD')
        check_test_ticker(ticker)
