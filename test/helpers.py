import datetime
import random
import signal
import string
from ledger import Amount
from ledger import Balance

from daemon import runner
from sqlalchemy_models import jsonify2
from sqlalchemy_models.util import filter_query_by_attr

from trade_manager import em, wm, ses
from trade_manager.plugin import ExchangePluginBase


def make_base_id(l=10):
    tid = "tid"
    for i in range(l):
        tid += random.choice(string.digits)
    return tid


class TestPlugin(ExchangePluginBase):
    """
    An Exchange Plugin for testing purposes only. Fakes all data.
    """
    NAME = 'Test'
    _user = None
    session = None

    """
    Action methods, and passive methods for synchronizing data.
    Override each of these!
    """

    @classmethod
    def sync_book(cls, market=None):
        """
        Sync the orderbook for this exchange.

        :param market str: If the exchange supports multiple markets, then the "market" param
                     can be used to specify a given orderbook. In case the exchange
                     does not support that, then the "market" param is ignored.

        :return: a list of bids and asks
        :rtype: list
        """
        pass

    def cancel_orders(self, oid=None, order_id=None, side=None, market=None):
        """
        Cancel all orders, or optionally just those matching the parameters.
        :return: True if orders were successfully canceled or no orders exist,
                otherwise False
        :rtype: bool
        """
        query = self.session.query(em.LimitOrder).filter(em.LimitOrder.exchange == self.NAME.lower()) \
            .filter(em.LimitOrder.state != 'closed')
        order_id = order_id if order_id is None or ("|" in str(order_id)) \
            else '%s|%s' % (self.NAME.lower(), order_id)
        query = filter_query_by_attr(query, em.LimitOrder, 'id', oid)
        query = filter_query_by_attr(query, em.LimitOrder, 'order_id', order_id)
        query = filter_query_by_attr(query, em.LimitOrder, 'side', side)
        query = filter_query_by_attr(query, em.LimitOrder, 'market', market)
        for order in query:
            if side is not None:
                assert order.side == side
            order.state = 'closed'
        self.session.commit()

    def create_order(self, oid):
        """
        Create a new order of a given market for a given size, at a certain price
        and a specific type.
        :return: The unique order id given by the exchange
        :rtype: str
        """
        order = self.session.query(em.LimitOrder).filter(em.LimitOrder.id == oid).one_or_none()
        order.load_commodities()
        return order

    def sync_orders(self, market=None):
        """
        :param market : Some exchanges return all open orders in one call, while
                      other exchanges require a market to be specified. If an exchange
                      does not require a market param, then the "market" param is ignored.

        :return:  a list of open orders as Order objects.
        :rtype: list
        """
        oorders = self.session.query(em.LimitOrder).filter(em.LimitOrder.exchange == self.NAME.lower()) \
            .filter(em.LimitOrder.state == 'open')
        oorders = filter_query_by_attr(oorders, em.LimitOrder, 'market', market)
        for oorder in oorders:
            oorder.state = 'closed'
            self.session.add(oorder)
        porders = self.session.query(em.LimitOrder).filter(em.LimitOrder.exchange == self.NAME.lower()) \
            .filter(em.LimitOrder.state == 'pending')
        porders = filter_query_by_attr(porders, em.LimitOrder, 'market', market)
        for porder in porders:
            porder.state = 'open'
            porder.order_id = porder.order_id.replace("tmp", self.NAME.lower())
            self.session.add(porder)
        self.session.commit()

    def sync_balances(self):
        """
        :return: the balances for a exchange. A tuple with the total balance first then available. (total, available)
        """
        total = Balance(Amount("0 USD")) + Amount("0 BTC")
        for amount in total:
            bal = self.session.query(wm.Balance).filter(wm.Balance.user_id == self.manager_user.id).one_or_none()
            if not bal:
                bal = wm.Balance(amount, amount, str(amount.commodity), "", self.manager_user.id)
            else:
                bal.amount = amount
                bal.available = amount
            self.session.add(bal)
        self.session.commit()

    def sync_ticker(self, market=None):
        """
        Return the current ticker for this exchange.
        :param market: If the exchange supports multiple markets, then the "market" param
                     can be used to specify a given orderbook. In case the exchange
                     does not support that, then the "market" param is ignored.

        :return: a Ticker with at minimum bid, ask and last.
        :rtype: Ticker
        """
        tick = em.Ticker(99, 101, 110, 90, 1000,
                         100, market, 'test')
        jtick = jsonify2(tick, 'Ticker')
        self.red.set('%s_%s_ticker' % (self.NAME.lower(), market), jtick)

    def sync_trades(self):
        """
        :return: a list of trades, possibly only a subset of them.
        """
        trade = em.Trade(make_base_id(), self.NAME.lower(), 'BTC_USD', 'buy',  0.01, 100, 0, 'quote')
        print trade
        self.session.add(trade)
        self.session.commit()

    def sync_credits(self):
        """
        :return: a list of credits, possibly only a subset of them.
        """
        credit = wm.Credit(1, make_base_id(10), 'BTC', 'Bitcoin', 'unconfirmed', "test", make_base_id(10),
                           self.manager_user.id, time=datetime.datetime.utcnow())
        print credit
        self.session.add(credit)
        self.session.commit()

    def sync_debits(self):
        """
        :return: a list of debits, possibly only a subset of them.
        """
        debit = wm.Debit(1, 0, make_base_id(10), 'BTC', 'Bitcoin', 'unconfirmed', "test", make_base_id(10),
                         self.manager_user.id, time=datetime.datetime.utcnow())
        print debit
        self.session.add(debit)
        self.session.commit()


def main():
    tp = TestPlugin(session=ses)
    daemon_runner = runner.DaemonRunner(tp)
    daemon_runner.daemon_context.signal_map[signal.SIGTERM] = tp.terminate
    daemon_runner.do_action()


if __name__ == "__main__":
    main()
