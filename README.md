# EMeasure

`EMeasure` is a Python library that provides tools for connecting, controlling, and managing VISA-based intruments (e.g., sourcemeters, oscilloscopes, lakeshore thermometer) in laboratory environments.
It allows users to send commands, acquire data, preprocess data.

## Features
- `EIns` module provides some instruments classes in common use, in which fundamental controlling command is realized.
- `ESave` module provides some thead-safe data savers to save and pass the acquired data to the plotting function.
- `EStat` module is designed to preprocess the data in the data acquisition (e.g. repeat, average, filter, outliers)

## Requirements
- Python 3.9 or higher
- NI-VISA or other compatible VISA libraries installed
- `pyvisa`, `numpy`, `pandas`, `scipy` libraries
