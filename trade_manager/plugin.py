import json

from trade_manager import CFG, em, um, wm, ses, logger
from sqlalchemy_models import sa, Base, util
import datetime
import importlib
import random
import string
from ledger import commodities


def load_plugins():
    plugins = {}
    for section in CFG.sections():
        if section not in ['db', 'bitjws', 'log', 'test', 'internal']:
            # assume section refers to a plugin module
            pname = "%s_manager" % section
            plugins[section] = importlib.import_module(pname)
    plugins['internal'] = InternalExchangePlugin()
    return plugins


def make_internal_id(l=10):
    tid = "tid"
    for i in range(l):
        tid += random.choice(string.digits)
    return tid


class InternalExchangePlugin(object):
    NAME = 'Internal'
    KEY = 'PubKey'
    _user = None
    session = None

    def __init__(self, key=None, secret=None, session=None):
        if key is not None:
            self.key = key
        else:
            self.key = CFG.get(self.NAME.lower(), 'key')

        if secret is not None:
            self.secret = secret
        else:
            self.secret = CFG.get(self.NAME.lower(), 'secret')
        if session is not None:
            self.session = session
        else:
            self.session = ses

        markets = json.loads(CFG.get(self.NAME.lower(), 'live_pairs'))
        self.active_currencies = set()
        for mark in markets:
            self.active_currencies = self.active_currencies.union(set(mark.split("_")))
        assert len(self.active_currencies) > 0

    def cancel_order(self, oid, pair=None):
        """Cancel a specific order.
        :return: True if order was already or now canceled, otherwise False
        :rtype: bool
        """
        pass

    def cancel_orders(self, otype=None, pair=None):
        """Cancel all orders, or optionally just those of a given type.
        :return: True if orders were successfully canceled or no orders exist, otherwise False
        :rtype: bool
        """
        pass

    def create_order(self, amount, price, otype, pair=None):
        """
        Create a new order of a given pair for a given size, at a certain price and 
        a specific type.
        :return: The unique order id given by the exchange
        :rtype: str
        """
        pass
    
    @classmethod
    def format_pair(cls, pair):
        """
        The default pair symbol is an uppercase string consisting of the base currency 
        on the left and the quote currency on the right, separated by an underscore.
        
        If the data provided by the exchange does not match the default
        implementation, then this method must be re-implemented.
        """
        pass

    @classmethod
    def unformat_pair(cls, pair):
        """
        Reverse format a pair to the format recognized by the exchange.
        If the data provided by the exchange does not match the default
        implementation, then this method must be re-implemented.        
        """
        pass

    def get_balance(self, btype='total'):
        """
        :param str btype: Balance types of 'total', 'available', and 'all' are supported.
        :return: the balance(s) for a exchange. If a btype of 'all' is specified, a tuple with the total balance first
                 then available. (total, available)
        """
        pass

    def get_open_orders(self, pair=None):
        """
        :param pair : Some exchanges return all open orders in one call, while 
                      other exchanges require a pair to be specified. If an exchange 
                      does not require a pair param, then the "pair" param is ignored.

        :return:  a list of open orders as Order objects.
        :rtype: list
        """
        pass

    @classmethod
    def get_order_book(cls, pair=None):
        """
        Get the orderbook for this exchange.

        :param pair str: If the exchange supports multiple pairs, then the "pair" param
                     can be used to specify a given orderbook. In case the exchange
                     does not support that, then the "pair" param is ignored.

        :return: a list of bids and asks
        :rtype: list
        """
        pass

    @classmethod
    def get_ticker(cls, pair=None):
        """
        Return the current ticker for this exchange.
        :param pair: If the exchange supports multiple pairs, then the "pair" param
                     can be used to specify a given orderbook. In case the exchange
                     does not support that, then the "pair" param is ignored.

        :return: a Ticker with at minimum bid, ask and last.
        :rtype: Ticker
        """
        pass

    def get_trades(self, begin=None, end=None, pair=None, offset=None,
                   limit=None):
        """
        :param limit: ?
        :return: a list of trades, possibly only a subset of them.
        """
        pass

    def get_deposit_address(self):
        """
        :return: a bitcoin address for making deposits to your account."""
        pass

    def get_nonce_db(self):
        class DBNonce(Base):
            __tablename__ = "%s_%s_nonce" % (self.name, self.key)

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

    def base_commodity(self, pair):
        return commodities.find_or_create(self.format_pair(pair).split("_")[0])

    def quote_commodity(self, pair):
        return commodities.find_or_create(self.format_pair(pair).split("_")[1])

    def save_trades(self, begin=None, end=None, pair=None):
        self.session.add(em.Trade(make_internal_id(), 'internal',
                              'BTC_USD', 'buy', 1, 100, 0, 'base',
                              datetime.datetime.utcnow()))
        self.session.add(em.Trade(make_internal_id(), 'internal',
                              'BTC_USD', 'sell', 1, 100, 0, 'base',
                              datetime.datetime.utcnow()))
        self.session.commit()

    def save_credits(self, begin=None, end=None, pair=None):
        self.session.add(wm.Credit(1, make_internal_id(), 'BTC', "Bitcoin", "complete", make_internal_id(),
                          "bitcoin|%s" % make_internal_id(), self.get_manager_user().id, datetime.datetime.utcnow()))
        self.session.commit()

    def save_debits(self, begin=None, end=None, pair=None):
        self.session.add(wm.Debit(1, 0.0001, make_internal_id(), 'BTC', "Bitcoin", "complete", make_internal_id(),
                          "bitcoin|%s" % make_internal_id(), self.get_manager_user().id, datetime.datetime.utcnow()))
        self.session.commit()

    def get_manager_user(self):
        """
        Get the User associated with this exchange Manager.
        This User is the owner of Credits, Debits, and other records for the exchange.

        :rtype: User
        :return: The Manager User
        """
        if not self._user:
            # try to get existing user
            self._user = ses.query(um.User).filter(um.User.username == '%sManager' % self.NAME) \
                .first()
        if not self._user:
            # create a new user
            userpubkey = CFG.get(self.NAME.lower(), 'userpubkey')
            self._user = util.create_user('%sManager' % self.NAME, userpubkey, self.session)
        return self._user
