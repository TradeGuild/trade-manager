import json
import os
import time
import unittest
from ledger import Amount
from ledger import Balance

from jsonschema import validate
from sqlalchemy_models import get_schemas, wallet as wm, exchange as em

from test.helpers import TestPlugin
from trade_manager import ses
from trade_manager.cli import handle_command
from trade_manager.plugin import get_orders, get_status, get_trades, sync_ticker, get_debits, sync_balances, \
    get_credits, \
    make_ledger, get_ticker, get_balances, create_order, sync_orders, cancel_orders, sync_credits, sync_debits, \
    sync_trades

tp = TestPlugin(session=ses)
SCHEMAS = get_schemas()


def start_test_man():
    os.system("python test/helpers.py start")
    status = 'blocked'
    countdown = 30
    while status != 'running' and countdown > 0:
        countdown -= 1
        status = get_status('test')
        time.sleep(0.01)


def stop_test_man():
    os.system("python test/helpers.py stop")
    status = 'running'
    countdown = 30
    while status != 'blocked' and countdown > 0:
        countdown -= 1
        status = get_status('test')
        time.sleep(0.01)


def test_status():
    status = get_status('test')
    assert status == 'stopped'
    start_test_man()
    status = get_status('test')
    assert status == 'running'
    stop_test_man()
    status = get_status('test')
    assert status == 'stopped'


def test_ledger():
    tp.session.query(em.Trade).delete()
    tp.session.query(wm.Credit).delete()
    tp.session.query(wm.Debit).delete()
    tp.session.commit()
    tp.session.close()
    tp.sync_credits()
    tp.sync_debits()
    tp.sync_trades()
    trades = get_trades('test', session=tp.session)
    countdown = 30
    while len(trades) != 1 and countdown > 0:
        countdown -= 1
        trades = get_trades('test', session=tp.session)
        if len(trades) != 1:
            time.sleep(0.01)
            tp.session.close()
    credit = get_credits(session=tp.session)[0]
    debit = get_debits(session=tp.session)[0]
    trade = trades[0]
    ledger = make_ledger('test')
    hardledger = """{0} test credit BTC
    Assets:test:BTC:credit    1.00000000 BTC
    Equity:Wallet:BTC:debit   -1.00000000 BTC

{1} test debit BTC
    Assets:test:BTC:debit    -1.00000000 BTC
    Equity:Wallet:BTC:credit   1.00000000 BTC

P {2} BTC 100.00000000 USD
P {2} USD 0.01000000 BTC
{2} test BTC_USD buy
    ;<Trade(trade_id='{3}', side='buy', amount=0.01000000 BTC, price=100.00000000 USD, fee=0.00000000 USD, fee_side='quote', market='BTC_USD', exchange='test', time={2})>
    Assets:test:USD    -1.00000000 USD @ 0.01000000 BTC
    FX:BTC_USD:buy   1.00000000 USD @ 0.01000000 BTC
    Assets:test:BTC    0.01000000 BTC @ 100.00000000 USD
    FX:BTC_USD:buy   -0.01000000 BTC @ 100.00000000 USD

""".format(credit.time.strftime('%Y/%m/%d %H:%M:%S'), debit.time.strftime('%Y/%m/%d %H:%M:%S'),
           trade.time.strftime('%Y/%m/%d %H:%M:%S'), trade.trade_id)
    assert ledger == hardledger


