import json
import os
import pytest
import time
from trade_manager import CFG, ses, eng, models
from trade_manager.plugin import InternalExchangePlugin

iep = InternalExchangePlugin()

def test_save_trades():
    period = 31536000 *3
    #period = 64000 * 3
    begin = 1384549600

    count = ses.query(models.ExchangeTrade).count()
    orders = iep.save_trades(begin=1384549600, end=begin+period)
    newcount = ses.query(models.ExchangeTrade).count()
    assert newcount > count

if __name__ == "__main__":
    test_save_trades()

