# trade-manager

A program for managing cryptocurrency trading on a variety of exchanges.

## Installation

Just run `make install`. This will automatically install all prereqs
including ledger-cli and sepc256k1.

Also make will create a data directory for storing your logs and
configuration files. On *nux systems, this directory will be
`~/.tapp/trademanager`

If and when you wish to change any configuration settings, edit
the .ini file in the data directory.

## Command Line Interface (CLI)

The trade-manager comes with a CLI for managing all of your exchanges
via the command line. The name of the trade-manager cli is 'tradem' 

``` bash
$ tradem
usage: tradem {ticker,ledger,order,trade,balance,address}

positional arguments:
  {ticker,ledger,order,trade,balance,address}
                        'tradem <command> help' for usage details
```

All basic features are available.
For instance, you can create, cancel, and get orders.

``` bash
$ tradem order create --help
usage: tradem [-h]
              {ticker,ledger,order,trade,balance,address}
              {get,sync,create,cancel} {bid,ask} amount price market exchange

positional arguments:
  {ticker,ledger,order,trade,balance,address}
                        'tradem <command> help' for usage details
  {get,sync,create,cancel}
                        Order sub-commands
  {bid,ask}             The order side
  amount                The order amount
  price                 The order price
  market                The order market
  exchange              The order exchange

optional arguments:
  -h, --help            show this help message and exit
```

That said, the responses are still ugly.

``` bash
tradem order get -e test
[<LimitOrder(price=100.00000000 USD, amount=0.10000000 BTC, exec_amount=0.00000000 BTC, market='BTC_USD', side='bid', exchange='test', order_id='test|7SdSiSfC2UsfcTi', state='closed', create_time=2016/07/27 10:21:23)>]
```