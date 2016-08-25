import argparse
import sys
import time
from ledger import Amount
from tapp_config import setup_redis
from trade_manager import ses
from trade_manager.plugin import sync_ticker, get_ticker, sync_orders, make_ledger, get_orders, cancel_orders, \
    get_balances, sync_balances, get_trades, sync_trades, create_order, sync_credits, sync_debits, add_active_market, \
    rem_active_market, set_preferred_exchange, get_preferred_exchange, sync_book, get_commodity_config, \
    set_commodity_config

red = setup_redis()


def handle_ticker_command(argv, parsers):
    parser = argparse.ArgumentParser(parents=parsers)
    parser.add_argument("subcommand", choices=["get", "sync"], help='The order sub-command to run.')
    parser.add_argument("-m", help='The market to get a ticker for.')
    parser.add_argument("-e", help='The exchange to get a ticker for.')
    args = parser.parse_args(argv)
    if args.subcommand == "get":
        return get_ticker(args.e, args.m, red=red)
    elif args.subcommand == "sync":
        sync_ticker(args.e, args.m)


def handle_ledger_command(argv, parsers, session=ses):
    parser = argparse.ArgumentParser(parents=parsers)
    parser.add_argument("subcommand", choices=["get", "sync"], help='The ledger sub-command to run.')
    parser.add_argument("-e", help='The exchange to get a ledger for.')
    parser.add_argument('--rescan', dest='rescan', action='store_true')
    parser.add_argument('--no-rescan', dest='rescan', action='store_false')
    parser.set_defaults(rescan=False)
    args = parser.parse_args(argv)
    if args.subcommand == "get":
        return make_ledger(exchange=args.e, session=session)
    elif args.subcommand == "sync":
        sync_credits(exchange=args.e, rescan=args.rescan)
        sync_debits(exchange=args.e, rescan=args.rescan)


def handle_order_command(argv, parsers, session=ses):
    oparser = argparse.ArgumentParser(parents=parsers, add_help=False)
    oparser.add_argument("subcommand", choices=['get', 'sync', 'create', 'cancel'], help='Order sub-commands')

    args = oparser.parse_args(argv[0:2])
    # parsers.append(oparser)
    parsers = [oparser]
    if args.subcommand == 'get':
        return handle_get_order(argv, parsers, session=session)
    elif args.subcommand == 'sync':
        return handle_sync_order(argv, parsers)
    elif args.subcommand == 'create':
        return handle_create_order(argv, parsers, session=session)
    elif args.subcommand == 'cancel':
        return handle_cancel_order(argv, parsers)


def handle_get_order(argv, parsers, session=ses):
    oparser = argparse.ArgumentParser(parents=parsers)
    oparser.add_argument("--oid", help='The order id.')
    oparser.add_argument("--order_id", help='The order order_id.')
    oparser.add_argument("-m", help='The order market.')
    oparser.add_argument("-e", help='The order exchange.')
    args = oparser.parse_args(argv)
    return get_orders(exchange=args.e, market=args.m, oid=args.oid, order_id=args.order_id, session=session)


def handle_sync_order(argv, parsers):
    oparser = argparse.ArgumentParser(parents=parsers)
    oparser.add_argument("--oid", help='The order id to sync.')
    oparser.add_argument("-e", help='The order exchange.')
    args = oparser.parse_args(argv)
    data = {}
    if args.oid:
        data['oid'] = args.oid
    sync_orders(args.e, data)


def handle_create_order(argv, parsers, session=ses):
    oparser = argparse.ArgumentParser(parents=parsers)
    oparser.add_argument("side", choices=['bid', 'ask'], help='The order side')
    oparser.add_argument("amount", help='The order amount')
    oparser.add_argument("price", help='The order price')
    oparser.add_argument("market", help='The order market')
    oparser.add_argument("exchange", help='The order exchange')
    args = oparser.parse_args(argv)
    return create_order(args.exchange, float(args.price), float(args.amount), args.market, args.side, session=session)


def handle_cancel_order(argv, parsers):
    oparser = argparse.ArgumentParser(parents=parsers)
    oparser.add_argument("--oid", help='The order id to cancel.')
    oparser.add_argument("--order_id", help='The order order_id.')
    oparser.add_argument("e", help='The order exchange. (required)')
    oparser.add_argument("-m", help='The order market.')
    oparser.add_argument("-s", help='The order side.')
    args = oparser.parse_args(argv)
    return cancel_orders(args.e, args.m, side=args.s, oid=args.oid, order_id=args.order_id)


def handle_balance_command(argv, parsers, session=ses):
    bparser = argparse.ArgumentParser(parents=parsers)
    bparser.add_argument("subcommand", choices=["get", "sync", "summary"], help='The balance sub-command to run.')
    bparser.add_argument("-e", help='The exchange.')
    bparser.add_argument("-c", help='The currency.')
    args = bparser.parse_args(argv)
    if args.subcommand == 'get':
        bals = get_balances(exchange=args.e, currency=args.c, session=session)
        rbals = []
        for bal in bals:
            rbals.append(bal.to_string())
        return rbals
    elif args.subcommand == 'sync':
        return sync_balances(args.e)
    elif args.subcommand == 'summary':
        return get_balance_summary(session=session)


