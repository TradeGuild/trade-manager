"""
The main trade_manager module. Initializes sessions, and connections.
"""
from sqlalchemy_models import wallet as wm, exchange as em, user as um, create_session_engine, setup_database
from tapp_config import get_config

CFG = get_config('trade_manager')
ses, eng = create_session_engine(cfg=CFG)
setup_database(eng, modules=[wm, em, um])

NETWORK_COMMODITY_MAP = {'BTC': 'Bitcoin', 'DASH': 'Dash', 'ETH': 'Ethereum', 'LTC': 'Litecoin'}
