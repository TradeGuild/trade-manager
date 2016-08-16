from setuptools import setup

classifiers = [
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 2",
    "Topic :: Software Development :: Libraries",
]

setup(
    name='trade_manager',
    version='0.0.5',
    packages=['trade_manager'],
    url='https://github.com/gitguild/trade-manager',
    license='MIT',
    classifiers=classifiers,
    author='Ira Miller',
    author_email='ira@gitguild.com',
    description=' A program for managing cryptocurrency trading on a variety of exchanges.',
    setup_requires=['pytest-runner'],
    install_requires=[
        'sqlalchemy>=1.0.9',
        'hashlib',
        'jsonschema',
        'alchemyjsonschema',
        'redis',
        'python-daemon',
        'supervisor'
        # 'secp256k1==0.11'#,
        # "bitjws==0.6.3.1",
        # "flask>=0.10.0",
        # "flask-login",
        # "flask-cors",
        # "flask-bitjws>=0.1.1.4",
    ],
    tests_require=['pytest', 'pytest-cov'],
    extras_require={"build": ["flask-swagger"]},
    entry_points="""
[console_scripts]
tradem = trade_manager.cli:handle_command
"""
)
