import time
from ledger import Amount, Balance

from alchemyjsonschema.dictify import datetime_rfc3339

from helper import TestPlugin, make_base_id
from sqlalchemy_models import get_schemas, exchange as em, wallet as wm
from test.helper import check_test_ticker
from trade_manager.plugin import get_ticker, get_balances, get_orders, get_trades, make_ledger, get_debits, get_credits

tp = TestPlugin()
tp.setup_connections()
tp.setup_logger()
SCHEMAS = get_schemas()


def test_ticker():
    tp.sync_ticker('BTC_USD')
    ticker = get_ticker('helper', market='BTC_USD')
    check_test_ticker(ticker)


def test_balance():
    tp.sync_balances()
    total, available = get_balances('helper', session=tp.session)
    assert isinstance(total, Balance)
    assert isinstance(available, Balance)
    for amount in total:
        assert amount >= available.commodity_amount(amount.commodity)


def test_order_lifecycle():
    order = em.LimitOrder(100, 0.1, 'BTC_USD', 'bid', 'helper', order_id=make_base_id(l=10))
    assert isinstance(order.price, Amount)
    assert order.price == Amount("100 USD")
    assert order.state == 'pending'
    tp.session.add(order)
    tp.session.commit()
    assert isinstance(order.id, int)
    torder = tp.create_order(order.id)
    assert torder.id == order.id
    assert isinstance(torder.id, int)
    assert isinstance(torder.price, Amount)
    assert torder.price == Amount("100 USD")
    assert torder.state == 'open'


def test_cancel_order_order_id():
    order = em.LimitOrder(100, 0.1, 'BTC_USD', 'bid', 'helper', order_id=make_base_id(l=10))
    tp.session.add(order)
    tp.session.commit()
    order = tp.create_order(order.id)
    assert isinstance(order.id, int)
    assert isinstance(order.price, Amount)
    assert order.price == Amount("100 USD")
    assert order.state == 'open'
    tp.cancel_orders(order_id=order.order_id)
    corder = get_orders(oid=order.id, session=tp.session)
    assert len(corder) == 1
    assert corder[0].state == 'closed'


def test_cancel_order_order_id_no_prefix():
    order = em.LimitOrder(100, 0.1, 'BTC_USD', 'bid', 'helper', order_id=make_base_id(l=10))
    tp.session.add(order)
    tp.session.commit()
    order = tp.create_order(order.id)
    assert isinstance(order.id, int)
    assert isinstance(order.price, Amount)
    assert order.price == Amount("100 USD")
    assert order.state == 'open'
    tp.cancel_orders(order_id=order.order_id.split("|")[1])
    corder = get_orders(oid=order.id, session=tp.session)
    assert len(corder) == 1
    assert corder[0].state == 'closed'


def test_cancel_orders_by_side():
    order = em.LimitOrder(100, 0.1, 'BTC_USD', 'bid', 'helper', order_id=make_base_id(l=10))
    tp.session.add(order)
    order2 = em.LimitOrder(100, 0.1, 'BTC_USD', 'bid', 'helper', order_id=make_base_id(l=10))
    tp.session.add(order2)
    tp.session.commit()
    tp.create_order(order.id)
    tp.create_order(order2.id)
    obids = len(get_orders(exchange='helper', side='bid', state='open', session=tp.session))
    assert obids >= 2
    order = em.LimitOrder(100, 0.1, 'BTC_USD', 'ask', 'helper', order_id=make_base_id(l=10))
    tp.session.add(order)
    order2 = em.LimitOrder(100, 0.1, 'BTC_USD', 'ask', 'helper', order_id=make_base_id(l=10))
    tp.session.add(order2)
    tp.session.commit()
    tp.create_order(order.id)
    tp.create_order(order2.id)
    oasks = len(get_orders(exchange='helper', side='ask', state='open', session=tp.session))
    assert oasks >= 2
    tp.cancel_orders(side='bid')
    bids = len(get_orders(exchange='helper', side='bid', state='open', session=tp.session))
    assert bids == 0
    asks = len(get_orders(exchange='helper', side='ask', state='open', session=tp.session))
    assert asks > 0
    assert oasks == asks


