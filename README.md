# trade-manager

An asynchronous program for managing cryptocurrency trading on a variety of exchanges. This program comes with a number of optional, configurable plugins.


+ [Bitfinex](https://github.com/GitGuild/bitfinex-manager/)
+ [Poloniex](https://github.com/GitGuild/poloniex-manager/)
+ [Kraken](https://github.com/GitGuild/kraken-manager/)

## Installation

Just run `make install`. This will automatically install all prereqs
including ledger-cli and sepc256k1.

Also make will create data directories for storing your logs and
configuration files. Expected to run on *nux systems, these directories will be as follows.

| For           | Location               |
|---------------|------------------------|
| logs          | /var/log/trademanager  |
| configuration | /etc/tapp/trademanager |
| pids          | /var/run/              |

If and when you wish to change any configuration settings, edit
the .ini file in the configuration directory.

## Command Line Interface (CLI)

The trade-manager comes with a CLI for managing all of your exchanges
via the command line. The name of the trade-manager cli is 'tradem' 

``` bash
$ tradem
usage: tradem {ticker,ledger,order,trade,balance,address,market,commodity}

positional arguments:
  {ticker,ledger,order,trade,balance,address,market,commodity}
                        'tradem <command> help' for usage details
```

All basic features are available.
For instance, you can create, cancel, and get orders.

``` bash
$ tradem order create --help
usage: tradem [-h]
              {ticker,ledger,order,trade,balance,address,market,commodity}
              {get,sync,create,cancel} {bid,ask} amount price market exchange

positional arguments:
  {ticker,ledger,order,trade,balance,address,market,commodity}
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
