"""
Ready to go plans for managing your trades.

WARNING: Use at your own risk!
No promise of financial gain is made, and any losses from use of this software are your responsibility.
"""
import time
from ledger import Amount
from tappmq.tappmq import get_running_workers
from trade_manager.plugin import get_balances, get_market_vol_shares, get_usd_value, red, create_order, sync_balances

MINMM = Amount("5 USD")
MINORDER = Amount("1 USD")


def fib_fan(side, amount, ticker, session):
    def calc_price(sid, index, offset):
        if sid == 'ask':
            return index * (Amount("1 %s" % index.commodity) + Amount("%s %s" % (offset, index.commodity)) / 100)
        else:
            return index * (Amount("1 %s" % index.commodity) - Amount("%s %s" % (offset, index.commodity)) / 100)

    usdamount = get_usd_value(amount)
    if usdamount <= MINORDER:
        print "ignoring dusty order %s worth %s" % (usdamount, usdamount)
        return
    fibseq = [1, 2, 3, 5, 8, 13]
    index = ticker.calculate_index()
    base = ticker.market.split("_")[0]
    if usdamount / Amount("{0} USD".format(len(fibseq))) <= MINORDER:
        price = calc_price(side, index, fibseq[int(round(len(fibseq) / 2))])
        if side == 'bid':
            amount = Amount("{0:.8f} {1}".format(amount.to_double(), base)) / \
                     Amount("{0:.8f} {1}".format(index.to_double(), base))
        # usdval = get_usd_value(amount)
        # print "{0} {1} @ {2:0.6f} {3} worth ${4:0.2f})".format(side, amount, price.to_double(), ticker.market,
        #                                                        usdval.to_double())
        create_order(ticker.exchange, price=price, amount=amount, market=ticker.market, side=side, session=session)
    else:
        if side == 'bid':
            amount = Amount("{0:.8f} {1}".format((amount / len(fibseq)).to_double(), base)) / \
                     Amount("{0:.8f} {1}".format(index.to_double(), base))
        else:
            amount /= len(fibseq)
        for fib in fibseq:
            price = calc_price(side, index, fib)
            create_order(ticker.exchange, price=price, amount=amount, market=ticker.market, side=side, session=session)
            # usdval = get_usd_value(amount) * price / index
            # print "{0} {1} @ {2:0.6f} {3} worth ${4:0.2f})".format(side, amount, price.to_double(),
            #                                                        ticker.market, usdval.to_double())
    sync_balances(ticker.exchange)


def mm(exchange, callback, session):
    print "__________%s mm %s__________" % (exchange, time.asctime(time.gmtime(time.time())))
    bals = get_balances(exchange, session=session)
    if bals is not None:
        available = bals[1]
        for amount in available:
            comm = str(amount.commodity)
            try:
                value = get_usd_value(amount)
            except TypeError as e:
                print e
                continue
            if value <= MINMM:
                print "ignoring dusty %s worth %s" % (amount, value)
                continue
            vshares = get_market_vol_shares(exchange, comm)
            for market in vshares:
                if market == 'total':
                    continue
                vshare = vshares[market]['vol_share']
                if market.find(comm) == 0:  # amount is base, so we sell
                    tosell = amount * Amount("%s %s" % (vshare, comm))
                    tosellval = get_usd_value(tosell)
                    # print "sell {0} out of {1} on {2} ({3:0.2f}% worth ${4:0.2f})".format(tosell, amount, market,
                    #                                                                       vshare * 100,
                    #                                                                       tosellval.to_double())
                    callback('ask', tosell, vshares[market]['ticker'], session)
                if market.find(comm) >= 3:  # amount is quote, so we buy
                    base = market.split("_")[1]
                    tobuy = Amount("%s %s" % (amount, base)) * Amount("%s %s" % (vshare, base))
                    tobuyval = get_usd_value(tobuy)
                    # print "spend {0} out of {1} on {2} ({3:0.2f}% worth ${4:0.2f})".format(tobuy, amount, market,
                    #                                                                        vshare * 100,
                    #                                                                        tobuyval.to_double())
                    callback('bid', tobuy, vshares[market]['ticker'], session)


if __name__ == "__main__":
    from trade_manager import ses, EXCHANGES, ses, ses

    for exch in get_running_workers(EXCHANGES, red=red):
        mm(exch, fib_fan, ses)
