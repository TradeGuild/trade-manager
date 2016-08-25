import time
import unittest

from helper import TestPlugin, start_test_man, stop_test_man
from sqlalchemy_models import get_schemas
from test.helper import check_test_ticker
from trade_manager.cli import handle_command
from trade_manager.plugin import get_orders, get_trades, sync_ticker, sync_balances

SCHEMAS = get_schemas()

tp = TestPlugin()
tp.setup_connections()
tp.setup_logger()


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
        sync_ticker('helper', market='BTC_USD')
        ticker = ""
        countdown = 30
        while (isinstance(ticker, int) or ticker == '') and countdown > 0:
            countdown -= 1
            time.sleep(0.1)
            ticker = handle_command(['ticker', 'get', '-e', 'helper', '-m', 'BTC_USD'], session=tp.session)
        check_test_ticker(ticker)
