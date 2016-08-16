import collections
import json
import time
from ledger import commodities, Balance

import datetime

from alchemyjsonschema.dictify import jsonify
from ledger import Amount

from sqlalchemy_models import sa, Base, create_session_engine, jsonify2
from sqlalchemy_models.util import filter_query_by_attr, multiply_tickers
from tapp_config import get_config, setup_redis
from tappmq.tappmq import publish, MQHandlerBase, get_running_workers
from trade_manager import em, um, wm, ses, EXCHANGES

red = setup_redis()


class ExchangePluginBase(MQHandlerBase):
    """
    A parent class for Exchange Manager Plugins.
    Plugins should inherit from this class, and overwrite all of the methods
    that raise a NotImplementedError.
    """
    NAME = 'Base'
    KEY = 'PubKey'
    _user = None
    session = None

    def __init__(self, key=None, secret=None, session=None, engine=None, red=None, cfg=None):
        super(ExchangePluginBase, self).__init__(key=key, secret=secret, session=session, engine=engine, red=red,
                                                 cfg=cfg)
        # ensure all are active in redis
        add_active_markets(self.NAME.lower(), json.loads(self.cfg.get(self.NAME.lower(), 'active_markets')))
        self.active_markets = get_active_markets(self.NAME.lower())
        self.active_currencies = set()
        for mark in self.active_markets:
            self.active_currencies = self.active_currencies.union(set(mark.split("_")))
        assert len(self.active_currencies) > 0

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
    Normalization helpers.
    """
    def add_trade(self, market, tid, trade_side, price, amount, fee, fee_side, dtime):
        tofind = '%s|%s' % (self.NAME.lower(), tid)
        found = self.session.query(em.Trade) \
            .filter(em.Trade.trade_id == tofind).count()
        if found != 0:
            self.logger.debug("; %s already known" % tid)
            return
        trade = em.Trade(tid, self.NAME.lower(), market, trade_side, amount, price, fee, fee_side, dtime)
        self.session.add(trade)
        self.logger.info("added trade %s" % trade)
        return trade

    def update_balance(self, currency, total, available=None, reference=""):
        bal = self.session.query(wm.Balance).filter(wm.Balance.user_id == self.manager_user.id) \
                .filter(wm.Balance.currency == currency).one_or_none()
        if not bal:
            if available is None:
                available = 0
            bal = wm.Balance(total, available, currency, reference, self.manager_user.id)
            self.session.add(bal)
        else:
            bal.load_commodities()
            bal.total = total
            bal.time = datetime.datetime.utcnow()
            if available is not None:
                bal.available = available
        self.logger.info("balance set %s" % bal)

    def add_order(self, price, amount, market, side, order_id=None, create_time=None,
                  change_time=None, exec_amount=0, state='pending'):
        prefix = 'tmp' if state == 'pending' else self.NAME.lower()
        order = self.session.query(em.LimitOrder) \
            .filter(em.LimitOrder.order_id == '%s|%s' % (prefix, order_id)).one_or_none()
        if order is not None:
            try:
                assert order.market == market
                assert order.side == side
            except AssertionError:
                return
            if order.exec_amount.to_double() == exec_amount and order.state == state:
                return
            order.order_id = "%s|%s" % (self.NAME.lower(), order_id)
            order.price = price
            order.amount = amount
            order.change_time = datetime.datetime.utcnow()
            order.state = state
            order.exec_amount = exec_amount
        else:
            order = em.LimitOrder(price, amount, market, side, self.NAME.lower(), order_id, create_time, change_time,
                                  exec_amount, state)
            self.session.add(order)
        self.logger.info("added order %s" % order)
        return order

    """
    Action methods, and passive methods for synchronizing data.
    Override each of these!
    """

    def cancel_orders(self, oid=None, order_id=None, side=None, market=None, price=None):
        """
        Cancel all orders, or optionally just those matching the parameters.
        :return: True if orders were successfully canceled or no orders exist,
                otherwise False
        :rtype: bool
        """
        raise NotImplementedError()

    def cancel_stale_orders(self):
        for market in self.active_markets:
            rticker = get_ticker(self.NAME, market=market, red=self.red)  # use the redis version of ticker
            ticker = em.Ticker.from_json(rticker)
            index = ticker.get_index(market)
            self.cancel_orders(market=market, price=index)

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


def set_preferred_exchange(market, exchange):
    red.set('%s_preferred_exchange' % market, exchange)


def get_preferred_exchange(market):
    exchange = red.get('%s_preferred_exchange' % market)
    if exchange is None or exchange == "":
        for ex in EXCHANGES:
            active_markets = red.get('%s_active_markets' % ex)
            if active_markets is not None and market in json.loads(active_markets):
                return ex
    else:
        return exchange


def set_active_markets(exchange, active_markets):
    red.set('%s_active_markets' % exchange, active_markets)


def add_active_market(exchange, market):
    add_active_markets(exchange, [market])


def add_active_markets(exchange, markets):
    marks = get_active_markets(exchange)
    active_markets = json.dumps(list(set(marks + markets)))
    red.set('%s_active_markets' % exchange, active_markets)


def rem_active_market(exchange, market):
    rem_active_markets(exchange, [market])


def rem_active_markets(exchange, markets):
    active_markets = get_active_markets(exchange)
    for mark in markets:
        try:
            active_markets.remove(mark)
        except ValueError:
            # safe to ignore; market was already inactive
            continue
    red.set('%s_active_markets' % exchange, active_markets)


def get_active_markets(exchange):
    active_markets = red.get('%s_active_markets' % exchange)
    if active_markets is not None and len(active_markets) > 2:  # is not "[]"
        markets = json.loads(active_markets)
    else:
        cfg = get_config(name=exchange)
        markets = json.loads(cfg.get(exchange, 'active_markets'))
    return markets


def set_commodity_config(commodity, weight=1.0, cfloor=0.0, ctarget=0.0, cceil=0.0):
    detail = {'weight': weight, 'floor': cfloor, 'target': ctarget, 'ceil': cceil}
    red.set('%s_config' % commodity, detail)


def get_commodity_config(commodity):
    comm_cfg = red.get('%s_config' % commodity)
    detail = {'weight': 1.0, 'floor': 0.0, 'target': 0.0, 'ceil': 0.0}

    def merge_details(default, tomerge):
        for key in tomerge:
            default[key] = tomerge[key]
        return default

    if comm_cfg is not None:
        return merge_details(detail, json.loads(comm_cfg))
    else:
        return detail


def get_ticker(exchange=None, market="BTC_USD", red=None):
    if red is None:
        red = setup_redis()

    def safe_get_ticker(exch, market, red):
        gt = red.get('%s_%s_ticker' % (exch, market))
        base, quote = market.split("_")
        if gt is not None:
            return em.Ticker.from_json(gt)
        elif quote == "USD":
            t1mark = "%s_BTC" % base
            t1ex = get_preferred_exchange(t1mark)
            t1r = red.get('%s_%s_ticker' % (t1ex, t1mark))
            if t1r is None:
                return
            t1 = em.Ticker.from_json(t1r)
            t2 = get_ticker(market='BTC_USD', red=red)
            if t2 is None:
                return
            return multiply_tickers(t1, t2)

    if exchange is None:
        exch = get_preferred_exchange(market)
        return safe_get_ticker(exch, market, red)
    else:
        return safe_get_ticker(exchange.lower(), market, red)


def submit_order(exchange, oid, expire=None):
    assert isinstance(oid, int)
    data = {'oid': oid}
    if expire is not None:
        data['expire'] = expire
    publish(exchange, 'create_order', data)


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


def sync_ticker(exchange=None, market=None):
    def sync_exchange_ticker(ex, mark=None):
        if mark is None:
            for mark in get_active_markets(ex):
                publish(ex, 'sync_ticker', {'market': mark})
        else:
            publish(ex, 'sync_ticker', {'market': mark})
    if exchange is None:
        for exch in get_running_workers(EXCHANGES, red=red):
            sync_exchange_ticker(exch, market)
    else:
        sync_exchange_ticker(exchange, market)


def sync_balances(exchange, data=None):
    if data is None:
        data = {}
    publish(exchange, 'sync_balances', data)


def sync_trades(exchange, market=None, rescan=False):
    data = {'rescan': rescan}
    if market is not None:
        data['market'] = market
    publish(exchange, 'sync_trades', data)


def sync_credits(exchange, rescan=False):
    data = {'rescan': rescan}
    publish(exchange, 'sync_credits', data)


def sync_debits(exchange, rescan=False):
    data = {'rescan': rescan}
    publish(exchange, 'sync_debits', data)


"""
DB helpers
"""


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
    query = filter_query_by_attr(query, wm.Credit, 'network', exchange)
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
    query = filter_query_by_attr(query, wm.Debit, 'network', exchange)
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


def get_order_by_order_id(order_id, exchange, session=None):
    if session is None:
        session = ses
    if "|" in order_id:
        order_id = order_id.split("|")[1]
    order = session.query(em.LimitOrder)\
        .filter(em.LimitOrder.order_id == "%s|%s" % (exchange.lower(), order_id)).one_or_none()
    if order is None:
        order = session.query(em.LimitOrder).filter(
            em.LimitOrder.order_id == "tmp|%s" % order_id).one_or_none()
    return order


def get_balances(exchange=None, currency=None, session=None):
    if session is None:
        session, eng = create_session_engine()
    query = session.query(wm.Balance)
    if currency is not None:
        query = filter_query_by_attr(query, wm.Balance, 'currency', currency)
    if exchange is not None:
        query = query.join(um.User).filter(um.User.username == "%sManager" % exchange.lower())
    total = Balance()
    available = Balance()
    for bal in query:
        total = total + bal.total
        available = available + bal.available
    return total, available


def create_order(exchange, price, amount, market, side, session, submit=True, expire=None):
    order = em.LimitOrder(price, amount, market, side, exchange.lower())
    session.add(order)
    try:
        session.commit()
    except Exception as e:
        print e
        session.rollback()
        session.flush()
    order.load_commodities()
    if submit:
        submit_order(exchange, order.id, expire=expire)
    return order


"""
Math helpers
"""


def get_usd_value(amount, price=None):
    if not isinstance(amount, Amount):
        raise TypeError("requires an Amount argument")
    comm = str(amount.commodity)
    if comm == 'USD':
        return amount
    elif comm != '':
        if price is None:
            ticker = get_ticker(market="%s_USD" % comm, red=red)
            if ticker is None:
                raise TypeError("inactive commodity %s" % comm)
            else:
                price = ticker.calculate_index()
        return Amount("%s USD" % amount.number()) * price


def get_weighted_usd_volume(ticker):
    if isinstance(ticker, dict):
        ticker = em.Ticker.from_dict(ticker)
    if isinstance(ticker, str):
        ticker = em.Ticker.from_json(ticker)
    base = str(ticker.volume.commodity)
    quote = str(ticker.last.commodity)
    base_comm_cfg = get_commodity_config(base)
    quote_comm_cfg = get_commodity_config(quote)
    weight = Amount("%s USD" % base_comm_cfg['weight']) * Amount("%s USD" % quote_comm_cfg['weight'])
    if 'USD' in base:  # flexible for USDT, but is this a potential conflict?
        return weight * Amount("%s USD" % ticker.volume.number())
    elif 'USD' in quote:  # flexible for USDT, but is this a potential conflict?
        return weight * Amount("%s USD" % ticker.volume.number()) * ticker.calculate_index()
    else:
        usdprice = get_usd_value(Amount("1 %s" % base))
        return Amount("%s USD" % usdprice.number()) * Amount("%s USD" % ticker.volume.number()) * weight


def get_market_vol_shares(exchange, c=None):
    vols = {'total': Amount("0 USD")}

    for market in get_active_markets(exchange):
        if c is None:
            tick = get_ticker(exchange, market.upper())
            vols[market] = {'USD_volume': get_weighted_usd_volume(tick), 'ticker': tick}
            vols['total'] += vols[market]['USD_volume']
        elif c.upper() in market.upper():
            tick = get_ticker(exchange, market.upper())
            # pair = market.split("_")
            uvol = get_weighted_usd_volume(tick)
            vols[market] = {'USD_volume': uvol, 'ticker': tick}
            vols['total'] += vols[market]['USD_volume']
    for market in vols:
        if market == 'total':
            continue
        if vols['total'] > 0:
            vols[market]['vol_share'] = (vols[market]['USD_volume'] / vols['total']).to_double()
        else:
            vols[market]['vol_share'] = 0
    return vols


def make_ledger(exchange=None, session=ses):
    """
    Make a ledger-cli style ledger for the given exchange.
    Accounts for all trades, debits and credits in the database.

    :param str exchange: The exchange to filter for. (optional)
    :param session: The sqlalchemy session.
    :rtype: str
    :return: The ledger string.
    """
    ledger = ""
    trades = session.query(em.Trade)
    credits = session.query(wm.Credit)
    debits = session.query(wm.Debit)
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
