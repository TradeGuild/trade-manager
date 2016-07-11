# trade-manager

A program for managing cryptocurrency trading on a variety of exchanges.

# Installation

### Pre-requisites

By default it's expected that [secp256k1](https://github.com/bitcoin/secp256k1) is available, so install it before proceeding; make sure to run `./configure --enable-module-recovery`. If you're using some other library that provides the functionality necessary for this, check the __Using a custom library__ section below.

bitjws can be installed by running `pip install bitjws`.

##### Building secp256k1

In case you need to install the `secp256k1` C library, the following sequence of commands is recommended. If you already have `secp256k1`, make sure it was compiled from the expected git commit or it might fail to work due to API incompatibilities.

```
git clone git://github.com/bitcoin/secp256k1.git libsecp256k1
cd libsecp256k1
git checkout d7eb1ae96dfe9d497a26b3e7ff8b6f58e61e400a
./autogen.sh
./configure --enable-module-recovery --enable-module-ecdh --enable-module-schnorr
make
make install
```

Additionally, you may need to set some environmental variables, pointing to the installation above.

```
INCLUDE_DIR=$(readlink -f ./libsecp256k1/include)
LIB_DIR=$(readlink -f ./libsecp256k1/.libs)
python setup.py -q install

LD_LIBRARY_PATH=$(readlink -f ./libsecp256k1/.libs)