class TestPluginRunning(unittest.TestCase):
    def setUp(self):
        start_test_man()

    def tearDown(self):
        stop_test_man()

    def test_ticker(self):
        sync_ticker('test', 'BTC_USD')
        ticker = get_ticker('test', 'BTC_USD')
        tick = json.loads(ticker)
        assert validate(tick, SCHEMAS['Ticker']) is None

    def test_balance(self):
        sync_balances('test')
        total, available = get_balances('test', session=tp.session)
        assert isinstance(total, Balance)
        assert isinstance(available, Balance)
        for amount in total:
            assert amount >= available.commodity_amount(amount.commodity)

    def test_order_lifecycle(self):
        order = create_order('test', 100, 0.1, 'BTC_USD', 'bid', session=tp.session)
        assert isinstance(order.id, int)
        assert isinstance(order.price, Amount)
        assert order.price == Amount("100 USD")
        assert order.state == 'pending'
        porder = get_orders(oid=order.id, session=tp.session)
        assert len(porder) == 1
        assert porder[0].state == 'pending'
        sync_orders('test')
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
        cancel_orders('test', oid=order.id)
        countdown = 30
        corder = get_orders('test', order_id=oorder[0].order_id, session=tp.session)
        while corder[0].state != 'closed' and countdown > 0:
            countdown -= 1
            corder = get_orders('test', order_id=oorder[0].order_id, session=tp.session)
            if corder[0].state != 'closed':
                time.sleep(0.01)
                tp.session.close()
        assert len(corder) == 1
        assert corder[0].state == 'closed'

    def test_cancel_order_order_id(self):
        order = create_order('test', 100, 0.1, 'BTC_USD', 'bid', session=tp.session)
        assert isinstance(order.id, int)
        assert isinstance(order.price, Amount)
        assert order.price == Amount("100 USD")
        assert order.state == 'pending'
        porder = get_orders(oid=order.id, session=tp.session)
        assert len(porder) == 1
        assert porder[0].state == 'pending'
        sync_orders('test')
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
        cancel_orders('test', order_id=oorder[0].order_id)
        corder = get_orders('test', order_id=order.order_id.split("|")[1], session=tp.session)
        while corder[0].state != 'closed' and countdown > 0:
            countdown -= 1
            corder = get_orders('test', order_id=order.order_id.split("|")[1], session=tp.session)
            if corder[0].state != 'closed':
                time.sleep(0.01)
                tp.session.close()
        assert len(corder) == 1
        assert corder[0].state == 'closed'

    def test_cancel_order_order_id_no_prefix(self):
        order = create_order('test', 100, 0.1, 'BTC_USD', 'bid', session=tp.session)
        assert isinstance(order.id, int)
        assert isinstance(order.price, Amount)
        assert order.price == Amount("100 USD")
        assert order.state == 'pending'
        porder = get_orders(oid=order.id, session=tp.session)
        assert len(porder) == 1
        assert porder[0].state == 'pending'
        sync_orders('test')
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
        cancel_orders('test', order_id=order.order_id.split("|")[1])
        corder = get_orders(oid=order.id, session=tp.session)
        while corder[0].state != 'closed' and countdown > 0:
            countdown -= 1
            corder = get_orders(oid=order.id, session=tp.session)
            if corder[0].state != 'closed':
                time.sleep(0.01)
                tp.session.close()
        assert len(corder) == 1
        assert corder[0].state == 'closed'

    def test_cancel_orders_by_side(self):
        create_order('test', 100, 0.1, 'BTC_USD', 'bid', session=tp.session)
        create_order('test', 100, 0.1, 'BTC_USD', 'bid', session=tp.session)
        obids = len(get_orders(side='bid', state='pending', session=tp.session))
        assert obids >= 2
        create_order('test', 100, 0.1, 'BTC_USD', 'ask', session=tp.session)
        create_order('test', 100, 0.1, 'BTC_USD', 'ask', session=tp.session)
        oasks = len(get_orders(side='ask', state='pending', session=tp.session))
        assert oasks >= 2
        cancel_orders('test', side='bid')
        bids = len(get_orders(side='bid', state='pending', session=tp.session))
        countdown = 30
        while bids != 0 and countdown > 0:
            countdown -= 1
            bids = len(get_orders(side='bid', state='pending', session=tp.session))
            if bids != 0:
                time.sleep(0.01)
                tp.session.close()
        assert bids == 0
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

    def test_cancel_orders_by_market(self):
        create_order('test', 100, 0.1, 'BTC_USD', 'bid', session=tp.session)
        create_order('test', 100, 0.1, 'BTC_USD', 'bid', session=tp.session)
        obids = len(get_orders(side='bid', state='pending', session=tp.session))
        assert obids >= 2
        create_order('test', 100, 0.1, 'BTC_USD', 'ask', session=tp.session)
        create_order('test', 100, 0.1, 'BTC_USD', 'ask', session=tp.session)
        create_order('test', 100, 0.1, 'DASH_BTC', 'ask', session=tp.session)
        oasks = len(get_orders(side='ask', state='pending', session=tp.session))
        assert oasks >= 3
        cancel_orders('test', market='BTC_USD')
        bids = len(get_orders(side='bid', state='pending', session=tp.session))
        countdown = 30
        while bids != 0 and countdown > 0:
            countdown -= 1
            bids = len(get_orders(side='bid', state='pending', session=tp.session))
            if bids != 0:
                time.sleep(0.01)
                tp.session.close()
        assert bids == 0
        asks = len(get_orders(side='ask', state='pending', session=tp.session))
        countdown = 30
        while asks != 0 and countdown > 0:
            countdown -= 1
            asks = len(get_orders(side='ask', state='pending', session=tp.session))
            if asks != 0:
                time.sleep(0.01)
                tp.session.close()
        assert asks >= 1

    def test_book(self):
        pass

    def test_sync_trades(self):
        trades = len(get_trades('test', session=tp.session))
        sync_trades('test')
        newtrades = len(get_trades('test', session=tp.session))
        countdown = 30
        while newtrades == trades and countdown > 0:
            countdown -= 1
            newtrades = len(get_trades('test', session=tp.session))
            if newtrades == trades:
                time.sleep(0.01)
                tp.session.close()
        assert newtrades > trades

    def test_sync_credits(self):
        credits = len(get_credits('test', session=tp.session))
        sync_credits('test')
        newcreds = len(get_credits('test', session=tp.session))
        countdown = 30
        while newcreds == credits and countdown > 0:
            countdown -= 1
            newcreds = len(get_credits('test', session=tp.session))
            if newcreds == credits:
                time.sleep(0.01)
                tp.session.close()
        assert newcreds > credits

    def test_sync_debits(self):
        debits = len(get_debits('test', session=tp.session))
        sync_debits('test')
        newdebs = len(get_debits('test', session=tp.session))
        countdown = 30
        while newdebs == debits and countdown > 0:
            countdown -= 1
            newdebs = len(get_debits('test', session=tp.session))
            if newdebs == debits:
                time.sleep(0.01)
                tp.session.close()
        assert newdebs > debits


