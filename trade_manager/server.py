import alchemyjsonschema as ajs
import bitjws
import copy
import json
import logging
import os
import sys
import sqlalchemy as sa
import sqlalchemy.orm as orm
from alchemyjsonschema.dictify import jsonify
from flask import Flask, request, current_app, make_response
from flask.ext.cors import CORS
from flask.ext.login import login_required, current_user
from flask_bitjws import FlaskBitjws, load_jws_from_request, FlaskUser
from jsonschema import validate, ValidationError
from sqlalchemy_login_models.model import UserKey, User as SLM_User
import plugin
from desw import CFG, models, ses, eng

ps = plugin.load_plugins()

# get the swagger spec for this server
iml = os.path.dirname(os.path.realpath(__file__))
SWAGGER_SPEC = json.loads(open(iml + '/static/swagger.json').read())
# invert definitions
def jsonify2(obj, name):
    #TODO replace this with a cached definitions patch
    #this is inefficient to do each time...
    spec = copy.copy(SWAGGER_SPEC['definitions'][name])
    spec['definitions'] = SWAGGER_SPEC['definitions']
    return jsonify(obj, spec)

__all__ = ['app', ]


def get_last_nonce(app, key, nonce):
    """
    Get the last_nonce used by the given key from the SQLAlchemy database.
    Update the last_nonce to nonce at the same time.

    :param str key: the public key the nonce belongs to
    :param int nonce: the last nonce used by this key
    """
    uk = ses.query(UserKey).filter(UserKey.key==key)\
            .filter(UserKey.last_nonce<nonce * 1000).first()
    if not uk:
        return None
    lastnonce = copy.copy(uk.last_nonce)
    # TODO Update DB record in same query as above, if possible
    uk.last_nonce = nonce * 1000
    try:
        ses.commit()
    except Exception as e:
        current_app.logger.exception(e)
        ses.rollback()
        ses.flush()
    return lastnonce


def get_user_by_key(app, key):
    """
    An SQLAlchemy User getting function. Get a user by public key.

    :param str key: the public key the user belongs to
    """
    user = ses.query(SLM_User).join(UserKey).filter(UserKey.key==key).first()
    return user

# Setup flask app and FlaskBitjws
app = Flask(__name__)
app._static_folder = "%s/static" % os.path.realpath(os.path.dirname(__file__))

FlaskBitjws(app, privkey=CFG.get('bitjws', 'PRIV_KEY'), get_last_nonce=get_last_nonce,
            get_user_by_key=get_user_by_key, basepath=CFG.get('bitjws', 'BASEPATH'))

CORS(app)


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8002, debug=True)

