import json
import time
import unittest
from ledger import Amount
from ledger import Balance

from jsonschema import validate
from sqlalchemy_models import get_schemas, wallet as wm, exchange as em
from tappmq.tappmq import get_status

from trade_manager.helper import TestPlugin, start_test_man, stop_test_man
from trade_manager.cli import handle_command
from trade_manager.plugin import get_orders, get_trades, sync_ticker, get_debits, sync_balances, get_credits, \
    make_ledger, get_ticker, get_balances, create_order, sync_orders, cancel_orders, sync_credits, sync_debits, \
    sync_trades, submit_order

SCHEMAS = get_schemas()

tp = TestPlugin()
tp.setup_connections()


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


def test_ledger():
    tp.session.query(em.Trade).delete()
    tp.session.query(wm.Credit).delete()
    tp.session.query(wm.Debit).delete()
    tp.session.commit()
    tp.sync_credits()
    tp.sync_debits()
    tp.sync_trades()
    trades = get_trades('helper', session=tp.session)
    countdown = 30
    while len(trades) != 1 and countdown > 0:
        countdown -= 1
        trades = get_trades('helper', session=tp.session)
        if len(trades) != 1:
            time.sleep(0.01)
    credit = get_credits(session=tp.session)[0]
    debit = get_debits(session=tp.session)[0]
    trade = trades[0]
    ledger = make_ledger('helper')
    hardledger = """{0} helper credit BTC
    Assets:helper:BTC:credit    1.00000000 BTC
    Equity:Wallet:BTC:debit   -1.00000000 BTC

{1} helper debit BTC
    Assets:helper:BTC:debit    -1.00000000 BTC
    Equity:Wallet:BTC:credit   1.00000000 BTC

P {2} BTC 100.00000000 USD
P {2} USD 0.01000000 BTC
{2} helper BTC_USD buy
    ;<Trade(trade_id='{3}', side='buy', amount=0.01000000 BTC, price=100.00000000 USD, fee=0.00000000 USD, fee_side='quote', market='BTC_USD', exchange='helper', time={2})>
    Assets:helper:USD    -1.00000000 USD @ 0.01000000 BTC
    FX:BTC_USD:buy   1.00000000 USD @ 0.01000000 BTC
    Assets:helper:BTC    0.01000000 BTC @ 100.00000000 USD
    FX:BTC_USD:buy   -0.01000000 BTC @ 100.00000000 USD

""".format(credit.time.strftime('%Y/%m/%d %H:%M:%S'), debit.time.strftime('%Y/%m/%d %H:%M:%S'),
           trade.time.strftime('%Y/%m/%d %H:%M:%S'), trade.trade_id)
    assert ledger == hardledger


class TestPluginRunning(unittest.TestCase):
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
        obids = len(get_orders(side='bid', state='pending', session=tp.session))
        assert obids >= 2
        create_order('helper', 100, 0.1, 'BTC_USD', 'ask', session=tp.session, submit=False)
        create_order('helper', 100, 0.1, 'BTC_USD', 'ask', session=tp.session, submit=False)
        create_order('helper', 100, 0.1, 'DASH_BTC', 'ask', session=tp.session, submit=False)
        oasks = len(get_orders(side='ask', state='pending', session=tp.session))
        assert oasks >= 3
        tp.session.close()
        cancel_orders('helper', market='BTC_USD')
        orders = len(get_orders(market='BTC_USD', state='pending', session=tp.session))
        countdown = 30
        while orders != 0 and countdown > 0:
            countdown -= 1
            orders = len(get_orders(market='BTC_USD', state='pending', session=tp.session))
            if orders != 0:
                time.sleep(0.01)
                tp.session.close()
        assert orders == 0
        dorders = len(get_orders(market='DASH_BTC', state='pending', session=tp.session))
        assert dorders >= 1

    def test_cancel_orders_by_side(self):
        create_order('helper', 100, 0.1, 'BTC_USD', 'bid', session=tp.session, submit=False)
        create_order('helper', 100, 0.1, 'BTC_USD', 'bid', session=tp.session, submit=False)
        obids = len(get_orders(side='bid', state='pending', session=tp.session))
        assert obids >= 2
        create_order('helper', 100, 0.1, 'BTC_USD', 'ask', session=tp.session, submit=False)
        create_order('helper', 100, 0.1, 'BTC_USD', 'ask', session=tp.session, submit=False)
        oasks = len(get_orders(side='ask', state='pending', session=tp.session))
        assert oasks >= 2
        tp.session.close()
        cancel_orders('helper', side='bid')
        bids = len(get_orders(side='bid', state='pending', session=tp.session))
        countdown = 30
        while bids != 0 and countdown > 0:
            countdown -= 1
            bids = len(get_orders(side='bid', state='pending', session=tp.session))
            if bids != 0:
                time.sleep(0.01)
                tp.session.close()
        assert bids == 0
        tp.session.close()
        asks = len(get_orders(side='ask', state='pending', session=tp.session))
        countdown = 30
        while asks != 0 and countdown > 0:
            countdown -= 1
            asks = len(get_orders(side='ask', state='pending', session=tp.session))
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
        credits = len(get_credits('helper', session=tp.session))
        sync_credits('helper')
        newcreds = len(get_credits('helper', session=tp.session))
        countdown = 30
        while newcreds == credits and countdown > 0:
            countdown -= 1
            newcreds = len(get_credits('helper', session=tp.session))
            if newcreds == credits:
                time.sleep(0.01)
        assert newcreds > credits

    def test_sync_debits(self):
        debits = len(get_debits('helper', session=tp.session))
        sync_debits('helper')
        newdebs = len(get_debits('helper', session=tp.session))
        countdown = 30
        while newdebs == debits and countdown > 0:
            countdown -= 1
            newdebs = len(get_debits('helper', session=tp.session))
            if newdebs == debits:
                time.sleep(0.01)
        assert newdebs > debits

    def test_sync_trades(self):
        trades = len(get_trades('helper', session=tp.session))
        sync_trades('helper')
        newtrades = len(get_trades('helper', session=tp.session))
        countdown = 30
        while newtrades == trades and countdown > 0:
            countdown -= 1
            newtrades = len(get_trades('helper', session=tp.session))
            if newtrades == trades:
                time.sleep(0.01)
        assert newtrades > trades

    def test_ticker(self):
        sync_ticker('helper', 'BTC_USD')
        tick = None
        countdown = 300
        while tick is None and countdown > 0:
            countdown -= 1
            ticker = get_ticker('helper', 'BTC_USD')
            try:
                tick = json.loads(ticker)
            except (ValueError, TypeError):
                pass
        assert validate(tick, SCHEMAS['Ticker']) is None


