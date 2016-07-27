import collections
import json
import os
import time
from ledger import commodities, Balance

from sqlalchemy_models import sa, Base, util, create_session_engine
from sqlalchemy_models.util import filter_query_by_attr
from tapp_config import get_config, setup_redis
from tappmq import publish, subscription_handler

from trade_manager import em, um, wm, ses


def set_status(name, status='loading'):
    red = setup_redis()
    if status in ['loading', 'running', 'stopped']:
        print("setting %s_status to %s" % (name.lower(), status))
        red.set("%s_status" % name.lower(), status)


class ExchangePluginBase(object):
    """
    A parent class for Exchange Manager Plugins.
    Plugins should inherit from this class, and overwrite all of the methods
    that raise a NotImplementedError.
    """
    NAME = 'Base'
    KEY = 'PubKey'
    _user = None
    session = None

    def __init__(self, key=None, secret=None, session=None, red=None, cfg=None):
        self.cfg = get_config(self.NAME) if cfg is not None else get_config('trade_manager')
        self.key = key if key is not None else self.cfg.get(self.NAME.lower(), 'key')
        self.secret = secret if secret is not None else self.cfg.get(self.NAME.lower(), 'secret')
        self.session = session if session is not None else create_session_engine(cfg=self.cfg)[0]
        self.red = setup_redis() if red is None else red
        # self.logger = setup_logging(self.cfg)

        markets = json.loads(self.cfg.get(self.NAME.lower(), 'live_pairs'))
        self.active_currencies = set()
        for mark in markets:
            self.active_currencies = self.active_currencies.union(set(mark.split("_")))
        assert len(self.active_currencies) > 0

        self.stdin_path = '/dev/null'
        self.stdout_path = os.path.join(self.cfg.get('log', 'DATA_DIR'), 'stdout.log')
        self.stderr_path = os.path.join(self.cfg.get('log', 'DATA_DIR'), 'stderr.log')
        self.pidfile_path = os.path.join(self.cfg.get('log', 'DATA_DIR'), 'manager.pid')
        self.pidfile_timeout = 5

    """
    Daemonization and process management section. Do not override.
    """

    @property
    def manager_user(self):
        """
        Get the User associated with this exchange Manager.
        This User is the owner of Credits, Debits, and other records for the exchange.

        :rtype: User
        :return: The Manager User
        """
        if not self._user:
            # try to get existing user
            self._user = self.session.query(um.User).filter(um.User.username == '%sManager' % self.NAME) \
                .first()
        if not self._user:
            # create a new user
            userpubkey = self.cfg.get(self.NAME.lower(), 'userpubkey')
            self._user = util.create_user('%sManager' % self.NAME, userpubkey, self.session)
        return self._user

    def run(self):
        """
        Run this manager as a daemon. Subscribes to a redis channel matching self.NAME
        and processes messages received there.
        """
        set_status(self.NAME.lower(), 'loading')
        # TODO syncronize before subscribing..
        set_status(self.NAME.lower(), 'running')
        subscription_handler(self.NAME.lower(), client=self)

    # noinspection PyUnusedLocal
    @classmethod
    def terminate(cls, signal, stack):
        """
        A termination handler that marks the plugin status as "stopped".

        :param signal: The OS signal number received.
        :param stack: The frame object at the point the signal was received.
        :raises: SystemExit
        """
        set_status(cls.NAME.lower(), 'stopped')
        raise SystemExit("Stopped (SIGTERM)")

    """
    Optional nonce helpers. Most exchanges can simply use a timestamp.
    """

    def get_nonce_db(self):
        class DBNonce(Base):
            __tablename__ = "%s_%s_nonce" % (self.NAME.lower(), self.key)

            id = sa.Column(sa.Integer, sa.Sequence('nonce_seq'), primary_key=True,
                           doc="primary key")
            exchange = sa.Column(sa.String(16), nullable=False)
            key = sa.Column(sa.String(80), nullable=False)

        return DBNonce

    def next_nonce(self):
        """Atomically increment and get a nonce for an exchange."""
        nonce = self.get_nonce_db()()
        self.session.add()
        self.session.commit()
        return nonce.id

    def create_nonce(self, nonce):
        """
        Save a starting nonce for a given exchange.

        :param int nonce: an integer that will be incremented on each
            next_nonce call.
        :return: nonce if an entry was created, None otherwise.
        """
        n = self.next_nonce()
        while n < nonce:
            n = self.next_nonce()
        return n

    """
    Classmethods for manipulating data types.
    If exchange conforms to standards, there is no need to override these.
    """

    @classmethod
    def format_market(cls, market):
        """
        The default market symbol is an uppercase string consisting of the base commodity
        on the left and the quote commodity on the right, separated by an underscore.

        If the data provided by the exchange does not match the default
        implementation, then this method must be re-implemented.
        """
        return market

    @classmethod
    def unformat_market(cls, market):
        """
        Reverse format a market to the format recognized by the exchange.
        If the data provided by the exchange does not match the default
        implementation, then this method must be re-implemented.
        """
        return market

    @classmethod
    def format_commodity(cls, commodity):
        """
        The default commodity symbol is an uppercase string of 3 or 4 letters.

        If the data provided by the exchange does not match the default
        implementation, then this method must be re-implemented.
        """
        return commodity

    @classmethod
    def unformat_commodity(cls, commodity):
        """
        Reverse format a commodity to the format recognized by the exchange.
        If the data provided by the exchange does not match the default
        implementation, then this method must be re-implemented.
        """
        return commodity

    @classmethod
    def base_commodity(cls, market):
        """
        The commodity that is base in the market pair. Traditionally this goes first, but some
        exchanges do not conform.
        """
        return commodities.find_or_create(cls.format_market(market).split("_")[0])

    @classmethod
    def quote_commodity(cls, market):
        """
        The commodity that is quote in the market pair. Traditionally this goes last, but some
        exchanges do not conform.
        """
        return commodities.find_or_create(cls.format_market(market).split("_")[1])

    """
    Action methods, and passive methods for synchronizing data.
    Override each of these!
    """

    def cancel_orders(self, oid=None, side=None, market=None):
        """
        Cancel all orders, or optionally just those matching the parameters.
        :return: True if orders were successfully canceled or no orders exist,
                otherwise False
        :rtype: bool
        """
        raise NotImplementedError()

    def create_order(self, oid):
        """
        Create a new order of a given market for a given size, at a certain price
        and a specific type.
        :return: The unique order id given by the exchange
        :rtype: str
        """
        raise NotImplementedError()

    def sync_orders(self, market=None):
        """
        :param market : Some exchanges return all open orders in one call, while
                      other exchanges require a market to be specified. If an exchange
                      does not require a market param, then the "market" param is ignored.

        :return:  a list of open orders as Order objects.
        :rtype: list
        """
        raise NotImplementedError()

    def sync_balances(self):
        """
        :return: the balances for a exchange. A tuple with the total balance first then available. (total, available)
        """
        raise NotImplementedError()

    def sync_ticker(self, market=None):
        """
        Return the current ticker for this exchange.
        :param market: If the exchange supports multiple markets, then the "market" param
                     can be used to specify a given orderbook. In case the exchange
                     does not support that, then the "market" param is ignored.

        :return: a Ticker with at minimum bid, ask and last.
        :rtype: Ticker
        """
        raise NotImplementedError()

    def sync_trades(self):
        """
        :return: a list of trades, possibly only a subset of them.
        """
        raise NotImplementedError()

    @classmethod
    def sync_book(cls, market=None):
        """
        Get the orderbook for this exchange.

        :param str market: If the exchange supports multiple markets, then the "market" param
                     can be used to specify a given orderbook. In case the exchange
                     does not support that, then the "market" param is ignored.

        :return: a list of bids and asks
        :rtype: list
        """
        raise NotImplementedError()