def test_cancel_orders_by_market():
    order = em.LimitOrder(100, 0.1, 'BTC_USD', 'bid', 'helper', order_id=make_base_id(l=10))
    tp.session.add(order)
    order2 = em.LimitOrder(100, 0.1,  'BTC_USD', 'bid', 'helper', order_id=make_base_id(l=10))
    tp.session.add(order2)
    tp.session.commit()
    tp.create_order(order.id)
    tp.create_order(order2.id)
    obids = len(get_orders(exchange='helper', side='bid', state='open', session=tp.session))
    assert obids >= 2
    order = em.LimitOrder(100, 0.1, 'BTC_USD', 'ask', 'helper', order_id=make_base_id(l=10))
    tp.session.add(order)
    order2 = em.LimitOrder(100, 0.1, 'BTC_USD', 'ask', 'helper', order_id=make_base_id(l=10))
    tp.session.add(order2)
    order3 = em.LimitOrder(100, 0.1, 'DASH_BTC', 'ask', 'helper', order_id=make_base_id(l=10))
    tp.session.add(order3)
    tp.session.commit()
    tp.create_order(order.id)
    tp.create_order(order2.id)
    tp.create_order(order3.id)
    oasks = len(get_orders(exchange='helper', side='ask', state='open', session=tp.session))
    assert oasks >= 3
    tp.cancel_orders(market='BTC_USD')
    bids = len(get_orders(exchange='helper', side='bid', state='open', session=tp.session))
    assert bids == 0
    asks = len(get_orders(exchange='helper', side='ask', state='open', session=tp.session))
    assert asks >= 1


def test_get_trades():
    trade = em.Trade(make_base_id(l=10), 'helper', 'BTC_USD', 'buy', 0.1, 100, 0, 'quote')
    assert isinstance(trade.price, Amount)
    assert trade.price == Amount("100 USD")
    tp.session.add(trade)
    trade2 = em.Trade(make_base_id(l=10), 'kraken', 'BTC_USD', 'sell', 0.1, 100, 0, 'quote')
    tp.session.add(trade2)
    trade3 = em.Trade(make_base_id(l=10), 'helper', 'DASH_BTC', 'buy', 0.1, 100, 0, 'quote')
    tp.session.add(trade3)
    trade4 = em.Trade(make_base_id(l=10), 'helper', 'BTC_USD', 'buy', 0.1, 100, 0, 'quote')
    tp.session.add(trade4)
    tp.session.commit()
    assert isinstance(trade.id, int)

    trades = get_trades(tid=trade.id, session=tp.session)
    assert len(trades) == 1
    assert trades[0].id == trade.id

    trades = get_trades(trade_id=trade.trade_id, session=tp.session)
    assert len(trades) == 1
    assert trades[0].id == trade.id

    trades = get_trades('helper', trade_id=trade.trade_id.split("|")[1], session=tp.session)
    assert len(trades) == 1
    assert trades[0].id == trade.id

    trades = get_trades(exchange='kraken', session=tp.session)
    assert len(trades) >= 1
    for trade in trades:
        assert trade.exchange == 'kraken'

    trades = get_trades(market='DASH_BTC', session=tp.session)
    assert len(trades) >= 1
    for trade in trades:
        assert trade.market == 'DASH_BTC'


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
    ;<Trade(trade_id='{4}', side='buy', amount=0.01000000 BTC, price=100.00000000 USD, fee=0.00000000 USD, fee_side='quote', market='BTC_USD', exchange='helper', time={3})>
    Assets:helper:USD    -1.00000000 USD @ 0.01000000 BTC
    FX:BTC_USD:buy   1.00000000 USD @ 0.01000000 BTC
    Assets:helper:BTC    0.01000000 BTC @ 100.00000000 USD
    FX:BTC_USD:buy   -0.01000000 BTC @ 100.00000000 USD

""".format(credit.time.strftime('%Y/%m/%d %H:%M:%S'), debit.time.strftime('%Y/%m/%d %H:%M:%S'),
           trade.time.strftime('%Y/%m/%d %H:%M:%S'),
           datetime_rfc3339(trade.time), trade.trade_id)
    assert ledger == hardledger
