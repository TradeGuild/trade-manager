import argparse
import sys

from tapp_config import setup_redis

from trade_manager import ses
from trade_manager.plugin import sync_ticker, get_ticker, sync_orders, make_ledger, get_orders, cancel_orders, \
    get_balances, sync_balances, get_trades, sync_trades, create_order

red = setup_redis()


def handle_ticker_command(argv, parsers):
    parser = argparse.ArgumentParser(parents=parsers)
    parser.add_argument("subcommand", choices=["get", "sync"], help='The order sub-command to run.')
    parser.add_argument("-m", default="BTC_USD", help='The market to get a ticker for.')
    parser.add_argument("-e", help='The exchange to get a ticker for.')
    args = parser.parse_args(argv)
    if args.subcommand == "get":
        return get_ticker(args.e, args.m, red=red)
    elif args.subcommand == "sync":
        sync_ticker(args.e, args.m)


def handle_ledger_command(argv, parsers):
    parser = argparse.ArgumentParser(parents=parsers)
    parser.add_argument("-e", help='The exchange to get a ledger for.')
    args = parser.parse_args(argv)
    exchange = args.e
    return make_ledger(exchange=exchange)


def handle_order_command(argv, parsers):
    oparser = argparse.ArgumentParser(parents=parsers, add_help=False)
    oparser.add_argument("subcommand", choices=['get', 'sync', 'create', 'cancel'], help='Order sub-commands')

    args = oparser.parse_args(argv[0:2])
    # parsers.append(oparser)
    parsers = [oparser]
    if args.subcommand == 'get':
        return handle_get_order(argv, parsers)
    elif args.subcommand == 'sync':
        return handle_sync_order(argv, parsers)
    elif args.subcommand == 'create':
        return handle_create_order(argv, parsers)
    elif args.subcommand == 'cancel':
        return handle_cancel_order(argv, parsers)


def handle_get_order(argv, parsers):
    oparser = argparse.ArgumentParser(parents=parsers)
    oparser.add_argument("--oid", help='The order id.')
    oparser.add_argument("--order_id", help='The order order_id.')
    oparser.add_argument("-m", help='The order market.')
    oparser.add_argument("-e", help='The order exchange.')
    args = oparser.parse_args(argv)
    return get_orders(exchange=args.e, market=args.m, oid=args.oid, order_id=args.order_id, session=ses)


def handle_sync_order(argv, parsers):
    oparser = argparse.ArgumentParser(parents=parsers)
    oparser.add_argument("--oid", help='The order id to sync.')
    oparser.add_argument("-e", help='The order exchange.')
    args = oparser.parse_args(argv)
    data = {}
    if args.oid:
        data['oid'] = args.oid
    sync_orders(args.e, data)


def handle_create_order(argv, parsers):
    oparser = argparse.ArgumentParser(parents=parsers)
    oparser.add_argument("side", choices=['bid', 'ask'], help='The order side')
    oparser.add_argument("amount", help='The order amount')
    oparser.add_argument("price", help='The order price')
    oparser.add_argument("market", help='The order market')
    oparser.add_argument("exchange", help='The order exchange')
    args = oparser.parse_args(argv)
    return create_order(args.exchange, float(args.price), float(args.amount), args.market, args.side, session=ses)


def handle_cancel_order(argv, parsers):
    oparser = argparse.ArgumentParser(parents=parsers)
    oparser.add_argument("--oid", help='The order id to cancel.')
    oparser.add_argument("--order_id", help='The order order_id.')
    oparser.add_argument("e", help='The order exchange. (required)')
    oparser.add_argument("-m", help='The order market.')
    oparser.add_argument("-s", help='The order side.')
    args = oparser.parse_args(argv)
    return cancel_orders(args.e, args.m, side=args.s, oid=args.oid, order_id=args.order_id)


def handle_balance_command(argv, parsers):
    bparser = argparse.ArgumentParser(parents=parsers)
    bparser.add_argument("subcommand", choices=["get", "sync"], help='The balance sub-command to run.')
    bparser.add_argument("-e", help='The exchange.')
    bparser.add_argument("-c", help='The currency.')
    args = bparser.parse_args(argv)
    if args.subcommand == 'get':
        bals = get_balances(args.e, session=ses)
        rbals = []
        for bal in bals:
            rbals.append(bal.to_string())
        return rbals
    elif args.subcommand == 'sync':
        return sync_balances(args.e)


def handle_trade_command(argv, parsers):
    tparser = argparse.ArgumentParser(parents=parsers)
    tparser.add_argument("subcommand", choices=["get", "sync"], help='The trade sub-command to run.')
    tparser.add_argument("-m", help='The market to get trades for.')
    tparser.add_argument("-e", help='The exchange to get trades for.')
    tparser.add_argument("--tid", help='The trade id to get.')
    args = tparser.parse_args(argv)

    if args.subcommand == "get":
        return get_trades(args.e, args.m, args.tid, session=ses)
    elif args.subcommand == "sync":
        return sync_trades(args.e, args.m)


def handle_command(argv=sys.argv[1:]):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("command", choices=['ticker', 'ledger', 'order', 'trade', 'balance', 'address'],
                        help="'%(prog)s <command> help' for usage details")
    if len(argv) == 0:
        parser.print_help()
        sys.exit()
    argvlimited = [argv[0]]
    args = parser.parse_args(argvlimited)
    if args.command == 'ticker':
        return handle_ticker_command(argv, [parser])
    elif args.command == 'ledger':
        return handle_ledger_command(argv, [parser])
    elif args.command == 'order':
        return handle_order_command(argv, [parser])
    elif args.command == 'trade':
        return handle_trade_command(argv, [parser])
    elif args.command == 'balance':
        return handle_balance_command(argv, [parser])


if __name__ == "__main__":
    result = handle_command()
    if result is not None:
        print(result)