"""
Redis command interface. Call these functions from anywhere and to any of the exchange managers.
"""


def get_ticker(exchange, market="BTC_USD", red=None):
    if red is None:
        red = setup_redis()
    return red.get('%s_%s_ticker' % (exchange.lower(), market))


def get_trades(exchange=None, market=None, tid=None, trade_id=None, session=None):
    if session is None:
        session, eng = create_session_engine()
    query = session.query(em.Trade)
    if trade_id is not None:
        trade_id = trade_id if "|" in str(trade_id) else '%s|%s' % (exchange.lower(), trade_id)
    query = filter_query_by_attr(query, em.Trade, 'trade_id', trade_id)
    query = filter_query_by_attr(query, em.Trade, 'exchange', exchange)
    query = filter_query_by_attr(query, em.Trade, 'market', market)
    query = filter_query_by_attr(query, em.Trade, 'id', tid)
    resp = []
    for trade in query:
        resp.append(trade)
    return resp


def get_credits(exchange=None, address=None, currency=None, ref_id=None, session=None):
    if session is None:
        session, eng = create_session_engine()
    query = session.query(wm.Credit)
    query = filter_query_by_attr(query, wm.Credit, 'ref_id', ref_id)
    query = filter_query_by_attr(query, wm.Credit, 'reference', exchange)
    query = filter_query_by_attr(query, wm.Credit, 'address', address)
    query = filter_query_by_attr(query, wm.Credit, 'currency', currency)
    resp = []
    for cred in query:
        resp.append(cred)
    return resp


