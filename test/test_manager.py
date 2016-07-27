import json
from ledger import Amount
from ledger import Balance

from jsonschema import validate
from sqlalchemy_models import get_schemas, exchange as em

from test.helpers import TestPlugin, make_base_id
from trade_manager.plugin import get_ticker, get_balances, get_orders, get_trades

tp = TestPlugin()
SCHEMAS = get_schemas()


def test_ticker():
    tp.sync_ticker('BTC_USD')
    ticker = get_ticker('test', 'BTC_USD')
    tick = json.loads(ticker)
    assert validate(tick, SCHEMAS['Ticker']) is None


def test_balance():
    tp.sync_balances()
    total, available = get_balances('test', session=tp.session)
    assert isinstance(total, Balance)
    assert isinstance(available, Balance)
    for amount in total:
        assert amount >= available.commodity_amount(amount.commodity)


def test_order_lifecycle():
    order = em.LimitOrder(100, 0.1, 'BTC_USD', 'bid', 'test', order_id=make_base_id(l=10))
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
    assert torder.state == 'pending'


def test_cancel_order_order_id():
    order = em.LimitOrder(100, 0.1, 'BTC_USD', 'bid', 'test', order_id=make_base_id(l=10))
    tp.session.add(order)
    tp.session.commit()
    order = tp.create_order(order.id)
    assert isinstance(order.id, int)
    assert isinstance(order.price, Amount)
    assert order.price == Amount("100 USD")
    assert order.state == 'pending'
    porder = get_orders(oid=order.id, session=tp.session)
    assert len(porder) == 1
    assert porder[0].state == 'pending'
    tp.sync_orders()
    oorder = get_orders(oid=order.id, session=tp.session)
    assert len(oorder) == 1
    assert oorder[0].state == 'open'
    tp.cancel_orders(order_id=order.order_id)
    corder = get_orders(oid=order.id, session=tp.session)
    assert len(corder) == 1
    assert corder[0].state == 'closed'


def test_cancel_order_order_id_no_prefix():
    order = em.LimitOrder(100, 0.1, 'BTC_USD', 'bid', 'test', order_id=make_base_id(l=10))
    tp.session.add(order)
    tp.session.commit()
    order = tp.create_order(order.id)
    assert isinstance(order.id, int)
    assert isinstance(order.price, Amount)
    assert order.price == Amount("100 USD")
    assert order.state == 'pending'
    porder = get_orders(oid=order.id, session=tp.session)
    assert len(porder) == 1
    assert porder[0].state == 'pending'
    tp.cancel_orders(order_id=order.order_id.split("|")[1])
    corder = get_orders(oid=order.id, session=tp.session)
    assert len(corder) == 1
    assert corder[0].state == 'closed'


def test_cancel_orders_by_side():
    order = em.LimitOrder(100, 0.1, 'BTC_USD', 'bid', 'test', order_id=make_base_id(l=10))
    tp.session.add(order)
    order2 = em.LimitOrder(100, 0.1, 'BTC_USD', 'bid', 'test', order_id=make_base_id(l=10))
    tp.session.add(order2)
    tp.session.commit()
    tp.create_order(order.id)
    tp.create_order(order2.id)
    obids = tp.session.query(em.LimitOrder).filter(em.LimitOrder.side == 'bid') \
        .filter(em.LimitOrder.state != 'closed').count()
    assert obids >= 2
    order = em.LimitOrder(100, 0.1, 'BTC_USD', 'ask', 'test', order_id=make_base_id(l=10))
    tp.session.add(order)
    order2 = em.LimitOrder(100, 0.1, 'BTC_USD', 'ask', 'test', order_id=make_base_id(l=10))
    tp.session.add(order2)
    tp.session.commit()
    tp.create_order(order.id)
    tp.create_order(order2.id)
    oasks = tp.session.query(em.LimitOrder).filter(em.LimitOrder.side == 'ask') \
        .filter(em.LimitOrder.state != 'closed').count()
    assert oasks >= 2
    tp.cancel_orders(side='bid')
    bids = tp.session.query(em.LimitOrder).filter(em.LimitOrder.side == 'bid') \
        .filter(em.LimitOrder.state != 'closed').count()
    assert bids == 0
    asks = tp.session.query(em.LimitOrder).filter(em.LimitOrder.side == 'ask') \
        .filter(em.LimitOrder.state != 'closed').count()
    assert asks > 0
    assert oasks == asks


def test_cancel_orders_by_market():
    order = em.LimitOrder(100, 0.1, 'BTC_USD', 'bid', 'test', order_id=make_base_id(l=10))
    tp.session.add(order)
    order2 = em.LimitOrder(100, 0.1,  'BTC_USD', 'bid', 'test', order_id=make_base_id(l=10))
    tp.session.add(order2)
    tp.session.commit()
    tp.create_order(order.id)
    tp.create_order(order2.id)
    obids = tp.session.query(em.LimitOrder).filter(em.LimitOrder.side == 'bid') \
        .filter(em.LimitOrder.state != 'closed').count()
    assert obids >= 2
    order = em.LimitOrder(100, 0.1, 'BTC_USD', 'ask', 'test', order_id=make_base_id(l=10))
    tp.session.add(order)
    order2 = em.LimitOrder(100, 0.1, 'BTC_USD', 'ask', 'test', order_id=make_base_id(l=10))
    tp.session.add(order2)
    order3 = em.LimitOrder(100, 0.1, 'DASH_BTC', 'ask', 'test', order_id=make_base_id(l=10))
    tp.session.add(order3)
    tp.session.commit()
    tp.create_order(order.id)
    tp.create_order(order2.id)
    tp.create_order(order3.id)
    oasks = tp.session.query(em.LimitOrder).filter(em.LimitOrder.side == 'ask') \
        .filter(em.LimitOrder.state != 'closed').count()
    assert oasks >= 3
    tp.cancel_orders(market='BTC_USD')
    bids = tp.session.query(em.LimitOrder).filter(em.LimitOrder.side == 'bid') \
        .filter(em.LimitOrder.state != 'closed').count()
    assert bids == 0
    asks = tp.session.query(em.LimitOrder).filter(em.LimitOrder.side == 'ask') \
        .filter(em.LimitOrder.state != 'closed').count()
    assert asks >= 1


def test_get_trades():
    trade = em.Trade(make_base_id(l=10), 'test', 'BTC_USD', 'buy', 0.1, 100, 0, 'quote')
    assert isinstance(trade.price, Amount)
    assert trade.price == Amount("100 USD")
    tp.session.add(trade)
    trade2 = em.Trade(make_base_id(l=10), 'kraken', 'BTC_USD', 'sell', 0.1, 100, 0, 'quote')
    tp.session.add(trade2)
    trade3 = em.Trade(make_base_id(l=10), 'test', 'DASH_BTC', 'buy', 0.1, 100, 0, 'quote')
    tp.session.add(trade3)
    trade4 = em.Trade(make_base_id(l=10), 'test', 'BTC_USD', 'buy', 0.1, 100, 0, 'quote')
    tp.session.add(trade4)
    tp.session.commit()
    assert isinstance(trade.id, int)

    trades = get_trades(tid=trade.id, session=tp.session)
    assert len(trades) == 1
    assert trades[0].id == trade.id

    trades = get_trades(trade_id=trade.trade_id, session=tp.session)
    assert len(trades) == 1
    assert trades[0].id == trade.id

    trades = get_trades('test', trade_id=trade.trade_id.split("|")[1], session=tp.session)
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


def test_book():
    pass
