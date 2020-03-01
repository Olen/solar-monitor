from setuptools import setup

setup(
    name='blegatt',
    packages=['blegatt'],
    version='0.1',
    description='BLE GATT for RPi',
    keywords='blegatt',
    py_modules=['gattctl'],
    entry_points={
        'console_scripts': ['gattctl = gattctl:main']
    }
)
