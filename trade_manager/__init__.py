import collections
import ConfigParser
import os
import time
from sqlalchemy_models import (wallet as wm, exchange as em, user as um,
                               create_session_engine, setup_database,
                               setup_logging)

CFG = ConfigParser.ConfigParser()
CFG.read(os.environ.get('TRADE_MANAGER_CONFIG_FILE', 'cfg.ini'))

ses, eng = create_session_engine(cfg=CFG)
setup_database(eng, modules=[wm, em, um])

logger = setup_logging(cfg=CFG)


class ExchangeError(Exception):
    """
    An error from one of the exchanges.
    """

    def __init__(self, exchange, message):
        self.exchange = exchange
        self.error = message
        super(ExchangeError, self).__init__(message)

    def __str__(self):
        return str(self.exchange) + ":\t" + str(self.error)


def make_ledger(exchange=None):
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


def guess_network_by_currency(currency):
    if currency == "BTC":
        return "Bitcoin"
    elif currency == "DASH":
        return "Dash"
    elif currency == "ETH":
        return "Ethereum"
    elif currency == "LTC":
        return "Litecoin"