def get_balance_summary(session=ses):
    bals = get_balances(session=session)
    resp = "\n_______ %s _______\n" % time.asctime(time.gmtime(time.time()))
    usdtotal = Amount("0 USD")
    details = {}
    for amount in bals[0]:
        comm = str(amount.commodity)
        if comm == 'USD':
            inde = Amount("1 USD")
            details['USD'] = {'index': inde, 'amount': amount}
            usdtotal = usdtotal + amount
        else:
            ticker = get_ticker(market="%s_USD" % comm, red=red)
            if not ticker:
                resp += "skipping inactive bal %s\n" % amount
                continue
            inde = ticker.calculate_index()
            details[comm] = {'index': inde, 'amount': Amount("%s USD" % amount.number()) * inde}
            usdtotal = usdtotal + details[comm]['amount']
    resp += "\nTotal Value:\t$%s\n\n" % usdtotal.number()

    for amount in bals[0]:
        comm = str(amount.commodity)
        if comm in details:
            damount = details[comm]['amount'].to_double()
            percent = (details[comm]['amount'] / usdtotal * Amount("100 USD")).to_double()
            resp += "{0:16s}\t==\t${1:8.2f} ({2:3.2f}%)\t@ ${3:8.4f}\n".format(amount, damount,
                                                                               percent,
                                                                               details[comm]['index'].to_double())
    return resp


def handle_trade_command(argv, parsers, session=ses):
    tparser = argparse.ArgumentParser(parents=parsers)
    tparser.add_argument("subcommand", choices=["get", "sync"], help='The trade sub-command to run.')
    tparser.add_argument("-m", help='The market to get trades for.')
    tparser.add_argument("-e", help='The exchange to get trades for.')
    tparser.add_argument("--tid", help='The trade id to get.')
    tparser.add_argument('--rescan', dest='rescan', action='store_true')
    tparser.add_argument('--no-rescan', dest='rescan', action='store_false')
    tparser.set_defaults(rescan=False)
    args = tparser.parse_args(argv)

    if args.subcommand == "get":
        return get_trades(args.e, args.m, args.tid, session=session)
    elif args.subcommand == "sync":
        return sync_trades(exchange=args.e, market=args.m, rescan=args.rescan)


def handle_market_command(argv, parsers):
    parser = argparse.ArgumentParser(parents=parsers)
    parser.add_argument("subcommand", choices=["add", "rem", "pref"], help='The configure markets sub-command to run.')
    parser.add_argument("market", help='The market to configure.')
    parser.add_argument("exchange", help='The exchange to configure with a market.')
    args = parser.parse_args(argv)
    if args.subcommand == "add":
        add_active_market(market=args.market, exchange=args.exchange)
    elif args.subcommand == "rem":
        rem_active_market(market=args.market, exchange=args.exchange)
    elif args.subcommand == "pref":
        if args.exchange is not None and args.exchange != "":
            set_preferred_exchange(market=args.market, exchange=args.exchange)
        else:
            set_preferred_exchange(market=args.market, exchange=None)


def handle_commodity_command(argv, parsers):
    parser = argparse.ArgumentParser(parents=parsers)
    parser.add_argument("subcommand", choices=["get", "set"],
                        help='The configure commodity sub-command to run.')
    parser.add_argument("commodity", help='The commodity to configure.')
    parser.add_argument("weight", help='The weight to give this commodity in deciding exposure.'
                                       ' Higher == more exposure')
    parser.add_argument("floor", help='The commodity percent of total holdings floor.')
    parser.add_argument("target", help='The commodity percent of total holdings target.')
    parser.add_argument("ceil", help='The commodity percent of total holdings ceiling.')
    args = parser.parse_args(argv)
    if args.subcommand == "get":
        return get_commodity_config(args.commodity)
    elif args.subcommand == "set":
        set_commodity_config(args.commodity, weight=args.weight, cfloor=args.floor, ctarget=args.target,
                             cceil=args.ceil)


# def handle_book_command(argv, parsers):
#     parser = argparse.ArgumentParser(parents=parsers)
#     parser.add_argument("subcommand", choices=["get", "sync"], help='The book sub-command to run.')
#     parser.add_argument("-m", help='The market to get a book for.')
#     parser.add_argument("-e", help='The exchange to get a book for.')
#     args = parser.parse_args(argv)
#     if args.subcommand == "get":
#         return get_book(args.e, args.m, red=red)
#     elif args.subcommand == "sync":
#         sync_book(args.e, args.m)


def handle_command(argv=sys.argv[1:], session=ses):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("command", choices=['ticker', 'ledger', 'order', 'trade', 'balance', 'address', 'market',
                                            'commodity'],
                        help="'%(prog)s <command> help' for usage details")
    if len(argv) == 0:
        parser.print_help()
        sys.exit()
    argvlimited = [argv[0]]
    args = parser.parse_args(argvlimited)
    if args.command == 'ticker':
        return handle_ticker_command(argv, [parser])
    elif args.command == 'ledger':
        return handle_ledger_command(argv, [parser], session=session)
    # elif args.command == 'book':
    #     return handle_book_command(argv, [parser], session=session)
    elif args.command == 'order':
        return handle_order_command(argv, [parser], session=session)
    elif args.command == 'trade':
        return handle_trade_command(argv, [parser], session=session)
    elif args.command == 'balance':
        return handle_balance_command(argv, [parser], session=session)
    elif args.command == 'market':
        return handle_market_command(argv, [parser])
    elif args.command == 'commodity':
        return handle_commodity_command(argv, [parser])


if __name__ == "__main__":
    result = handle_command()
    if result is not None:
        print(result)