def get_debits(exchange=None, address=None, currency=None, ref_id=None, session=None):
    if session is None:
        session, eng = create_session_engine()
    query = session.query(wm.Debit)
    query = filter_query_by_attr(query, wm.Debit, 'ref_id', ref_id)
    query = filter_query_by_attr(query, wm.Debit, 'reference', exchange)
    query = filter_query_by_attr(query, wm.Debit, 'address', address)
    query = filter_query_by_attr(query, wm.Debit, 'currency', currency)
    resp = []
    for deb in query:
        resp.append(deb)
    return resp


def get_orders(exchange=None, market=None, side=None, oid=None, order_id=None, state=None, session=None):
    if session is None:
        session, eng = create_session_engine()
    query = session.query(em.LimitOrder)
    if order_id is not None:
        order_id = order_id if "|" in str(order_id) else '%s|%s' % (exchange.lower(), order_id)
    query = filter_query_by_attr(query, em.LimitOrder, 'order_id', order_id)
    query = filter_query_by_attr(query, em.LimitOrder, 'market', market)
    query = filter_query_by_attr(query, em.LimitOrder, 'side', side)
    query = filter_query_by_attr(query, em.LimitOrder, 'exchange', exchange)
    query = filter_query_by_attr(query, em.LimitOrder, 'id', oid)
    query = filter_query_by_attr(query, em.LimitOrder, 'state', state)
    resp = []
    for order in query:
        resp.append(order)
    return resp


def get_balances(exchange=None, session=None):
    if session is None:
        session, eng = create_session_engine()
    query = session.query(wm.Balance)
    if exchange is not None:
        query = query.join(um.User).filter(um.User.username == "%sManager" % exchange.lower())
    total = Balance()
    available = Balance()
    for bal in query:
        total += bal.total
        available += bal.available
    return total, available


def create_order(exchange, price, amount, market, side, session=None):
    if session is None:
        session, eng = create_session_engine()
    order = em.LimitOrder(price, amount, market, side, exchange.lower())
    session.add(order)
    session.commit()
    data = {'oid': order.id}
    publish(exchange, 'create_order', data)
    order.load_commodities()
    return order


def cancel_orders(exchange, market=None, oid=None, side=None, order_id=None):
    data = {}
    if order_id is not None:
        data['order_id'] = order_id if "|" in str(order_id) else '%s|%s' % (exchange.lower(), order_id)
    if oid is not None:
        data['oid'] = oid
    if side is not None:
        data['side'] = side
    if market is not None:
        data['market'] = market
    publish(exchange, 'cancel_orders', data)


def sync_orders(exchange, data=None):
    if data is None:
        data = {}
    publish(exchange, 'sync_orders', data)


def sync_ticker(exchange, market="BTC_USD"):
    publish(exchange, 'sync_ticker', {'market': market})


def sync_balances(exchange, data=None):
    if data is None:
        data = {}
    publish(exchange, 'sync_balances', data)


def sync_trades(exchange, market=None):
    data = {}
    if market is not None:
        data['market'] = market
    publish(exchange, 'sync_trades', data)


def sync_credits(exchange):
    data = {}
    publish(exchange, 'sync_credits', data)


def sync_debits(exchange):
    data = {}
    publish(exchange, 'sync_debits', data)


def make_ledger(exchange=None):
    """
    Make a ledger-cli style ledger for the given exchange.
    Accounts for all trades, debits and credits in the database.

    :param str exchange: The exchange to filter for. (optional)
    :rtype: str
    :return: The ledger string.
    """
    ledger = ""
    trades = ses.query(em.Trade)
    credits = ses.query(wm.Credit)
    debits = ses.query(wm.Debit)
    if exchange is not None:
        trades = trades.filter(em.Trade.exchange == exchange)
        credits = credits.filter(wm.Credit.reference == exchange)
        debits = debits.filter(wm.Debit.reference == exchange)
    entries = collections.OrderedDict()

    for credit in credits:
        timmy = "%s.c%s" % (int(time.mktime(credit.time.timetuple())), credit.id)
        entries[timmy] = credit
    for debit in debits:
        timmy = "%s.d%s" % (int(time.mktime(debit.time.timetuple())), debit.id)
        entries[timmy] = debit
    for trade in trades:
        timmy = "%s.t%s" % (int(time.mktime(trade.time.timetuple())), trade.id)
        entries[timmy] = trade

    for entry in sorted(entries):
        ledger += entries[entry].get_ledger_entry()

    return ledger


def get_status(exchange, red=None):
    if red is None:
        red = setup_redis()
    status = red.get("%s_status" % exchange.lower())
    return status if status is not None else 'stopped'
