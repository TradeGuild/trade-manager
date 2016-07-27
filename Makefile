makebase = if [ !  -d ~/.tapp ]; \
	then \
		mkdir ~/.tapp; \
	fi

makedirs = if [ !  -d ~/.tapp/trademanager ]; \
	then \
		mkdir ~/.tapp/trademanager; \
		mkdir ~/.tapp/test; \
		cp cfg.ini ~/.tapp/trademanager; \
		cp cfg.ini ~/.tapp/test; \
	fi

installprereqs = if [ !  -d $(1)ledger ]; \
    git clone git://github.com/ledger/ledger.git \
    pushd $(1)ledger \
    ./acprep --python update \
    popd \
    export PYTHONPATH=$PYTHONPATH:$(readlink -f $(1)ledger) \
    if [ !  -d $(1)libsecp256k1 ]; \
    git clone git://github.com/bitcoin/secp256k1.git libsecp256k1 \
    pushd $(1)libsecp256k1 \
    git checkout d7eb1ae96dfe9d497a26b3e7ff8b6f58e61e400a \
    ./autogen.sh \
    ./configure --enable-module-recovery --enable-module-ecdh --enable-module-schnorr \
    make \
    make install \
    popd \
    INCLUDE_DIR=$(readlink -f $(1)libsecp256k1/include) \
    LIB_DIR=$(readlink -f $(1)libsecp256k1/.libs) \
    LD_LIBRARY_PATH=$(readlink -f $(1)libsecp256k1/.libs)

build:
	python setup.py build

install:
	$(call makebase, "")
	$(call makedirs, "")
    #if [ $(target) ] \
    #then \
    #    $(call installprereqs, $(target)) \
	#else \
	#    $(call installprereqs, ./) \
    #fi
	python setup.py -v install

clean:
	rm -rf .cache build dist *.egg-info test/__pycache__
	rm -rf test/*.pyc *.egg *~ *pyc test/*~ .eggs
	rm -f .coverage*

purge:
	rm -rf .cache build dist *.egg-info test/__pycache__
	rm -rf test/*.pyc *.egg *~ *pyc test/*~ .eggs
	rm -f .coverage*
	rm -rf ~/.tapp/trademanager
	rm -rf ~/.tapp/test