class TestCLI(unittest.TestCase):
    def setUp(self):
        start_test_man()

    def tearDown(self):
        stop_test_man()

    def test_ticker(self):
        sync_ticker('test', 'BTC_USD')
        ticker = ""
        countdown = 30
        while (isinstance(ticker, int) or ticker == '') and countdown > 0:
            countdown -= 1
            time.sleep(0.1)
            ticker = handle_command(['ticker', 'get', '-e', 'test'])
        assert '{"volume": 1000.0, "last": 100.0, "exchange": "test", "bid": 99.0, "high": 110.0, ' \
               '"low": 90.0, "time": "' in ticker
        assert '", "ask": 101.0, "market": "BTC_USD"}' in ticker

    def test_balance(self):
        sync_balances('test')
        balance = ""
        countdown = 30
        while (isinstance(balance, int) or balance == '') and countdown > 0:
            countdown -= 1
            time.sleep(0.1)
            balance = handle_command(['balance', 'get', '-e', 'test'])
        assert str(balance) == "['0', '0']"

    def test_order_lifecycle(self):
        order = str(handle_command(['order', 'create', 'bid', '100', '0.1', 'BTC_USD', 'test']))
        order_id = order[order.find("order_id") + 10: order.find("state") - 3]
        exporder = "<LimitOrder(price=0.10000000 USD, amount=100.00000000 BTC, exec_amount=0.00000000 BTC, " \
                   "market='BTC_USD', side='bid', exchange='test', order_id='{0}', state='pending', " \
                   "create_time=".format(order_id)
        assert exporder in order
        gotorder = str(handle_command(['order', 'get', '-e', 'test', '--order_id', order_id]))
        assert exporder in order
        assert exporder in gotorder

        handle_command(['order', 'sync', '-e', 'test'])
        order_id = order_id.replace('tmp', 'test')
        exporder = exporder.replace("pending", "open").replace('tmp', 'test')
        oorder = get_orders('test', order_id=order_id, session=tp.session)
        countdown = 30
        while (len(oorder) == 0 or oorder[0].state == 'pending') and countdown > 0:
            countdown -= 1
            oorder = get_orders('test', order_id=order_id, session=tp.session)
            if len(oorder) == 0 or oorder[0].state == 'pending':
                time.sleep(0.01)
                tp.session.close()
        assert len(oorder) == 1
        assert oorder[0].state == 'open'
        clioorder = str(handle_command(['order', 'get', '-e', 'test', '--order_id', order_id.split("|")[1]]))
        assert exporder in clioorder.strip('[]')
        handle_command(['order', 'cancel', 'test', '--order_id', order_id.replace('tmp', 'test').split("|")[1]])
        exporder = exporder.replace("open", "closed")
        countdown = 30
        corder = get_orders('test', order_id=oorder[0].order_id, session=tp.session)
        while corder[0].state != 'closed' and countdown > 0:
            countdown -= 1
            corder = get_orders('test', order_id=oorder[0].order_id, session=tp.session)
            if corder[0].state != 'closed':
                time.sleep(0.01)
                tp.session.close()
        assert len(corder) == 1
        assert corder[0].state == 'closed'
        clicorder = str(handle_command(['order', 'get', '-e', 'test', '--order_id', order_id.split("|")[1]]))
        assert exporder.replace("pending", "closed").replace('tmp', 'test') in clicorder.strip('[]')

    def test_sync_trades(self):
        trades = len(get_trades('test', session=tp.session))
        handle_command(['trade', 'sync', '-e', 'test'])
        newtrades = len(get_trades('test', session=tp.session))
        countdown = 30
        while newtrades == trades and countdown > 0:
            countdown -= 1
            newtrades = len(get_trades('test', session=tp.session))
            if newtrades == trades:
                time.sleep(0.01)
                tp.session.close()
        assert newtrades > trades