class TestCLI(unittest.TestCase):
    def setUp(self):
        start_test_man()

    def tearDown(self):
        stop_test_man()

    def test_balance(self):
        sync_balances('helper')
        balance = ""
        countdown = 30
        while (isinstance(balance, int) or balance == '') and countdown > 0:
            countdown -= 1
            time.sleep(0.1)
            balance = handle_command(['balance', 'get', '-e', 'helper'], session=tp.session)
        assert str(balance) == "['0', '0']"

    def test_order_lifecycle(self):
        order = str(handle_command(['order', 'create', 'bid', '100', '0.1', 'BTC_USD', 'helper'], session=tp.session))
        order_id = order[order.find("order_id") + 10: order.find("state") - 3]
        exporder = "<LimitOrder(price=0.10000000 USD, amount=100.00000000 BTC, exec_amount=0.00000000 BTC, " \
                   "market='BTC_USD', side='bid', exchange='helper', order_id='{0}', state='pending', " \
                   "create_time=".format(order_id)
        assert exporder in order
        gotorder = str(handle_command(['order', 'get', '-e', 'helper', '--order_id', order_id], session=tp.session))
        assert exporder in order
        assert exporder in gotorder

        order_id = order_id.replace('tmp', 'helper')
        exporder = exporder.replace("pending", "open").replace('tmp', 'helper')
        tp.session.close()
        oorder = get_orders('helper', order_id=order_id, session=tp.session)
        countdown = 30
        while (len(oorder) == 0 or oorder[0].state != 'open') and countdown > 0:
            countdown -= 1
            oorder = get_orders('helper', order_id=order_id, session=tp.session)
            if len(oorder) == 0 or oorder[0].state != 'open':
                time.sleep(0.01)
                tp.session.close()
        assert len(oorder) == 1
        assert oorder[0].state == 'open'
        clioorder = str(
            handle_command(['order', 'get', '-e', 'helper', '--order_id', order_id.split("|")[1]], session=tp.session))
        assert exporder in clioorder.strip('[]')
        handle_command(['order', 'cancel', 'helper', '--order_id', order_id.replace('tmp', 'helper').split("|")[1]],
                       session=tp.session)
        exporder = exporder.replace("open", "closed")
        countdown = 30
        tp.session.close()
        corder = get_orders('helper', order_id=oorder[0].order_id, session=tp.session)
        while corder[0].state != 'closed' and countdown > 0:
            countdown -= 1
            corder = get_orders('helper', order_id=oorder[0].order_id, session=tp.session)
            if corder[0].state != 'closed':
                time.sleep(0.01)
                tp.session.close()
        assert len(corder) == 1
        assert corder[0].state == 'closed'
        clicorder = str(
            handle_command(['order', 'get', '-e', 'helper', '--order_id', order_id.split("|")[1]], session=tp.session))
        assert exporder in clicorder.strip('[]')

    def test_sync_trades(self):
        trades = len(get_trades('helper', session=tp.session))
        handle_command(['trade', 'sync', '-e', 'helper'], session=tp.session)
        tp.session.close()
        newtrades = len(get_trades('helper', session=tp.session))
        countdown = 30
        while newtrades == trades and countdown > 0:
            countdown -= 1
            newtrades = len(get_trades('helper', session=tp.session))
            if newtrades == trades:
                time.sleep(0.01)
                tp.session.close()
        assert newtrades > trades

    def test_ticker(self):
        sync_ticker('helper', 'BTC_USD')
        ticker = ""
        countdown = 30
        while (isinstance(ticker, int) or ticker == '') and countdown > 0:
            countdown -= 1
            time.sleep(0.1)
            ticker = handle_command(['ticker', 'get', '-e', 'helper'], session=tp.session)
        assert '{"volume": 1000.0, "last": 100.0, "exchange": "helper", "bid": 99.0, "high": 110.0, ' \
               '"low": 90.0, "time": "' in ticker
        assert '", "ask": 101.0, "market": "BTC_USD"}' in ticker
